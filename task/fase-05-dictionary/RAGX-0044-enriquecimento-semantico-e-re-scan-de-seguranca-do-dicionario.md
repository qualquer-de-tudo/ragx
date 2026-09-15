# RAGX-0044 — Enriquecimento semântico e re-scan de segurança do dicionário

| | |
|---|---|
| **Fase** | 5 — Knowledge Dictionary |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0043` |
| **Bloqueia** | — |
| **Documentação** | [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `todo` |

## Objetivo

Preencher as seções inferidas marcando o que é inferência, e impedir que um artefato compartilhado vire superfície de vazamento.

## Entregáveis

- [ ] `--semantic` preenchendo apenas `concepts`, `glossary` e `summaries`
- [ ] Marcação `"source": "llm"` + `confidence` em cada item inferido
- [ ] Re-scan de segurança antes de gravar: item que casa com regra de segredo é descartado e gera `security_event`
- [ ] Respeita `security.allow_remote_llm`

## Fora de escopo

- Habilitar por padrão

## Critérios de aceite

- [ ] Item inferido é distinguível de item derivado por teste automatizado
- [ ] Nenhum valor de segredo ou de variável de ambiente em qualquer arquivo de `knowledge/`
- [ ] Desabilitado por padrão

## Testes

- [ ] LLM fake devolvendo conteúdo com segredo — precisa ser descartado

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
