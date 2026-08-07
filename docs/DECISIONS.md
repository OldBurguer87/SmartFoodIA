# Decisões Oficiais do SmartFoodIA

- **DEC-001 — Old Burguer como cliente piloto:** aprovada.
- **DEC-002 — Arquitetura multiempresa:** aprovada.
- **DEC-003 — Core como fonte da verdade:** aprovada.
- **DEC-004 — Consumer como adaptador:** aprovada.
- **DEC-005 — OpenAI como provedor substituível:** aprovada.
- **DEC-006 — WhatsApp como canal substituível:** aprovada.
- **DEC-007 — Códigos PDV como referência externa:** aprovada.
- **DEC-008 — IA sem acesso direto ao banco:** aprovada.
- **DEC-009 — Cálculos fora da IA:** aprovada.
- **DEC-010 — Confirmação explícita antes do pedido:** aprovada.
- **DEC-011 — Escalonamento humano:** aprovada.
- **DEC-012 — Aprendizado por incidentes:** aprovada.
- **DEC-013 — Produto inexistente gera descoberta opcional:** aprovada.
- **DEC-014 — Memória pertence ao SmartFoodIA:** aprovada.
- **DEC-015 — GitHub como repositório oficial:** aprovada.
- **DEC-016 — Desenvolvimento local com GitHub Desktop e VS Code:** aprovada.
- **DEC-017 — Escopo V1 congelado:** aprovada.
- **DEC-018 — API de parceiro do Consumer:** aprovada.
- **DEC-019 — PostgreSQL, FastAPI, SQLAlchemy e Alembic:** aprovada.
- **DEC-020 — Docker para ambiente de execução:** aprovada.
- **DEC-021 — VPS de produção na Master da Web:** aprovada para a fase atual de homologação e piloto.
- **DEC-022 — Domínio público oficial `smartfoodia.com.br`:** aprovado.
- **DEC-023 — Cloudflare como autoridade/gerenciador DNS:** aprovada; DNSSEC permanece desligado durante a troca inicial de nameservers e pode ser reavaliado após estabilização.
- **DEC-024 — Caddy como proxy reverso e emissor/renovador de HTTPS:** aprovado.
- **DEC-025 — Base pública canônica da API no domínio raiz:** aprovada como `https://smartfoodia.com.br`; a API é publicada pelos caminhos `/api/...`, sem dependência atual de `api.smartfoodia.com.br`.
- **DEC-026 — Primeiro gate externo é o pedido aparecer no Consumer:** aprovado. Antes de ampliar o escopo, o SmartFoodIA deve publicar a API, passar os diagnósticos e fazer um pedido completo aparecer corretamente na fila do Consumer.
- **DEC-027 — Consumer é o primeiro ERP integrado, não o núcleo do produto:** reafirmada. Novos ERPs ou um ERP próprio devem entrar por adaptadores sem acoplar as regras do Core.
- **DEC-028 — `configure_consumer_partner` é o provisionador oficial da integração Consumer:** aprovado. Referências a `configure_consumer_integration` são consideradas legadas.

## Regra de governança

Uma decisão nova que altere arquitetura, escopo V1, contrato de integração, infraestrutura pública ou segurança deve ser registrada aqui antes de ser tratada como padrão oficial do projeto.
