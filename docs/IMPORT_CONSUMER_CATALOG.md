# Importação do Catálogo Consumer

## O que esta importação faz

- lê a planilha `.xlsx` exportada pelo Consumer;
- cria categorias;
- cria produtos;
- atualiza produtos existentes pelo código PDV;
- remove espaços e tabulações extras dos nomes;
- evita duplicação em importações repetidas;
- bloqueia códigos PDV conflitantes;
- gera relatório JSON dos problemas encontrados;
- **desativa produtos que existiam no SmartFoodIA e desapareceram da nova exportação do Consumer**, quando existe ao menos uma linha válida importada.

## Regra de desativação

Após processar as linhas válidas, o importador compara os códigos importados com os produtos já existentes. Produtos ausentes da nova planilha são marcados como:

```text
active = false
available_for_delivery = false
available_for_takeout = false
```

Proteções existentes:

- se nenhuma linha válida for importada, o catálogo inteiro não é desativado;
- códigos associados a linhas inválidas ou conflitos ficam protegidos contra desativação acidental;
- o relatório informa `products_deactivated`.

## Segurança dos dados

A planilha real da Old Burguer não deve ser enviada ao repositório público.

Arquivos `cardapioConsumer-*.xlsx` estão ignorados pelo Git.

## Preparação

Depois de iniciar os containers e executar as migrations:

```bash
docker compose up --build
docker compose exec api alembic upgrade head
```

## Importar

Exemplo:

```bash
docker compose exec api python -m app.scripts.import_consumer_catalog \
  --file data/import/cardapio-consumer.xlsx
```

## Relatório

O importador gera relatório JSON em `data/reports/` com quantidades de produtos criados, atualizados, inalterados, desativados, conflitos e linhas inválidas.

Códigos PDV repetidos com preços, nomes ou categorias diferentes não são importados automaticamente. Eles ficam no relatório para correção manual.
