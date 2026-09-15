# RAGX-0001 — Bootstrap do projeto Python

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Bloqueia** | `RAGX-0002`, `RAGX-0003` |
| **Documentação** | [01-arquitetura.md](../../docs/01-arquitetura.md) · [adr/ADR-0001-python-e-toolchain.md](../../docs/adr/ADR-0001-python-e-toolchain.md) |
| **Status** | `todo` |

## Objetivo

Criar o esqueleto do pacote, o build e as ferramentas de qualidade, de modo que qualquer tarefa seguinte já nasça com lint, tipos e testes rodando.

## Entregáveis

- [ ] `pyproject.toml` com hatchling, `requires-python = ">=3.11"` e os dois console scripts (`rag`, `ragx`)
- [ ] Layout `src/ragx/` com os subpacotes vazios de `docs/01-arquitetura.md` (`core`, `security`, `storage`, `indexing`, `cli`)
- [ ] `uv.lock` versionado; dependências iniciais: typer, rich, pydantic, pydantic-settings, pathspec
- [ ] Configuração de `ruff` (lint + format) e `mypy` (strict em `core/` e `security/`) no pyproject
- [ ] `pytest` configurado com marcadores `unit`, `integration`, `security`, `e2e`
- [ ] `ragx --version` e `ragx --version` funcionando
- [ ] README com instalação via `uv tool install` e a nota sobre o alias (ADR-0007)

## Fora de escopo

- Qualquer lógica de indexação, busca ou segurança
- Publicação no PyPI

## Critérios de aceite

- [ ] `uv sync` em máquina limpa instala tudo sem erro
- [ ] `ruff check .` e `ruff format --check .` passam
- [ ] `mypy --strict src/ragx/core src/ragx/security` passa (pacotes ainda vazios)
- [ ] `pytest` roda e coleta 0 testes sem falhar
- [ ] `ragx --version` imprime a versão de `pyproject.toml`

## Testes

- [ ] Smoke test do entrypoint da CLI (`--version`, `--help`)

## Notas

Fixar `CHUNKER_VERSION = "1"` e `SCHEMA_VERSION` já em `core/__init__.py`, mesmo sem uso — evita esquecer depois.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
