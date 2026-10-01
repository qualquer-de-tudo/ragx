# RAGX-0195 — Fechar a v2: medir S1 a S14, publicar o relatório e conferir a documentação

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | todas as P0 e P1 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) · [25-spec-v2.md](../../docs/25-spec-v2.md) (seção 3, SLOs S1 a S14) · [ROTEIRO-V2.md](../ROTEIRO-V2.md) |
| **Status** | `todo` |

## Objetivo

A v2 promete três coisas (gastar menos tokens, não deixar o Claude lento, nunca raciocinar sobre código velho) e a spec 25 as traduz em 14 SLOs. Cada tarefa registrou o seu número antes e depois, mas ninguém reuniu os números, repetiu a medição com o código final nem conferiu se a documentação ainda diz a verdade (`README.md:72` fala em "33 ferramentas", `AGENTS.md:45` em "1087 testes"). Esta tarefa mede S1 a S14 de novo, escreve `docs/26-resultados-v2.md` e confere a documentação contra o código. **Não decide nada de produto**: o que anunciar, o padrão do perfil `slim` e rodadas que gastam cota são decisões de uma pessoa, e a tarefa termina em `review`.

## Entregáveis

- [ ] Reler a seção **Medição** de cada tarefa feita e rodar os comandos que ela definiu, com o código final da branch `feat/v2`. Mapa de SLO para tarefa: S1 → 0154 (e 0165) · S2 → 0157 (com 0155 e 0158) · S3 → 0111 da fase 14 · S4 → 0129, 0130 (e 0139) · S5 → 0131 (e 0140) · S6 → 0140 e 0141 · S7 e S8 → 0143 · S9 → 0142 · S10 → 0134 · S11 → 0171, 0172, 0173 (linha de base na 0177) · S12 → 0135 · S13 → 0190 (e 0156) · S14 → 0162 (e 0163).
- [ ] `docs/26-resultados-v2.md` (novo) com a tabela **S1 a S14** nas colunas Hoje, Meta, Medido, Status e Método (comando exato, corpus, máquina, data, commit). Status só pode ser `atingida`, `não atingida` ou `n/a — tarefa X não concluída` (ou `n/a — <motivo>`). Seção "Fora do que a v2 prometeu" listando tarefas em `review` ou `blocked` e o que falta uma pessoa decidir.
- [ ] Onde a medição não puder ser feita, escrever `n/a` e o motivo: S3 se a 0111 (fase 14, pendente) não entrou; S14 se o A/B real da 0162 não foi rodado (o harness entrega só `--dry-run` e simulado, de propósito); S11 com menos projetos no hub do que os 12 do enunciado (registrar quantos havia, sem extrapolar). **Nenhum número não medido entra no relatório, no CHANGELOG ou no README.**
- [ ] Suítes completas com os números do relatório: `uv run ruff check .`, `uv run mypy src/ragx/core src/ragx/security`, `uv run pytest -m "not slow"`, `uv run pytest tests/security`, e em `src/app` `npm test`, `npm run lint`, `npx tsc -p tsconfig.app.json --noEmit` e `npx tsc -p tsconfig.electron.json --noEmit`.
- [ ] Documentação conferida contra o código, corrigindo o que divergir: `docs/09-mcp.md` e `README.md:72` (contar com `ragx mcp tools --json`, o mesmo comando do `release.yml`; descrever o perfil `full` e o `slim`), `docs/14-cli.md` (comandos novos contra `ragx --help`), `docs/05-busca.md` (cache de `load_index`, `degraded`, `stale_paths`), `docs/12-git-sync.md` (clone novo e `knowledge/` estável), `docs/08-dictionary.md` (só promete níveis se a 0111 entrou), `src/app/README.md` (telas novas, preferências, atualização; a tabela de tarefas diz "16 tipos", mas `JobKind` em `src/types/ragx-bridge.d.ts:114-131` tem 17, com `ragx-install`), `AGENTS.md:45` (contagem com `uv run pytest -m "not slow" --collect-only -q`).
- [ ] `task/README.md`, `task/BACKLOG.md` e `docs/roadmap.md` com as fases 19 a 22: o `task/README.md` já as lista (estrutura e abertura), mas a tabela "Resumo" do `BACKLOG.md` para na fase 14 (total 80) e o `roadmap.md` não tem fase acima de 11. Somar a coluna Est. de cada `README.md` de fase; acrescentar `24`, `25` e `26` ao índice de `docs/README.md`.
- [ ] Coluna Status dos quatro `README.md` de fase e o campo Status de cada tarefa refletem a realidade (`done`, `review`, `blocked`, `todo`).
- [ ] Seção `[Não lançado]` do `CHANGELOG.md` revisada: uma entrada por tarefa concluída, nenhuma por tarefa não concluída, números iguais aos de `docs/26-resultados-v2.md`. Sem subir versão, sem tag.

## Fora de escopo

- Decidir o que anunciar, trocar o padrão do perfil `slim` (0157), rodar o A/B com chamadas reais (0162), ligar o auto-update (0192) ou baixar modelos grandes (0169).
- Implementar o que ficou incompleto: abrir tarefa nova, não improvisar.
- Subir versão, criar tag, push ou release (regra 9 do prompt do loop).
- Refazer a auditoria 24 ou reabrir o que a spec 25 (seção 4.2) decidiu não fazer.

## Critérios de aceite

- [ ] Toda linha S1 a S14 tem Medido preenchido com número e comando reproduzível, ou `n/a` com motivo; nenhuma linha em branco.
- [ ] Reexecutar três linhas escolhidas ao acaso do relatório (um S de velocidade, um de tokens, um do painel) reproduz o número dentro da variação que a auditoria 24 já admite (tempos oscilam 2 a 3 vezes no Windows): registrar as três em Andamento.
- [ ] S12 é critério de correção, não de tempo: o teste de propriedade da 0135 passa e o relatório cita o arquivo de teste.
- [ ] Nenhuma divergência restante: `ragx mcp tools --json` bate com `README.md` e `docs/09-mcp.md`; a contagem de testes de `AGENTS.md` bate com a coleta do `pytest`.
- [ ] `git status` mostra só `docs/`, `task/`, `README.md`, `AGENTS.md`, `CHANGELOG.md` e `src/app/README.md` alterados; **nenhum arquivo de `knowledge/` no commit** (se um comando o regravar, não inclua).
- [ ] Status final da tarefa: `review`.

## Testes

- [ ] Nenhum teste novo de código. A verificação é executar as suítes existentes e os comandos de medição.
- [ ] Se algum comando de medição for reaproveitável, cite no relatório o teste ou script que já o cobre (por exemplo o conjunto de avaliação de `tests/eval`), em vez de criar outro.

## Notas

- Os SLOs são medidos "no corpus do próprio repositório (aproximadamente 6,6k chunks) numa máquina de desenvolvimento" (spec 25, seção 3). Se o corpus mudou de tamanho, diga quanto e meça de novo; a máquina da auditoria era Windows, GPU AMD, com carga variável, então o relatório declara a máquina e não promete o mesmo número em outra.
- S13 e S14 são de **medição**: S13 fica "medida e visível no painel" (a meta se fixa depois de 2 semanas de dados); S14 só existe com A/B real.
- Princípio 4 da spec: sem número antes e depois no CHANGELOG, a tarefa não está pronta; esta é a hora de achar as que faltaram.
- Este arquivo não tem comando de medição próprio de propósito: os comandos moram na seção Medição de cada tarefa de origem, e duplicá-los aqui os deixaria desatualizados.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Relatório `docs/26-resultados-v2.md` escrito com a tabela S1–S14 (hoje / meta / medido / status) e o método de cada medição
- [ ] Documentação conferida contra o código: `docs/09-mcp.md`, `docs/14-cli.md`, `docs/05-busca.md`, `docs/12-git-sync.md`, `docs/08-dictionary.md`, `README.md`, `src/app/README.md`, `AGENTS.md` (contagem de testes, de ferramentas MCP, comandos)
- [ ] `task/README.md`, `task/BACKLOG.md` e `docs/roadmap.md` atualizados com as fases 19–22
- [ ] CHANGELOG com a seção da v2 coerente com o que foi entregue
- [ ] Commit `docs(v2): resultados e fechamento (RAGX-0195)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
