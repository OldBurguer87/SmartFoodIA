from __future__ import annotations

import base64
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.commercial import StoreCommercialRules
from app.models.order import Order
from app.models.payment import PaymentReceipt


MANAUS_TZ = ZoneInfo("America/Manaus")
BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")


class PixReceiptAnalysisError(RuntimeError):
    pass


PIX_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "is_pix_receipt": {
            "type": "boolean",
        },
        "receiver_name": {
            "type": ["string", "null"],
        },
        "receiver_document": {
            "type": ["string", "null"],
        },
        "pix_key": {
            "type": ["string", "null"],
        },
        "amount": {
            "type": ["number", "null"],
        },
        "paid_date": {
            "type": ["string", "null"],
            "description": "Data em YYYY-MM-DD.",
        },
        "paid_time": {
            "type": ["string", "null"],
            "description": "Hora em HH:MM:SS, formato 24 horas.",
        },
        "transaction_id": {
            "type": ["string", "null"],
        },
        "transaction_status": {
            "type": ["string", "null"],
        },
        "payment_completed": {
            "type": ["boolean", "null"],
        },
        "payer_name": {
            "type": ["string", "null"],
        },
        "institution": {
            "type": ["string", "null"],
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "notes": {
            "type": ["string", "null"],
        },
    },
    "required": [
        "is_pix_receipt",
        "receiver_name",
        "receiver_document",
        "pix_key",
        "amount",
        "paid_date",
        "paid_time",
        "transaction_id",
        "transaction_status",
        "payment_completed",
        "payer_name",
        "institution",
        "confidence",
        "notes",
    ],
}


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return " ".join(value.split())


def _normalize_document(value: str | None) -> str:
    return "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )


def _document_matches(
    expected: str | None,
    actual: str | None,
) -> bool | None:
    expected_digits = _normalize_document(expected)
    actual_digits = _normalize_document(actual)

    if not expected_digits or not actual_digits:
        return None

    if expected_digits == actual_digits:
        return True

    # Muitos bancos mascaram CPF/CNPJ e mostram apenas parte dos dígitos,
    # por exemplo ***.559.652-**.
    if (
        len(actual_digits) >= 6
        and actual_digits in expected_digits
    ):
        return True

    if (
        len(expected_digits) >= 6
        and expected_digits in actual_digits
    ):
        return True

    return False


def _institution_matches(
    expected: str | None,
    actual: str | None,
) -> bool | None:
    expected_n = _normalize_text(expected)
    actual_n = _normalize_text(actual)

    if not expected_n or not actual_n:
        return None

    ignored = {
        "IP",
        "LTDA",
        "SA",
        "S",
        "A",
        "INSTITUICAO",
        "DE",
        "PAGAMENTO",
    }

    expected_tokens = [
        token
        for token in expected_n.split()
        if token not in ignored
    ]

    actual_tokens = set(actual_n.split())

    if not expected_tokens:
        return None

    return all(
        token in actual_tokens
        for token in expected_tokens
    )


def _normalize_key(value: str | None) -> str:
    return re.sub(
        r"\s+",
        "",
        str(value or "").strip().lower(),
    )


def _receiver_name_matches(
    expected: str | None,
    actual: str | None,
) -> bool:
    expected_n = _normalize_text(expected)
    actual_n = _normalize_text(actual)

    if not expected_n or not actual_n:
        return False

    legal_words = {
        "LTDA",
        "ME",
        "EPP",
        "EIRELI",
        "SA",
        "S",
        "A",
    }

    expected_tokens = [
        token
        for token in expected_n.split()
        if token not in legal_words
    ]

    actual_tokens = set(actual_n.split())

    if not expected_tokens:
        return False

    matched = sum(
        1
        for token in expected_tokens
        if token in actual_tokens
    )

    return matched / len(expected_tokens) >= 0.80


def _parse_paid_at(
    paid_date: str | None,
    paid_time: str | None,
    *,
    reference_time: datetime | None = None,
) -> datetime | None:
    if not paid_date or not paid_time:
        return None

    patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]

    raw = f"{paid_date.strip()} {paid_time.strip()}"
    local_dt = None

    for pattern in patterns:
        try:
            local_dt = datetime.strptime(raw, pattern)
            break
        except ValueError:
            continue

    if local_dt is None:
        return None

    # Alguns comprovantes exibem horário local de Manaus/Coari;
    # outros exibem horário de Brasília. Consideramos ambos.
    candidates = [
        local_dt.replace(
            tzinfo=MANAUS_TZ
        ).astimezone(timezone.utc),
        local_dt.replace(
            tzinfo=BRASILIA_TZ
        ).astimezone(timezone.utc),
    ]

    # Remove duplicatas, inclusive em períodos em que os offsets
    # eventualmente coincidam.
    unique: list[datetime] = []

    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)

    if reference_time is None:
        return unique[0]

    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(
            tzinfo=timezone.utc
        )

    # O comprovante normalmente é enviado logo após o pagamento.
    # Escolhemos a interpretação temporal mais próxima do momento
    # em que o arquivo chegou ao SmartFoodIA.
    return min(
        unique,
        key=lambda candidate: abs(
            (candidate - reference_time).total_seconds()
        ),
    )



class PixReceiptAnalyzer:
    def __init__(self, *, client=None) -> None:
        if client is None:
            if not settings.openai_api_key:
                raise PixReceiptAnalysisError(
                    "OPENAI_API_KEY não configurada."
                )

            from openai import OpenAI

            client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )

        self.client = client

    def analyze(
        self,
        *,
        receipt: PaymentReceipt,
    ) -> dict:
        path = Path(receipt.storage_path)

        if not path.exists():
            raise PixReceiptAnalysisError(
                f"Arquivo do comprovante não encontrado: {path}"
            )

        raw = path.read_bytes()
        encoded = base64.b64encode(raw).decode("ascii")

        instructions = (
            "Você analisa comprovantes brasileiros de pagamento PIX. "
            "Extraia SOMENTE informações que estejam visíveis no arquivo. "
            "Não invente CPF/CNPJ, chave PIX, valor, data, hora, ID, "
            "destinatário ou status. "
            "Se um campo não estiver visível ou legível, retorne null. "
            "payment_completed deve ser true quando o documento for "
            "claramente um comprovante de uma transferência PIX realizada, "
            "especialmente quando houver valor, data/hora e ID da transação "
            "ou E2E. Use false quando houver indicação explícita de "
            "agendado, pendente, em processamento, cancelado, recusado ou "
            "falha. Frases institucionais genéricas como 'sujeita a análise' "
            "não significam, sozinhas, que a transação PIX esteja pendente. "
            "paid_date deve ser YYYY-MM-DD e paid_time deve ser HH:MM:SS. "
            "confidence representa a confiança geral na leitura, entre 0 e 1. "
            "O campo institution deve conter SOMENTE a instituição do "
            "recebedor/destinatário do PIX, nunca o banco ou instituição "
            "do pagador/origem. "
            "receiver_name, receiver_document e pix_key também pertencem "
            "sempre ao recebedor/destinatário. "
            "payer_name pertence ao pagador/origem. "
            "Você NÃO decide se o comprovante deve ser aceito pela loja; "
            "apenas extrai os fatos visíveis."
        )

        content = [
            {
                "type": "input_text",
                "text": instructions,
            }
        ]

        mime = (
            receipt.mime_type
            or "application/octet-stream"
        ).lower()

        if mime.startswith("image/"):
            content.append(
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{mime};base64,{encoded}"
                    ),
                    "detail": "high",
                }
            )

        elif mime == "application/pdf":
            content.append(
                {
                    "type": "input_file",
                    "filename": (
                        receipt.original_filename
                        or "comprovante-pix.pdf"
                    ),
                    "file_data": encoded,
                }
            )

        else:
            raise PixReceiptAnalysisError(
                f"MIME não suportado para análise: {mime}"
            )

        try:
            response = self.client.responses.create(
                model=settings.openai_model,
                store=False,
                input=[
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "pix_receipt_extraction",
                        "strict": True,
                        "schema": PIX_EXTRACTION_SCHEMA,
                    }
                },
            )
        except Exception as error:
            raise PixReceiptAnalysisError(
                f"Falha na análise OpenAI: {error}"
            ) from error

        output_text = getattr(
            response,
            "output_text",
            None,
        )

        if not output_text:
            raise PixReceiptAnalysisError(
                "OpenAI não devolveu dados do comprovante."
            )

        try:
            return json.loads(output_text)
        except json.JSONDecodeError as error:
            raise PixReceiptAnalysisError(
                "Resposta estruturada inválida."
            ) from error


class PixReceiptValidationService:
    def __init__(self, *, analyzer=None) -> None:
        self.analyzer = analyzer or PixReceiptAnalyzer()

    def process(
        self,
        db: Session,
        *,
        receipt: PaymentReceipt,
    ) -> PaymentReceipt:
        if receipt.order_id is None:
            receipt.status = "NEEDS_ORDER"
            db.commit()
            db.refresh(receipt)
            return receipt

        order = db.get(Order, receipt.order_id)

        if order is None:
            receipt.status = "NEEDS_REVIEW"
            receipt.validation_json = {
                **(receipt.validation_json or {}),
                "decision": "NEEDS_REVIEW",
                "reasons": ["ORDER_NOT_FOUND"],
            }
            db.commit()
            db.refresh(receipt)
            return receipt

        rules = db.scalar(
            select(StoreCommercialRules).where(
                StoreCommercialRules.store_id
                == receipt.store_id
            )
        )

        if rules is None:
            receipt.status = "NEEDS_REVIEW"
            receipt.validation_json = {
                **(receipt.validation_json or {}),
                "decision": "NEEDS_REVIEW",
                "reasons": [
                    "PIX_RULES_NOT_CONFIGURED",
                ],
            }
            db.commit()
            db.refresh(receipt)
            return receipt

        try:
            extracted = self.analyzer.analyze(
                receipt=receipt
            )
        except Exception as error:
            receipt.status = "NEEDS_REVIEW"
            receipt.validation_json = {
                **(receipt.validation_json or {}),
                "decision": "NEEDS_REVIEW",
                "reasons": [
                    "ANALYSIS_FAILED",
                ],
                "analysis_error": str(error)[:500],
            }
            db.commit()
            db.refresh(receipt)
            return receipt

        receipt.extracted_receiver_name = (
            extracted.get("receiver_name")
        )
        receipt.extracted_receiver_document = (
            extracted.get("receiver_document")
        )
        receipt.extracted_pix_key = (
            extracted.get("pix_key")
        )

        amount = extracted.get("amount")

        if amount is not None:
            try:
                receipt.extracted_amount = Decimal(
                    str(amount)
                )
            except InvalidOperation:
                receipt.extracted_amount = None

        receipt.extracted_paid_at = _parse_paid_at(
            extracted.get("paid_date"),
            extracted.get("paid_time"),
            reference_time=receipt.created_at,
        )

        receipt.extracted_transaction_id = (
            extracted.get("transaction_id")
        )
        receipt.extracted_transaction_status = (
            extracted.get("transaction_status")
        )
        receipt.extracted_payer_name = (
            extracted.get("payer_name")
        )
        receipt.extracted_institution = (
            extracted.get("institution")
        )

        try:
            receipt.ai_confidence = Decimal(
                str(extracted.get("confidence", 0))
            )
        except InvalidOperation:
            receipt.ai_confidence = Decimal("0")

        # ----------------------------------------------------
        # IDENTIFICAR O PEDIDO CORRETO PELO VALOR
        # ----------------------------------------------------

        previous_validation = (
            receipt.validation_json or {}
        )

        candidate_display_ids = (
            previous_validation.get("candidate_orders")
            or []
        )

        order_reassigned = False
        order_match_ambiguous = False

        if (
            receipt.extracted_amount is not None
            and candidate_display_ids
        ):
            tolerance_for_match = (
                rules.pix_amount_tolerance
                or Decimal("0.01")
            )

            candidate_orders = list(
                db.scalars(
                    select(Order)
                    .where(
                        Order.store_id == receipt.store_id,
                        Order.display_id.in_(
                            candidate_display_ids
                        ),
                        Order.payment_method == "PIX",
                    )
                    .order_by(Order.created_at.desc())
                ).all()
            )

            amount_matches = [
                candidate
                for candidate in candidate_orders
                if abs(
                    candidate.total
                    - receipt.extracted_amount
                )
                <= tolerance_for_match
            ]

            if len(amount_matches) == 1:
                matched_order = amount_matches[0]

                if matched_order.id != order.id:
                    order = matched_order
                    receipt.order_id = matched_order.id
                    order_reassigned = True

            elif len(amount_matches) > 1:
                order_match_ambiguous = True

        checks: dict[str, object] = {}
        reasons: list[str] = []

        checks["order_reassigned_by_amount"] = (
            order_reassigned
        )
        checks["order_match_ambiguous"] = (
            order_match_ambiguous
        )

        if order_match_ambiguous:
            reasons.append(
                "ORDER_AMBIGUOUS_BY_AMOUNT"
            )

        checks["is_pix_receipt"] = bool(
            extracted.get("is_pix_receipt")
        )

        if not checks["is_pix_receipt"]:
            reasons.append("NOT_IDENTIFIED_AS_PIX")

        transaction_status_n = _normalize_text(
            extracted.get("transaction_status")
        )

        negative_status_terms = {
            "AGENDADO",
            "AGENDADA",
            "PENDENTE",
            "PROCESSAMENTO",
            "PROCESSANDO",
            "CANCELADO",
            "CANCELADA",
            "RECUSADO",
            "RECUSADA",
            "FALHA",
            "FALHOU",
        }

        explicit_negative_status = any(
            term in transaction_status_n
            for term in negative_status_terms
        )

        has_transaction_id = bool(
            str(
                extracted.get("transaction_id")
                or ""
            ).strip()
        )

        payment_completed = (
            not explicit_negative_status
            and (
                extracted.get("payment_completed") is True
                or (
                    bool(extracted.get("is_pix_receipt"))
                    and has_transaction_id
                )
            )
        )

        checks["payment_completed"] = payment_completed
        checks[
            "explicit_negative_status"
        ] = explicit_negative_status
        checks[
            "transaction_id_present"
        ] = has_transaction_id

        if explicit_negative_status:
            reasons.append(
                "EXPLICIT_NEGATIVE_TRANSACTION_STATUS"
            )

        if not has_transaction_id:
            reasons.append(
                "TRANSACTION_ID_MISSING"
            )

        if not payment_completed:
            reasons.append(
                "PAYMENT_NOT_CLEARLY_COMPLETED"
            )

        # ----------------------------------------------------
        # VALOR
        # ----------------------------------------------------

        tolerance = (
            rules.pix_amount_tolerance
            or Decimal("0.01")
        )

        amount_match = False

        if receipt.extracted_amount is not None:
            amount_match = (
                abs(
                    receipt.extracted_amount
                    - order.total
                )
                <= tolerance
            )

        checks["amount_expected"] = str(order.total)
        checks["amount_extracted"] = (
            str(receipt.extracted_amount)
            if receipt.extracted_amount is not None
            else None
        )
        checks["amount_match"] = amount_match

        if not amount_match:
            reasons.append("AMOUNT_MISMATCH_OR_MISSING")

        # ----------------------------------------------------
        # DESTINATÁRIO
        # ----------------------------------------------------

        name_match = _receiver_name_matches(
            rules.pix_receiver_name,
            receipt.extracted_receiver_name,
        )

        checks["receiver_name_match"] = name_match

        expected_document = _normalize_document(
            rules.pix_receiver_document
        )
        actual_document = _normalize_document(
            receipt.extracted_receiver_document
        )

        document_match = _document_matches(
            expected_document,
            actual_document,
        )

        if document_match is False:
            reasons.append(
                "RECEIVER_DOCUMENT_MISMATCH"
            )

        checks["receiver_document_match"] = document_match

        expected_key = _normalize_key(
            rules.pix_key
        )
        actual_key = _normalize_key(
            receipt.extracted_pix_key
        )

        key_match = None

        if expected_key and actual_key:
            key_match = expected_key == actual_key

            if not key_match:
                reasons.append(
                    "PIX_KEY_MISMATCH"
                )

        checks["pix_key_match"] = key_match

        institution_match = _institution_matches(
            rules.pix_receiver_institution,
            receipt.extracted_institution,
        )

        checks[
            "receiver_institution_match"
        ] = institution_match

        if rules.pix_receiver_institution:
            if institution_match is False:
                reasons.append(
                    "RECEIVER_INSTITUTION_MISMATCH"
                )
            elif institution_match is not True:
                reasons.append(
                    "RECEIVER_INSTITUTION_NOT_CONFIRMED"
                )

        strong_identity_match = (
            document_match is True
            or key_match is True
        )

        # Nome sozinho não é suficiente para confirmação automática.
        # É preciso também bater CPF/CNPJ mascarado/completo ou chave PIX.
        receiver_match = (
            name_match
            and strong_identity_match
        )

        checks["receiver_match"] = receiver_match

        if not receiver_match:
            reasons.append(
                "RECEIVER_NOT_CONFIRMED"
            )

        # ----------------------------------------------------
        # DATA / HORA
        # ----------------------------------------------------

        now = datetime.now(timezone.utc)
        paid_at = receipt.extracted_paid_at

        time_match = False

        if paid_at is not None:
            max_age = timedelta(
                minutes=rules.pix_receipt_max_age_minutes
            )

            earliest_allowed = max(
                now - max_age,
                (
                    order.created_at
                    - timedelta(minutes=60)
                ),
            )

            latest_allowed = (
                now + timedelta(minutes=10)
            )

            time_match = (
                earliest_allowed
                <= paid_at
                <= latest_allowed
            )

        checks["paid_at"] = (
            paid_at.isoformat()
            if paid_at
            else None
        )
        checks["date_time_match"] = time_match

        if not time_match:
            reasons.append(
                "DATE_TIME_OUTSIDE_EXPECTED_WINDOW"
            )

        # ----------------------------------------------------
        # DUPLICIDADE DE ARQUIVO
        # ----------------------------------------------------

        duplicate_file = bool(
            previous_validation.get(
                "duplicate_file"
            )
        )

        checks["duplicate_file"] = duplicate_file

        if duplicate_file:
            reasons.append(
                "DUPLICATE_RECEIPT_FILE"
            )

        # ----------------------------------------------------
        # DUPLICIDADE DE ID / E2E
        # ----------------------------------------------------

        duplicate_transaction = False

        transaction_id = (
            receipt.extracted_transaction_id
            or ""
        ).strip()

        if transaction_id:
            previous = db.scalar(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.store_id
                    == receipt.store_id,
                    PaymentReceipt.id
                    != receipt.id,
                    PaymentReceipt.extracted_transaction_id
                    == transaction_id,
                    PaymentReceipt.status.in_(
                        [
                            "AUTO_CONFIRMED",
                            "HUMAN_CONFIRMED",
                        ]
                    ),
                )
                .limit(1)
            )

            duplicate_transaction = (
                previous is not None
            )

        checks[
            "duplicate_transaction_id"
        ] = duplicate_transaction

        if duplicate_transaction:
            reasons.append(
                "DUPLICATE_TRANSACTION_ID"
            )

        # ----------------------------------------------------
        # CONFIANÇA DA LEITURA
        # ----------------------------------------------------

        confidence = float(
            receipt.ai_confidence or 0
        )

        confidence_ok = (
            confidence
            >= settings.pix_receipt_min_ai_confidence
        )

        checks["ai_confidence"] = confidence
        checks["ai_confidence_ok"] = (
            confidence_ok
        )

        if not confidence_ok:
            reasons.append(
                "LOW_AI_CONFIDENCE"
            )

        # ----------------------------------------------------
        # CONFIGURAÇÃO OFICIAL DA LOJA
        # ----------------------------------------------------

        config_complete = bool(
            rules.pix_receiver_name
            and (
                rules.pix_receiver_document
                or rules.pix_key
            )
        )

        checks[
            "official_pix_configured"
        ] = config_complete

        if not config_complete:
            reasons.append(
                "OFFICIAL_PIX_DATA_NOT_CONFIGURED"
            )

        # ----------------------------------------------------
        # DECISÃO
        # ----------------------------------------------------

        can_auto_confirm = (
            rules.pix_auto_verify_enabled
            and not reasons
        )

        receipt.status = (
            "AUTO_CONFIRMED"
            if can_auto_confirm
            else "NEEDS_REVIEW"
        )

        receipt.validation_json = {
            **previous_validation,
            "extraction": extracted,
            "checks": checks,
            "reasons": reasons,
            "decision": receipt.status,
            "order_display_id": order.display_id,
        }

        db.commit()
        db.refresh(receipt)

        return receipt
