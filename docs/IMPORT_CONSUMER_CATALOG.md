# Importação do Catálogo Consumer

## O que esta importação faz

- lê a planilha `.xlsx` exportada pelo Consumer;
- cria categorias;
- cria produtos;
- atualiza produtos existentes pelo código PDV;
- remove espaços e tabulações extras dos nomes;
- evita duplicação em importações repetidas;
- bloqueia códigos PDV conflitantes;
- gera relatório JSON dos problemas encontrados.

## Segurança dos dados

A planilha real da Old Burguer não deve ser enviada ao repositório público.

Coloque-a localmente em:

```text
data/import/
```

Essa pasta está protegida pelo `.gitignore`.

## Preparação

Depois de iniciar os containers e executar as migrations:

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

Copie o arquivo exportado do Consumer para:

```text
data/import/cardapio-consumer.xlsx
```

## Importar

Execute:

```bash
docker compose exec api python -m app.scripts.import_consumer_catalog   --file /app/../data/import/cardapio-consumer.xlsx
```

Como o container atual monta apenas `backend:/app`, no Windows a forma mais simples durante
o desenvolvimento é copiar temporariamente a planilha para `backend/data/import/` e executar:

```bash
docker compose exec api python -m app.scripts.import_consumer_catalog   --file data/import/cardapio-consumer.xlsx
```

## Relatório

O importador gera:

```text
data/reports/consumer_catalog_import.json
```

Códigos PDV repetidos com preços, nomes ou categorias diferentes não são importados
automaticamente. Eles ficam no relatório para correção manual, evitando preços errados.
