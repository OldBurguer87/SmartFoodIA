import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_auth
from app.api.deps import require_store_access, require_store_write_access
from app.core.config import settings
from app.models.catalog import Store
from app.models.customer import CustomerAddress
from app.models.order import Order, OrderPayment
from app.models.payment import PaymentReceipt
from app.database.session import get_db
from app.models.conversation import HumanTicket, Message
from app.repositories.channel import ChannelRepository
from app.repositories.conversation import ConversationRepository
from app.schemas.customer import AddressCreate
from app.schemas.conversation import (
    ConversationTakeoverRequest,
    HumanReplyRequest,
    MessageCreate,
    StoreOperationModeRequest,
)
from app.services.auth import (
    AuthenticatedUser,
    StoreAccess,
    resolve_store_access,
)
from app.services.customer import CustomerService
from app.services.conversation import (
    ConversationNotFoundError,
    ConversationService,
    ConversationStateError,
)
from app.services.conversation_media import (
    ConversationMediaStorage,
    ConversationMediaStorageError,
)
from app.services.olivia_release_resume import (
    OliviaReleaseResumeService,
)
from app.services.commercial_status import (
    CommercialStatusService,
)

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])
conversations = ConversationService()
conversation_repository = ConversationRepository()
channel_repository = ChannelRepository()
customer_service = CustomerService()
olivia_release_resume = OliviaReleaseResumeService()
commercial_status_service = CommercialStatusService()


def require_conversation_access(
    conversation_id: UUID,
    authenticated: AuthenticatedUser = Depends(current_auth),
    db: Session = Depends(get_db),
) -> StoreAccess:
    conversation = conversation_repository.get(
        db,
        conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        )

    access = resolve_store_access(
        db,
        authenticated.user,
        conversation.store_id,
    )

    if access is None:
        raise HTTPException(
            status_code=403,
            detail="Você não tem acesso a esta loja.",
        )

    return access


def require_conversation_write_access(
    access: StoreAccess = Depends(
        require_conversation_access,
    ),
) -> StoreAccess:
    if not access.can_write:
        raise HTTPException(
            status_code=403,
            detail="Seu usuário não pode alterar esta loja.",
        )

    return access


def conversation_to_dict(conversation) -> dict:
    last_message = conversation.messages[-1] if conversation.messages else None
    return {
        "id": str(conversation.id),
        "store_id": str(conversation.store_id),
        "customer_id": str(conversation.customer_id)
        if conversation.customer_id
        else None,
        "channel": conversation.channel,
        "external_conversation_id": conversation.external_conversation_id,
        "status": conversation.status,
        "unread_count": conversation.unread_count,
        "last_message_at": conversation.last_message_at,
        "last_message": (
            {
                "sender_type": last_message.sender_type,
                "content": last_message.content,
                "created_at": last_message.created_at,
            }
            if last_message
            else None
        ),
    }


@router.get("/stores/{store_id}/operation-mode")
def get_store_operation_mode(
    store_id: UUID,
    access: StoreAccess = Depends(require_store_access),
    db: Session = Depends(get_db),
) -> dict:
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(
            status_code=404,
            detail="Loja não encontrada.",
        )

    configured_mode = store.operation_mode
    server_forced_human = bool(settings.human_only_mode)
    effective_mode = (
        "HUMAN_ONLY"
        if server_forced_human
        or configured_mode == "HUMAN_ONLY"
        else "OLIVIA"
    )

    return {
        "configured_mode": configured_mode,
        "effective_mode": effective_mode,
        "server_forced_human": server_forced_human,
        "can_change": access.can_write,
    }


@router.put("/stores/{store_id}/operation-mode")
def update_store_operation_mode(
    store_id: UUID,
    payload: StoreOperationModeRequest,
    _access: StoreAccess = Depends(require_store_write_access),
    db: Session = Depends(get_db),
) -> dict:
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(
            status_code=404,
            detail="Loja não encontrada.",
        )

    if (
        settings.human_only_mode
        and payload.operation_mode == "OLIVIA"
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "O modo 100% humano está obrigatório no servidor. "
                "A Olívia não pode ser reativada pelo painel neste momento."
            ),
        )

    store.operation_mode = payload.operation_mode
    db.commit()
    db.refresh(store)

    server_forced_human = bool(settings.human_only_mode)
    effective_mode = (
        "HUMAN_ONLY"
        if server_forced_human
        or store.operation_mode == "HUMAN_ONLY"
        else "OLIVIA"
    )

    return {
        "configured_mode": store.operation_mode,
        "effective_mode": effective_mode,
        "server_forced_human": server_forced_human,
        "can_change": True,
    }


@router.get("/stores/{store_id}/conversations")
def list_conversations(
    store_id: UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _access: StoreAccess = Depends(require_store_access),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = conversation_repository.list_for_store(
        db,
        store_id=store_id,
        status=status,
        limit=limit,
    )

    shift = commercial_status_service.current_shift_window(
        db,
        store_id,
    )

    result = []

    for item in items:
        body = conversation_to_dict(item)

        if item.status != "OPEN":
            body["current_shift"] = False

        elif not shift["reliable"]:
            # Horário ausente/incompleto:
            # preserva comportamento antigo.
            body["current_shift"] = True

        elif not shift["active"]:
            # Fora do expediente não existe turno ativo.
            body["current_shift"] = False

        else:
            last_activity = item.last_message_at

            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(
                    tzinfo=timezone.utc,
                )
            else:
                last_activity = last_activity.astimezone(
                    timezone.utc,
                )

            shift_start = shift[
                "started_at"
            ].astimezone(timezone.utc)

            body["current_shift"] = (
                last_activity >= shift_start
            )

        result.append(body)

    return result



@router.post("/conversations/{conversation_id}/read")
def mark_conversation_read(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(
        require_conversation_access,
    ),
) -> dict:
    try:
        conversation = conversations.mark_read(
            db,
            conversation_id=conversation_id,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        ) from error

    return {
        "id": str(conversation.id),
        "unread_count": conversation.unread_count,
    }


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(
        require_conversation_access,
    ),
) -> dict:
    conversation = conversation_repository.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    messages = conversation_repository.list_messages(db, conversation_id, limit=200)
    payload = conversation_to_dict(conversation)
    payload["messages"] = [
        {
            "id": str(message.id),
            "direction": message.direction,
            "sender_type": message.sender_type,
            "content_type": message.content_type,
            "content": message.content,
            "metadata_json": message.metadata_json,
            "created_at": message.created_at,
        }
        for message in messages
    ]
    return payload

@router.get(
    "/conversations/{conversation_id}/messages/{message_id}/media"
)
def get_conversation_message_media(
    conversation_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db),
    _access: StoreAccess = Depends(
        require_conversation_access,
    ),
):
    message = db.get(Message, message_id)

    if (
        message is None
        or message.conversation_id != conversation_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Mídia da conversa não encontrada.",
        )

    metadata = message.metadata_json or {}

    relative_path = str(
        metadata.get("stored_media_path") or ""
    ).strip()

    if not relative_path:
        raise HTTPException(
            status_code=404,
            detail="Mídia da conversa não encontrada.",
        )

    storage = ConversationMediaStorage()

    try:
        media_path = storage.resolve(relative_path)
    except ConversationMediaStorageError as error:
        raise HTTPException(
            status_code=404,
            detail="Mídia da conversa não encontrada.",
        ) from error

    if not media_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Arquivo de mídia não encontrado.",
        )

    mime_type = str(
        metadata.get("mime_type")
        or "application/octet-stream"
    )

    filename = Path(
        str(
            metadata.get("filename")
            or media_path.name
        )
    ).name

    if not filename:
        filename = media_path.name

    return FileResponse(
        path=media_path,
        media_type=mime_type,
        filename=filename,
        content_disposition_type="inline",
    )



@router.post(
    "/conversations/{conversation_id}/media"
)
def human_media_reply(
    conversation_id: UUID,
    file: UploadFile = File(...),
    assigned_to: str = Form(...),
    caption: str = Form(default=""),
    _access: StoreAccess = Depends(
        require_conversation_write_access,
    ),
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(
        db,
        conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        )

    if conversation.status != "HUMAN":
        raise HTTPException(
            status_code=422,
            detail=(
                "Assuma a conversa antes de enviar "
                "um arquivo."
            ),
        )

    if conversation.channel != "WHATSAPP":
        raise HTTPException(
            status_code=422,
            detail=(
                "Envio de arquivo disponível somente "
                "para WhatsApp nesta versão."
            ),
        )

    if not conversation.external_conversation_id:
        raise HTTPException(
            status_code=422,
            detail="Conversa sem destinatário externo.",
        )

    assigned_to = assigned_to.strip()

    if len(assigned_to) < 2 or len(assigned_to) > 160:
        raise HTTPException(
            status_code=422,
            detail="Atendente inválido.",
        )

    caption = caption.strip()

    if len(caption) > 1024:
        raise HTTPException(
            status_code=422,
            detail=(
                "A legenda deve ter no máximo "
                "1024 caracteres."
            ),
        )

    allowed_mime = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    mime_type = (
        str(file.content_type or "")
        .split(";")[0]
        .strip()
        .lower()
    )

    if mime_type not in allowed_mime:
        raise HTTPException(
            status_code=422,
            detail=(
                "Formato não permitido. "
                "Envie PDF, JPG, PNG ou WEBP."
            ),
        )

    account = channel_repository.get_account_by_store(
        db,
        store_id=conversation.store_id,
        provider="WHATSAPP_CLOUD",
    )

    if account is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Conta WhatsApp ativa não encontrada "
                "para a loja."
            ),
        )

    storage = ConversationMediaStorage()

    # Lê no máximo limite + 1 para não aceitar upload
    # arbitrariamente grande em memória.
    content = file.file.read(
        storage.max_bytes + 1
    )

    try:
        stored = storage.store(
            store_id=conversation.store_id,
            conversation_id=conversation.id,
            content=content,
            mime_type=mime_type,
            original_filename=file.filename,
        )
    except ConversationMediaStorageError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    media_path = storage.resolve(
        stored.relative_path
    )

    filename = (
        stored.original_filename
        or media_path.name
    )

    media_type = (
        "image"
        if stored.mime_type.startswith("image/")
        else "document"
    )

    display_content = (
        caption
        or (
            "[Imagem enviada]"
            if media_type == "image"
            else f"[Arquivo enviado: {filename}]"
        )
    )

    message = conversations.add_message(
        db,
        conversation_id=conversation.id,
        payload=MessageCreate(
            direction="OUTBOUND",
            sender_type="HUMAN",
            content_type=(
                "IMAGE"
                if media_type == "image"
                else "DOCUMENT"
            ),
            content=display_content,
            metadata_json={
                "source": "HUMAN_UPLOAD",
                "assigned_to": assigned_to,
                "stored_media": True,
                "stored_media_path":
                    stored.relative_path,
                "mime_type": stored.mime_type,
                "file_size": stored.file_size,
                "sha256": stored.sha256,
                "filename": filename,
                "media_type": media_type,
                "caption": caption or None,
            },
        ),
    )

    outbound = (
        channel_repository.create_media_file_outbound(
            db,
            account=account,
            conversation_id=conversation.id,
            recipient=(
                conversation.external_conversation_id
            ),
            content=json.dumps(
                {
                    "path": str(media_path),
                    "mime_type": stored.mime_type,
                    "media_type": media_type,
                    "filename": filename,
                    "caption": caption or None,
                },
                ensure_ascii=False,
            ),
        )
    )

    return {
        "message_id": str(message.id),
        "outbound_id": str(outbound.id),
        "status": outbound.status,
        "content_type": message.content_type,
        "filename": filename,
        "mime_type": stored.mime_type,
        "file_size": stored.file_size,
    }


@router.post(
    "/conversations/{conversation_id}/orders/{order_id}/pix/confirm"
)
def confirm_human_pix(
    conversation_id: UUID,
    order_id: UUID,
    message_id: UUID = Form(...),
    assigned_to: str = Form(...),
    _access: StoreAccess = Depends(
        require_conversation_write_access,
    ),
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(
        db, conversation_id,
    )
    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        )
    if conversation.status != "HUMAN":
        raise HTTPException(
            status_code=422,
            detail="Assuma a conversa antes de confirmar o PIX.",
        )
    assigned_to = assigned_to.strip()
    if len(assigned_to) < 2 or len(assigned_to) > 160:
        raise HTTPException(
            status_code=422,
            detail="Atendente inválido.",
        )
    order = db.get(Order, order_id)
    if order is None or order.store_id != conversation.store_id:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado nesta loja.",
        )
    order_has_pix = (
        str(order.payment_method or "").upper() == "PIX"
        or db.scalar(
            select(OrderPayment.id)
            .where(
                OrderPayment.order_id == order.id,
                OrderPayment.method == "PIX",
            )
            .limit(1)
        )
        is not None
    )

    if not order_has_pix:
        raise HTTPException(
            status_code=422,
            detail="O pedido informado não utiliza PIX.",
        )
    if str(order.status).upper() == "CANCELLED":
        raise HTTPException(
            status_code=422,
            detail="Pedido cancelado não pode receber confirmação PIX.",
        )
    conversation_phone = "".join(
        c for c in str(conversation.external_conversation_id or "")
        if c.isdigit()
    )
    order_phone = "".join(
        c for c in str(order.customer_phone or "")
        if c.isdigit()
    )
    same_customer = (
        order.customer_id == conversation.customer_id
        if conversation.customer_id is not None
        else bool(conversation_phone and conversation_phone == order_phone)
    )
    if not same_customer:
        raise HTTPException(
            status_code=422,
            detail="O pedido não pertence ao cliente desta conversa.",
        )
    message = db.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise HTTPException(
            status_code=404,
            detail="Comprovante não encontrado nesta conversa.",
        )
    if (
        message.direction != "INBOUND"
        or message.sender_type != "CUSTOMER"
        or message.content_type not in {"IMAGE", "DOCUMENT"}
    ):
        raise HTTPException(
            status_code=422,
            detail="Selecione uma imagem ou documento recebido do cliente.",
        )
    metadata = message.metadata_json or {}
    if metadata.get("stored_media") is not True:
        raise HTTPException(
            status_code=422,
            detail="O arquivo original deste comprovante não está armazenado.",
        )
    relative_path = str(metadata.get("stored_media_path") or "").strip()
    mime_type = str(metadata.get("mime_type") or "").strip().lower()
    allowed_mime = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
    }
    if mime_type not in allowed_mime:
        raise HTTPException(
            status_code=422,
            detail="Formato não permitido para comprovante PIX.",
        )
    storage = ConversationMediaStorage()
    try:
        source_path = storage.resolve(relative_path)
    except ConversationMediaStorageError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not source_path.is_file():
        raise HTTPException(
            status_code=422,
            detail="Arquivo do comprovante não encontrado no armazenamento.",
        )
    content = source_path.read_bytes()
    if not content:
        raise HTTPException(status_code=422, detail="Comprovante vazio.")
    digest = hashlib.sha256(content).hexdigest()
    expected_digest = str(metadata.get("sha256") or "").strip().lower()
    if expected_digest and digest != expected_digest:
        raise HTTPException(
            status_code=422,
            detail="O arquivo armazenado não corresponde ao comprovante original.",
        )

    if len(content) > settings.payment_receipt_max_bytes:
        raise HTTPException(
            status_code=422,
            detail="Comprovante excede o tamanho máximo permitido.",
        )

    confirmed = db.scalar(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.store_id == order.store_id,
            PaymentReceipt.order_id == order.id,
            PaymentReceipt.status.in_(
                ["AUTO_CONFIRMED", "HUMAN_CONFIRMED"]
            ),
        )
        .order_by(PaymentReceipt.created_at.desc())
        .limit(1)
    )
    if confirmed is not None:
        return {
            "receipt_id": str(confirmed.id),
            "order_id": str(order.id),
            "display_id": order.display_id,
            "status": confirmed.status,
            "message_id": str(message.id),
            "already_confirmed": True,
        }

    duplicate = db.scalar(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.store_id == order.store_id,
            PaymentReceipt.file_sha256 == digest,
        )
        .order_by(PaymentReceipt.created_at.desc())
        .limit(1)
    )

    if duplicate is not None:
        if duplicate.order_id != order.id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Este comprovante já está registrado em outro pedido."
                ),
            )
        if duplicate.status == "HUMAN_REJECTED":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Este comprovante já foi recusado pela equipe."
                ),
            )
        receipt = duplicate
    else:
        receipt_id = uuid4()
        receipt_dir = (
            Path(settings.payment_receipt_storage_path)
            / str(order.store_id)
        )
        try:
            receipt_dir.mkdir(parents=True, exist_ok=True)
            destination = (
                receipt_dir
                / f"{receipt_id}{allowed_mime[mime_type]}"
            )
            destination.write_bytes(content)
        except OSError as error:
            raise HTTPException(
                status_code=500,
                detail="Não foi possível armazenar o comprovante PIX.",
            ) from error

        receipt = PaymentReceipt(
            id=receipt_id,
            store_id=order.store_id,
            order_id=order.id,
            conversation_id=conversation.id,
            external_media_id=(
                str(metadata.get("media_id") or "").strip() or None
            ),
            media_type=message.content_type,
            mime_type=mime_type,
            original_filename=(
                str(metadata.get("filename") or "").strip() or None
            ),
            storage_path=str(destination),
            file_sha256=digest,
            status="HUMAN_CONFIRMED",
        )
        db.add(receipt)

    receipt.status = "HUMAN_CONFIRMED"
    receipt.reviewed_by = f"{assigned_to} via Central Web"
    receipt.reviewed_at = datetime.now(timezone.utc)
    receipt.review_notes = (
        "Comprovante confirmado manualmente pela Central de Atendimento."
    )
    receipt.validation_json = {
        **(receipt.validation_json or {}),
        "manual_confirmation": True,
        "source": "CENTRAL_WEB",
        "source_message_id": str(message.id),
        "conversation_id": str(conversation.id),
        "order_display_id": order.display_id,
    }

    message.metadata_json = {
        **metadata,
        "payment_receipt_id": str(receipt.id),
        "payment_receipt_status": "HUMAN_CONFIRMED",
        "payment_order_id": str(order.id),
        "payment_order_display_id": order.display_id,
    }

    try:
        db.commit()
        db.refresh(receipt)
    except Exception as error:
        db.rollback()
        if duplicate is None:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(
            status_code=500,
            detail="Não foi possível confirmar o PIX.",
        ) from error

    return {
        "receipt_id": str(receipt.id),
        "order_id": str(order.id),
        "display_id": order.display_id,
        "status": receipt.status,
        "message_id": str(message.id),
        "already_confirmed": False,
    }

# HUMAN_PIX_ENDPOINT_END

@router.post("/conversations/{conversation_id}/takeover")
def take_over(
    conversation_id: UUID,
    payload: ConversationTakeoverRequest,
    _access: StoreAccess = Depends(
        require_conversation_write_access,
    ),
    db: Session = Depends(get_db),
) -> dict:
    try:
        conversation = conversations.take_over(
            db,
            conversation_id=conversation_id,
            assigned_to=payload.assigned_to,
        )

        ticket = db.scalar(
            select(HumanTicket)
            .where(
                HumanTicket.conversation_id == conversation_id,
                HumanTicket.status.in_(["OPEN", "IN_PROGRESS"]),
            )
            .order_by(HumanTicket.created_at.desc())
            .limit(1)
        )
        if ticket is not None:
            conversations.assign_ticket(
                db,
                ticket_id=ticket.id,
                assigned_to=payload.assigned_to,
            )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.") from error
    except ConversationStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return conversation_to_dict(conversation)


@router.post("/conversations/{conversation_id}/release")
def release_to_olivia(
    conversation_id: UUID,
    payload: ConversationTakeoverRequest,
    _access: StoreAccess = Depends(
        require_conversation_write_access,
    ),
    db: Session = Depends(get_db),
) -> dict:
    try:
        conversation = conversations.release_to_olivia(
            db,
            conversation_id=conversation_id,
            assigned_to=payload.assigned_to,
        )

        olivia_release_resume.resume_if_needed(
            db,
            conversation=conversation,
        )

        db.refresh(conversation)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.") from error
    except ConversationStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return conversation_to_dict(conversation)


@router.post(
    "/conversations/{conversation_id}/close"
)
def close_human_conversation(
    conversation_id: UUID,
    payload: ConversationTakeoverRequest,
    _access: StoreAccess = Depends(
        require_conversation_write_access,
    ),
    db: Session = Depends(get_db),
) -> dict:
    try:
        conversation = (
            conversations.close_human_conversation(
                db,
                conversation_id=conversation_id,
                assigned_to=payload.assigned_to,
            )
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        ) from error
    except ConversationStateError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return conversation_to_dict(conversation)




@router.post("/conversations/{conversation_id}/reply")
def human_reply(
    conversation_id: UUID,
    payload: HumanReplyRequest,
    _access: StoreAccess = Depends(
        require_conversation_write_access,
    ),
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    if conversation.channel != "WHATSAPP":
        raise HTTPException(
            status_code=422,
            detail="Envio humano disponível somente para WhatsApp nesta versão.",
        )
    account = channel_repository.get_account_by_store(
        db,
        store_id=conversation.store_id,
        provider="WHATSAPP_CLOUD",
    )
    if account is None:
        raise HTTPException(
            status_code=422,
            detail="Conta WhatsApp ativa não encontrada para a loja.",
        )
    if not conversation.external_conversation_id:
        raise HTTPException(
            status_code=422,
            detail="Conversa sem destinatário externo.",
        )

    try:
        message = conversations.add_human_message(
            db,
            conversation_id=conversation_id,
            content=payload.content,
            assigned_to=payload.assigned_to,
        )
    except ConversationStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    outbound = channel_repository.create_outbound(
        db,
        account=account,
        conversation_id=conversation.id,
        recipient=conversation.external_conversation_id,
        content=payload.content,
    )
    return {
        "message_id": str(message.id),
        "outbound_id": str(outbound.id),
        "status": outbound.status,
    }


# HUMAN_ORDER_MANAGEMENT_HOTFIX
def _human_address_to_dict(address: CustomerAddress) -> dict:
    return {
        "id": str(address.id),
        "label": address.label,
        "street": address.street,
        "number": address.number,
        "neighborhood": address.neighborhood,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "complement": address.complement,
        "reference": address.reference,
        "is_default": address.is_default,
        "active": address.active,
    }


@router.post(
    "/conversations/{conversation_id}/customer/addresses",
    status_code=201,
)
def create_human_customer_address(
    conversation_id: UUID,
    payload: AddressCreate,
    _access: StoreAccess = Depends(require_conversation_write_access),
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(db, conversation_id)

    if conversation is None or conversation.customer_id is None:
        raise HTTPException(
            status_code=409,
            detail="A conversa ainda não está vinculada a um cliente.",
        )

    address = customer_service.add_address(
        db,
        customer_id=conversation.customer_id,
        payload=payload,
    )

    return _human_address_to_dict(address)


@router.patch(
    "/conversations/{conversation_id}/customer/addresses/{address_id}",
)
def update_human_customer_address(
    conversation_id: UUID,
    address_id: UUID,
    payload: AddressCreate,
    _access: StoreAccess = Depends(require_conversation_write_access),
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(db, conversation_id)

    if conversation is None or conversation.customer_id is None:
        raise HTTPException(
            status_code=409,
            detail="A conversa ainda não está vinculada a um cliente.",
        )

    address = db.get(CustomerAddress, address_id)

    if (
        address is None
        or address.customer_id != conversation.customer_id
        or not address.active
    ):
        raise HTTPException(
            status_code=404,
            detail="Endereço não encontrado para este cliente.",
        )

    if payload.is_default:
        others = db.scalars(
            select(CustomerAddress).where(
                CustomerAddress.customer_id == conversation.customer_id,
                CustomerAddress.id != address.id,
                CustomerAddress.active.is_(True),
            )
        ).all()

        for other in others:
            other.is_default = False

    for field, value in payload.model_dump().items():
        setattr(address, field, value)

    db.commit()
    db.refresh(address)

    return _human_address_to_dict(address)


@router.post(
    "/conversations/{conversation_id}/orders/{order_id}/cancel",
)
def cancel_human_pending_order(
    conversation_id: UUID,
    order_id: UUID,
    _access: StoreAccess = Depends(require_conversation_write_access),
    db: Session = Depends(get_db),
) -> dict:
    conversation = conversation_repository.get(db, conversation_id)

    if conversation is None or conversation.customer_id is None:
        raise HTTPException(
            status_code=409,
            detail="A conversa ainda não está vinculada a um cliente.",
        )

    order = db.get(Order, order_id)

    if (
        order is None
        or order.store_id != conversation.store_id
        or order.customer_id != conversation.customer_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado para esta conversa.",
        )

    if order.status == "CANCELLED":
        return {
            "id": str(order.id),
            "display_id": order.display_id,
            "status": order.status,
        }

    if order.consumer_order_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este pedido já foi enviado ao Consumer. "
                "O cancelamento deve ser feito diretamente no Consumer/PDV."
            ),
        )

    if order.status != "READY_FOR_INTEGRATION":
        raise HTTPException(
            status_code=409,
            detail=(
                "Somente pedidos ainda aguardando integração "
                "podem ser cancelados por esta tela."
            ),
        )

    order.status = "CANCELLED"
    db.commit()
    db.refresh(order)

    return {
        "id": str(order.id),
        "display_id": order.display_id,
        "status": order.status,
    }
