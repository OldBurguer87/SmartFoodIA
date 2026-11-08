# Fechamento de Turno e WhatsApp Administrativo

**Data da implantação:** 13/10/2026
**Projeto:** SmartFoodIA
**Loja validada:** Old Burguer 87
**Ambiente:** Produção

## 1. Objetivo

Esta implantação teve dois objetivos independentes e complementares:

1. disponibilizar no painel web do SmartFoodIA um fechamento de turno consultável por data;
2. interromper o envio de mensagens administrativas do SmartFoodIA para o WhatsApp da atendente, mantendo normalmente o atendimento dos clientes pela Olívia e as funcionalidades administrativas do site.

O fechamento de turno no site não depende do envio do relatório pelo WhatsApp.

---

## 2. Fechamento de turno no painel

Foi criado um relatório histórico de fechamento de turno acessível pelo painel da loja.

O relatório permite selecionar a data do turno e apresenta:

- faturamento;
- ticket médio;
- pedidos válidos;
- pedidos cancelados;
- total recebido;
- diferença de conferência;
- valores e quantidade por forma de pagamento;
- quantidade e valor de pedidos PIX;
- PIX confirmados;
- valor PIX confirmado;
- confirmações automáticas;
- confirmações realizadas pela equipe;
- PIX pendentes de revisão;
- pedidos PIX sem comprovante;
- distribuição dos pedidos por status.

### Regra do turno

O intervalo é calculado a partir de `StoreBusinessHours` e do timezone configurado na loja.

Turnos que atravessam a meia-noite são tratados como um único turno comercial.

### Regra dos pedidos

Pedidos com status `CANCELLED` não entram no faturamento.

Os demais pedidos encontrados dentro do intervalo do turno são considerados válidos para o fechamento.

### Pagamentos

O relatório utiliza os pagamentos persistidos do pedido e mantém compatibilidade com o fallback legado através de `payment_parts_from_order`.

A conferência compara:

- faturamento dos pedidos válidos;
- soma das formas de pagamento.

A diferença é disponibilizada pelo campo `difference`.

### PIX

A conferência PIX considera comprovantes associados aos pedidos.

Estados confirmados:

- `AUTO_CONFIRMED`
- `HUMAN_CONFIRMED`

Estado pendente:

- `NEEDS_REVIEW`

Quando um comprovante confirmado não possui valor extraído, o valor PIX do próprio pedido é utilizado como fallback e contabilizado em `fallback_values`.

Existe tolerância de 5 minutos após o encerramento do turno para considerar comprovantes recebidos.

---

## 3. Endpoint

Endpoint criado:

`GET /api/v1/operations/stores/{store_id}/shift-closing?shift_date=YYYY-MM-DD`

O endpoint utiliza `require_store_access`, preservando o controle de acesso da loja.

Arquivos principais:

- `backend/app/services/shift_closing.py`
- `backend/app/api/analytics.py`

---

## 4. Interface web

Foi criado:

- `frontend/components/shift-closing-panel.tsx`

E modificados:

- `frontend/components/dashboard.tsx`
- `frontend/lib/api.ts`
- `frontend/app/globals.css`

O painel possui a opção **Fechamento de turno** e permite consultar datas anteriores.

O layout possui regras específicas `shiftClosing*` para evitar compressão dos valores e descrições.

---

## 5. Validação do fechamento

Foi realizada validação com dados reais da Old Burguer 87.

Para o turno de 10/10/2026 foram obtidos:

- 8 pedidos;
- 8 pedidos válidos;
- 0 cancelados;
- faturamento de R$ 262,80;
- ticket médio de R$ 32,85;
- total de pagamentos de R$ 262,80;
- diferença de R$ 0,00;
- PIX: 4 pedidos / R$ 120,00;
- dinheiro: 3 pedidos / R$ 80,00;
- débito: 1 pedido / R$ 62,80;
- 4 PIX confirmados;
- 0 PIX pendentes;
- 0 PIX sem comprovante.

A conferência financeira fechou sem diferença.

---

## 6. Deploy do frontend

Imagem de rollback preservada:

`smartfoodia-web:rollback-before-shift-closing-20261012`

Imagem inicial do recurso:

`smartfoodia-web:shift-closing-20261012`

Imagem final com correção de layout:

`smartfoodia-web:shift-layout-fix-20261012`

SHA256 da imagem final:

`719100f95fb5b69a6026dd6805c7fc8b88f94e66a64a60becd59f4404db43993`

A imagem final foi promovida para `smartfoodia-web:latest`.

O deploy foi realizado exclusivamente no serviço `web`, sem reiniciar API, worker, banco ou Caddy naquele momento.

---

## 7. Desativação do WhatsApp administrativo

Em 13/10/2026 foi desativado o envio administrativo de WhatsApp para o cadastro:

- Nome: `Atendente`
- Número: `5597984053985`

Estado configurado:

`notify_whatsapp = False`

O cadastro permanece:

`active = True`

Portanto, a atendente continua existindo no sistema; somente sua participação no canal administrativo de WhatsApp foi desativada.

---

## 8. Proteção dos envios administrativos

Os fluxos que selecionam destinatários através de `notify_whatsapp=True` deixam de selecionar a atendente desativada.

Entre os fluxos auditados estão:

- notificações de takeover/ASSUMIR;
- timeout de atendimento;
- escalonamentos;
- revisão de comprovante PIX;
- fechamento PIX enviado pelo WhatsApp.

Também foi alterado:

`backend/app/repositories/staff.py`

O método que encontra o atendente responsável por uma conversa passou a exigir:

`StoreStaffMember.notify_whatsapp.is_(True)`

Isso impede encaminhamento de novas mensagens/mídias de clientes para um atendente cujo WhatsApp administrativo esteja desativado.

---

## 9. Proteção contra mensagem recebida da atendente

O método `get_by_phone()` foi intencionalmente mantido capaz de reconhecer o número como membro da equipe.

Isso é uma proteção importante.

Se o cadastro deixasse de ser reconhecido como staff, uma mensagem enviada pela atendente poderia ser interpretada como mensagem de cliente e cair no fluxo da Olívia.

Por isso foi adicionada proteção em:

`backend/app/channels/whatsapp/service.py`

Depois da identificação do remetente como staff:

- se `notify_whatsapp=True`, o fluxo administrativo continua normalmente;
- se `notify_whatsapp=False`, o evento recebe status `IGNORED`;
- nenhum comando administrativo é executado;
- nenhuma resposta administrativa é gerada;
- a mensagem não segue para o fluxo de cliente/Olívia.

Mensagem interna registrada:

`WhatsApp administrativo desativado para este membro da equipe.`

---

## 10. O que NÃO foi desativado

Esta alteração não desativa o WhatsApp da loja.

Continuam funcionando normalmente:

- mensagens da Olívia para clientes;
- mensagens recebidas de clientes;
- catálogo/cardápio;
- carrinho;
- checkout;
- pedidos;
- PIX do cliente;
- integração Consumer;
- atualizações de pedido;
- atendimento automático;
- painel web;
- fechamento de turno no site.

A desativação é específica para o WhatsApp administrativo do membro da equipe configurado com `notify_whatsapp=False`.

Não deve ser criado bloqueio global em `ChannelRepository.create_outbound`, na conta WhatsApp ou no worker para implementar esta regra.

---

## 11. Validação em produção

Após a alteração foi confirmado:

- `Ativo = True`
- `notify_whatsapp = False`
- `current_conversation_id = None`
- mensagens `PENDING` para `5597984053985` = 0
- mensagens `RETRY` para `5597984053985` = 0

A última mensagem encontrada para o número estava em estado `DELIVERED`, portanto não havia mensagem antiga aguardando envio.

A sintaxe dos arquivos alterados foi validada com `py_compile`.

A API utiliza:

`uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

O reload automático foi confirmado após alterações em:

- `app/repositories/staff.py`
- `app/channels/whatsapp/service.py`

O worker utiliza:

`python -m app.scripts.run_channel_worker`

Como o worker não possui reload automático, somente o container `smartfoodia-worker` foi reiniciado.

Após o reinício foi confirmado:

`Worker de canais iniciado.`

API, web, banco e Caddy permaneceram em execução.

---

## 12. Backups relacionados

Backups do fechamento:

- `backend/app/api/analytics.py.pre-shift-closing-20261011`
- `backend/app/services/shift_closing.py.pre-financial-20261011`
- `frontend/lib/api.ts.pre-shift-closing-20261011`
- `frontend/components/dashboard.tsx.pre-shift-closing-20261011`
- `frontend/components/shift-closing-panel.tsx.pre-layout-fix-20261012`
- `frontend/app/globals.css.pre-shift-closing-20261011`
- `frontend/app/globals.css.pre-shift-layout-fix-20261012`

Backups do WhatsApp administrativo:

- `backend/app/repositories/staff.py.pre-disable-staff-whatsapp-20261013`
- `backend/app/channels/whatsapp/service.py.pre-disable-staff-whatsapp-20261013`

---

## 13. Reativação futura do WhatsApp administrativo

A reativação normal deve ser feita através da configuração do membro da equipe, restaurando:

`notify_whatsapp = True`

Não é necessário remover a proteção adicionada ao gateway.

A proteção foi desenvolvida para respeitar dinamicamente o valor de `notify_whatsapp`.

Depois da reativação, devem ser validados:

1. cadastro ativo;
2. `notify_whatsapp=True`;
3. ausência de mensagens antigas indevidas na fila;
4. recebimento de uma notificação administrativa controlada;
5. comportamento dos comandos administrativos.

---

## 14. Regra operacional definitiva

O SmartFoodIA deve separar:

**Canal do cliente**
- Olívia;
- pedidos;
- status;
- cardápio;
- checkout;
- mensagens operacionais do pedido.

**Canal administrativo da equipe**
- takeover;
- alertas;
- revisão PIX;
- relatórios/notificações internas.

A propriedade `notify_whatsapp` controla a participação do membro da equipe no segundo grupo e nunca deve transformar esse membro em cliente da Olívia.

O fechamento de turno permanece disponível no painel independentemente dessa configuração.
