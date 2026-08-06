# SmartFoodIA

Base oficial do projeto SmartFoodIA.

## Versão atual

`0.1.0 — Conversations, Support & Knowledge Gaps`

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

- catálogo, clientes, carrinho e pedidos;
- API de parceiro do Consumer;
- ferramentas seguras da Olívia;
- conversas persistentes;
- histórico de mensagens;
- tickets humanos;
- lacunas de conhecimento;
- contagem de perguntas repetidas;
- resolução de lacunas;
- eventos técnicos da IA;
- escalação humana persistida.

Consulte:

```text
docs/CONVERSATIONS_AND_SUPPORT.md
```

A próxima etapa será integrar o primeiro provedor de IA à camada de ferramentas.
