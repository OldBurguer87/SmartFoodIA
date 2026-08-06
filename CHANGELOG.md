# Changelog

## 0.0.5

- Adicionado importador de planilhas `.xlsx` do Consumer.
- Adicionada criação automática da empresa e loja piloto.
- Adicionada importação idempotente por código PDV.
- Adicionada atualização de produtos existentes.
- Adicionada normalização de espaços e tabulações.
- Adicionado bloqueio de códigos PDV conflitantes.
- Adicionado relatório JSON da importação.
- Adicionados testes do importador.
- Adicionado `openpyxl`.

## 0.0.4

- Adicionado Smart Catalog Engine.
- Adicionado `CatalogService`.
- Adicionados DTOs desacoplados do banco.
- Adicionada busca normalizada e ranking de relevância.
- Adicionados filtros de disponibilidade.
- Adicionado retorno de complementos compatíveis.

## 0.0.3

- Adicionados grupos de complementos.
- Adicionados complementos e códigos PDV.
- Adicionadas relações produto × grupo e grupo × complemento.
- Adicionadas regras de seleção.

## 0.0.2

- Adicionadas configurações do Alembic.
- Criada a primeira migration.
- Criadas as tabelas de empresas, lojas, categorias e produtos.
- Criada API inicial do catálogo.

## 0.0.1

- Estrutura inicial do projeto.
- FastAPI configurado.
- PostgreSQL via Docker Compose.
- Endpoints básicos e testes.
