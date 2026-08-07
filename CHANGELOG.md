# Changelog

## 0.3.4

- Alinhado o roadmap com o histórico real das versões implementadas.
- Registradas formalmente as decisões de VPS, domínio, Cloudflare, Caddy e URL pública canônica.
- Registrada a prioridade absoluta de homologar o primeiro pedido no Consumer antes de expandir escopo.
- Consolidado `configure_consumer_partner` como provisionador oficial.
- Removidas referências documentais ao script obsoleto `configure_consumer_integration`.
- Substituído `api.seudominio.com` por `smartfoodia.com.br` na documentação oficial do piloto.
- Atualizado `.env.example` para a base pública oficial da homologação.
- Nenhuma regra funcional do Core ou contrato de integração foi alterado nesta versão.

## 0.3.3

- Adicionada implantação de produção com Caddy e HTTPS automático.
- Adicionado `docker-compose.production.yml`.
- Adicionado endpoint protegido de diagnóstico Consumer.
- Adicionadas verificações de integração, merchant, token e HTTPS.
- Adicionado script externo de verificação da API pública.
- Adicionados testes de diagnóstico.
- Adicionado roteiro de homologação do primeiro pedido.

## 0.3.2

- Endurecido o contrato Consumer e removidas dependências fixas de loja.
