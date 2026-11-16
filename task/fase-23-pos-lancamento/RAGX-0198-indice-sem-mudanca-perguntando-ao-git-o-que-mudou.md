# RAGX-0198 — Índice sem mudança: perguntar ao git o que mudou, em vez de varrer todos os arquivos

| | |
|---|---|
| **Fase** | 23 — Pós-lançamento |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0196 |
| **Documentação** | [26-resultados-v2.md](../../docs/26-resultados-v2.md) (S4) · [04-indexacao.md](../../docs/04-indexacao.md) · [02-seguranca.md](../../docs/02-seguranca.md) · [27-benchmarks.md](../../docs/27-benchmarks.md) |
| **Status** | `review` |

## Objetivo

A meta S4 (índice sem mudança em um repositório de ~20 mil arquivos em **≤ 1,5 s**) não foi atingida: a rodada leva ~3,7 s, e a RAGX-0196 mostrou que o custo é **por arquivo, em Python** (`stat` 1,3 s, regras de ignore 1,5 s, `pathlib` ~1,2 s no perfil), sem atalho seguro dentro da varredura. Esta tarefa troca a pergunta: em vez de olhar cada arquivo, **perguntar ao git o que mudou**. Medido num repositório sintético de 20.000 arquivos sem mudança, `git status --porcelain=v2 --branch --untracked-files=normal` leva **138 ms** e `git diff --name-only HEAD`, 133 ms (git 2.53 no Windows, sem `fsmonitor`), contra os ~3.700 ms da varredura.

O RAGX já usa o git em dois lugares: o hook de edição (`ragx touch` reindexa só o arquivo editado) e a contagem de arquivos defasados (`gitinfo.changed_paths`, `indexing/freshness.py`). Falta o caminho da indexação completa (`index_project`: hook de commit e de checkout, `ragx index`, refresh), que ainda passa por todos os arquivos.

## Entregáveis

- [x] **Medir primeiro, num caso real**: o número de 138 ms é de um repositório sintético simples. Medir `git status` e a varredura atual no repositório do RAGX (~850 arquivos), no `sturdy-bassoon` (3.480, monorepo com `node_modules` ignorado e `.gitignore` aninhado) e num sintético de 20 mil com pastas ignoradas. Registrar em Medição
- [x] Guardar, no fim de cada indexação, o **commit** em que o índice está (já há `finished_at`/`commit` no status; conferir o que o banco guarda hoje e acrescentar em `meta` se faltar)
- [x] Caminho rápido em `index_project`: com git disponível, repositório sem mudança de regras e o commit anterior conhecido, a lista de candidatos é `git diff --name-only <commit-do-índice> HEAD` mais `git status` (alterados, novos e apagados), **sem** `iter_candidates` sobre a árvore toda. Quem decide o que entra continua sendo o mesmo pipeline por arquivo (ignore, Security Gate, parser)
- [x] **Recuo para a varredura completa** (sem tentar adivinhar) quando: não é repositório git; o `git` falha ou passa de um limite de tempo; o commit guardado não existe mais (rebase, `gc`); o conjunto de regras mudou (`.ragignore`, `ruleset`, `max_file_bytes`, versão do chunker); há submódulo ou link simbólico na lista; ou a pessoa pede (`ragx index --full-scan`)
- [x] Coerência com as regras de ignore do RAGX: arquivo que o git ignora e o RAGX também ignora fica de fora nos dois caminhos; arquivo que o RAGX indexa mas o git ignora (negação em `.gitignore`, regra só do `.ragignore`) **precisa** sobreviver, então o caminho rápido compara com o que a varredura acharia numa amostra e a suíte inclui esses casos
- [x] Teste de equivalência: em repositórios de teste (com arquivos novos, apagados, renomeados, ignorados, binários, grandes, segredos), o conjunto indexado pelo caminho rápido é **idêntico** ao da varredura completa
- [x] Medir depois e atualizar `benchmarks.json` e `docs/26-resultados-v2.md` (S4) com o número real, atingindo ou não a meta

## Fora de escopo

- Trocar o `pathspec`/`IgnoreEngine` ou mexer em qualquer decisão do Security Gate: o Gate continua rodando em cada arquivo que entra na fila, antes do parser (ver `docs/02-seguranca.md`). Só muda **quais** arquivos entram na fila
- Reaproveitar o hash de blob do git como `content_hash` do RAGX (são hashes diferentes; o sinal usado é o mesmo do cache de `stat` do próprio git)
- `core.fsmonitor`, `watchman` ou qualquer daemon de observação de arquivos
- Projeto que não é repositório git (continua na varredura)

## Critérios de aceite

- [x] Rodada sem mudança em 20 mil arquivos **≤ 1,5 s** (ou o número real, dito como está, se não chegar): **0,46 s** (mediana de 5), em repositório git
- [x] O conjunto de arquivos indexados é idêntico ao da varredura completa nos casos de teste; todo recuo listado acima tem teste
- [x] `tests/security` verde sem alteração; nenhum arquivo chega ao parser sem passar pelo Gate (teste novo: `tests/security/test_indice_git_gate.py`)
- [ ] Funciona e tem teste em Windows, Linux e macOS (CRLF, caminhos com espaço e acento, `core.quotepath`): os testes existem e passam no Windows; Linux e macOS ficam para o CI. O teste de link simbólico novo é pulado no Windows sem permissão de criar link

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Rodada sem mudança, 20.000 arquivos sintéticos (repositório git com `node_modules/` de 2.000 arquivos e `build/` ignorados, `.gitignore` aninhado) | **4,87 s** (mediana de 3, `index_project` inteiro, `scripts/medir_sem_mudanca.py` no código anterior) | **0,46 s** (mediana de 5; 0,38 a 0,63 s). Na mesma árvore com `full_scan=True`: 4,38 s no melhor caso (mediana 10,2 s com a máquina carregada). Perfil da rodada: git ~0,29 s (2 processos), descoberta dos arquivos de ignore ~0,2 s |
| `git status` no mesmo repositório | **138 ms** (3 execuções), `git diff --name-only HEAD` 133 ms, `git ls-files -s` 182 ms | `status -uall -z` + `ls-files -o -i --directory`: ~0,29 s juntos, dentro da rodada |
| Repositório do RAGX (clone em pasta temporária, 909 documentos, 1.001 arquivos vistos) | 0,51 s (varredura, mediana de 5) | **0,33 s** (mediana de 5). No checkout real (só leitura): `status` 34 ms, `ls-files` dos ignorados 87 ms |
| `sturdy-bassoon` (3.480 arquivos) | ~2,1 s (`ragx index .`, incremental) | sem mudança: a cópia desta máquina **não é repositório git** (não tem `.git`), então continua na varredura (`nao_e_repositorio_git`) |
| Juriflux (17.887 arquivos rastreados; a origem: 10–20 s por hook, máx. 92 s) | — | só o git, sem indexar (só leitura): `status -uall` 74 ms, `ls-files -o -i --directory` 162 ms, `diff` de 3 commits 43 ms, `rev-parse` 29 ms. `status --ignored` levaria 1,1 s: por isso os ignorados vêm do `ls-files` |

## Testes

- [x] Equivalência caminho rápido × varredura em repositório de teste (novo, apagado, renomeado, ignorado, binário, grande, segredo)
- [x] Cada recuo: sem git, `git` que falha ou demora, commit sumido, regras mudadas, submódulo, link simbólico, `--full-scan`
- [x] Negação em `.gitignore` e regra só do `.ragignore`
- [x] Caminhos com espaço, acento e `core.quotepath`; fim de linha CRLF

## Andamento

- 2026-10-02 — Registrada. Origem: pergunta da pessoa depois de a RAGX-0196 fechar em `review` sem otimização segura ("não dá para usar o git para ver o hash do arquivo, sem passar por tudo?"). A medição do `git status` (138 ms contra ~3.700 ms) mostra que o caminho vale a tarefa; não foi implementado nada ainda. Para a rotina da pessoa o ganho é pequeno (no `sturdy-bassoon` a atualização leva ~2 s, em segundo plano, no hook), então fica como P3.
- 2026-11-16 — Implementada, em `review`. O que ficou:
  - **Registro** em `meta` (`git_snapshot`): commit do índice, raiz, resumo das regras (`verdict_context` + `follow_symlinks` + tamanho de chunk + os padrões de TODAS as fontes de ignore carregadas) e uma lista de caminhos para olhar de novo. Sai do banco no começo de cada rodada e só volta no fim de uma que terminou. `index_runs.git_commit` já guardava o commit, mas não dizia se a rodada terminou nem com que regras.
  - **Caminho pelo git** (`gitinfo.mudancas`, `walk.iter_selecao`, `pipeline._planejar`): `status --porcelain=v2 -z --no-renames -uall` (dá também branch, commit e sujeira: o `read_state` da rodada saiu), `diff --raw -z --no-renames <commit> <HEAD>` só quando o commit mudou, e `ls-files -o -i --exclude-standard --directory`. Os candidatos passam pelo mesmo `_decidir` + `read_candidate` (Gate) da varredura; os documentos fora da lista contam como vistos e sem mudança.
  - **A "amostra" virou a lista inteira**: em vez de comparar com a varredura numa amostra, toda rodada olha o que o git ignora e o RAGX ainda alcançaria (arquivo que o RAGX não ignora; pasta que ele não poda, varrida inteira). Cobre negação com caminho no `.gitignore` (`!build/keep.py`, que o git não reinclui e o `pathspec` sim), negação no `.ragignore`, `[index].include` e `.git/info/exclude`/exclusão global, que o RAGX não lê.
  - **Lista para olhar de novo**: o que estava sujo (desfeito com `git checkout` some do `status`), o que entrou por caminho (`index_paths`: `touch`, `watch`), o que foi lido com `mtime` até 2 s antes do início da rodada, ilegíveis e pastas que não abriram, e o que o git ignora e o RAGX indexa.
  - **Recuos** (`IndexReport.scan_fallback`, também em `ragx index --json`): `full`, `full_scan`, `follow_symlinks`, `nao_e_repositorio_git`, `sem_git`, `git_falhou`, `git_demorou` (10 s por chamada), `sem_commit`, `sem_commit_guardado` (primeira rodada, rodada interrompida, `.ragx/` de outra raiz, `ragx import`), `regras_mudaram`, `commit_do_indice_sumiu`, `submodulo` (inclui `.gitmodules`; nesse caso nem o registro é gravado), `link_simbolico`, `nome_nao_utf8`, `caixa_divergente` (Windows/macOS).
  - Limite conhecido, documentado em `docs/04-indexacao.md`: arquivo com `assume-unchanged`/`skip-worktree` alterado no disco não aparece no `status` (`--full-scan` resolve).
  - Testes: `tests/integration/test_index_git.py` (equivalência por cópia da árvore e por varredura logo depois, cada recuo, CLI `--full-scan`), `tests/unit/test_gitinfo.py` (leitura do `status`/`diff`, espaço, acento, `core.quotepath`, CRLF, subpasta), `tests/security/test_indice_git_gate.py`.
  - Esta branch partiu de um commit sem o `_drain_touch_queue` da RAGX-0199; a mudança aqui não mexe em `_drain_pending`, e o `_index_paths_once` que a drenagem usa já acrescenta à lista para olhar de novo.
