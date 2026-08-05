# Constituição do Projeto SmartFoodIA

Versão: 1.0  
Status: Aprovada  
Primeiro cliente piloto: Old Burguer 87  
Primeira atendente virtual: Olívia  
Primeira integração ERP/PDV: Consumer

## 1. Propósito

O SmartFoodIA existe para transformar conversas em pedidos corretos, reduzir trabalho operacional e gerar informações confiáveis para o crescimento de restaurantes.

## 2. Objetivo da versão 1.0

A versão 1.0 será considerada concluída quando este fluxo funcionar de ponta a ponta:

1. O cliente conversa com a Olívia pelo WhatsApp.
2. A Olívia consulta o catálogo real.
3. A Olívia entende o pedido, adicionais e observações.
4. O Smart Core valida produtos, preços, quantidades e compatibilidades.
5. O cliente confirma entrega ou retirada, endereço e pagamento.
6. O pedido é criado no SmartFoodIA.
7. O pedido é disponibilizado ao Consumer pela API de parceiro.
8. O Consumer recebe o pedido na fila.
9. O SmartFoodIA recebe atualizações de status.
10. O cliente recebe as atualizações pelo WhatsApp.

## 3. Princípios imutáveis

### 3.1 Fonte da verdade

- A IA nunca inventa produtos, preços, adicionais, promoções, taxa de entrega ou disponibilidade.
- O Smart Core e o banco de dados são a fonte da verdade.

### 3.2 Responsabilidade da IA

A Olívia conversa, entende intenção, consulta ferramentas, sugere adicionais compatíveis, ajuda a concluir o pedido e pede ajuda humana quando não consegue confirmar uma informação.

A Olívia não calcula preços, altera valores, grava diretamente no banco, envia pedidos diretamente ao Consumer ou decide regras comerciais por conta própria.

### 3.3 Responsabilidade do Core

O Smart Core valida produtos e códigos PDV, valida complementos permitidos, calcula subtotais, taxas, descontos e total, controla carrinho, cliente, endereço e pedido, impede duplicidade, registra eventos e falhas e escolhe os adaptadores externos.

## 4. Arquitetura oficial

```text
Canais
  ├── WhatsApp
  ├── Site
  └── futuros canais
        │
        ▼
Smart Gateway
        │
        ▼
Smart Core
  ├── Catálogo
  ├── Clientes
  ├── Carrinhos
  ├── Pedidos
  ├── Pagamentos
  ├── Conversas
  ├── Tickets
  └── Conhecimento
        │
        ▼
Adaptadores
  ├── Consumer
  ├── OpenAI
  ├── WhatsApp
  └── futuros provedores
```

Nenhuma integração externa pode se tornar dependência direta do domínio.

## 5. Multiempresa

- O SmartFoodIA nasce multiempresa.
- A Old Burguer 87 é o primeiro cliente piloto.
- Empresas e lojas são entidades próprias.
- Cada dado operacional pertence a uma empresa/loja.
- Nenhum código deve depender de nomes específicos da Old Burguer.

## 6. Catálogo

O catálogo contém categorias, produtos, variações, complementos, grupos de complementos, códigos PDV (`externalCode`), preços, descrições, disponibilidade e regras de compatibilidade.

O `externalCode` é a referência de integração com o Consumer.

## 7. Atendimento humano e aprendizado

Quando uma informação necessária não estiver disponível ou não puder ser confirmada:

1. A Olívia informa ao cliente que solicitará ajuda.
2. O atendimento gera um alerta para a equipe.
3. Um ticket de conhecimento é criado.
4. O incidente é classificado.
5. A equipe corrige a origem do problema.
6. Um teste confirma a correção.
7. O ticket é encerrado somente após validação.

Toda falha deve gerar aprendizado permanente.

## 8. Produto inexistente no cardápio

Quando o cliente procurar um produto que não existe:

1. A Olívia informa com transparência que não está disponível.
2. Pergunta, de forma breve e opcional, como seria o produto procurado.
3. Não insiste se o cliente não quiser responder.
4. Registra a intenção e as características desejadas.
5. Sugere um produto semelhante existente, quando houver.
6. A informação alimenta tendências futuras, fora do núcleo operacional da V1.

## 9. Memória do cliente

A memória pertence ao SmartFoodIA, não ao provedor de IA. Pode armazenar histórico de pedidos, endereços, preferências, restrições, forma de pagamento favorita e pedido favorito.

## 10. Consumer

- O Consumer é um adaptador, não o núcleo.
- O SmartFoodIA implementará a API de parceiro.
- O Consumer fará polling de eventos.
- O Consumer consultará detalhes do pedido.
- O Consumer enviará eventos e alterações de status.
- Produtos e complementos devem utilizar códigos PDV válidos.
- A assinatura Premium é necessária para testes e operação da integração.

## 11. Segurança

- Segredos ficam somente em `.env` ou serviço seguro de secrets.
- `.env` nunca vai ao GitHub.
- Tokens devem ser diferentes por loja.
- Toda requisição do Consumer deve ser autenticada.
- Logs não devem expor chaves, tokens ou dados sensíveis.
- Pedidos devem ter proteção contra duplicidade e reprocessamento.

## 12. Regras de engenharia

- Toda funcionalidade crítica deve ter teste.
- Toda mudança relevante deve atualizar documentação.
- Toda integração externa deve usar adaptador.
- Toda regra de negócio deve ficar no Core.
- Não se usa código descartável na branch principal.
- A branch `main` deve permanecer estável.
- O projeto usa versionamento semântico.
- Alterações incompatíveis exigem decisão registrada.

## 13. Escopo congelado da V1

Entram catálogo, clientes, endereços, carrinho, pedidos, adicionais, pagamento offline, entrega e retirada, integração Consumer, integração OpenAI, integração WhatsApp, alertas humanos, tickets básicos, logs, auditoria e atualizações de status.

Não entram BI avançado, tendências entre restaurantes, benchmark, forecast, campanhas automáticas, fidelidade, cashback, pagamento online, marketplace de plugins, múltiplos ERPs em produção, mesas e comandas na primeira entrega.

## 14. Critério de sucesso

> Pedidos concluídos automaticamente pela Olívia e recebidos corretamente no Consumer.
