# SmartFoodIA

Base oficial do projeto SmartFoodIA.

## Versão atual

`0.0.6 — Customers & Persistent Cart`

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

4. Crie ou atualize as tabelas:

```bash
docker compose exec api alembic upgrade head
```

5. Acesse:

- API: http://localhost:8000
- Health check: http://localhost:8000/health
- Swagger: http://localhost:8000/docs

## Estado atual

Esta versão contém:

- catálogo e complementos;
- Smart Catalog Engine;
- importador Consumer;
- clientes identificados pelo telefone;
- múltiplos endereços;
- carrinho persistente;
- itens e complementos;
- validação de compatibilidade;
- cálculo de subtotal feito pelo Core;
- APIs para criar, consultar, alterar e limpar o carrinho.

Consulte:

```text
docs/CUSTOMERS_AND_CART.md
```

A próxima etapa será checkout, entrega, pagamento e pedido persistente.
