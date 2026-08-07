# SmartFoodIA

## Versão atual

`0.3.4 — Documentation & Governance Alignment`

Esta versão não altera regras funcionais do Core nem o contrato da API Parceiro. Ela alinha a documentação ao estado real do projeto e às decisões aprovadas para a homologação:

- roadmap atualizado com o histórico real de versões;
- prioridade explícita para o primeiro pedido entrar no Consumer;
- VPS, domínio, Cloudflare e Caddy registrados em decisões oficiais;
- `smartfoodia.com.br` definido como base pública da homologação;
- `configure_consumer_partner` consolidado como único provisionador oficial;
- referências obsoletas ao antigo configurador removidas;
- documentação de homologação e URLs finais corrigidas.

A base funcional permanece a da `0.3.3 — Consumer Homologation & Public HTTPS`:

- implantação pública com HTTPS automático;
- proxy reverso Caddy;
- endpoint protegido de diagnóstico da integração;
- verificador externo de DNS, HTTPS, autenticação e polling;
- geração das quatro URLs finais;
- roteiro do primeiro pedido de homologação.

Consulte:

- `docs/PROJECT_CONSTITUTION.md`
- `docs/DECISIONS.md`
- `docs/V1_SCOPE.md`
- `docs/ROADMAP.md`
- `docs/CONSUMER_HOMOLOGATION.md`
