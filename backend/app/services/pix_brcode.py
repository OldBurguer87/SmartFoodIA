from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata


def _tlv(tag: str, value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) > 99:
        raise ValueError(f"Campo PIX {tag} excede 99 bytes.")
    return f"{tag}{len(encoded):02d}{value}"


def _ascii_text(value: str, *, max_length: int) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.upper()
    normalized = re.sub(r"[^A-Z0-9 .\-/]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:max_length]


def _crc16_ccitt(value: str) -> str:
    crc = 0xFFFF

    for byte in value.encode("utf-8"):
        crc ^= byte << 8

        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    return f"{crc:04X}"


def build_pix_copy_paste(
    *,
    pix_key: str,
    merchant_name: str,
    merchant_city: str,
    amount,
    txid: str,
) -> str:
    key = str(pix_key or "").strip()
    if not key:
        raise ValueError("Chave PIX não cadastrada.")

    value = Decimal(str(amount)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if value <= 0:
        raise ValueError("Valor PIX deve ser maior que zero.")

    name = _ascii_text(
        merchant_name or "LOJA",
        max_length=25,
    ) or "LOJA"

    city = _ascii_text(
        merchant_city or "COARI",
        max_length=15,
    ) or "COARI"

    clean_txid = re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(txid or ""),
    ).upper()[:25]

    if not clean_txid:
        clean_txid = "***"

    merchant_account = (
        _tlv("00", "BR.GOV.BCB.PIX")
        + _tlv("01", key)
    )

    additional_data = _tlv(
        "05",
        clean_txid,
    )

    payload = "".join(
        [
            _tlv("00", "01"),
            _tlv("26", merchant_account),
            _tlv("52", "0000"),
            _tlv("53", "986"),
            _tlv("54", f"{value:.2f}"),
            _tlv("58", "BR"),
            _tlv("59", name),
            _tlv("60", city),
            _tlv("62", additional_data),
            "6304",
        ]
    )

    return payload + _crc16_ccitt(payload)
