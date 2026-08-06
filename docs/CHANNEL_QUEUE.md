# Fila e retentativas dos canais

O webhook agora apenas valida, deduplica e grava o evento. O processamento da Olívia ocorre fora da requisição HTTP.

Execute uma rodada da fila:

```bash
docker compose exec api python -m app.scripts.process_channel_queue
```

Estados: `RECEIVED`, `RETRY`, `PROCESSED`, `IGNORED` e `DEAD`. As retentativas usam atraso exponencial e param após cinco tentativas. Mensagens de saída também usam `PENDING`, `RETRY`, `SENT` e `DEAD`.
