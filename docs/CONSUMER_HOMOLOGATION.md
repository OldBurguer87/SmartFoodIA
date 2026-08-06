# Homologação da API Parceiro Consumer

## Objetivo

Esta etapa não adiciona funcionalidades fora do MVP. Ela prepara o ambiente
público HTTPS e valida os quatro endpoints usados pelo Consumer.

## Pré-requisitos

- domínio público apontando para o servidor;
- portas 80 e 443 liberadas;
- assinatura Premium do Consumer;
- integração Consumer cadastrada para a loja;
- produtos e complementos com código PDV (`externalCode`).

## Variáveis

No `.env`:

```text
PUBLIC_DOMAIN=api.seudominio.com
PUBLIC_BASE_URL=https://api.seudominio.com
ACME_EMAIL=seu-email@dominio.com
```

## Subir produção com HTTPS automático

```bash
docker compose   -f docker-compose.yml   -f docker-compose.production.yml   up -d --build
```

O Caddy solicita e renova automaticamente o certificado TLS.

## Configurar a loja

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner   --store-slug old-burguer-87   --merchant-id ID_DO_CONSUMER   --merchant-name "Old Burguer 87"   --base-url https://api.seudominio.com
```

Guarde o token exibido. Apenas o hash fica no banco.

## Diagnóstico protegido

```text
GET /api/v1/integrations/consumer/{store_slug}/diagnostics
```

Parâmetro:

```text
base_url=https://api.seudominio.com
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
python -m app.scripts.verify_consumer_partner   --store-slug old-burguer-87   --base-url https://api.seudominio.com   --token TOKEN
```

O verificador testa:

- endpoint de diagnóstico;
- polling;
- ausência de token;
- token inválido;
- pedido inexistente.

## Cadastro no Consumer

Cadastrar:

```text
Polling:          /events
Detalhes:         /orders/{order_id}
Evento ODR:       /orders/{order_id}/events
Atualização:      /orders/{order_id}/status
```

Depois ativar a fila em:

```text
Principal → Fila de Pedidos
```

## Primeiro pedido controlado

1. Criar um pedido de teste pela Olívia.
2. Confirmar explicitamente.
3. Conferir o evento `PLACED / PLC` no polling.
4. Aguardar o Consumer consultar os detalhes.
5. Confirmar o pedido no Consumer.
6. Verificar o status interno e a mensagem na fila do WhatsApp.
7. Repetir com `DISPATCHED`, `CONCLUDED` e um cancelamento controlado.
