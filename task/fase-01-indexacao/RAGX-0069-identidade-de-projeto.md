# RAGX-0069 — Identidade de projeto

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,25d |
| **Depende de** | `RAGX-0014` |
| **Bloqueia** | `RAGX-0072` |
| **Documentação** | [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [adr/ADR-0009-tres-camadas-de-conhecimento.md](../../docs/adr/ADR-0009-tres-camadas-de-conhecimento.md) |
| **Status** | `todo` |

## Objetivo

Fixar quem é este projeto — id estável, nome, tipo e visibilidade — antes que qualquer coisa seja gravada. Acrescentar isso depois custaria migrar todo o schema e reindexar toda a base.

## Entregáveis

- [ ] `project_id` gerado no `ragx init`: derivado do `git remote` quando existir, senão aleatório e estável
- [ ] `meta`: `project_id`, `project_name`, `project_kind`, `visibility`
- [ ] `[project] kind` e `visibility` em `ragx.toml` (`workspace` | `private`)
- [ ] `project_id` no `manifest.json` de `knowledge/`
- [ ] Derivação do remote por **hash**, nunca pela URL — ela pode conter token

## Fora de escopo

- Registro no hub (RAGX-0074)

## Critérios de aceite

- [ ] `project_id` é estável entre reindexações e entre máquinas do mesmo repositório
- [ ] Clonar o repositório em outra pasta preserva o `project_id`
- [ ] Repositório sem Git recebe id estável (gravado no `ragx.toml`)
- [ ] Nenhuma URL de remote em claro em lugar nenhum
- [ ] `visibility = "private"` é respeitado desde já por quem for consumir

## Testes

- [ ] Estabilidade do id entre clones
- [ ] Remote com credencial embutida não vaza

## Notas

Tarefa pequena e desproporcionalmente importante: é o que evita reindexar tudo quando a Fase 11 chegar.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
