from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import (
    Modifier,
    ModifierGroup,
    ModifierGroupItem,
    Product,
    ProductModifierGroup,
    Store,
)


MANAGED_GROUP_PREFIX = "Consumer::Complementos::"
MAX_MODIFIER_QUANTITY = 20


@dataclass
class ProdconImportReport:
    file_name: str
    store_id: str
    consumer_version: str
    products_in_file: int = 0
    product_details_in_file: int = 0
    complement_products_in_file: int = 0
    compatibility_links_in_file: int = 0
    modifiers_created: int = 0
    modifiers_updated: int = 0
    groups_created: int = 0
    product_group_links_created: int = 0
    group_items_created: int = 0
    products_with_complements: int = 0
    products_not_found: int = 0
    complement_details_not_found: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class ConsumerProdconImportService:
    """Importa complementos e compatibilidades do backup .prodcon do Consumer.

    O arquivo .prodcon é um ZIP que contém ``produtosdata.json``. Para produtos
    simples e variações/tamanhos, o código PDV usado na exportação do Consumer
    corresponde a ``ProdutoDetalhe.CODIGO``. O mesmo vale para os complementos.
    """

    def import_file(
        self,
        db: Session,
        *,
        store_id: UUID,
        file_path: Path,
        report_path: Path | None = None,
    ) -> ProdconImportReport:
        store = db.get(Store, store_id)
        if store is None:
            raise ValueError(f"Loja não encontrada: {store_id}")

        data = self._load_prodcon(file_path)
        products_data = data.get("Produtos") or []
        details_data = data.get("ProdutoDetalhe") or []
        links_data = data.get("ProdutoDetalheComplemento") or []

        version = data.get("VersaoConsumer") or {}
        version_text = ".".join(
            str(version.get(key, 0)) for key in ("Major", "Minor", "Build", "Revision")
        )

        report = ProdconImportReport(
            file_name=file_path.name,
            store_id=str(store_id),
            consumer_version=version_text,
            products_in_file=len(products_data),
            product_details_in_file=len(details_data),
            compatibility_links_in_file=len(links_data),
        )

        product_master_by_code = {
            self._as_int(row.get("CODIGO")): row
            for row in products_data
            if self._as_int(row.get("CODIGO")) is not None
        }
        detail_by_code = {
            self._as_int(row.get("CODIGO")): row
            for row in details_data
            if self._as_int(row.get("CODIGO")) is not None
        }

        complement_master_codes = {
            code
            for code, row in product_master_by_code.items()
            if code is not None and self._as_int(row.get("CODIGOPRODUTOTIPO")) == 3
        }
        report.complement_products_in_file = len(complement_master_codes)

        complement_detail_codes = {
            code
            for code, detail in detail_by_code.items()
            if code is not None
            and self._as_int(detail.get("CODIGOPRODUTO")) in complement_master_codes
            and detail.get("DATADELETE") is None
        }

        current_products = {
            product.external_code: product
            for product in db.scalars(
                select(Product).where(Product.store_id == store_id)
            ).all()
        }
        current_modifiers = {
            modifier.external_code: modifier
            for modifier in db.scalars(
                select(Modifier).where(Modifier.store_id == store_id)
            ).all()
        }

        # Remove somente grupos gerenciados por este importador. Isso torna a
        # sincronização idempotente e não toca em grupos criados manualmente.
        managed_groups = db.scalars(
            select(ModifierGroup).where(
                ModifierGroup.store_id == store_id,
                ModifierGroup.name.startswith(MANAGED_GROUP_PREFIX),
            )
        ).all()
        for group in managed_groups:
            db.delete(group)
        db.flush()

        # Complementos do Consumer são produtos do tipo 3. O código PDV que vai
        # no pedido é o código do ProdutoDetalhe, não o código mestre do produto.
        modifier_by_detail_code: dict[int, Modifier] = {}
        for detail_code in sorted(complement_detail_codes):
            detail = detail_by_code[detail_code]
            master_code = self._as_int(detail.get("CODIGOPRODUTO"))
            master = product_master_by_code.get(master_code)
            if master is None:
                report.complement_details_not_found += 1
                continue

            external_code = str(detail_code)
            modifier = current_modifiers.get(external_code)
            active = (
                str(master.get("DESCONTINUADO") or "N").upper() != "S"
                and detail.get("DATADELETE") is None
                and detail.get("DATAPAUSADO") is None
            )
            price = Decimal(str(detail.get("PRECOVENDA") or 0)).quantize(Decimal("0.01"))
            name = str(master.get("NOME") or "").strip()
            description = str(master.get("DESCRICAO") or "").strip() or None

            if modifier is None:
                modifier = Modifier(
                    store_id=store_id,
                    external_code=external_code,
                    name=name,
                    description=description,
                    price=price,
                    active=active,
                )
                db.add(modifier)
                db.flush()
                current_modifiers[external_code] = modifier
                report.modifiers_created += 1
            else:
                changed = False
                for attribute, value in {
                    "name": name,
                    "description": description,
                    "price": price,
                    "active": active,
                }.items():
                    if getattr(modifier, attribute) != value:
                        setattr(modifier, attribute, value)
                        changed = True
                if changed:
                    report.modifiers_updated += 1

            modifier_by_detail_code[detail_code] = modifier

        compatibilities: dict[int, list[int]] = {}
        for row in links_data:
            parent_code = self._as_int(row.get("CODIGOPRODUTODETALHE"))
            complement_code = self._as_int(
                row.get("CODIGOPRODUTODETALHECOMPLEMENTO")
            )
            if parent_code is None or complement_code is None:
                continue
            compatibilities.setdefault(parent_code, []).append(complement_code)

        for parent_code in sorted(compatibilities):
            product = current_products.get(str(parent_code))
            if product is None:
                report.products_not_found += 1
                continue

            allowed_codes = [
                code
                for code in dict.fromkeys(compatibilities[parent_code])
                if code in modifier_by_detail_code
            ]
            if not allowed_codes:
                continue

            group = ModifierGroup(
                store_id=store_id,
                name=f"{MANAGED_GROUP_PREFIX}{parent_code}",
                description="Complementos cadastrados no Consumer.",
                min_select=0,
                # Não há limite agregado de seleção no .prodcon. O limite abaixo
                # apenas soma o máximo técnico individual aceito pela API da Olívia.
                max_select=len(allowed_codes) * MAX_MODIFIER_QUANTITY,
                allow_repeat=True,
                display_order=0,
                active=True,
            )
            db.add(group)
            db.flush()
            report.groups_created += 1

            db.add(
                ProductModifierGroup(
                    product_id=product.id,
                    modifier_group_id=group.id,
                    display_order=0,
                )
            )
            report.product_group_links_created += 1
            report.products_with_complements += 1

            for display_order, complement_code in enumerate(allowed_codes):
                modifier = modifier_by_detail_code[complement_code]
                db.add(
                    ModifierGroupItem(
                        modifier_group_id=group.id,
                        modifier_id=modifier.id,
                        display_order=display_order,
                        min_quantity=0,
                        max_quantity=MAX_MODIFIER_QUANTITY,
                        default_quantity=0,
                    )
                )
                report.group_items_created += 1

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        if report_path is not None:
            report.save(report_path)

        return report

    @staticmethod
    def _load_prodcon(file_path: Path) -> dict[str, Any]:
        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
        try:
            with zipfile.ZipFile(file_path) as archive:
                raw = archive.read("produtosdata.json")
        except (zipfile.BadZipFile, KeyError) as error:
            raise ValueError(
                "Arquivo .prodcon inválido ou sem produtosdata.json."
            ) from error
        return json.loads(raw.decode("utf-8-sig"))

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
