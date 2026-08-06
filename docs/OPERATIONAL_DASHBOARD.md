# Visão operacional do piloto

## Endpoint

```text
GET /api/v1/operations/stores/{store_id}/overview
```

Período padrão: últimas 24 horas.

Para alterar:

```text
?hours=168
```

## Informações retornadas

- conversas abertas, humanas e encerradas;
- tickets abertos, em andamento, resolvidos e urgentes;
- pedidos, receita e distribuição por status;
- eventos da IA, erros e duração média;
- estado das filas de entrada e saída;
- lacunas de conhecimento abertas;
- alertas operacionais.

## Alertas

O endpoint gera alertas para:

- itens em estado `DEAD`;
- mensagens aguardando retentativa;
- tickets urgentes;
- lacunas de conhecimento abertas.

Esta API será a fonte do primeiro painel simples de monitoramento da Old Burguer 87.
