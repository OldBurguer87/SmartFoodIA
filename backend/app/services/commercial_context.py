from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Store
from app.models.commercial import StoreBusinessHours, StoreDeliveryZone
from app.services.commercial_status import CommercialStatusService


class CommercialContextService:
    def build(self, db: Session, store_id: UUID) -> str:
        store = db.get(Store, store_id)
        if store is None:
            return "REGRAS COMERCIAIS: loja não encontrada."

        service = CommercialStatusService()
        rules = service.get_or_create_rules(db, store_id)
        status = service.current_status(db, store_id)
        hours = list(db.scalars(select(StoreBusinessHours).where(StoreBusinessHours.store_id == store_id)).all())
        zones = list(db.scalars(select(StoreDeliveryZone).where(StoreDeliveryZone.store_id == store_id, StoreDeliveryZone.active.is_(True))).all())

        payments = []
        if rules.accepts_pix:
            payments.append("PIX")
        if rules.accepts_credit:
            payments.append("CREDIT")
        if rules.accepts_debit:
            payments.append("DEBIT")
        if rules.accepts_cash:
            payments.append("CASH")

        pix_context = ""

        if rules.accepts_pix:
            if rules.pix_key and rules.pix_receiver_name:
                pix_parts = [
                    f"chave PIX={rules.pix_key}",
                    f"recebedor={rules.pix_receiver_name}",
                ]

                if rules.pix_receiver_institution:
                    pix_parts.append(
                        f"instituição={rules.pix_receiver_institution}"
                    )

                pix_context = (
                    " DADOS OFICIAIS PARA RECEBIMENTO PIX: "
                    + "; ".join(pix_parts)
                    + ". Quando o cliente escolher PIX ou pedir a chave, "
                    "informe estes dados diretamente. "
                    "Não solicite atendimento humano para fornecer a chave PIX. "
                    "Não pergunte se o cliente quer a chave: quando o pagamento "
                    "for PIX, envie-a diretamente. "
                    "Após o pedido PIX ser confirmado, solicite que o cliente "
                    "envie o comprovante pelo próprio WhatsApp."
                )
            else:
                pix_context = (
                    " PIX está habilitado, mas os dados de recebimento "
                    "não estão completos; nesse caso não invente dados."
                )

        hours_text = "não cadastrado"
        if hours:
            parts = []
            for item in sorted(hours, key=lambda row: row.weekday):
                if item.closed:
                    parts.append("dia %s fechado" % item.weekday)
                else:
                    parts.append("dia %s %s-%s delivery %s retirada %s" % (
                        item.weekday,
                        item.open_time or "?",
                        item.close_time or "?",
                        item.delivery_until or "?",
                        item.takeout_until or "?",
                    ))
            hours_text = "; ".join(parts)

        fee_text = "taxa fixa R$ %.2f" % rules.fixed_delivery_fee
        if rules.delivery_fee_mode != "FIXED":
            zone_parts = []
            for zone in zones:
                zone_parts.append("%s=R$ %.2f%s" % (zone.name, zone.fee, " não atende" if not zone.delivery_allowed else ""))
            fee_text = "taxa por região: " + ("; ".join(zone_parts) or "não cadastrada")

        return (
            "REGRAS COMERCIAIS DA LOJA %s. "
            "Situação atual: %s. Motivo: %s. "
            "Delivery: %s. Retirada: %s. Pedido mínimo delivery: R$ %.2f. %s. "
            "Pagamentos: %s. Troco: %s. Tempo médio: %s min. Horários: %s. Observações: %s.%s "
            "Consulte estas regras antes de iniciar e novamente antes de finalizar pedido. Não invente exceções."
        ) % (
            store.name,
            "ABERTO" if status["open"] else "FECHADO",
            status["reason"],
            "sim" if rules.delivery_enabled else "não",
            "sim" if rules.takeout_enabled else "não",
            rules.minimum_delivery_subtotal,
            fee_text,
            ", ".join(payments) or "nenhum cadastrado",
            "permitido" if rules.allow_change else "não permitido",
            rules.average_prep_minutes or "não cadastrado",
            hours_text,
            rules.general_notes or "nenhuma",
            pix_context,
        )
