# Estado real de produção

Última auditoria operacional: **2026-08-11**.

Este documento registra o que estava efetivamente executando na VPS e o que já foi homologado na prática. Ele não substitui a Constituição nem o Roadmap; serve para separar três conceitos que não devem ser confundidos:

1. **implementado no código**;
2. **configurado na produção**;
3. **homologado em operação real**.

## Snapshot da VPS

- branch: `main`;
- commit base: `1a912a74999ef18fb42eadbfece8354c007d4533`;
- ambiente: `production`;
- domínio público: `smartfoodia.com.br`;
- HTTPS ativo via Caddy;
- PostgreSQL 17;
- Python 3.12;
- frontend Next.js 16 / React 19;
- migrations Alembic em `0008 (head)`.

A API em execução reportava `APP_VERSION=0.3.3`, embora a documentação e os manifests do repositório estivessem em `0.3.4`. Até a versão de runtime ser sincronizada, esta diferença deve permanecer explícita.

## Serviços ativos

- `smartfoodia-api`: ativo e saudável;
- `smartfoodia-worker`: ativo;
- `smartfoodia-web`: ativo;
- `smartfoodia-db`: ativo e saudável;
- `smartfoodia-caddy`: ativo.

## Consumer

Estado: **configurado e homologado** para a Old Burguer 87.

Foram homologados de ponta a ponta:

### Retirada

- polling;
- consulta de detalhes;
- entrada do pedido no Consumer;
- `Confirmed`;
- `ReadyToPickup`;
- `Concluded`;
- persistência dos eventos e estados internos.

### Delivery

- polling;
- consulta de detalhes;
- entrada do pedido no Consumer;
- `Confirmed`;
- `Em Rota` / despacho;
- `Concluded`;
- persistência dos eventos e estados internos.

### Autenticação observada

O Consumer real envia o token no header:

```text
xapikey: TOKEN
```

O backend também aceita `Authorization: Bearer TOKEN` por compatibilidade.

### Callback de status observado

A URL utilizada pelo Consumer homologado é:

```text
POST /api/v1/integrations/consumer/{store_slug}/orders/status
```

O `OrderId` vem no corpo JSON. A rota antiga com UUID no caminho continua disponível como compatibilidade:

```text
POST /api/v1/integrations/consumer/{store_slug}/orders/{order_id}/status
```

### Consulta de detalhes

O Consumer consulta:

```text
GET /api/v1/integrations/consumer/{store_slug}/orders/{order_id}
```

No runtime homologado, essa consulta marca o `PLC / PLACED` pendente como entregue. O endpoint ODR continua disponível, porém o fluxo real homologado não deve depender exclusivamente do recebimento de ODR.

### Compatibilidade de detalhes

O runtime possui também:

```text
POST /api/v1/integrations/consumer/{store_slug}/orders/details
```

Essa rota foi adicionada como compatibilidade operacional e ainda precisa ser consolidada no código versionado antes de um novo deploy substituir a imagem atual.

### Normalização de status

A produção normaliza diferenças de maiúsculas, hífens, espaços, underscores e nomes compactos.

Mapeamentos homologados/aceitos:

- `Confirmed` → `CONFIRMED`;
- `ReadyToPickup` / `READY_TO_PICKUP` → `READY`;
- `ReadyForPickup` / `READY_FOR_PICKUP` → `READY`;
- `Dispatched` → `DISPATCHED`;
- `OutForDelivery` / `OUT_FOR_DELIVERY` → `DISPATCHED`;
- `Concluded` → `CONCLUDED`;
- `Delivered` → `CONCLUDED`;
- `Cancelled` → `CANCELLED`.

### Payload DELIVERY homologado

O payload que passou a ser aceito pelo Consumer contém:

- `deliveredBy: "Partner"`;
- `formattedAddress`;
- `coordinates.latitude`;
- `coordinates.longitude`;
- `delivery.observations`.

Durante a homologação, a entrada do pedido DELIVERY passou a funcionar após a inclusão conjunta desses campos. Não foi feito teste isolado para afirmar qual deles é individualmente obrigatório. Portanto, esse conjunto deve ser tratado como **baseline homologado** e não deve ser reduzido sem nova homologação A/B.

## Hotfixes ainda não versionados no commit base

Na auditoria de 2026-08-11, os seguintes arquivos estavam modificados localmente na VPS e em uso pela API:

- `backend/app/api/consumer_partner.py`;
- `backend/app/integrations/consumer/adapter.py`;
- `backend/app/integrations/consumer/mapper.py`;
- `backend/app/integrations/consumer/status.py`.

Essas diferenças incluem o comportamento homologado descrito acima. Um novo deploy feito somente a partir do commit base pode removê-las. Antes do próximo deploy, os hotfixes devem ser revisados, testados e versionados.

## OpenAI / Olívia

Estado do código: **implementado**.

Estado da produção auditada:

- `OPENAI_CONFIGURED = False`;
- modelo configurado no ambiente: `gpt-5.5`;
- não havia `OPENAI_API_KEY` ativa na VPS.

Portanto, a integração OpenAI existe no projeto, mas **não estava operacional na produção auditada**.

## WhatsApp

Estado do código: **implementado**.

Estado da produção auditada:

- `WHATSAPP_TOKEN_CONFIGURED = False`;
- `WHATSAPP_APP_SECRET_CONFIGURED = False`;
- nenhuma conta em `channel_accounts`;
- worker de canais em execução.

Portanto, o WhatsApp ainda não estava configurado para tráfego real. O ciclo Consumer → SmartFoodIA foi homologado, mas a notificação final ao cliente pelo WhatsApp ainda depende da configuração do canal.

## Catálogo

O importador Consumer vigente também desativa produtos que existiam no SmartFoodIA e desapareceram da nova planilha, desde que exista ao menos uma linha válida importada. Códigos associados a erros/conflitos são protegidos contra desativação acidental.

## Exposição pública atual

Via Caddy estão publicados para o backend:

- `/api/*`;
- `/live`;
- `/ready`.

As rotas internas `/health` e `/version` existem na FastAPI, mas no domínio público raiz são encaminhadas ao frontend e retornam `404`. Para diagnóstico externo atual, usar `/ready` e os endpoints sob `/api/...`.

## Não conformidade de segurança aberta

A Constituição do projeto determina que logs não exponham tokens ou dados sensíveis. Durante a homologação, o access log JSON do Caddy registrou o header `xapikey` em texto.

Esse comportamento deve ser tratado como **bloqueador de segurança antes do piloto produtivo assistido**. Até a correção, logs que contenham esse header devem ser tratados como sensíveis e não devem ser compartilhados publicamente.

## Gate atual

Situação em 2026-08-11:

- Gate A — DNS público: **concluído**;
- Gate B — HTTPS público: **concluído**;
- Gate C — diagnóstico API Parceiro: **concluído**;
- Gate D — configuração no Consumer: **concluído**;
- Gate E — primeiro pedido controlado: **concluído**;
- Gate F — retorno de status: **concluído para retirada e delivery**;
- Gate G — homologação ampliada: **em andamento**;
- Gate H — produção assistida: **pendente**.
