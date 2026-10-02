# RAGX-0195 — Fechar a v2: medir S1 a S14, publicar o relatório e conferir a documentação

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | todas as P0 e P1 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) · [25-spec-v2.md](../../docs/25-spec-v2.md) (seção 3, SLOs S1 a S14) · [ROTEIRO-V2.md](../ROTEIRO-V2.md) |
| **Status** | `review` |

## Objetivo

A v2 promete três coisas (gastar menos tokens, não deixar o Claude lento, nunca raciocinar sobre código velho) e a spec 25 as traduz em 14 SLOs. Cada tarefa registrou o seu número antes e depois, mas ninguém reuniu os números, repetiu a medição com o código final nem conferiu se a documentação ainda diz a verdade (`README.md:72` fala em "33 ferramentas", `AGENTS.md:45` em "1087 testes"). Esta tarefa mede S1 a S14 de novo, escreve `docs/26-resultados-v2.md` e confere a documentação contra o código. **Não decide nada de produto**: o que anunciar, o padrão do perfil `slim` e rodadas que gastam cota são decisões de uma pessoa, e a tarefa termina em `review`.

## Entregáveis

- [x] Reler a seção **Medição** de cada tarefa feita e rodar os comandos que ela definiu, com o código final da branch `feat/v2`. Mapa de SLO para tarefa: S1 → 0154 (e 0165) · S2 → 0157 (com 0155 e 0158) · S3 → 0111 da fase 14 · S4 → 0129, 0130 (e 0139) · S5 → 0131 (e 0140) · S6 → 0140 e 0141 · S7 e S8 → 0143 · S9 → 0142 · S10 → 0134 · S11 → 0171, 0172, 0173 (linha de base na 0177) · S12 → 0135 · S13 → 0190 (e 0156) · S14 → 0162 (e 0163).
- [x] `docs/26-resultados-v2.md` (novo) com a tabela **S1 a S14** nas colunas Hoje, Meta, Medido, Status e Método (comando exato, corpus, máquina, data, commit). Status só pode ser `atingida`, `não atingida` ou `n/a — tarefa X não concluída` (ou `n/a — <motivo>`). Seção "Fora do que a v2 prometeu" listando tarefas em `review` ou `blocked` e o que falta uma pessoa decidir.
- [x] (S3 e S14 ficaram `n/a`; S11 foi medido com 12 projetos de fixture, não com os do hub real) Onde a medição não puder ser feita, escrever `n/a` e o motivo: S3 se a 0111 (fase 14, pendente) não entrou; S14 se o A/B real da 0162 não foi rodado (o harness entrega só `--dry-run` e simulado, de propósito); S11 com menos projetos no hub do que os 12 do enunciado (registrar quantos havia, sem extrapolar). **Nenhum número não medido entra no relatório, no CHANGELOG ou no README.**
- [x] Suítes completas com os números do relatório: `uv run ruff check .`, `uv run mypy src/ragx/core src/ragx/security`, `uv run pytest -m "not slow"`, `uv run pytest tests/security`, e em `src/app` `npm test`, `npm run lint`, `npx tsc -p tsconfig.app.json --noEmit` e `npx tsc -p tsconfig.electron.json --noEmit`.
- [x] Documentação conferida contra o código, corrigindo o que divergir: `docs/09-mcp.md` e `README.md:72` (contar com `ragx mcp tools --json`, o mesmo comando do `release.yml`; descrever o perfil `full` e o `slim`), `docs/14-cli.md` (comandos novos contra `ragx --help`), `docs/05-busca.md` (cache de `load_index`, `degraded`, `stale_paths`), `docs/12-git-sync.md` (clone novo e `knowledge/` estável), `docs/08-dictionary.md` (só promete níveis se a 0111 entrou), `src/app/README.md` (telas novas, preferências, atualização; a tabela de tarefas diz "16 tipos", mas `JobKind` em `src/types/ragx-bridge.d.ts:114-131` tem 17, com `ragx-install`), `AGENTS.md:45` (contagem com `uv run pytest -m "not slow" --collect-only -q`).
- [x] `task/README.md`, `task/BACKLOG.md` e `docs/roadmap.md` com as fases 19 a 22: o `task/README.md` já as lista (estrutura e abertura), mas a tabela "Resumo" do `BACKLOG.md` para na fase 14 (total 80) e o `roadmap.md` não tem fase acima de 11. Somar a coluna Est. de cada `README.md` de fase; acrescentar `24`, `25` e `26` ao índice de `docs/README.md`.
- [x] Coluna Status dos quatro `README.md` de fase e o campo Status de cada tarefa refletem a realidade (`done`, `review`, `blocked`, `todo`).
- [x] Seção `[Não lançado]` do `CHANGELOG.md` revisada: uma entrada por tarefa concluída, nenhuma por tarefa não concluída, números iguais aos de `docs/26-resultados-v2.md`. Sem subir versão, sem tag.

## Fora de escopo

- Decidir o que anunciar, trocar o padrão do perfil `slim` (0157), rodar o A/B com chamadas reais (0162), ligar o auto-update (0192) ou baixar modelos grandes (0169).
- Implementar o que ficou incompleto: abrir tarefa nova, não improvisar.
- Subir versão, criar tag, push ou release (regra 9 do prompt do loop).
- Refazer a auditoria 24 ou reabrir o que a spec 25 (seção 4.2) decidiu não fazer.

## Critérios de aceite

- [x] Toda linha S1 a S14 tem Medido preenchido com número e comando reproduzível, ou `n/a` com motivo; nenhuma linha em branco.
- [x] Reexecutar três linhas escolhidas ao acaso do relatório (um S de velocidade, um de tokens, um do painel) reproduz o número dentro da variação que a auditoria 24 já admite (tempos oscilam 2 a 3 vezes no Windows): registrar as três em Andamento.
- [x] S12 é critério de correção, não de tempo: o teste de propriedade da 0135 passa e o relatório cita o arquivo de teste.
- [x] Nenhuma divergência restante: `ragx mcp tools --json` bate com `README.md` e `docs/09-mcp.md`; a contagem de testes de `AGENTS.md` bate com a coleta do `pytest`.
- [x] `git status` mostra só `docs/`, `task/`, `README.md`, `AGENTS.md`, `CHANGELOG.md` e `src/app/README.md` alterados; **nenhum arquivo de `knowledge/` no commit** (se um comando o regravar, não inclua).
- [x] Status final da tarefa: `review`.

## Testes

- [x] Nenhum teste novo de código. A verificação é executar as suítes existentes e os comandos de medição.
- [x] Se algum comando de medição for reaproveitável, cite no relatório o teste ou script que já o cobre (por exemplo o conjunto de avaliação de `tests/eval`), em vez de criar outro.

## Notas

- Os SLOs são medidos "no corpus do próprio repositório (aproximadamente 6,6k chunks) numa máquina de desenvolvimento" (spec 25, seção 3). Se o corpus mudou de tamanho, diga quanto e meça de novo; a máquina da auditoria era Windows, GPU AMD, com carga variável, então o relatório declara a máquina e não promete o mesmo número em outra.
- S13 e S14 são de **medição**: S13 fica "medida e visível no painel" (a meta se fixa depois de 2 semanas de dados); S14 só existe com A/B real.
- Princípio 4 da spec: sem número antes e depois no CHANGELOG, a tarefa não está pronta; esta é a hora de achar as que faltaram.
- Este arquivo não tem comando de medição próprio de propósito: os comandos moram na seção Medição de cada tarefa de origem, e duplicá-los aqui os deixaria desatualizados.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo): todos rodados, mas o **S4 não foi atingido** (7,69 s contra 1,5 s em 20 mil arquivos) e S2 só vale no `slim`; o relatório diz isso, e a decisão é de uma pessoa
- [x] Relatório `docs/26-resultados-v2.md` escrito com a tabela S1–S14 (hoje / meta / medido / status) e o método de cada medição
- [x] Documentação conferida contra o código: `docs/09-mcp.md`, `docs/14-cli.md`, `docs/05-busca.md`, `docs/12-git-sync.md`, `docs/08-dictionary.md`, `README.md`, `src/app/README.md`, `AGENTS.md` (contagem de testes, de ferramentas MCP, comandos)
- [x] `task/README.md`, `task/BACKLOG.md` e `docs/roadmap.md` atualizados com as fases 19–22
- [x] CHANGELOG com a seção da v2 coerente com o que foi entregue
- [x] Commit `docs(v2): resultados e fechamento (RAGX-0195)` na branch `feat/v2` (local, sem push, sem tag)

## Andamento

- 2026-10-02 — **Medi de novo, com o código final** (`d087721` mais as correções de documentação), e escrevi `docs/26-resultados-v2.md` com a tabela S1 a S14 (Hoje, Meta, Medido, Status, Método). **Resultado: 10 atingidos** (S1, S5, S6, S7, S8, S9, S10, S11, S12, S13), **S2 não atingida no padrão** (`full` 2.680 tokens; 370 só com `--profile slim`, decisão da 0157), **S4 não atingida** (7,69 s com 20 mil arquivos sintéticos contra 1,5 s; 0,21 s no repo real), **S3 e S14 `n/a`** (RAGX-0111 pendente; A/B real não rodado).
- **O achado que a v2 não entregou: S4 em 20 mil arquivos.** O projeto sintético (`scripts/medir_indice_inicial.py --arquivos 20000 --provider hashing --jobs 4 --segunda-rodada`) levou 120,9 s no primeiro índice e 7,69 s na rodada sem mudança, o limite inferior do que a auditoria mediu (7,6 a 15 s). Não investiguei a causa (suspeita: `stat` de 20 mil arquivos no NTFS com antivírus, ~0,4 ms cada, sem poda de dependências para ajudar). Proponho tarefa nova, não improvisei.
- **Três linhas reproduzidas** (critério de aceite): S1 3.004 para 2.958 tokens (−1,5%), S7 86 para 75 ms, S11 ~4 filhos/min visível e 0 oculta (≈4,1 e 0): todas dentro da variação. As cinco medições de velocidade foram feitas em sequência, sem a máquina ociosa; os tempos do Windows oscilam, como a auditoria já dizia.
- **Suítes**: `ruff` e `mypy` limpos; `pytest -m "not slow"` 1.945 passaram e 5 ignorados (1.950 coletados); `tests/security` 147 passaram; `npm run check` verde (vitest 1.921) e `tsc` do Electron limpo. Antes de o relatório existir, 3 testes de links de `test_documentacao.py` apontavam para o `26-resultados-v2.md` e falharam; depois de escrevê-lo, passaram.
- **Documentação corrigida**: `AGENTS.md` (1087 para 1950 testes); `README.md` (33 ferramentas no `full`, `--profile slim` expõe 6); `docs/09-mcp.md` (slim ~360 para ~370 tokens); `docs/05-busca.md` ganhou a seção `stale_paths`; `src/app/README.md` (17 tipos de tarefa, com `ragx-install`); `task/BACKLOG.md`, `docs/roadmap.md` e `docs/README.md` (fases 19 a 22, 24, 25 e 26). Conferidos sem divergência: `docs/14-cli.md` contra `ragx --help` (todos os comandos de topo presentes; `ragx worktree status` já entrou na 0170), `docs/09-mcp.md` contra `ragx mcp tools --json` (33), `docs/12-git-sync.md` e `docs/08-dictionary.md` (só promete níveis se a 0111 entrou: não promete). Status de cada tarefa e linha do README de fase: 0 divergências (script).
- **Desvios e cuidados**: (1) o script `measure-runtime.mjs` acrescenta uma seção a `src/app/docs/medicao-runtime.md`; reverti esse arquivo para o `git status` ficar só nos arquivos que o critério lista, e o relatório cita os números. (2) S11 foi medido com 12 repositórios `git init` de fixture, o plano da própria 0177, não com os projetos do hub real. (3) S6 e S5 usam projeto sintético e o `README.md` (editado e revertido). (4) Nenhum arquivo de `knowledge/` foi alterado. (5) Nada de push, tag ou release.
- **Fica para uma pessoa**: o que anunciar; trocar o padrão para `slim` (0157); o A/B real (0162); ligar o auto-update (0192); aceitar a queda do MRR do grafo (0145); aceitar o corte de 47% da 0151 (a implementação está na branch local `wip/ragx-0151-grafo-incremental`); aceitar a 0170 sem semente; desbloquear a fase 14 (0104, 0099, 0111) para liberar 0166 a 0169; e decidir se o S4 em 20 mil arquivos vira tarefa.

