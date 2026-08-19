from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.conversation import AIEvent, Conversation
from app.models.staff import StoreStaffMember
from app.repositories.channel import ChannelRepository
from app.repositories.staff import StaffRepository


MANAGER_ALERT_TEMPLATE_NAME = "alerta_operacional_gerente"
MANAGER_ALERT_TEMPLATE_LANGUAGE = "pt_BR"


class ManagerEscalationService:
    def __init__(self) -> None:
        self.channels = ChannelRepository()
        self.staff = StaffRepository()

    @staticmethod
    def _window_open(
        manager: StoreStaffMember,
        *,
        now: datetime | None = None,
    ) -> bool:
        if manager.last_seen_at is None:
            return False

        current = now or datetime.now(timezone.utc)
        seen = manager.last_seen_at

        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)

        # Margem antes das 24h da janela de atendimento da Meta.
        return seen >= current - timedelta(
            hours=23,
            minutes=50,
        )

    @staticmethod
    def conversation_code(conversation: Conversation) -> str:
        value = (
            conversation.external_conversation_id
            or str(conversation.id)
        )

        digits = "".join(
            character
            for character in value
            if character.isdigit()
        )

        if digits:
            return digits[-6:]

        return (
            str(conversation.id)
            .replace("-", "")[-6:]
            .upper()
        )

    @staticmethod
    def _template_payload(
        *,
        alert_type: str,
        reference: str,
        details: str,
    ) -> dict:
        return {
            "name": MANAGER_ALERT_TEMPLATE_NAME,
            "language": {
                "code": MANAGER_ALERT_TEMPLATE_LANGUAGE,
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": alert_type,
                        },
                        {
                            "type": "text",
                            "text": reference,
                        },
                        {
                            "type": "text",
                            "text": details,
                        },
                    ],
                }
            ],
        }

    def _send_manager_alert(
        self,
        db: Session,
        *,
        account,
        manager: StoreStaffMember,
        current: datetime,
        conversation_id,
        text_content: str,
        alert_type: str,
        reference: str,
        template_details: str,
    ) -> None:
        if self._window_open(
            manager,
            now=current,
        ):
            self.channels.create_outbound(
                db,
                account=account,
                conversation_id=conversation_id,
                recipient=manager.phone,
                content=text_content,
            )
        else:
            payload = self._template_payload(
                alert_type=alert_type,
                reference=reference,
                details=template_details,
            )

            self.channels.create_template_outbound(
                db,
                account=account,
                conversation_id=conversation_id,
                recipient=manager.phone,
                content=json.dumps(
                    payload,
                    ensure_ascii=False,
                ),
            )

        manager.last_notified_at = current

    def notify_conversation(
        self,
        db: Session,
        *,
        store_id,
        conversation_id,
        title: str,
        details: str,
        source: str,
        now: datetime | None = None,
    ) -> int:
        account = self.channels.get_account_by_store(
            db,
            store_id=store_id,
            provider="WHATSAPP_CLOUD",
        )

        conversation = db.get(
            Conversation,
            conversation_id,
        )

        if account is None or conversation is None:
            return 0

        managers = self.staff.list_managers(
            db,
            store_id=store_id,
        )

        if not managers:
            return 0

        current = now or datetime.now(timezone.utc)
        code = self.conversation_code(conversation)

        customer = (
            conversation.external_conversation_id
            or "não identificado"
        )

        content = (
            f"🚨 {title}\n\n"
            f"Cliente: {customer}\n"
            f"Código: {code}\n\n"
            f"{details}\n\n"
            "A Olívia continua atendendo o cliente enquanto isso.\n\n"
            "Se quiser assumir a conversa, responda:\n"
            f"ASSUMIR {code}"
        )

        template_details = (
            f"Cliente: {customer}. "
            f"{details} "
            "A Olívia continua atendendo normalmente. "
            f"Para assumir a conversa, envie ASSUMIR {code}."
        )

        notified = 0

        for manager in managers:
            self._send_manager_alert(
                db,
                account=account,
                manager=manager,
                current=current,
                conversation_id=None,
                text_content=content,
                alert_type=title,
                reference=f"Conversa {code}",
                template_details=template_details,
            )

            notified += 1

        if notified:
            db.add(
                AIEvent(
                    store_id=store_id,
                    conversation_id=conversation.id,
                    event_type="MANAGER_ESCALATION",
                    success=True,
                    payload_json={
                        "source": source,
                        "code": code,
                        "notified": notified,
                    },
                )
            )
            db.commit()

        return notified

    def notify_system(
        self,
        db: Session,
        *,
        store_id,
        title: str,
        details: str,
        source: str,
        now: datetime | None = None,
    ) -> int:
        account = self.channels.get_account_by_store(
            db,
            store_id=store_id,
            provider="WHATSAPP_CLOUD",
        )

        if account is None:
            return 0

        managers = self.staff.list_managers(
            db,
            store_id=store_id,
        )

        if not managers:
            return 0

        current = now or datetime.now(timezone.utc)
        notified = 0

        for manager in managers:
            self._send_manager_alert(
                db,
                account=account,
                manager=manager,
                current=current,
                conversation_id=None,
                text_content=(
                    f"🚨 {title}\n\n"
                    f"{details}\n\n"
                    f"Origem: {source}"
                ),
                alert_type=title,
                reference=source,
                template_details=details,
            )

            notified += 1

        if notified:
            db.commit()

        return notified
