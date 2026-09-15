# RAGX-0004 — IgnoreEngine

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0002` |
| **Bloqueia** | `RAGX-0008` |
| **Documentação** | [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

Reduzir o volume de arquivos candidatos aplicando a semântica de gitignore de múltiplas fontes, na ordem correta de precedência.

## Entregáveis

- [ ] `security/ignore_engine.py` usando `pathspec` com `GitWildMatchPattern`
- [ ] Fontes na ordem: defaults embutidos → `.gitignore` (inclusive aninhados) → `.dockerignore` → `.ragignore` → `ragx.toml` → flags
- [ ] Suporte a negação (`!pattern`) e a padrões por diretório
- [ ] `security/rules/default_ignore.txt` com a lista completa do doc 02
- [ ] API: `should_ignore(rel_path) -> tuple[bool, str | None]` devolvendo a regra que decidiu

## Fora de escopo

- Decisão de segurança — o IgnoreEngine trata de ruído, não de segredo

## Critérios de aceite

- [ ] `.gitignore` aninhado em subdiretório afeta apenas sua subárvore
- [ ] Negação reverte um padrão anterior
- [ ] Origem da decisão (arquivo + linha do padrão) é reportável para depuração
- [ ] Arquivo ignorado é classificado `SKIP`, nunca `BLOCK` — a distinção importa no relatório

## Testes

- [ ] Unitários cobrindo negação, aninhamento, `**`, barra inicial e final
- [ ] Teste explícito: `.env` NÃO listado no `.gitignore` continua chegando ao scanner

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
