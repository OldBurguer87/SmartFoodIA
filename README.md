# SmartFoodIA

Base oficial do projeto SmartFoodIA.

## Versão atual

`0.0.4 — Smart Catalog Engine`

## Executar

1. Copie `.env.example` para `.env`.
2. Troque a senha `change-me`.
3. Execute:

```bash
docker compose up --build
```

4. Crie ou atualize as tabelas:

```bash
docker compose exec api alembic upgrade head
```

5. Acesse:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Saúde: `http://localhost:8000/health`

## Catálogo

- `GET /api/v1/products?store_id=<uuid>`
- `GET /api/v1/products/search?store_id=<uuid>&q=monster`
- `GET /api/v1/products/{external_code}?store_id=<uuid>`

O retorno de produto inclui categoria, disponibilidade, grupos de complementos e complementos permitidos.

## Testes

```bash
docker compose exec api pytest -q
```

A próxima versão implementará o importador do arquivo exportado pelo Consumer e a carga inicial da Old Burguer 87.
