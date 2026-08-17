from datetime import time
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import require_store_access, require_store_write_access
from app.models.catalog import Store
from app.models.commercial import StoreBusinessHours, StoreDeliveryZone
from app.services.commercial_status import CommercialStatusService, normalize_zone_name

router = APIRouter(prefix="/api/v1/operations/stores", tags=["commercial-rules"])
service = CommercialStatusService()


class RulesUpdate(BaseModel):
    manual_paused: bool = False
    pause_reason: str | None = None
    delivery_enabled: bool = True
    takeout_enabled: bool = True
    minimum_delivery_subtotal: Decimal = Decimal("0.00")
    delivery_fee_mode: str = Field(default="FIXED", pattern="^(FIXED|ZONE)$")
    fixed_delivery_fee: Decimal = Decimal("0.00")

    accepts_pix: bool = True
    pix_receiver_name: str | None = Field(default=None, max_length=180)
    pix_receiver_document: str | None = Field(default=None, max_length=40)
    pix_key: str | None = Field(default=None, max_length=200)
    pix_receiver_institution: str | None = Field(default=None, max_length=180)
    pix_auto_verify_enabled: bool = False
    pix_receipt_max_age_minutes: int = Field(default=360, ge=1, le=10080)
    pix_amount_tolerance: Decimal = Field(
        default=Decimal("0.01"),
        ge=0,
        le=100,
    )

    accepts_credit: bool = True
    accepts_debit: bool = True
    accepts_cash: bool = True
    allow_change: bool = True

    average_prep_minutes: int | None = Field(default=None, ge=1, le=600)

    allow_scheduled_orders: bool = True
    allow_scheduled_when_closed: bool = True
    scheduled_min_notice_minutes: int | None = Field(
        default=None,
        ge=0,
        le=10080,
    )
    scheduled_max_days_ahead: int | None = Field(
        default=None,
        ge=0,
        le=365,
    )

    general_notes: str | None = None


class HoursUpdate(BaseModel):
    closed: bool = False
    open_time: time | None = None
    close_time: time | None = None
    delivery_until: time | None = None
    takeout_until: time | None = None


class ZoneCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    fee: Decimal = Field(ge=0)
    delivery_allowed: bool = True
    active: bool = True


def rules_dict(db: Session, store_id: UUID) -> dict:
    rules = service.get_or_create_rules(db, store_id)
    status = service.current_status(db, store_id)
    hours = list(db.scalars(select(StoreBusinessHours).where(StoreBusinessHours.store_id == store_id).order_by(StoreBusinessHours.weekday)).all())
    zones = list(db.scalars(select(StoreDeliveryZone).where(StoreDeliveryZone.store_id == store_id).order_by(StoreDeliveryZone.name)).all())
    return {
        "store_id": str(store_id),
        "current_status": {"open": status["open"], "reason": status["reason"], "local_time": status["local_time"]},
        "rules": {
            "manual_paused": rules.manual_paused,
            "pause_reason": rules.pause_reason,
            "delivery_enabled": rules.delivery_enabled,
            "takeout_enabled": rules.takeout_enabled,
            "minimum_delivery_subtotal": float(rules.minimum_delivery_subtotal),
            "delivery_fee_mode": rules.delivery_fee_mode,
            "fixed_delivery_fee": float(rules.fixed_delivery_fee),
            "accepts_pix": rules.accepts_pix,
            "pix_receiver_name": rules.pix_receiver_name,
            "pix_receiver_document": rules.pix_receiver_document,
            "pix_key": rules.pix_key,
            "pix_receiver_institution": rules.pix_receiver_institution,
            "pix_auto_verify_enabled": rules.pix_auto_verify_enabled,
            "pix_receipt_max_age_minutes": rules.pix_receipt_max_age_minutes,
            "pix_amount_tolerance": float(rules.pix_amount_tolerance),
            "accepts_credit": rules.accepts_credit,
            "accepts_debit": rules.accepts_debit,
            "accepts_cash": rules.accepts_cash,
            "allow_change": rules.allow_change,
            "average_prep_minutes": rules.average_prep_minutes,
            "allow_scheduled_orders": rules.allow_scheduled_orders,
            "allow_scheduled_when_closed": rules.allow_scheduled_when_closed,
            "scheduled_min_notice_minutes": rules.scheduled_min_notice_minutes,
            "scheduled_max_days_ahead": rules.scheduled_max_days_ahead,
            "general_notes": rules.general_notes,
        },
        "hours": [
            {
                "weekday": h.weekday,
                "closed": h.closed,
                "open_time": h.open_time,
                "close_time": h.close_time,
                "delivery_until": h.delivery_until,
                "takeout_until": h.takeout_until,
            }
            for h in hours
        ],
        "zones": [
            {"id": str(z.id), "name": z.name, "fee": float(z.fee), "delivery_allowed": z.delivery_allowed, "active": z.active}
            for z in zones
        ],
    }


@router.get("/{store_id}/commercial-rules")
def get_rules(
    store_id: UUID,
    db: Session = Depends(get_db),
    _access=Depends(require_store_access),
) -> dict:
    if db.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="Loja não encontrada.")
    return rules_dict(db, store_id)


@router.put("/{store_id}/commercial-rules")
def update_rules(
    store_id: UUID,
    payload: RulesUpdate,
    db: Session = Depends(get_db),
    _access=Depends(require_store_write_access),
) -> dict:
    rules = service.get_or_create_rules(db, store_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rules, key, value)
    db.commit()
    return rules_dict(db, store_id)


@router.put("/{store_id}/commercial-rules/hours/{weekday}")
def update_hours(
    store_id: UUID,
    weekday: int,
    payload: HoursUpdate,
    db: Session = Depends(get_db),
    _access=Depends(require_store_write_access),
) -> dict:
    if weekday < 0 or weekday > 6:
        raise HTTPException(status_code=422, detail="Dia da semana deve estar entre 0 e 6.")
    item = db.scalar(select(StoreBusinessHours).where(StoreBusinessHours.store_id == store_id, StoreBusinessHours.weekday == weekday))
    if item is None:
        item = StoreBusinessHours(store_id=store_id, weekday=weekday)
        db.add(item)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return rules_dict(db, store_id)


@router.post("/{store_id}/commercial-rules/zones")
def create_zone(
    store_id: UUID,
    payload: ZoneCreate,
    db: Session = Depends(get_db),
    _access=Depends(require_store_write_access),
) -> dict:
    normalized = normalize_zone_name(payload.name)
    item = db.scalar(select(StoreDeliveryZone).where(StoreDeliveryZone.store_id == store_id, StoreDeliveryZone.normalized_name == normalized))
    if item is None:
        item = StoreDeliveryZone(store_id=store_id, name=payload.name, normalized_name=normalized, fee=payload.fee, delivery_allowed=payload.delivery_allowed, active=payload.active)
        db.add(item)
    else:
        item.name = payload.name
        item.fee = payload.fee
        item.delivery_allowed = payload.delivery_allowed
        item.active = payload.active
    db.commit()
    return rules_dict(db, store_id)


@router.delete("/{store_id}/commercial-rules/zones/{zone_id}")
def delete_zone(
    store_id: UUID,
    zone_id: UUID,
    db: Session = Depends(get_db),
    _access=Depends(require_store_write_access),
) -> dict:
    item = db.scalar(select(StoreDeliveryZone).where(StoreDeliveryZone.id == zone_id, StoreDeliveryZone.store_id == store_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Zona não encontrada.")
    db.delete(item)
    db.commit()
    return rules_dict(db, store_id)
