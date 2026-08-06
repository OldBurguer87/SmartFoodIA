# SmartFoodIA

Base oficial do projeto SmartFoodIA.

## Versão atual

`0.0.7 — Checkout & Persistent Orders`

## Requisitos

- Docker Desktop
- Git

## Como executar

1. Copie `.env.example` para `.env`.
2. Troque a senha `change-me` no `.env`.
3. Execute:

```bash
docker compose up --build
```

4. Atualize as tabelas:

```bash
docker compose exec api alembic upgrade head
```

5. Acesse:

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs

## Estado atual

Esta versão contém:

- catálogo e complementos;
- importador Consumer;
- clientes e endereços;
- carrinho persistente;
- checkout;
- entrega e retirada;
- PIX, crédito, débito e dinheiro;
- validação de troco;
- pedido persistente;
- snapshots de dados e preços;
- evento `PLACED / PLC`;
- proteção contra pedido duplicado pelo mesmo carrinho.

Consulte:

```text
docs/CHECKOUT_AND_ORDERS.md
```

A próxima etapa será disponibilizar os endpoints da API de parceiro do Consumer.
