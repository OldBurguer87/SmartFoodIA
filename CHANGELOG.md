# Changelog

## 0.1.4

- Adicionado worker contínuo para filas de canais.
- Adicionado serviço separado no Docker Compose.
- Adicionado reinício automático da API, worker e banco.
- Adicionadas configurações de intervalo, lote e tentativas.
- Adicionado endpoint de liveness `/live`.
- Adicionado endpoint de readiness `/ready`.
- Adicionado healthcheck da API.
- Adicionada dependência do worker sobre a prontidão da API.
- Adicionados testes de saúde.

## 0.1.3

- Adicionada fila persistente e retentativas do WhatsApp.
