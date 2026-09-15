# RAGX-0006 — SecurityScanner — fase 2: detecção de segredo em conteúdo

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0005` |
| **Bloqueia** | `RAGX-0007` |
| **Documentação** | [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

Detectar segredos dentro de arquivos legítimos, combinando regras de alta precisão, entropia e contexto — sem transformar o scanner em gerador de falso positivo.

## Entregáveis

- [ ] Carregador de regras YAML declarativas (`id`, `severity`, `pattern`, `action`, `min_entropy`)
- [ ] `security/rules/patterns.yaml` com os provedores listados no doc 02 (AWS, GitHub, Google, Slack, Stripe, OpenAI/Anthropic, JWT, PEM, Azure, Twilio, SendGrid, npm, URIs com senha)
- [ ] Detector de atribuição + `security/entropy.py` (Shannon) com limiar configurável
- [ ] Allowlist de placeholders (`changeme`, `${...}`, `process.env.*`, ...)
- [ ] Multiplicadores de severidade por contexto de arquivo, sem jamais rebaixar regra de alta precisão
- [ ] Compilação de regex uma única vez, no carregamento

## Fora de escopo

- Verificação ativa de validade da credencial (chamar a API do provedor)

## Critérios de aceite

- [ ] `config.yaml` e `docker-compose.yml` da fixture são detectados com a linha correta
- [ ] `.env.example` com placeholders NÃO gera achado
- [ ] `tests/fixtures/sample.json` com valor de alta entropia sem semântica de segredo NÃO é bloqueado
- [ ] `AKIA...` dentro de `tests/` continua `BLOCK` apesar do rebaixamento de contexto
- [ ] Scan de 5.000 arquivos acrescenta menos de 10% ao tempo total de indexação

## Testes

- [ ] Corpus de positivos (um por regra) e de negativos (placeholders, hashes, UUIDs, base64 de imagem)
- [ ] Benchmark de regressão de desempenho do scanner

## Notas

Regras em YAML são requisito, não preferência: elas precisam ser auditáveis por alguém de segurança sem ler Python.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
