# SmartFoodIA

Base inicial oficial do projeto SmartFoodIA.

## Requisitos

- Docker Desktop
- Git

## Como executar

1. Copie `.env.example` para `.env`.
2. Ajuste as senhas no `.env`.
3. Execute:

```bash
docker compose up --build
```

4. Acesse:

- API: http://localhost:8000
- Health check: http://localhost:8000/health
- Swagger: http://localhost:8000/docs

## Resposta esperada

```json
{
  "application": "SmartFoodIA",
  "version": "0.0.1",
  "status": "online"
}
```

## Estado atual

Esta versão contém apenas a infraestrutura inicial:

- FastAPI
- PostgreSQL
- Docker Compose
- Configuração por ambiente
- Endpoint de saúde
- Testes básicos

Ainda não contém catálogo, carrinho, Olívia ou integração com Consumer.
