# SmartFoodIA

Base oficial do projeto SmartFoodIA.

## Versão atual

`0.0.5 — Consumer Catalog Importer`

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

## Importador do Consumer

O SmartFoodIA agora importa a planilha `.xlsx` exportada pelo Consumer.

Consulte:

```text
docs/IMPORT_CONSUMER_CATALOG.md
```

O arquivo real do cardápio não deve ser enviado ao GitHub público.

## Estado atual

Esta versão contém:

- FastAPI;
- PostgreSQL;
- Docker Compose;
- SQLAlchemy e Alembic;
- empresas, lojas, categorias e produtos;
- grupos e complementos;
- Smart Catalog Engine;
- importador idempotente da planilha Consumer;
- relatório de códigos PDV inválidos ou conflitantes.

A próxima etapa será criar clientes, endereços e o carrinho persistente.
