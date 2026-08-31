from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.catalog import Store
from app.models.commercial import StoreDeliveryPlace


COARI_DELIVERY_PLACES = [
    {
        "place_type": "HOTEL",
        "name": "Hotel São Francisco",
        "aliases": [
            "São Francisco",
            "Sao Francisco",
            "Hotel Sao Francisco",
        ],
        "street": "Rua 15 de Novembro",
        "number": "239",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Hotel MF5 Center",
        "aliases": [
            "MF5",
            "MF 5",
            "M F5",
            "Hotel MF5",
            "MF5 Center",
        ],
        "street": "Rua Independência",
        "number": "389",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Hotel Beija Flor",
        "aliases": [
            "Beija Flor",
            "Hotel Beija Flor",
        ],
        "street": "Praça Getúlio Vargas",
        "number": "146",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Hagia Sophia Hotel",
        "aliases": [
            "Hagia Sophia",
            "Hotel Hagia Sophia",
            "Hagia",
        ],
        "street": "Rua Independência",
        "number": "141",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Conquista Flat Hotel",
        "aliases": [
            "Conquista Flat",
            "Hotel Conquista Flat",
            "Conquista",
        ],
        "street": "Praça Getúlio Vargas",
        "number": "168",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Hotel CP Flat 2",
        "aliases": [
            "CP Flat 2",
            "Hotel CP Flat 2",
            "CP Flat II",
        ],
        "street": "Rua Cinco de Setembro",
        "number": "196",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Hotel El Shaday",
        "aliases": [
            "El Shaday",
            "Hotel El Shaday",
            "Elshaday",
        ],
        "street": "Rua Dois de Agosto",
        "number": "521",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Uruçu Plaza Hotel",
        "aliases": [
            "Uruçu Plaza",
            "Urucu Plaza",
            "Hotel Uruçu Plaza",
            "Hotel Urucu Plaza",
        ],
        "street": "Praça Getúlio Vargas",
        "number": "72",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Hotel LH Centro",
        "aliases": [
            "LH Centro",
            "Hotel LH",
            "LH Hotel",
        ],
        "street": "Rua Cinco de Setembro",
        "number": "113",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Ideal Hotel",
        "aliases": [
            "Hotel Ideal",
            "Ideal Hotel",
        ],
        "street": "Rua Independência",
        "number": "71",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Hotel Regional II",
        "aliases": [
            "Regional II",
            "Regional 2",
            "Hotel Regional 2",
        ],
        "street": "Rua Independência",
        "number": "168",
        "neighborhood": "Centro",
    },
    {
        "place_type": "HOTEL",
        "name": "Santorini Hotel",
        "aliases": [
            "Santorini",
            "Hotel Santorini",
        ],
        "street": "Rua Quinze de Novembro",
        "number": "213",
        "neighborhood": "Centro",
    },
    {
        "place_type": "POUSADA",
        "name": "Sol Amigo Pousada",
        "aliases": [
            "Sol Amigo",
            "Pousada Sol Amigo",
            "Solamigo",
        ],
        "street": "Rua Dorival dos Santos",
        "number": "102",
        "neighborhood": "Santa Efigênia",
    },
]


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


def seed_store_places(
    db: Session,
    store: Store,
) -> tuple[int, int]:
    created = 0
    updated = 0

    for item in COARI_DELIVERY_PLACES:
        normalized_name = normalize(item["name"])

        place = db.scalar(
            select(StoreDeliveryPlace).where(
                StoreDeliveryPlace.store_id == store.id,
                StoreDeliveryPlace.normalized_name
                == normalized_name,
            )
        )

        values = {
            **item,
            "normalized_name": normalized_name,
            "city": "Coari",
            "state": "AM",
            "postal_code": "69460-000",
            "reference": item["name"],
            "active": True,
        }

        if place is None:
            db.add(
                StoreDeliveryPlace(
                    store_id=store.id,
                    **values,
                )
            )
            created += 1
            continue

        for key, value in values.items():
            setattr(place, key, value)

        updated += 1

    db.commit()
    return created, updated


def main() -> None:
    with SessionLocal() as db:
        store = db.scalar(
            select(Store).where(
                Store.slug == "old-burguer-87"
            )
        )

        if store is None:
            raise RuntimeError(
                "Loja old-burguer-87 não encontrada."
            )

        created, updated = seed_store_places(
            db,
            store,
        )

        print(
            f"Locais: {created} criados, "
            f"{updated} atualizados."
        )


if __name__ == "__main__":
    main()
