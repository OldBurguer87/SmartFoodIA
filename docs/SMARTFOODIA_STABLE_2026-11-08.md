# SmartFoodIA — Marco Estável 2026-11-08

## 1. Status

Data do marco: 08/11/2026.

O SmartFoodIA encontra-se em operação real há aproximadamente três meses e este documento registra o estado funcional consolidado utilizado como referência para futuras evoluções.

Repositório:

- Projeto: SmartFoodIA
- Diretório de produção: `/root/smartFoodIA`
- Branch de consolidação: `feature/plataforma-multiempresa`
- Commit-base anterior: `6f07e84559d7b23d395ccdd1855321014e3a6d32`
- Data do commit-base: 06/10/2026

Este marco deve representar somente o SmartFoodIA.

SmartToy, SmartToy Migration, SmartToy Licensing, Gestor de Empréstimos e demais projetos hospedados na mesma VPS são projetos independentes e não fazem parte deste marco.

---

## 2. Arquitetura operacional

O SmartFoodIA utiliza uma arquitetura composta por:

- frontend web;
- API backend;
- worker de canais;
- banco de dados;
- proxy HTTPS;
- integração WhatsApp Cloud API;
- integração Consumer;
- camada de IA/Olívia;
- serviços de pedidos, clientes, carrinho e checkout;
- atendimento humano;
- relatórios e fechamento de turno.

A aplicação é multiempresa. Regras, configurações comerciais e dados operacionais devem permanecer vinculados à empresa/loja correta.

Não criar dependências hardcoded específicas da Old Burguer 87 em funcionalidades que pertencem ao núcleo multiempresa.

---

## 3. WhatsApp e Olívia

O WhatsApp é um dos principais canais operacionais do SmartFoodIA.

A Olívia realiza atendimento automatizado e utiliza ferramentas internas para consultar catálogo, cliente, carrinho, pedido, status, checkout e demais dados necessários.

Regras consolidadas:

- o telefone recebido pelo WhatsApp já identifica o cliente e não deve ser solicitado novamente;
- pedidos ambíguos devem ser esclarecidos antes da inclusão no carrinho;
- produtos prontos devem ser priorizados quando correspondem ao pedido;
- apresentação ampla do cardápio prioriza o PDF;
- pedidos explícitos de link utilizam o endereço oficial configurado;
- localização estruturada recebida pelo WhatsApp deve ser reaproveitada;
- informações de pedido finalizado devem ser consultadas no sistema antes de responder;
- problemas operacionais são encaminhados para atendimento humano;
- incidentes críticos recebem escalada urgente.

A Olívia deve responder de forma curta e natural no WhatsApp, evitando respostas excessivamente longas.

---

## 4. Atendimento humano

O sistema possui takeover de conversa para atendimento humano.

O operador pode:

- assumir conversa;
- responder manualmente;
- devolver conversa para a Olívia;
- acompanhar mensagens e mídias;
- lançar pedidos durante o atendimento;
- fechar atendimento humano.

O painel de lançamento de pedido permanece aberto durante atualizações normais da conversa, evitando perda do trabalho do operador.

A timeline acompanha novas mensagens quando o operador está no final da conversa e preserva a posição quando ele está consultando mensagens anteriores.

Há indicação de novas mensagens abaixo quando necessário.

---

## 5. WhatsApp administrativo

O envio de notificações administrativas por WhatsApp pode ser desativado individualmente para membros da equipe.

Quando `notify_whatsapp` está desativado:

- o membro continua reconhecido como integrante da equipe;
- mensagens dele não devem cair acidentalmente no fluxo de cliente/Olívia;
- notificações administrativas deixam de ser encaminhadas para aquele membro.

Essa regra não interfere no atendimento pelo painel web.

---

## 6. Pedidos e carrinho

O fluxo operacional suporta:

- identificação/criação do cliente;
- seleção de produtos;
- adicionais/complementos;
- quantidade;
- observações;
- carrinho;
- retirada;
- entrega;
- pagamento;
- checkout;
- integração operacional.

Complementos opcionais não impedem a inclusão do produto quando as exigências obrigatórias já fazem parte da configuração do item.

No painel humano, o botão `Adicionar item` fica junto à pesquisa de produtos depois que um produto é selecionado.

Isso permite adicionar rapidamente o produto sem precisar percorrer toda a lista de complementos opcionais.

A regra de negócio dos complementos não foi alterada por essa mudança visual.

---

## 7. PIX

O SmartFoodIA possui tratamento específico para PIX.

No fechamento automatizado pela Olívia:

- o checkout precisa ser concluído antes da confirmação do pedido;
- o código PIX correto é enviado deterministicamente pelo sistema;
- a IA não deve inventar código, QR Code ou confirmação;
- o comprovante é tratado separadamente;
- PIX somente é considerado pré-pago após confirmação segura.

Para atendimento humano existe ação rápida:

`Enviar chave PIX`

O botão consulta a configuração comercial da loja e envia somente a chave PIX cadastrada.

A chave não fica hardcoded no frontend.

Se PIX estiver desativado ou sem chave cadastrada, o envio é bloqueado com mensagem de erro.

---

## 8. Comprovantes PIX

O status do comprovante deve ser obtido do sistema.

Estados relevantes incluem situações equivalentes a:

- não recebido;
- recebido/em análise;
- necessidade de revisão;
- confirmado;
- recusado.

A Olívia não deve afirmar que um PIX foi confirmado somente porque o cliente informou que pagou.

`payment_confirmed` e o status persistido do comprovante são a fonte da verdade.

---

## 9. Consumer

A integração Consumer permanece como adaptador externo do SmartFoodIA.

O sistema suporta o envio de pedidos para o fluxo operacional do Consumer e processamento dos respectivos estados.

Princípios consolidados:

- integração externa não deve controlar regras centrais do domínio;
- callbacks devem ser tratados com segurança;
- estados não devem regredir indevidamente;
- TAKEOUT e DELIVERY são tratados pelo fluxo de integração;
- pagamento PIX depende da confirmação apropriada antes da liberação quando aplicável;
- identificadores externos devem ser usados conforme sua finalidade correta.

Códigos de família não devem ser tratados como código PDV vendável quando não representam uma opção real de produto.

---

## 10. Fechamento de turno

Foi implementado fechamento operacional/financeiro por data.

Backend:

`backend/app/services/shift_closing.py`

Endpoint:

`GET /api/v1/operations/stores/{store_id}/shift-closing`

Parâmetro:

`shift_date=YYYY-MM-DD`

Frontend:

`frontend/components/shift-closing-panel.tsx`

O relatório consolida informações como:

- total de pedidos;
- pedidos válidos;
- cancelamentos;
- faturamento;
- ticket médio;
- formas de pagamento;
- informações de PIX;
- dados financeiros do período.

O painel está integrado ao dashboard através da opção `Fechamento de turno`.

---

## 11. Mídias de conversas

O SmartFoodIA suporta arquivos associados às conversas, incluindo imagens e documentos.

Os arquivos operacionais são persistidos em:

`data/conversation-media/`

Esse diretório contém dados reais de produção e está explicitamente excluído do Git.

Mídias de clientes nunca devem ser adicionadas ao repositório.

---

## 12. Frontend operacional

O frontend consolidado inclui melhorias no console de conversas e lançamento de pedidos.

Entre elas:

- identificação do cliente na conversa;
- painel de pedido durante atendimento humano;
- preservação do painel durante refresh;
- acompanhamento inteligente da timeline;
- indicação de novas mensagens;
- envio rápido da chave PIX;
- editor do produto próximo à busca;
- botão `Adicionar item` junto à busca após selecionar o produto;
- fechamento de turno no dashboard.

Mudanças puramente visuais não devem alterar regras de checkout, produtos, complementos ou pagamentos.

---

## 13. Produção

Serviços principais do SmartFoodIA:

- `smartfoodia-web`
- `smartfoodia-api`
- `smartfoodia-worker`
- `smartfoodia-db`
- `smartfoodia-caddy`

Alterações de frontend devem ser compiladas utilizando a URL pública correta da API.

Build de produção:

`NEXT_PUBLIC_API_URL=https://smartfoodia.com.br`

Nunca publicar frontend de produção compilado com `localhost` como API efetiva.

Antes de substituir uma imagem de produção deve existir referência de rollback.

---

## 14. Segurança de versionamento

Nunca versionar:

- `.env`;
- tokens;
- senhas;
- chaves privadas;
- credenciais de API;
- mídias reais de clientes;
- exports operacionais;
- backups locais;
- arquivos temporários.

O `.gitignore` deve proteger esses artefatos.

Não utilizar `git add .` em produção sem inspeção prévia.

Preferir inclusão seletiva de arquivos.

---

## 15. Isolamento da VPS

A VPS hospeda outros projetos.

Regra obrigatória:

Mudanças do SmartFoodIA não podem modificar, reiniciar, interromper ou reconfigurar SmartToy, SmartToy Migration, SmartToy Licensing, Gestor de Empréstimos ou outros serviços independentes.

Arquivos compartilhados ou com alterações de outros projetos devem ser tratados separadamente.

Em especial, alterações existentes em:

- `Caddyfile`;
- `docker-compose.yml`;
- `docker-compose.production.yml`;
- `frontend/components/platform-dashboard.tsx`;

não devem ser incluídas automaticamente no marco SmartFoodIA quando contiverem integração/configuração pertencente a outros projetos.

---

## 16. Git e continuidade

Este marco foi preparado para encerrar o período de alterações acumuladas posteriores ao commit de 06/10/2026.

Procedimento recomendado para futuras alterações:

1. consultar esta documentação;
2. verificar `git status`;
3. identificar exatamente os arquivos envolvidos;
4. fazer backup local quando necessário;
5. alterar somente o projeto correto;
6. executar validações mínimas necessárias;
7. atualizar documentação relevante;
8. revisar `git diff`;
9. fazer `git add` seletivo;
10. criar commit descritivo;
11. preservar referência de rollback quando houver publicação.

---

## 17. Estado do marco

Em 08/11/2026 o SmartFoodIA é considerado uma base operacional estável para continuidade do desenvolvimento.

Este marco não significa encerramento do desenvolvimento.

Significa que novas funcionalidades devem evoluir a partir deste estado documentado e versionado, preservando:

- estabilidade operacional;
- isolamento multiempresa;
- integridade dos pedidos;
- segurança dos pagamentos;
- continuidade das conversas;
- isolamento dos demais projetos da VPS.
