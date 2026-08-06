# Changelog

## 0.0.4

- Criado `CatalogService` como porta oficial de acesso ao catálogo.
- Criados DTOs imutáveis para produtos, grupos e complementos.
- Implementada busca normalizada, sem diferença de acentos e pontuação.
- Implementado ranking de relevância por nome, descrição e categoria.
- Adicionada busca de produto mais provável.
- Adicionados filtros de disponibilidade para entrega e retirada.
- A API de consulta passou a usar o Service em vez de acessar o banco diretamente.
- Adicionados testes do motor de catálogo.

## 0.0.3

- Criados grupos de complementos e complementos.
- Criadas relações de compatibilidade entre produtos, grupos e complementos.
- Adicionadas regras de mínimo, máximo, repetição e quantidade padrão.

## 0.0.2

- Adicionadas configurações do Alembic.
- Criada a primeira migration.
- Criadas as tabelas de empresas, lojas, categorias e produtos.
- Criados schemas Pydantic do catálogo.
- Criado repositório de produtos.
- Criada API inicial do catálogo.

## 0.0.1

- Estrutura inicial do projeto.
- FastAPI configurado.
- PostgreSQL via Docker Compose.
- Endpoints `/`, `/health` e `/version`.
