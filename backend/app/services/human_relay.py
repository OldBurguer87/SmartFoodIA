from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.channel import ChannelAccount
from app.models.conversation import Conversation, HumanTicket
from app.schemas.conversation import MessageCreate
from app.models.staff import StoreStaffMember
from app.repositories.channel import ChannelRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.staff import StaffRepository
from app.services.conversation import ConversationService


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

    def notify_waiting(
        self,
        db: Session,
        *,
        store_id: UUID,
        conversation_id: UUID,
        reason: str,
        reminder: bool = False,
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

        members = self.staff.list_notifiable(db, store_id=store_id)
        if not members:
            return 0

        code = self.conversation_code(conversation)
        client = conversation.external_conversation_id or "cliente"

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

        now = datetime.now(timezone.utc)

        for member in members:
            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=None,
                recipient=member.phone,
                content=message,
            )
            member.last_notified_at = now

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
                    "STATUS — ver cliente atual\n"
                    "RESOLVER solução — resolver o chamado e devolver para a Olívia\n"
                    "DEVOLVER — devolver sem marcar o chamado como resolvido\n\n"
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
