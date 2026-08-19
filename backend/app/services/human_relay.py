from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import Store
from app.models.channel import ChannelAccount
from app.models.commercial import StoreBusinessHours
from app.models.conversation import AIEvent, Conversation, HumanTicket
from app.models.order import Order
from app.schemas.conversation import MessageCreate
from app.models.staff import StoreStaffMember
from app.repositories.channel import ChannelRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.staff import StaffRepository
from app.services.conversation import ConversationService
from app.services.pix_receipt_review import PixReceiptReviewService


def normalize_phone(value: str) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())

    if (
        digits.startswith("55")
        and len(digits) == 12
        and digits[4] in "6789"
    ):
        return f"{digits[:4]}9{digits[4:]}"

    return digits


class HumanRelayService:
    def __init__(self) -> None:
        self.staff = StaffRepository()
        self.channels = ChannelRepository()
        self.conversations = ConversationService()
        self.conversation_repository = ConversationRepository()
        self.pix_review = PixReceiptReviewService()

    @staticmethod
    def conversation_code(conversation: Conversation) -> str:
        value = conversation.external_conversation_id or str(conversation.id)
        digits = "".join(character for character in value if character.isdigit())
        if digits:
            return digits[-6:]
        return str(conversation.id).replace("-", "")[-6:].upper()

    def get_staff_sender(
        self,
        db: Session,
        *,
        store_id: UUID,
        phone: str,
    ) -> StoreStaffMember | None:
        return self.staff.get_by_phone(
            db,
            store_id=store_id,
            phone=normalize_phone(phone),
        )

    @staticmethod
    def _format_money(value) -> str:
        formatted = f"{float(value):,.2f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"

    def _order_alert_context(
        self,
        db: Session,
        *,
        store_id: UUID,
        conversation_id: UUID,
        reason: str,
    ) -> str:
        match = re.search(
            r"Pedido #([0-9]+)",
            reason,
            flags=re.IGNORECASE,
        )

        if not match:
            return ""

        display_id = match.group(1).zfill(6)

        order = db.scalar(
            select(Order)
            .where(
                Order.store_id == store_id,
                Order.display_id == display_id,
            )
            .options(selectinload(Order.items))
            .limit(1)
        )

        if order is None:
            return ""

        status_labels = {
            "READY_FOR_INTEGRATION": "Pedido recebido, aguardando confirmação",
            "CONFIRMED": "Pedido confirmado e em preparação",
            "READY": "Pedido pronto",
            "DISPATCHED": "Pedido saiu para entrega",
            "CONCLUDED": "Pedido finalizado",
            "CANCELLED": "Pedido cancelado",
        }

        issue_labels = {
            "DELAY": "Atraso",
            "WRONG_ITEM": "Item errado",
            "MISSING_ITEM": "Item faltando",
            "QUALITY": "Problema de qualidade",
            "NOT_RECEIVED": "Pedido não recebido",
            "PAYMENT": "Pagamento / cobrança",
            "CANCELLATION": "Solicitação de cancelamento",
            "OTHER": "Outro problema",
        }

        issue_match = re.search(
            r"tipo=([A-Z_]+)",
            reason,
            flags=re.IGNORECASE,
        )

        issue_type = (
            issue_match.group(1).upper()
            if issue_match
            else None
        )

        issue_label = (
            issue_labels.get(issue_type, issue_type)
            if issue_type
            else "Atendimento solicitado"
        )

        created_at = order.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        elapsed_minutes = max(
            0,
            int(
                (
                    datetime.now(timezone.utc) - created_at
                ).total_seconds()
                // 60
            ),
        )

        service_label = (
            "Entrega"
            if order.service_mode == "DELIVERY"
            else "Retirada"
        )

        items = list(order.items)
        item_lines = [
            f"• {item.quantity}x {item.product_name}"
            for item in items[:6]
        ]

        if len(items) > 6:
            item_lines.append(
                f"• +{len(items) - 6} outro(s) item(ns)"
            )

        ticket = self._active_ticket(
            db,
            conversation_id=conversation_id,
        )

        customer_report = (
            ticket.customer_message.strip()
            if ticket is not None and ticket.customer_message
            else None
        )

        lines = [
            "",
            f"📦 Pedido #{order.display_id}",
            f"Nome: {order.customer_name}",
            f"Status: {status_labels.get(order.status, order.status)}",
            f"Atendimento: {service_label}",
        ]

        if order.status not in {"CONCLUDED", "CANCELLED"}:
            lines.append(f"Tempo decorrido: {elapsed_minutes} min")

        lines.extend(
            [
                f"Total: {self._format_money(order.total)}",
                f"Pagamento: {order.payment_method}",
            ]
        )

        if item_lines:
            lines.extend(
                [
                    "",
                    "Itens:",
                    *item_lines,
                ]
            )

        lines.extend(
            [
                "",
                f"⚠️ Problema: {issue_label}",
            ]
        )

        if customer_report:
            report = customer_report.replace("\n", " ").strip()
            if len(report) > 350:
                report = report[:347] + "..."
            lines.append(f'Relato: "{report}"')

        return "\n".join(lines)

    def staff_is_available_now(
        self,
        db: Session,
        *,
        store_id: UUID,
        now: datetime | None = None,
    ) -> bool:
        """Disponibilidade operacional da equipe pelo horário da loja."""
        store = db.get(Store, store_id)
        if store is None:
            return False

        local_tz = ZoneInfo(store.timezone)
        current = now or datetime.now(timezone.utc)

        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        local_now = current.astimezone(local_tz)
        local_time = local_now.time().replace(tzinfo=None)
        weekday = local_now.weekday()

        today = db.scalar(
            select(StoreBusinessHours).where(
                StoreBusinessHours.store_id == store_id,
                StoreBusinessHours.weekday == weekday,
            )
        )

        if (
            today is not None
            and not today.closed
            and today.open_time is not None
            and today.close_time is not None
        ):
            if today.open_time <= today.close_time:
                if today.open_time <= local_time <= today.close_time:
                    return True
            elif local_time >= today.open_time:
                return True

        # Trata expediente que atravessa a meia-noite.
        previous = db.scalar(
            select(StoreBusinessHours).where(
                StoreBusinessHours.store_id == store_id,
                StoreBusinessHours.weekday == ((weekday - 1) % 7),
            )
        )

        if (
            previous is not None
            and not previous.closed
            and previous.open_time is not None
            and previous.close_time is not None
            and previous.open_time > previous.close_time
            and local_time <= previous.close_time
        ):
            return True

        return False

    def notify_waiting(
        self,
        db: Session,
        *,
        store_id: UUID,
        conversation_id: UUID,
        reason: str,
        reminder: bool = False,
        now: datetime | None = None,
    ) -> int:
        conversation = self.conversation_repository.get(db, conversation_id)
        store = db.get(Store, store_id)
        account = self.channels.get_account_by_store(
            db,
            store_id=store_id,
            provider="WHATSAPP_CLOUD",
        )

        if conversation is None or store is None or account is None:
            return 0

        if not self.staff_is_available_now(
            db,
            store_id=store_id,
            now=now,
        ):
            return 0

        members = self.staff.list_notifiable(db, store_id=store_id)
        if not members:
            return 0

        code = self.conversation_code(conversation)
        client = conversation.external_conversation_id or "cliente"

        order_context = self._order_alert_context(
            db,
            store_id=store_id,
            conversation_id=conversation_id,
            reason=reason,
        )

        title = (
            f"⚠️ {store.name} — cliente ainda aguardando"
            if reminder
            else f"🔔 {store.name} — atendimento solicitado"
        )
        wait_note = (
            "A espera já passou de 2 minutos.\n\n"
            if reminder
            else ""
        )

        if order_context:
            message = (
                f"{title}\n\n"
                f"{wait_note}"
                f"WhatsApp: {client}\n"
                f"{order_context}\n\n"
                f"Código: {code}\n\n"
                f"Responda:\n"
                f"ASSUMIR {code}"
            )
        else:
            message = (
                f"{title}\n\n"
                f"{wait_note}"
                f"Cliente: {client}\n"
                f"Motivo: {reason}\n"
                f"Código: {code}\n\n"
                f"Responda:\n"
                f"ASSUMIR {code}\n\n"
                f"para atender esse cliente pelo WhatsApp."
            )

        current_time = now or datetime.now(timezone.utc)

        for member in members:
            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=None,
                recipient=member.phone,
                content=message,
            )
            member.last_notified_at = current_time

        if not reminder:
            wait_event = db.scalar(
                select(AIEvent)
                .where(
                    AIEvent.conversation_id == conversation_id,
                    AIEvent.event_type == "HUMAN_WAITING",
                )
                .order_by(AIEvent.created_at.desc())
                .limit(1)
            )

            if wait_event is not None:
                last_start = db.scalar(
                    select(AIEvent)
                    .where(
                        AIEvent.conversation_id == conversation_id,
                        AIEvent.event_type == "HUMAN_WAIT_STARTED",
                        AIEvent.created_at >= wait_event.created_at,
                    )
                    .order_by(AIEvent.created_at.desc())
                    .limit(1)
                )

                last_pause = db.scalar(
                    select(AIEvent)
                    .where(
                        AIEvent.conversation_id == conversation_id,
                        AIEvent.event_type == "HUMAN_WAIT_PAUSED",
                        AIEvent.created_at >= wait_event.created_at,
                    )
                    .order_by(AIEvent.created_at.desc())
                    .limit(1)
                )

                needs_start = (
                    last_start is None
                    or (
                        last_pause is not None
                        and last_pause.created_at >= last_start.created_at
                    )
                )

                if needs_start:
                    db.add(
                        AIEvent(
                            store_id=store_id,
                            conversation_id=conversation_id,
                            event_type="HUMAN_WAIT_STARTED",
                            success=True,
                            payload_json={
                                "wait_event_id": str(wait_event.id),
                                "notified": len(members),
                            },
                        )
                    )

        db.commit()
        return len(members)

    def notify_timeout(
        self,
        db: Session,
        *,
        store_id: UUID,
        conversation_id: UUID,
    ) -> int:
        conversation = self.conversation_repository.get(db, conversation_id)
        store = db.get(Store, store_id)
        account = self.channels.get_account_by_store(
            db,
            store_id=store_id,
            provider="WHATSAPP_CLOUD",
        )

        if conversation is None or store is None or account is None:
            return 0

        if not self.staff_is_available_now(
            db,
            store_id=store_id,
        ):
            return 0

        members = self.staff.list_notifiable(db, store_id=store_id)
        if not members:
            return 0

        code = self.conversation_code(conversation)

        message = (
            f"⏱️ {store.name} — tempo de espera encerrado\n\n"
            f"Atendimento: {code}\n"
            f"Cliente: {conversation.external_conversation_id or 'cliente'}\n\n"
            "Ninguém assumiu dentro do tempo máximo. "
            "A Olívia retomou automaticamente a conversa e está tentando "
            "resolver por outra abordagem."
        )

        for member in members:
            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=None,
                recipient=member.phone,
                content=message,
            )

        return len(members)

    def _send_internal(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        content: str,
    ) -> None:
        self.channels.create_outbound(
            db,
            account=account,
            conversation_id=None,
            recipient=staff.phone,
            content=content,
        )

    def _waiting_conversations(
        self,
        db: Session,
        *,
        store_id: UUID,
        code: str | None = None,
    ) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(
                Conversation.store_id == store_id,
                Conversation.status == "WAITING_HUMAN",
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(10)
        )

        if code:
            statement = statement.where(
                Conversation.external_conversation_id.endswith(code)
            )

        return list(db.scalars(statement).all())

    def _manager_escalated_conversations(
        self,
        db: Session,
        *,
        store_id: UUID,
        code: str | None = None,
        now: datetime | None = None,
    ) -> list[Conversation]:
        current = now or datetime.now(timezone.utc)

        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        cutoff = current - timedelta(minutes=30)

        escalated_ids = (
            select(AIEvent.conversation_id)
            .where(
                AIEvent.store_id == store_id,
                AIEvent.event_type == "MANAGER_ESCALATION",
                AIEvent.created_at >= cutoff,
            )
        )

        statement = (
            select(Conversation)
            .where(
                Conversation.store_id == store_id,
                Conversation.status == "OPEN",
                Conversation.id.in_(escalated_ids),
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(10)
        )

        if code:
            statement = statement.where(
                Conversation.external_conversation_id.endswith(code)
            )

        return list(db.scalars(statement).all())

    def _active_ticket(
        self,
        db: Session,
        *,
        conversation_id: UUID,
    ) -> HumanTicket | None:
        return db.scalar(
            select(HumanTicket)
            .where(
                HumanTicket.conversation_id == conversation_id,
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
            )
            .order_by(HumanTicket.created_at.desc())
            .limit(1)
        )

    def _current(
        self,
        db: Session,
        *,
        staff: StoreStaffMember,
    ) -> Conversation | None:
        if staff.current_conversation_id is None:
            return None
        return self.conversation_repository.get(
            db,
            staff.current_conversation_id,
        )

    def _localizar_pedido(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        display_id: str,
    ) -> None:
        normalized_id = display_id.strip().lstrip("#").zfill(6)

        order = db.scalar(
            select(Order)
            .where(
                Order.store_id == staff.store_id,
                Order.display_id == normalized_id,
            )
            .limit(1)
        )

        if order is None:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    f"Não encontrei o pedido #{normalized_id}."
                ),
            )
            return

        if str(order.service_mode or "").upper() != "DELIVERY":
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    f"O pedido #{normalized_id} não é DELIVERY. "
                    "O comando LOCALIZAR PEDIDO é exclusivo para entregas."
                ),
            )
            return

        if str(order.status or "").upper() in {
            "CANCELLED",
            "CONCLUDED",
        }:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    f"O pedido #{normalized_id} já está "
                    f"{order.status} e não pode iniciar localização."
                ),
            )
            return

        raw_phone = "".join(
            character
            for character in str(order.customer_phone or "")
            if character.isdigit()
        )
        normalized_phone = normalize_phone(raw_phone)

        phone_variants = {
            value
            for value in {
                raw_phone,
                normalized_phone,
            }
            if value
        }

        # Compatibilidade com conversas antigas que possam estar
        # registradas sem o nono dígito.
        if (
            normalized_phone.startswith("55")
            and len(normalized_phone) == 13
            and normalized_phone[4] == "9"
        ):
            phone_variants.add(
                normalized_phone[:4] + normalized_phone[5:]
            )

        conversation = db.scalar(
            select(Conversation)
            .where(
                Conversation.store_id == staff.store_id,
                Conversation.channel == "WHATSAPP",
                Conversation.status.in_(
                    ["OPEN", "WAITING_HUMAN", "HUMAN"]
                ),
                Conversation.external_conversation_id.in_(
                    phone_variants
                ),
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )

        if conversation is None:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    f"Encontrei o pedido #{normalized_id}, mas não "
                    "encontrei uma conversa WhatsApp vinculada ao "
                    f"telefone {order.customer_phone}."
                ),
            )
            return

        current = self._current(
            db,
            staff=staff,
        )

        if (
            current is not None
            and current.status == "HUMAN"
            and current.id != conversation.id
        ):
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Você já está atendendo outro cliente. "
                    "Envie DEVOLVER antes de usar LOCALIZAR PEDIDO."
                ),
            )
            return

        owner = self.staff.get_by_current_conversation(
            db,
            conversation_id=conversation.id,
        )

        if (
            conversation.status == "HUMAN"
            and owner is not None
            and owner.id != staff.id
        ):
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    f"O pedido #{normalized_id} já está sendo atendido "
                    f"por {owner.name}."
                ),
            )
            return

        assigned_to = f"{staff.name} via WhatsApp"

        self.conversations.take_over(
            db,
            conversation_id=conversation.id,
            assigned_to=assigned_to,
        )

        ticket = self._active_ticket(
            db,
            conversation_id=conversation.id,
        )

        if ticket is not None:
            self.conversations.assign_ticket(
                db,
                ticket_id=ticket.id,
                assigned_to=assigned_to,
            )

        staff.current_conversation_id = conversation.id
        staff.last_seen_at = datetime.now(timezone.utc)
        db.commit()

        customer_text = (
            f"Olá, {order.customer_name}. Estamos com dificuldade "
            f"para localizar o endereço do pedido #{normalized_id}.\n\n"
            "Por favor, envie sua localização pelo WhatsApp ou uma "
            "foto da fachada/rua. Se puder, informe também um ponto "
            "de referência para ajudar o entregador."
        )

        message = self.conversations.add_human_message(
            db,
            conversation_id=conversation.id,
            content=customer_text,
            assigned_to=assigned_to,
        )

        self.channels.create_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=conversation.external_conversation_id,
            content=message.content,
        )

        address_parts = []

        if order.address_street:
            street = order.address_street
            if order.address_number:
                street += f", {order.address_number}"
            address_parts.append(street)

        if order.address_neighborhood:
            address_parts.append(order.address_neighborhood)

        if order.address_reference:
            address_parts.append(
                f"Referência: {order.address_reference}"
            )

        address_text = (
            " | ".join(address_parts)
            if address_parts
            else "Endereço não informado no pedido"
        )

        self._send_internal(
            db,
            account=account,
            staff=staff,
            content=(
                f"📍 Localização iniciada para o pedido "
                f"#{normalized_id}.\n"
                f"Cliente: {order.customer_name}\n"
                f"Telefone: {conversation.external_conversation_id}\n"
                f"Endereço: {address_text}\n"
                f"Código da conversa: "
                f"{self.conversation_code(conversation)}\n\n"
                "A conversa foi assumida por você imediatamente. "
                "O cliente recebeu o pedido para enviar localização "
                "ou foto da fachada. Responda normalmente quando ele "
                "retornar."
            ),
        )

    def _assume(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        code: str | None,
    ) -> None:
        current = self._current(db, staff=staff)

        if current is not None and current.status == "HUMAN":
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Você já está atendendo o cliente "
                    f"{current.external_conversation_id}. "
                    "Envie DEVOLVER antes de assumir outro atendimento."
                ),
            )
            return

        matches = self._waiting_conversations(
            db,
            store_id=staff.store_id,
            code=code,
        )

        # O gerente pode assumir também uma conversa que já voltou
        # para a Olívia, desde que ela tenha sido escalada ao gerente
        # recentemente. Atendentes comuns continuam restritos a
        # WAITING_HUMAN.
        if staff.role == "MANAGER":
            escalated = self._manager_escalated_conversations(
                db,
                store_id=staff.store_id,
                code=code,
            )

            known_ids = {item.id for item in matches}
            matches.extend(
                item
                for item in escalated
                if item.id not in known_ids
            )

        if not matches:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content="Não encontrei atendimento aguardando com esse código.",
            )
            return

        if code is None and len(matches) > 1:
            options = "\n".join(
                f"- {self.conversation_code(item)} — "
                f"{item.external_conversation_id}"
                for item in matches[:5]
            )
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Há mais de um cliente aguardando. "
                    "Use ASSUMIR + código:\n\n"
                    f"{options}"
                ),
            )
            return

        if len(matches) > 1:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Esse código corresponde a mais de uma conversa. "
                    "Informe mais dígitos do telefone do cliente."
                ),
            )
            return

        conversation = matches[0]

        assigned_to = f"{staff.name} via WhatsApp"

        self.conversations.take_over(
            db,
            conversation_id=conversation.id,
            assigned_to=assigned_to,
        )

        ticket = self._active_ticket(
            db,
            conversation_id=conversation.id,
        )
        if ticket is not None:
            self.conversations.assign_ticket(
                db,
                ticket_id=ticket.id,
                assigned_to=assigned_to,
            )

        staff.current_conversation_id = conversation.id
        staff.last_seen_at = datetime.now(timezone.utc)
        db.commit()

        history = self.conversation_repository.list_messages(
            db,
            conversation.id,
            limit=6,
        )

        history_text = "\n".join(
            (
                "CLIENTE"
                if item.sender_type == "CUSTOMER"
                else "OLÍVIA"
                if item.sender_type == "OLIVIA"
                else "ATENDENTE"
            )
            + f": {item.content}"
            for item in history
        )

        self._send_internal(
            db,
            account=account,
            staff=staff,
            content=(
                f"✅ Atendimento {self.conversation_code(conversation)} assumido.\n"
                f"Cliente: {conversation.external_conversation_id}\n\n"
                f"Últimas mensagens:\n{history_text}\n\n"
                "Agora responda normalmente por aqui. "
                "Quando resolver o problema, envie RESOLVER + a solução. "
                "Use DEVOLVER somente se quiser retornar para a Olívia "
                "sem marcar o chamado como resolvido."
            ),
        )

    def _resolve(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        resolution: str,
    ) -> None:
        conversation = self._current(db, staff=staff)

        if conversation is None or conversation.status != "HUMAN":
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Você não está com atendimento humano ativo. "
                    "Use ASSUMIR + código antes de resolver um chamado."
                ),
            )
            return

        resolution = resolution.strip()

        if len(resolution) < 3:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Informe também a solução. Exemplo:\n\n"
                    "RESOLVER pedido verificado, já saiu para entrega"
                ),
            )
            return

        ticket = self._active_ticket(
            db,
            conversation_id=conversation.id,
        )

        if ticket is None:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Não encontrei chamado aberto para esta conversa. "
                    "Se quiser apenas devolver o atendimento para a Olívia, "
                    "envie DEVOLVER."
                ),
            )
            return

        assigned_to = f"{staff.name} via WhatsApp"

        resolved = self.conversations.resolve_ticket(
            db,
            ticket_id=ticket.id,
            resolution=resolution,
            assigned_to=assigned_to,
        )

        # Contexto interno: fica no histórico para a Olívia saber exatamente
        # o que o humano verificou, mas não é enviado como mensagem ao cliente.
        self.conversations.add_message(
            db,
            conversation_id=conversation.id,
            payload=MessageCreate(
                direction="OUTBOUND",
                sender_type="SYSTEM",
                content=(
                    "CONTEXTO INTERNO DO ATENDIMENTO HUMANO: "
                    f"chamado {resolved.id} resolvido por {assigned_to}. "
                    f"Solução informada: {resolution}"
                ),
                metadata_json={
                    "type": "HUMAN_TICKET_RESOLUTION",
                    "ticket_id": str(resolved.id),
                    "assigned_to": assigned_to,
                    "resolution": resolution,
                },
            ),
        )

        self.conversations.release_to_olivia(
            db,
            conversation_id=conversation.id,
            assigned_to=assigned_to,
        )

        staff.current_conversation_id = None
        db.commit()

        self._send_internal(
            db,
            account=account,
            staff=staff,
            content=(
                "✅ Chamado resolvido e registrado.\n\n"
                f"Solução: {resolution}\n\n"
                "A conversa foi devolvida para a Olívia e ela terá "
                "esse resultado no contexto do atendimento."
            ),
        )

    def _release(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
    ) -> None:
        conversation = self._current(db, staff=staff)

        if conversation is None:
            staff.current_conversation_id = None
            db.commit()
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content="Você não está atendendo nenhum cliente no momento.",
            )
            return

        if conversation.status == "HUMAN":
            self.conversations.release_to_olivia(
                db,
                conversation_id=conversation.id,
                assigned_to=f"{staff.name} via WhatsApp",
            )

        staff.current_conversation_id = None
        db.commit()

        self._send_internal(
            db,
            account=account,
            staff=staff,
            content=(
                "✅ Atendimento devolvido para a Olívia. "
                "Ela volta a responder as próximas mensagens do cliente."
            ),
        )

    def _status(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
    ) -> None:
        conversation = self._current(db, staff=staff)

        if conversation is None or conversation.status != "HUMAN":
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content="Você não está com nenhum atendimento ativo.",
            )
            return

        self._send_internal(
            db,
            account=account,
            staff=staff,
            content=(
                "Atendimento ativo:\n"
                f"Cliente: {conversation.external_conversation_id}\n"
                f"Código: {self.conversation_code(conversation)}\n\n"
                "Responda normalmente para falar com o cliente. "
                "Envie DEVOLVER quando terminar."
            ),
        )

    def handle_staff_message(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        staff: StoreStaffMember,
        body: str,
    ) -> None:
        staff.last_seen_at = datetime.now(timezone.utc)
        db.commit()

        text = body.strip()
        upper = text.upper()

        open_pix_match = re.fullmatch(
            r"PIX_REVIEW_OPEN:#?([0-9]{1,10})",
            upper,
        )

        if open_pix_match:
            error = self.pix_review.open_review(
                db,
                account=account,
                staff=staff,
                display_id=open_pix_match.group(1),
            )

            if error:
                self._send_internal(
                    db,
                    account=account,
                    staff=staff,
                    content=error,
                )

            return

        confirm_pix_match = re.fullmatch(
            r"CONFIRMAR\s+PIX\s+#?([0-9]{1,10})",
            upper,
        )

        if confirm_pix_match:
            result = self.pix_review.confirm(
                db,
                account=account,
                staff=staff,
                display_id=confirm_pix_match.group(1),
            )

            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=result,
            )
            return

        reject_pix_match = re.match(
            r"^RECUSAR\s+PIX\s+#?([0-9]{1,10})(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if reject_pix_match:
            result = self.pix_review.reject(
                db,
                account=account,
                staff=staff,
                display_id=reject_pix_match.group(1),
                reason=reject_pix_match.group(2),
            )

            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=result,
            )
            return

        localizar_match = re.fullmatch(
            r"LOCALIZAR\s+PEDIDO\s+#?([0-9]{1,10})",
            upper,
        )

        if localizar_match:
            self._localizar_pedido(
                db,
                account=account,
                staff=staff,
                display_id=localizar_match.group(1),
            )
            return

        assume_match = re.fullmatch(
            r"ASSUMIR(?:\s+([0-9]{3,15}))?",
            upper,
        )

        if assume_match:
            self._assume(
                db,
                account=account,
                staff=staff,
                code=assume_match.group(1),
            )
            return

        resolve_match = re.match(
            r"^RESOLVER(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if resolve_match:
            self._resolve(
                db,
                account=account,
                staff=staff,
                resolution=resolve_match.group(1) or "",
            )
            return

        if upper in {"DEVOLVER", "FINALIZAR", "ENCERRAR"}:
            self._release(
                db,
                account=account,
                staff=staff,
            )
            return

        if upper in {"STATUS", "SITUAÇÃO", "SITUACAO"}:
            self._status(
                db,
                account=account,
                staff=staff,
            )
            return

        if upper in {"AJUDA", "COMANDOS"}:
            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Comandos do atendimento SmartFoodIA:\n\n"
                    "ASSUMIR código — assumir um cliente\n"
                    "LOCALIZAR PEDIDO número — localizar cliente de delivery\n"
                    "STATUS — ver cliente atual\n"
                    "RESOLVER solução — resolver o chamado e devolver para a Olívia\n"
                    "DEVOLVER — devolver sem marcar o chamado como resolvido\n"
                    "CONFIRMAR PIX pedido — confirmar comprovante pendente\n"
                    "RECUSAR PIX pedido — solicitar novo comprovante\n\n"
                    "Com atendimento ativo, qualquer outra mensagem "
                    "é enviada diretamente ao cliente."
                ),
            )
            return

        conversation = self._current(db, staff=staff)

        if conversation is None or conversation.status != "HUMAN":
            if staff.current_conversation_id is not None:
                staff.current_conversation_id = None
                db.commit()

            self._send_internal(
                db,
                account=account,
                staff=staff,
                content=(
                    "Você não está com atendimento ativo. "
                    "Use ASSUMIR + código ou envie AJUDA."
                ),
            )
            return

        message = self.conversations.add_human_message(
            db,
            conversation_id=conversation.id,
            content=text,
            assigned_to=f"{staff.name} via WhatsApp",
        )

        self.channels.create_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=conversation.external_conversation_id,
            content=message.content,
        )

    def forward_customer_media_to_staff(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        conversation: Conversation,
        media_id: str,
        media_type: str,
        filename: str | None = None,
        caption: str | None = None,
    ) -> bool:
        staff = self.staff.get_by_current_conversation(
            db,
            conversation_id=conversation.id,
        )

        if staff is None:
            return False

        code = self.conversation_code(conversation)

        if media_type == "image":
            label = f"📷 Cliente {code}"
        else:
            label = f"📎 Cliente {code}"

        if caption:
            label += f": {caption}"

        payload = {
            "media_id": media_id,
            "media_type": media_type,
            "caption": label,
        }

        if filename:
            payload["filename"] = filename

        self.channels.create_media_id_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=staff.phone,
            content=json.dumps(
                payload,
                ensure_ascii=False,
            ),
        )

        return True

    def forward_customer_message_to_staff(
        self,
        db: Session,
        *,
        account: ChannelAccount,
        conversation: Conversation,
        body: str,
    ) -> bool:
        staff = self.staff.get_by_current_conversation(
            db,
            conversation_id=conversation.id,
        )

        if staff is None:
            return False

        self._send_internal(
            db,
            account=account,
            staff=staff,
            content=(
                f"💬 Cliente {self.conversation_code(conversation)}:\n"
                f"{body}\n\n"
                "Responda normalmente para enviar ao cliente."
            ),
        )
        return True
