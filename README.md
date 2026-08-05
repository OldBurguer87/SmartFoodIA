# SmartFoodIA

## Versão atual

`0.0.3 — Catálogo: grupos, complementos e compatibilidade`

## Como executar

1. Copie `.env.example` para `.env`.
2. Troque a senha `change-me` no `.env`.
3. Execute:

```bash
docker compose up --build
```

4. Aplique as migrations:

```bash
docker compose exec api alembic upgrade head
```

5. Acesse o Swagger em `http://localhost:8000/docs`.

## Recursos presentes

- empresas e lojas;
- categorias e produtos;
- grupos de complementos;
- complementos com código PDV;
- ligação produto × grupo;
- ligação grupo × complemento;
- mínimo, máximo, repetição e quantidade padrão;
- API inicial de consulta e cadastro;
- validações de domínio e banco.

## Próxima etapa

Importador do cardápio exportado pelo Consumer e validação idempotente de códigos PDV.
