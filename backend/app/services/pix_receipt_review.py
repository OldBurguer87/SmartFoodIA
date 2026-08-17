from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.channel import ChannelAccount
from app.models.conversation import Conversation
from app.models.order import Order
from app.models.payment import PaymentReceipt
from app.models.staff import StoreStaffMember
from app.repositories.channel import ChannelRepository
from app.repositories.staff import StaffRepository


PIX_REVIEW_TEMPLATE_NAME = "alerta_pix_conferencia"
PIX_REVIEW_TEMPLATE_LANGUAGE = "pt_BR"
PIX_REVIEW_BUTTON_PREFIX = "PIX_REVIEW_OPEN:"


REASON_LABELS = {
    "NOT_IDENTIFIED_AS_PIX": "não foi possível confirmar que é um comprovante PIX",
    "PAYMENT_NOT_CLEARLY_COMPLETED": "pagamento não aparece claramente como concluído",
    "AMOUNT_MISMATCH_OR_MISSING": "valor diferente ou não identificado",
    "RECEIVER_DOCUMENT_MISMATCH": "CPF/CNPJ do destinatário não confere",
    "PIX_KEY_MISMATCH": "chave PIX não confere",
    "RECEIVER_NOT_CONFIRMED": "destinatário não pôde ser confirmado",
    "RECEIVER_INSTITUTION_MISMATCH": "instituição do recebedor não confere",
    "DATE_TIME_OUTSIDE_EXPECTED_WINDOW": "data/hora precisa de conferência",
    "DUPLICATE_RECEIPT_FILE": "mesma imagem/arquivo já foi usado antes",
    "DUPLICATE_TRANSACTION_ID": "ID/E2E do PIX já foi usado antes",
    "LOW_AI_CONFIDENCE": "leitura automática com baixa confiança",
    "OFFICIAL_PIX_DATA_NOT_CONFIGURED": "dados PIX oficiais da loja incompletos",
    "ANALYSIS_FAILED": "não foi possível analisar automaticamente o arquivo",
    "ORDER_NOT_FOUND": "pedido não foi localizado",
    "ORDER_AMBIGUOUS_BY_AMOUNT": "há mais de um pedido PIX com o mesmo valor",
    "PIX_RULES_NOT_CONFIGURED": "configuração PIX da loja não foi localizada",
}


class PixReceiptReviewService:
    def __init__(self) -> None:
        self.channels = ChannelRepository()
        self.staff = StaffRepository()

    @staticmethod
    def _money(value) -> str:
        if value is None:
            return "não identificado"

        formatted = f"{float(value):,.2f}"
        formatted = (
            formatted
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        return f"R$ {formatted}"

    def _find_pending(
        self,
        db: Session,
        *,
        store_id,
        display_id: str,
    ) -> tuple[PaymentReceipt | None, Order | None]:
        normalized = display_id.strip().lstrip("#").zfill(6)

        order = db.scalar(
            select(Order)
            .where(
                Order.store_id == store_id,
                Order.display_id == normalized,
            )
            .limit(1)
        )

        if order is None:
            return None, None

        receipt = db.scalar(
            select(PaymentReceipt)
            .where(
                PaymentReceipt.store_id == store_id,
                PaymentReceipt.order_id == order.id,
                PaymentReceipt.status == "NEEDS_REVIEW",
                PaymentReceipt.retention_purged_at.is_(None),
            )
            .order_by(PaymentReceipt.created_at.desc())
            .limit(1)
        )

        return receipt, order

    @staticmethod
    def _staff_window_open(
        staff: StoreStaffMember,
        *,
        now: datetime | None = None,
    ) -> bool:
        if staff.last_seen_at is None:
            return False

        current = now or datetime.now(timezone.utc)
        seen = staff.last_seen_at

        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)

        # Margem de 10 minutos antes das 24h da Meta.
        return seen >= current - timedelta(
            hours=23,
            minutes=50,
        )

    @staticmethod
    def _template_payload(display_id: str) -> dict:
        return {
            "name": PIX_REVIEW_TEMPLATE_NAME,
            "language": {
                "code": PIX_REVIEW_TEMPLATE_LANGUAGE,
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": f"#{display_id}",
                        }
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": "0",
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": (
                                PIX_REVIEW_BUTTON_PREFIX
                                + display_id
                            ),
                        }
                    ],
                },
            ],
        }

    def _review_content(
        self,
        *,
        receipt: PaymentReceipt,
        order: Order,
    ) -> tuple[str, Path, str, str, str]:
        validation = receipt.validation_json or {}
        reasons = validation.get("reasons") or []

        reason_text = "\n".join(
            f"• {REASON_LABELS.get(reason, reason)}"
            for reason in reasons[:8]
        )

        if not reason_text:
            reason_text = "• conferência manual solicitada"

        paid_at = "não identificada"

        if receipt.extracted_paid_at:
            local = receipt.extracted_paid_at.astimezone(
                __import__("zoneinfo").ZoneInfo(
                    "America/Manaus"
                )
            )
            paid_at = local.strftime("%d/%m/%Y %H:%M")

        duplicate_file = bool(
            validation.get("duplicate_file")
        )

        if duplicate_file:
            message = (
                "⚠️ Comprovante PIX já utilizado\n\n"
                f"Pedido: #{order.display_id}\n"
                f"Cliente: {order.customer_name}\n"
                f"Total do pedido: {self._money(order.total)}\n\n"
                "Este mesmo arquivo de comprovante já foi enviado "
                "anteriormente em outro pedido.\n"
                "A confirmação automática foi bloqueada por segurança.\n\n"
                "Confira o comprovante anexado antes de decidir e responda:\n"
                f"CONFIRMAR PIX {order.display_id}\n"
                "ou\n"
                f"RECUSAR PIX {order.display_id}"
            )
        else:
            message = (
                "⚠️ PIX precisa de conferência\n\n"
                f"Pedido: #{order.display_id}\n"
                f"Cliente: {order.customer_name}\n"
                f"Total do pedido: {self._money(order.total)}\n\n"
                "Dados lidos do comprovante:\n"
                f"Destinatário: "
                f"{receipt.extracted_receiver_name or 'não identificado'}\n"
                f"Valor: {self._money(receipt.extracted_amount)}\n"
                f"Data/hora: {paid_at}\n"
                f"Status: "
                f"{receipt.extracted_transaction_status or 'não identificado'}\n"
                f"ID/E2E: "
                f"{receipt.extracted_transaction_id or 'não identificado'}\n\n"
                "Motivos da revisão:\n"
                f"{reason_text}\n\n"
                "Confira o comprovante anexado e responda:\n"
                f"CONFIRMAR PIX {order.display_id}\n"
                "ou\n"
                f"RECUSAR PIX {order.display_id}"
            )

        file_path = Path(receipt.storage_path)
        mime_type = (
            receipt.mime_type
            or "application/octet-stream"
        )

        if mime_type.startswith("image/"):
            media_type = "image"
            filename = (
                receipt.original_filename
                or f"pix-{order.display_id}.jpg"
            )
        else:
            media_type = "document"
            filename = (
                receipt.original_filename
                or f"pix-{order.display_id}.pdf"
            )

        return (
            message,
            file_path,
            mime_type,
            media_type,
            filename,
        )

    def _queue_review_details(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        recipient: str,
        receipt: PaymentReceipt,
        order: Order,
    ) -> None:
        (
            message,
            file_path,
            mime_type,
            media_type,
            filename,
        ) = self._review_content(
            receipt=receipt,
            order=order,
        )

        self.channels.create_outbound(
            db,
            account=account,
            conversation_id=None,
            recipient=recipient,
            content=message,
        )

        if file_path.exists():
            self.channels.create_media_file_outbound(
                db,
                account=account,
                conversation_id=None,
                recipient=recipient,
                content=json.dumps(
                    {
                        "path": str(file_path),
                        "mime_type": mime_type,
                        "media_type": media_type,
                        "filename": filename,
                        "caption": (
                            "Comprovante PIX — "
                            f"Pedido #{order.display_id}"
                        ),
                    },
                    ensure_ascii=False,
                ),
            )

    def notify_review(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        receipt: PaymentReceipt,
    ) -> int:
        if receipt.order_id is None:
            return 0

        order = db.get(Order, receipt.order_id)

        if order is None:
            return 0

        members = self.staff.list_notifiable(
            db,
            store_id=receipt.store_id,
        )

        if not members:
            return 0

        notified = 0

        for member in members:
            if not self._staff_window_open(member):
                # Não iniciar conversa paga com template.
                # O comprovante continua pendente e o monitor
                # tentará novamente após o atendente interagir
                # com o WhatsApp e abrir a janela de atendimento.
                continue

            self._queue_review_details(
                db,
                account=account,
                recipient=member.phone,
                receipt=receipt,
                order=order,
            )
            notified += 1

        return notified

    def open_review(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        display_id: str,
    ) -> str | None:
        receipt, order = self._find_pending(
            db,
            store_id=staff.store_id,
            display_id=display_id,
        )

        if receipt is None or order is None:
            return (
                "Não encontrei comprovante PIX aguardando "
                f"conferência para o pedido "
                f"#{display_id.strip().lstrip('#').zfill(6)}."
            )

        self._queue_review_details(
            db,
            account=account,
            recipient=staff.phone,
            receipt=receipt,
            order=order,
        )

        return None

    def confirm(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        display_id: str,
    ) -> str:
        receipt, order = self._find_pending(
            db,
            store_id=staff.store_id,
            display_id=display_id,
        )

        if receipt is None or order is None:
            return (
                "Não encontrei comprovante PIX aguardando "
                f"conferência para o pedido #{display_id.zfill(6)}."
            )

        receipt.status = "HUMAN_CONFIRMED"
        receipt.reviewed_by = (
            f"{staff.name} via WhatsApp"
        )
        receipt.reviewed_at = datetime.now(timezone.utc)
        receipt.review_notes = (
            "Comprovante confirmado manualmente pela equipe."
        )

        db.commit()

        if receipt.conversation_id is not None:
            conversation = db.get(
                Conversation,
                receipt.conversation_id,
            )

            if (
                conversation is not None
                and conversation.external_conversation_id
            ):
                self.channels.create_outbound(
                    db,
                    account=account,
                    conversation_id=conversation.id,
                    recipient=conversation.external_conversation_id,
                    content=(
                        f"Pagamento PIX do pedido "
                        f"#{order.display_id} confirmado pela "
                        "nossa equipe ✅"
                    ),
                )

        return (
            f"✅ PIX do pedido #{order.display_id} confirmado.\n"
            f"Valor: {self._money(order.total)}\n"
            f"Conferido por: {staff.name}"
        )

    def reject(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        display_id: str,
        reason: str | None = None,
    ) -> str:
        receipt, order = self._find_pending(
            db,
            store_id=staff.store_id,
            display_id=display_id,
        )

        if receipt is None or order is None:
            return (
                "Não encontrei comprovante PIX aguardando "
                f"conferência para o pedido #{display_id.zfill(6)}."
            )

        receipt.status = "HUMAN_REJECTED"
        receipt.reviewed_by = (
            f"{staff.name} via WhatsApp"
        )
        receipt.reviewed_at = datetime.now(timezone.utc)
        receipt.review_notes = (
            reason.strip()
            if reason and reason.strip()
            else "Comprovante não confirmado pela equipe."
        )

        db.commit()

        if receipt.conversation_id is not None:
            conversation = db.get(
                Conversation,
                receipt.conversation_id,
            )

            if (
                conversation is not None
                and conversation.external_conversation_id
            ):
                self.channels.create_outbound(
                    db,
                    account=account,
                    conversation_id=conversation.id,
                    recipient=conversation.external_conversation_id,
                    content=(
                        f"A equipe não conseguiu confirmar o "
                        f"comprovante PIX do pedido "
                        f"#{order.display_id}. "
                        "Pode enviar o comprovante novamente, "
                        "por favor?"
                    ),
                )

        return (
            f"❌ Comprovante PIX do pedido "
            f"#{order.display_id} marcado como não confirmado.\n"
            "O cliente foi orientado a enviar novamente."
        )
