# RAGX-0067 — Empacotamento e release

| | |
|---|---|
| **Fase** | 10 — Hardening + Release |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0066` |
| **Bloqueia** | `RAGX-0068` |
| **Documentação** | [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Tornar o RAGX instalável por alguém que nunca viu o repositório.

## Entregáveis

- [ ] Build de wheel e sdist; publicação no PyPI (ou índice interno)
- [ ] `CHANGELOG.md` seguindo Keep a Changelog; versão SemVer em `pyproject.toml` e em `meta.ragx_version`
- [ ] Teste de migração a partir de cada versão de schema anterior suportada
- [ ] Teste de instalação limpa: `uv tool install ragx && ragx --version`
- [ ] README com o caminho completo `init → index → search → mcp`

## Fora de escopo

- Binário único (PyInstaller) — pós-MVP

## Critérios de aceite

- [ ] Instalação limpa em máquina sem RAGX executa `init → index → search → mcp` seguindo só o README
- [ ] Migração de cada versão anterior suportada é testada
- [ ] Checklist de release do doc 13 inteiramente marcado

## Testes

- [ ] Job de instalação limpa em container/VM

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
