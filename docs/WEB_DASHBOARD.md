# Painel web operacional

## Tecnologia

- Next.js 16 com App Router;
- React 19;
- TypeScript;
- CSS próprio, sem biblioteca visual externa;
- frontend separado do backend.

O App Router é a arquitetura moderna recomendada na documentação do Next.js.

## Executar

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

Acessos:

```text
Painel:  http://localhost:3000
API:     http://localhost:8000
Swagger: http://localhost:8000/docs
```

## Primeiro acesso

No painel, cole o UUID da loja Old Burguer 87.

O navegador guarda esse UUID localmente. Nenhuma credencial ou chave de API é
armazenada no frontend.

## Dados exibidos

- conversas ativas;
- atendimentos humanos;
- pedidos e receita;
- tickets e urgências;
- saúde da IA;
- estado das filas;
- lacunas de conhecimento;
- alertas operacionais.

## Integração

O frontend consulta:

```text
GET /api/v1/operations/stores/{store_id}/overview
```

O backend permite requisições do endereço configurado em:

```text
FRONTEND_ORIGIN=http://localhost:3000
```
