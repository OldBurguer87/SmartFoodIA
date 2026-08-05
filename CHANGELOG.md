# Changelog

## 0.0.3

- Criados grupos de complementos.
- Criados complementos com código PDV e preço.
- Criada compatibilidade entre produto e grupo.
- Criada composição de complementos por grupo.
- Adicionadas regras de mínimo, máximo, repetição e quantidade padrão.
- Criada migration `0002`.
- Criada API inicial de grupos e complementos.
- Adicionados testes de validação do domínio.

## 0.0.2

- Adicionadas configurações do Alembic.
- Criada a primeira migration.
- Criadas as tabelas de empresas, lojas, categorias e produtos.
- Criados schemas Pydantic do catálogo.
- Criado repositório de produtos.
- Criada API inicial do catálogo.
- Adicionados testes do schema de produto.

## 0.0.1

- Estrutura inicial do projeto.
- FastAPI configurado.
- PostgreSQL via Docker Compose.
- Configuração por `.env`.
- Endpoints `/`, `/health` e `/version`.
- Testes básicos.
