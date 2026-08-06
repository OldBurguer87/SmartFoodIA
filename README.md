# SmartFoodIA

Base oficial do projeto SmartFoodIA.

## Versão atual

`0.0.8 — Consumer Partner API`

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

- catálogo e importador Consumer;
- clientes, endereços e carrinhos;
- checkout e pedidos persistentes;
- eventos de pedido;
- credenciais Consumer por loja;
- token armazenado somente como hash;
- polling;
- detalhes completos do pedido;
- recebimento de evento ODR;
- atualização de status;
- proteção por loja e token;
- idempotência de atualizações.

Consulte:

```text
docs/CONSUMER_PARTNER_API.md
```

A próxima etapa será criar as ferramentas da Olívia para catálogo, cliente, carrinho e checkout.
