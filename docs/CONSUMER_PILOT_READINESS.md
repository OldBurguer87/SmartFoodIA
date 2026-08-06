# Preparação do piloto Consumer

## Objetivo

Fechar o ciclo aprovado:

```text
WhatsApp → Olívia → pedido confirmado → Consumer → atualização de status → WhatsApp
```

## Configuração da loja

Execute dentro do container da API:

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner \
  --store-slug old-burguer-87 \
  --merchant-id ID_DO_ESTABELECIMENTO_NO_CONSUMER \
  --merchant-name "Old Burguer 87" \
  --base-url https://seu-dominio-publico.com
```

O comando gera um token seguro e imprime as quatro URLs que devem ser cadastradas no Consumer.

## Atualizações ao cliente

Quando o Consumer enviar um novo status e ele realmente mudar, o SmartFoodIA cria uma mensagem na fila do WhatsApp. Atualizações repetidas são idempotentes e não geram mensagens duplicadas.

Status com mensagem automática:

- `CONFIRMED`;
- `READY`;
- `DISPATCHED`;
- `CONCLUDED`;
- `CANCELLED`.

## Segurança

- apenas o hash do token é armazenado;
- o token em texto aparece uma única vez no comando de configuração;
- cada integração pertence a uma loja;
- todas as rotas exigem `Authorization: Bearer TOKEN`.
