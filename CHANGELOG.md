# Changelog

## 0.0.8

- Adicionadas credenciais de integração por loja.
- Adicionado armazenamento de token somente como hash SHA-256.
- Adicionada autenticação Bearer por loja.
- Adicionado endpoint de polling do Consumer.
- Adicionado endpoint de detalhes do pedido.
- Adicionado recebimento de evento `ODR`.
- Adicionada atualização de status do pedido.
- Adicionado mapeamento do pedido para o contrato Consumer.
- Adicionada filtragem de eventos por loja.
- Adicionada idempotência na atualização de status.
- Adicionado script seguro de configuração da integração.
- Adicionados testes da API de parceiro.

## 0.0.7

- Adicionado checkout e pedidos persistentes.
- Adicionado evento `PLACED / PLC`.
- Adicionada idempotência por carrinho.

## 0.0.6

- Adicionados clientes, endereços e carrinho persistente.

## 0.0.5

- Adicionado importador do catálogo Consumer.

## 0.0.4

- Adicionado Smart Catalog Engine.

## 0.0.3

- Adicionados grupos de complementos.

## 0.0.2

- Criadas tabelas iniciais e API de catálogo.

## 0.0.1

- Estrutura inicial, FastAPI, PostgreSQL e Docker.
