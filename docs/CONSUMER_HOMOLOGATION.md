# Homologação da API Parceiro Consumer

## Objetivo

Esta etapa não adiciona funcionalidades fora do MVP. Ela publica a API Parceiro do SmartFoodIA em HTTPS e valida o fluxo necessário para o primeiro pedido controlado aparecer na fila do Consumer.

Base pública oficial desta homologação:

```text
https://smartfoodia.com.br
```

## Pré-requisitos

- nameservers do domínio `smartfoodia.com.br` propagados e reconhecidos pela Cloudflare;
- DNS público apontando para a VPS;
- portas 80 e 443 liberadas na VPS/firewall;
- Caddy em execução;
- assinatura Premium do Consumer;
- integração Consumer disponível para a loja;
- produtos e complementos com código PDV (`externalCode`);
- `merchantId` real confirmado antes do primeiro pedido de homologação.

## Variáveis

No `.env` de produção:

```text
PUBLIC_DOMAIN=smartfoodia.com.br
PUBLIC_BASE_URL=https://smartfoodia.com.br
ACME_EMAIL=seu-email@dominio.com
```

`ACME_EMAIL` deve ser um e-mail operacional válido, mas não deve ser colocado em documentação pública se for pessoal.

## Subir produção com HTTPS automático

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  up -d --build
```

O Caddy solicita e renova automaticamente o certificado TLS quando o DNS público já aponta corretamente para a VPS.

## Configurar a loja

Use o provisionador oficial:

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner \
  --store-slug old-burguer-87 \
  --merchant-id ID_DO_CONSUMER \
  --merchant-name "Old Burguer 87" \
  --base-url https://smartfoodia.com.br
```

Guarde o token exibido pelo comando. Apenas o hash necessário à validação deve permanecer persistido.

Não utilizar `configure_consumer_integration`; esse script foi aposentado.

## Diagnóstico protegido

```text
GET /api/v1/integrations/consumer/{store_slug}/diagnostics
```

Parâmetro:

```text
base_url=https://smartfoodia.com.br
```

Cabeçalho:

```text
Authorization: Bearer TOKEN
```

O diagnóstico não altera pedidos e informa:

- integração ativa;
- merchant configurado;
- token configurado;
- uso de HTTPS;
- quantidade de eventos pendentes;
- quatro URLs finais.

## Verificação externa

Execute fora do servidor, para confirmar DNS, HTTPS e autenticação:

```bash
python -m app.scripts.verify_consumer_partner \
  --store-slug old-burguer-87 \
  --base-url https://smartfoodia.com.br \
  --token TOKEN
```

O verificador testa:

- endpoint de diagnóstico;
- polling;
- ausência de token;
- token inválido;
- pedido inexistente.

## URLs finais para cadastro no Consumer

```text
Polling:
https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/events

Detalhes:
https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}

Evento ODR:
https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/events

Atualização de status:
https://smartfoodia.com.br/api/v1/integrations/consumer/old-burguer-87/orders/{order_id}/status
```

No Consumer, cadastrar as URLs e o token em:

```text
APPS → Pedidos Online → API do parceiro
```

Depois ativar a fila em:

```text
Principal → Fila de Pedidos
```

## Primeiro pedido controlado

1. Confirmar que DNS e HTTPS estão válidos externamente.
2. Confirmar que o diagnóstico protegido está saudável.
3. Criar um pedido de teste pelo fluxo do SmartFoodIA/Olívia.
4. Exigir confirmação explícita do cliente.
5. Conferir o evento `PLACED / PLC` no polling.
6. Aguardar o Consumer consultar os detalhes.
7. Confirmar que o pedido apareceu na fila do Consumer.
8. Confirmar o pedido no Consumer.
9. Verificar a atualização do status interno.
10. Repetir de forma controlada com cancelamento, pronto, saiu para entrega e conclusão.

## Critério de aprovação deste gate

A homologação só passa para a próxima etapa quando um pedido completo, com itens e códigos PDV válidos, aparecer corretamente na fila do Consumer sem duplicidade e o SmartFoodIA receber ao menos uma atualização de status enviada pelo Consumer.
