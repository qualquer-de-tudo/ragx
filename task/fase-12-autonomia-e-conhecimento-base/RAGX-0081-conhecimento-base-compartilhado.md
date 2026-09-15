# RAGX-0081 — Conhecimento base compartilhado entre projetos

| | |
|---|---|
| **Fase** | 12 — Autonomia + Conhecimento base |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0073` |
| **Bloqueia** | `RAGX-0084` |
| **Documentação** | [18-conhecimento-base.md](../../docs/18-conhecimento-base.md) · [ADR-0013](../../docs/adr/ADR-0013-conhecimento-base-compartilhado.md) |
| **Status** | `done` |

## Objetivo

Permitir que conhecimento que não pertence a repositório nenhum — guardrails,
padrões de arquitetura, política de revisão — viva uma vez por máquina e seja
indexado em todos os projetos que o declaram.

## Entregáveis

- [x] `ragx.base.source`: registro em `~/.ragx/base/sources.json`, clone raso, atualização, enable/disable
- [x] Prefixo `@base/<fonte>/` no índice, sem colisão com caminho de projeto
- [x] `iter_files(prefix=...)` — base entra pelo MESMO caminho auditado do projeto
- [x] Gate próprio por fonte, enraizado nela (regra de nome e `.gitignore` avaliam o caminho real)
- [x] Serialização exclui `@base/` de documents, chunks, embeddings, entities e relations
- [x] `knowledge/base.json` — a receita (origem, ref, commit) viaja no Git
- [x] `ragx base add|list|sync|update|enable|disable|remove`
- [x] `--declare` grava `[base] sources` no `ragx.toml` preservando comentários
- [x] `[base]` em `Config`

## Fora de escopo

- Interface para editar o conteúdo da fonte (edita-se no repositório de origem)
- Resolução de conflito entre duas fontes que dizem coisas opostas

## Critérios de aceite

- [x] Fonte instalada e declarada aparece como `@base/...` no índice e na busca
- [x] Fonte instalada e **não** declarada não aparece — instalar não indexa
- [x] Segredo dentro de uma fonte base é BLOQUEADO pelo gate, como no projeto
- [x] `knowledge/` não contém nenhum documento `@base/`
- [x] `ragx base disable` + `ragx index` remove os documentos do índice
- [x] `base.json` carrega a URL declarada e permite reproduzir em outra máquina

## Testes

- [x] `tests/integration/test_base.py` — 8 testes
- [x] `test_base_gerencia_fontes_mas_nao_le_conteudo` — `ragx.base` nunca chama `read_bytes`/`open`
- [x] `test_conhecimento_base_fica_fora_do_git` — as consultas de serialização continuam filtrando

## Notas

O opt-in por projeto **não** estava no desenho inicial. Foi acrescentado
depois que sete testes de pipeline quebraram: a fonte instalada nesta máquina
vazou para todo projeto temporário, indexando 40 documentos onde se esperavam
4. O sintoma apareceu em teste; em produção apareceria como a busca devolvendo
a regra de outro contexto, sem explicação. A correção foi de design, não de
teste.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [x] Testes escritos e verdes
- [x] `ruff` limpo
- [x] Suíte `security/` continua verde
- [x] Documentação da fase confere com o comportamento implementado
