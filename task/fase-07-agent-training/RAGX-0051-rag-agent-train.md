# RAGX-0051 — ragx agent train

| | |
|---|---|
| **Fase** | 7 — Agent Knowledge Training |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0050` |
| **Bloqueia** | `RAGX-0052`, `RAGX-0053`, `RAGX-0079` |
| **Documentação** | [10-agent-training.md](../../docs/10-agent-training.md) |
| **Status** | `todo` |

## Objetivo

Compilar conhecimento, regras e dicionário recortado num perfil utilizável, sem destruir o que foi curado à mão.

## Entregáveis

- [ ] `agents/trainer.py` com o fluxo do doc 10
- [ ] Dicionário recortado por `manifest.scope`
- [ ] `rules/security.md` obrigatório, derivado do ruleset do RAGX — perfil sem ele não compila
- [ ] Geração em `rules/*.generated.md` com merge explícito; arquivo curado à mão sempre vence
- [ ] `instructions.md` montado por template, referenciando ferramentas MCP em vez de embutir conhecimento
- [ ] Registro em `manifest.knowledge` (index_run, dictionary_hash, contagens)

## Fora de escopo

- Fine-tuning de modelo — não é isso que esta fase faz

## Critérios de aceite

- [ ] Retreinar com índice inalterado não altera nenhum arquivo curado manualmente
- [ ] Perfil sem `rules/security.md` falha a compilação com mensagem clara
- [ ] `instructions.md` cabe no orçamento de tokens definido em `--tokens`
- [ ] Nenhum arquivo em `agents/**` contém segredo

## Testes

- [ ] Teste de preservação de arquivo curado
- [ ] Teste de segurança sobre `agents/**`

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
