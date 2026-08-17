from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.whatsapp.client import WhatsAppCloudClient
from app.core.config import settings
from app.models.channel import ChannelAccount, ChannelEvent
from app.models.commercial import StoreCommercialRules
from app.models.conversation import Conversation
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.repositories.channel import ChannelRepository
from app.schemas.conversation import MessageCreate
from app.services.conversation import ConversationService
from app.services.pix_receipt_validation import PixReceiptValidationService
from app.services.pix_receipt_review import PixReceiptReviewService


class PixReceiptError(RuntimeError):
    pass


class PixReceiptService:
    def __init__(self) -> None:
        self.channels = ChannelRepository()
        self.conversations = ConversationService()
        self.validator = PixReceiptValidationService()
        self.review = PixReceiptReviewService()

    @staticmethod
    def _digits(value: str | None) -> str:
        return "".join(
            character
            for character in str(value or "")
            if character.isdigit()
        )

    @staticmethod
    def _extension(mime_type: str | None) -> str:
        normalized = (mime_type or "").split(";")[0].strip().lower()

        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/pdf": ".pdf",
        }

        return mapping.get(normalized, ".bin")

    def _recent_pix_orders(
        self,
        db: Session,
        *,
        store_id,
        customer_phone: str,
    ) -> list[Order]:
        rules = db.scalar(
            select(StoreCommercialRules).where(
                StoreCommercialRules.store_id == store_id
            )
        )

        max_age_minutes = (
            rules.pix_receipt_max_age_minutes
            if rules is not None
            else 360
        )

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(minutes=max_age_minutes)
        )

        possible = list(
            db.scalars(
                select(Order)
                .where(
                    Order.store_id == store_id,
                    Order.payment_method == "PIX",
                    Order.created_at >= cutoff,
                    Order.status != "CANCELLED",
                )
                .order_by(Order.created_at.desc())
                .limit(20)
            ).all()
        )

        expected_phone = self._digits(customer_phone)

        matched = [
            order
            for order in possible
            if self._digits(order.customer_phone) == expected_phone
        ]

        candidates: list[Order] = []

        for order in matched:
            confirmed_receipt = db.scalar(
                select(PaymentReceipt.id)
                .where(
                    PaymentReceipt.order_id == order.id,
                    PaymentReceipt.status.in_(
                        [
                            "AUTO_CONFIRMED",
                            "HUMAN_CONFIRMED",
                        ]
                    ),
                )
                .limit(1)
            )

            if confirmed_receipt is None:
                candidates.append(order)

        return candidates

    def _save_customer_message(
        self,
        db: Session,
        *,
        conversation: Conversation,
        event: ChannelEvent,
        receipt: PaymentReceipt | None,
        message_type: str,
        media_id: str,
    ) -> None:
        metadata = {
            "whatsapp_media_id": media_id,
            "message_type": message_type,
        }

        if receipt is not None:
            metadata["payment_receipt_id"] = str(receipt.id)
            metadata["payment_receipt_status"] = receipt.status

        self.conversations.add_message(
            db,
            conversation_id=conversation.id,
            payload=MessageCreate(
                direction="INBOUND",
                sender_type="CUSTOMER",
                content_type=message_type.upper(),
                content=(
                    "[Comprovante PIX recebido]"
                    if receipt is not None
                    else "[Imagem/arquivo recebido]"
                ),
                external_message_id=event.external_event_id,
                metadata_json=metadata,
            ),
        )

    def receive_whatsapp_media(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        event: ChannelEvent,
        conversation: Conversation,
        sender: str,
        message: dict,
        client: WhatsAppCloudClient,
        allow_customer_reply: bool,
    ) -> PaymentReceipt | None:
        message_type = str(message.get("type") or "").lower()

        if message_type not in {"image", "document"}:
            raise PixReceiptError(
                f"Tipo de mídia não suportado: {message_type}."
            )

        media_payload = message.get(message_type) or {}
        media_id = str(media_payload.get("id") or "").strip()

        if not media_id:
            raise PixReceiptError(
                "Mensagem de mídia sem media_id."
            )

        existing = db.scalar(
            select(PaymentReceipt)
            .where(
                PaymentReceipt.channel_event_id == event.id
            )
            .limit(1)
        )

        if existing is not None:
            return existing

        candidates = self._recent_pix_orders(
            db,
            store_id=account.store_id,
            customer_phone=sender,
        )

        # Não baixa e não armazena fotos aleatórias se não houver
        # nenhum pedido PIX recente para esse cliente.
        if not candidates:
            self._save_customer_message(
                db,
                conversation=conversation,
                event=event,
                receipt=None,
                message_type=message_type,
                media_id=media_id,
            )

            if allow_customer_reply:
                self.channels.create_outbound(
                    db,
                    account=account,
                    conversation_id=conversation.id,
                    recipient=sender,
                    content=(
                        "Recebi sua imagem/arquivo 😊 "
                        "Se for um comprovante de PIX, não encontrei "
                        "um pedido PIX recente vinculado a este número. "
                        "Me informe o número do pedido para eu localizar."
                    ),
                )

            return None

        mime_type_from_message = media_payload.get("mime_type")

        if (
            message_type == "document"
            and mime_type_from_message
            and str(mime_type_from_message).lower()
            != "application/pdf"
        ):
            self._save_customer_message(
                db,
                conversation=conversation,
                event=event,
                receipt=None,
                message_type=message_type,
                media_id=media_id,
            )

            if allow_customer_reply:
                self.channels.create_outbound(
                    db,
                    account=account,
                    conversation_id=conversation.id,
                    recipient=sender,
                    content=(
                        "Recebi o arquivo. Para comprovante de PIX, "
                        "envie uma imagem ou um PDF, por favor."
                    ),
                )

            return None

        downloaded = client.download_media(
            phone_number_id=account.external_account_id,
            media_id=media_id,
        )

        if downloaded.file_size > settings.payment_receipt_max_bytes:
            raise PixReceiptError(
                "Comprovante excede o tamanho máximo permitido."
            )

        mime_type = (
            downloaded.mime_type
            or mime_type_from_message
        )

        normalized_mime = (
            str(mime_type or "")
            .split(";")[0]
            .strip()
            .lower()
        )

        if normalized_mime not in {
            "image/jpeg",
            "image/png",
            "application/pdf",
        }:
            raise PixReceiptError(
                f"Formato não permitido para comprovante: "
                f"{normalized_mime or 'desconhecido'}."
            )

        digest = hashlib.sha256(downloaded.content).hexdigest()

        duplicate = db.scalar(
            select(PaymentReceipt)
            .where(
                PaymentReceipt.store_id == account.store_id,
                PaymentReceipt.file_sha256 == digest,
            )
            .order_by(PaymentReceipt.created_at.desc())
            .limit(1)
        )

        # Se houver pedidos PIX candidatos, começamos pelo mais recente.
        # O validador confirma/reassocia usando o valor extraído do
        # comprovante antes da decisão final.
        order = candidates[0] if candidates else None

        receipt_id = uuid4()
        extension = self._extension(normalized_mime)

        directory = (
            Path(settings.payment_receipt_storage_path)
            / str(account.store_id)
        )
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = directory / f"{receipt_id}{extension}"
        destination.write_bytes(downloaded.content)

        status = (
            "NEEDS_REVIEW"
            if duplicate is not None
            else "RECEIVED"
        )

        validation_json = {
            "meta_sha256": downloaded.meta_sha256,
            "candidate_orders": [
                candidate.display_id
                for candidate in candidates
            ],
        }

        if duplicate is not None:
            validation_json["duplicate_file"] = True
            validation_json["duplicate_receipt_id"] = str(
                duplicate.id
            )

        receipt = PaymentReceipt(
            id=receipt_id,
            store_id=account.store_id,
            order_id=order.id if order is not None else None,
            conversation_id=conversation.id,
            channel_event_id=event.id,
            external_media_id=media_id,
            media_type=message_type.upper(),
            mime_type=normalized_mime,
            original_filename=media_payload.get("filename"),
            storage_path=str(destination),
            file_sha256=digest,
            status=status,
            validation_json=validation_json,
        )

        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        if (
            receipt.order_id is not None
            and receipt.status == "RECEIVED"
        ):
            receipt = self.validator.process(
                db,
                receipt=receipt,
            )

        if receipt.status == "NEEDS_REVIEW":
            already_notified = bool(
                (receipt.validation_json or {}).get(
                    "staff_review_notified"
                )
            )

            if not already_notified:
                notified = self.review.notify_review(
                    db,
                    account=account,
                    receipt=receipt,
                )

                receipt.validation_json = {
                    **(receipt.validation_json or {}),
                    "staff_review_notified": bool(notified),
                    "staff_review_notified_count": notified,
                }

                db.commit()
                db.refresh(receipt)

        self._save_customer_message(
            db,
            conversation=conversation,
            event=event,
            receipt=receipt,
            message_type=message_type,
            media_id=media_id,
        )

        if allow_customer_reply:
            if receipt.status == "AUTO_CONFIRMED":
                response = (
                    f"Comprovante do pedido "
                    f"#{order.display_id} conferido ✅ "
                    "Os dados do PIX estão de acordo com o pedido."
                )

            elif receipt.status == "NEEDS_ORDER":
                numbers = ", ".join(
                    f"#{candidate.display_id}"
                    for candidate in candidates[:5]
                )

                response = (
                    "Recebi seu comprovante 😊 "
                    "Encontrei mais de um pedido PIX recente "
                    f"({numbers}). "
                    "Me informe o número do pedido ao qual ele pertence."
                )

            elif receipt.status == "NEEDS_REVIEW":
                staff_was_notified = bool(
                    (receipt.validation_json or {}).get(
                        "staff_review_notified"
                    )
                )

                review_message = (
                    "Já encaminhei para análise da nossa equipe."
                    if staff_was_notified
                    else (
                        "Seu comprovante ficou registrado e será "
                        "analisado quando o atendimento estiver disponível."
                    )
                )

                response = (
                    f"Recebi seu comprovante"
                    + (
                        f" do pedido #{order.display_id}"
                        if order is not None
                        else ""
                    )
                    + ". Alguns dados precisam de conferência "
                    "da nossa equipe antes da confirmação. "
                    + review_message
                )

            else:
                response = (
                    f"Recebi seu comprovante"
                    + (
                        f" do pedido #{order.display_id}"
                        if order is not None
                        else ""
                    )
                    + " 😊 Estou conferindo os dados do PIX."
                )

            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=conversation.id,
                recipient=sender,
                content=response,
            )

        return receipt
