# Integração OpenAI da Olívia

A integração usa a Responses API do SDK oficial da OpenAI por meio de um adaptador substituível.

## Estado do código

Implementado.

O fluxo inclui persistência da mensagem, contexto recente, chamadas de ferramenta, retorno de `function_call_output`, resposta final e registro técnico em `ai_events`.

## Configuração

Variáveis esperadas:

```text
OPENAI_API_KEY=sua_chave
OPENAI_MODEL=gpt-5.5
OPENAI_TIMEOUT_SECONDS=45
OLIVIA_MAX_TOOL_ROUNDS=8
```

Nunca envie a chave ao GitHub.

## Estado da produção auditada em 2026-08-11

```text
OPENAI_CONFIGURED=False
OPENAI_MODEL=gpt-5.5
OPENAI_TIMEOUT_SECONDS=45
OLIVIA_MAX_TOOL_ROUNDS=8
```

Portanto, a integração existe no projeto, mas ainda não estava ativa na VPS com uma chave real. Isso significa que o Consumer já foi homologado independentemente da etapa final de ativação da Olívia em produção.

## Fluxo implementado

1. A mensagem do cliente é persistida.
2. O histórico recente é enviado ao provedor.
3. O modelo responde ou chama uma ferramenta.
4. A ferramenta executa um Service do SmartFoodIA.
5. O resultado volta como `function_call_output`.
6. A resposta final é persistida.
7. Chamadas, duração e erros ficam em `ai_events`.

## Endpoint

```text
POST /api/v1/olivia/reply
```

## Próximo gate operacional

Antes do piloto real, configurar a chave na VPS, validar o endpoint com provedor real e então testar o ciclo WhatsApp → Olívia → Core → Consumer.

Consulte `docs/PRODUCTION_RUNTIME.md`.
