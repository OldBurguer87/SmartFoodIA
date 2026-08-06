# Worker contínuo e verificação de prontidão

## Worker

O `docker compose` agora inicia um serviço separado:

```text
smartfoodia-worker
```

Ele processa continuamente:

- eventos recebidos do WhatsApp;
- respostas pendentes;
- retentativas;
- mensagens que atingiram o limite de falhas.

Configurações:

```text
CHANNEL_WORKER_POLL_SECONDS=2
CHANNEL_WORKER_BATCH_SIZE=50
CHANNEL_WORKER_MAX_ATTEMPTS=5
```

## Saúde da aplicação

### Liveness

```text
GET /live
```

Confirma que o processo da API está funcionando.

### Readiness

```text
GET /ready
```

Confirma que a API consegue consultar o banco.

O container da API usa `/ready` no healthcheck. O worker só inicia depois que a API e o banco estiverem prontos.

## Inicialização

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

Para acompanhar:

```bash
docker compose logs -f api worker
```
