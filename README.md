# SmartFoodIA

## Estado atual do projeto

Documentação de referência: **0.3.4**, com homologação operacional atualizada em **2026-08-11**.

A auditoria da VPS mostrou que a aplicação em execução ainda reporta `APP_VERSION=0.3.3`. Essa diferença é conhecida e está documentada; não deve ser confundida com o estado funcional já homologado.

## O que já está homologado

### Infraestrutura

- VPS de produção ativa;
- domínio `smartfoodia.com.br` resolvendo para a VPS;
- Caddy como proxy reverso;
- HTTPS válido;
- PostgreSQL em produção;
- frontend e worker ativos.

### Consumer Partner API

A integração da Old Burguer 87 já foi validada de ponta a ponta para:

- polling;
- consulta de detalhes;
- pedido de retirada entrando no Consumer;
- pedido delivery entrando no Consumer;
- confirmação;
- pronto para retirada;
- despacho / Em Rota;
- conclusão;
- retorno e persistência dos estados no SmartFoodIA.

A homologação real revelou diferenças em relação à documentação anterior, incluindo uso de `xapikey`, callback de status sem UUID no caminho, normalização de status CamelCase e requisitos práticos do payload DELIVERY. Essas diferenças estão registradas em `docs/PRODUCTION_RUNTIME.md` e `docs/CONSUMER_PARTNER_API.md`.

## O que ainda não está ativo em produção

Embora exista no código:

- OpenAI/Olívia ainda não tinha chave configurada na VPS auditada;
- WhatsApp ainda não tinha token, app secret nem `channel_account` configurado;
- o ciclo completo WhatsApp → Olívia → Consumer → WhatsApp ainda precisa ser homologado.

## Gate atual

O projeto já concluiu DNS, HTTPS, configuração Consumer, primeiro pedido e retorno de status para retirada e delivery.

O gate atual é **homologação ampliada**, seguido de produção assistida.

## Atenção antes de novo deploy

A VPS auditada contém hotfixes funcionais do Consumer ainda não consolidados no commit base do GitHub. Um novo deploy não deve ser realizado até revisar e versionar essas diferenças.

Também existe uma não conformidade de segurança: o access log do Caddy foi observado registrando `xapikey` em texto. Isso deve ser corrigido antes do piloto produtivo assistido.

## Documentos principais

- `docs/PROJECT_CONSTITUTION.md`
- `docs/DECISIONS.md`
- `docs/V1_SCOPE.md`
- `docs/ROADMAP.md`
- `docs/PRODUCTION_RUNTIME.md`
- `docs/CONSUMER_PARTNER_API.md`
- `docs/CONSUMER_HOMOLOGATION.md`
