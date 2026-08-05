# Escopo Oficial da Versão 1.0

## Objetivo

Receber um pedido completo pelo WhatsApp e fazê-lo chegar corretamente ao Consumer, com atualização de status ao cliente.

## Funcionalidades obrigatórias

### Atendimento
- receber mensagens;
- manter contexto;
- consultar catálogo;
- responder dúvidas;
- sugerir adicionais compatíveis;
- detectar pedido, alteração e cancelamento;
- transferir para humano quando necessário.

### Catálogo
- importar produtos, categorias e complementos;
- usar códigos PDV;
- controlar disponibilidade;
- controlar compatibilidade entre produto e complemento.

### Cliente
- identificar pelo telefone;
- cadastrar cliente;
- salvar nome e endereços;
- manter histórico básico.

### Carrinho e checkout
- criar carrinho;
- adicionar, alterar e remover itens;
- adicionar complementos;
- registrar observações;
- calcular subtotal e total;
- entrega ou retirada;
- taxa de entrega;
- PIX, crédito, débito e dinheiro;
- troco;
- resumo e confirmação explícita.

### Pedido e Consumer
- gerar pedido persistente;
- gerar evento `PLACED`;
- impedir duplicação;
- manter histórico de status;
- polling;
- detalhes;
- eventos;
- alterações de status;
- autenticação por token;
- mapeamento por `externalCode`.

### Suporte
- alerta humano;
- ticket de conhecimento;
- classificação básica;
- registro de contexto e pergunta.

## Fora do escopo

Pagamento online, PIX automático, cashback, fidelidade, relatórios avançados, inteligência de mercado agregada, previsão de demanda, campanhas automáticas, aplicativo móvel, mesas e comandas.
