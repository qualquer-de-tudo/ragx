# RAGX-0062 — Git hooks e receita de CI

| | |
|---|---|
| **Fase** | 9 — Git Sync / Merge |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0061` |
| **Bloqueia** | `RAGX-0063` |
| **Documentação** | [12-git-sync.md](../../docs/12-git-sync.md) |
| **Status** | `todo` |

## Objetivo

Barrar segredo antes do commit e manter o conhecimento atualizado sem esforço manual.

## Entregáveis

- [ ] `ragx init --git-hooks` instalando `pre-commit`, `post-merge`, `post-checkout` com consentimento explícito
- [ ] `pre-commit` → `ragx security scan --staged` (único que bloqueia)
- [ ] `post-merge`/`post-checkout` → `ragx sync --quiet`, degradando para aviso em caso de falha
- [ ] Merge driver `ragx-derived` opcional
- [ ] Receita de CI documentada, incluindo `ragx size --check` e `git diff --exit-code knowledge/`

## Fora de escopo

- Instalar hooks sem consentimento — nunca

## Critérios de aceite

- [ ] `pre-commit` barra commit com segredo e explica qual regra disparou
- [ ] Falha no `post-checkout` não impede troca de branch
- [ ] Hooks não sobrescrevem hooks existentes sem aviso
- [ ] Receita de CI funciona de ponta a ponta em repositório de exemplo

## Testes

- [ ] Repositório Git sintético exercitando os 3 hooks

## Notas

Porta de saída da Fase 9.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
