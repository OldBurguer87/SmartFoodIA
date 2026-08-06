# SmartFoodIA

## Versão atual

`0.2.0 — First Web Operational Dashboard`

Esta versão entrega a primeira funcionalidade visual do SmartFoodIA:

- painel web responsivo;
- visão de conversas, pedidos, receita e tickets;
- saúde da IA e das filas;
- lacunas de conhecimento;
- alertas operacionais;
- integração direta com a API existente;
- serviço web no Docker Compose;
- CORS configurável.

## Iniciar

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

Acesse:

```text
http://localhost:3000
```

Consulte `docs/WEB_DASHBOARD.md`.
