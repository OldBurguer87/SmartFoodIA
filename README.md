# SmartFoodIA

## Versão atual

`0.1.4 — Continuous Worker & Readiness`

Esta versão adiciona:

- worker contínuo para a fila de canais;
- serviço `worker` no Docker Compose;
- reinício automático;
- configurações de lote, intervalo e tentativas;
- endpoint `/live`;
- endpoint `/ready`;
- healthcheck da API;
- inicialização ordenada entre banco, API e worker.

Consulte `docs/WORKER_AND_READINESS.md`.
