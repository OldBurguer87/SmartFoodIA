# Endurecimento do adaptador Consumer — v0.3.2

Esta versão não adiciona funcionalidades fora do MVP. Ela corrige e reforça o
contrato já aprovado para a API de Parceiros do Consumer.

## Alterações

- o endpoint de eventos aceita apenas `ODR`;
- quando informado, `EventFullCode` deve ser
  `ORDER_DETAILS_REQUESTED`;
- a mesma validação existe no adaptador, independentemente do endpoint HTTP;
- notificações usam o nome real da loja, sem referência fixa à Old Burguer 87;
- o script duplicado `configure_consumer_integration.py` foi removido;
- o único provisionador oficial passa a ser
  `configure_consumer_partner.py`;
- foram adicionados testes de contrato e modularidade.

## Script oficial

```bash
docker compose exec api python -m app.scripts.configure_consumer_partner \\
  --store-slug old-burguer-87 \\
  --merchant-id ID_DO_CONSUMER \\
  --merchant-name "Old Burguer 87" \\
  --base-url https://seu-dominio-publico.com
```

## Limite desta versão

A estrutura atual de `store_integrations` continua suficiente para o piloto.
Uma futura evolução para credenciais e configurações JSON deve ocorrer somente
quando um segundo ERP exigir campos diferentes, evitando abstração prematura.
