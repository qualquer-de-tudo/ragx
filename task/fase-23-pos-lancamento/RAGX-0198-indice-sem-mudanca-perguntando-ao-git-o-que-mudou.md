# RAGX-0198 — Índice sem mudança: perguntar ao git o que mudou, em vez de varrer todos os arquivos

| | |
|---|---|
| **Fase** | 23 — Pós-lançamento |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0196 |
| **Documentação** | [26-resultados-v2.md](../../docs/26-resultados-v2.md) (S4) · [04-indexacao.md](../../docs/04-indexacao.md) · [02-seguranca.md](../../docs/02-seguranca.md) · [27-benchmarks.md](../../docs/27-benchmarks.md) |
| **Status** | `todo` |

## Objetivo

A meta S4 (índice sem mudança em um repositório de ~20 mil arquivos em **≤ 1,5 s**) não foi atingida: a rodada leva ~3,7 s, e a RAGX-0196 mostrou que o custo é **por arquivo, em Python** (`stat` 1,3 s, regras de ignore 1,5 s, `pathlib` ~1,2 s no perfil), sem atalho seguro dentro da varredura. Esta tarefa troca a pergunta: em vez de olhar cada arquivo, **perguntar ao git o que mudou**. Medido num repositório sintético de 20.000 arquivos sem mudança, `git status --porcelain=v2 --branch --untracked-files=normal` leva **138 ms** e `git diff --name-only HEAD`, 133 ms (git 2.53 no Windows, sem `fsmonitor`), contra os ~3.700 ms da varredura.

O RAGX já usa o git em dois lugares: o hook de edição (`ragx touch` reindexa só o arquivo editado) e a contagem de arquivos defasados (`gitinfo.changed_paths`, `indexing/freshness.py`). Falta o caminho da indexação completa (`index_project`: hook de commit e de checkout, `ragx index`, refresh), que ainda passa por todos os arquivos.

## Entregáveis

- [ ] **Medir primeiro, num caso real**: o número de 138 ms é de um repositório sintético simples. Medir `git status` e a varredura atual no repositório do RAGX (~850 arquivos), no `sturdy-bassoon` (3.480, monorepo com `node_modules` ignorado e `.gitignore` aninhado) e num sintético de 20 mil com pastas ignoradas. Registrar em Medição
- [ ] Guardar, no fim de cada indexação, o **commit** em que o índice está (já há `finished_at`/`commit` no status; conferir o que o banco guarda hoje e acrescentar em `meta` se faltar)
- [ ] Caminho rápido em `index_project`: com git disponível, repositório sem mudança de regras e o commit anterior conhecido, a lista de candidatos é `git diff --name-only <commit-do-índice> HEAD` mais `git status` (alterados, novos e apagados), **sem** `iter_candidates` sobre a árvore toda. Quem decide o que entra continua sendo o mesmo pipeline por arquivo (ignore, Security Gate, parser)
- [ ] **Recuo para a varredura completa** (sem tentar adivinhar) quando: não é repositório git; o `git` falha ou passa de um limite de tempo; o commit guardado não existe mais (rebase, `gc`); o conjunto de regras mudou (`.ragignore`, `ruleset`, `max_file_bytes`, versão do chunker); há submódulo ou link simbólico na lista; ou a pessoa pede (`ragx index --full-scan`)
- [ ] Coerência com as regras de ignore do RAGX: arquivo que o git ignora e o RAGX também ignora fica de fora nos dois caminhos; arquivo que o RAGX indexa mas o git ignora (negação em `.gitignore`, regra só do `.ragignore`) **precisa** sobreviver, então o caminho rápido compara com o que a varredura acharia numa amostra e a suíte inclui esses casos
- [ ] Teste de equivalência: em repositórios de teste (com arquivos novos, apagados, renomeados, ignorados, binários, grandes, segredos), o conjunto indexado pelo caminho rápido é **idêntico** ao da varredura completa
- [ ] Medir depois e atualizar `benchmarks.json` e `docs/26-resultados-v2.md` (S4) com o número real, atingindo ou não a meta

## Fora de escopo

- Trocar o `pathspec`/`IgnoreEngine` ou mexer em qualquer decisão do Security Gate: o Gate continua rodando em cada arquivo que entra na fila, antes do parser (ver `docs/02-seguranca.md`). Só muda **quais** arquivos entram na fila
- Reaproveitar o hash de blob do git como `content_hash` do RAGX (são hashes diferentes; o sinal usado é o mesmo do cache de `stat` do próprio git)
- `core.fsmonitor`, `watchman` ou qualquer daemon de observação de arquivos
- Projeto que não é repositório git (continua na varredura)

## Critérios de aceite

- [ ] Rodada sem mudança em 20 mil arquivos **≤ 1,5 s** (ou o número real, dito como está, se não chegar)
- [ ] O conjunto de arquivos indexados é idêntico ao da varredura completa nos casos de teste; todo recuo listado acima tem teste
- [ ] `tests/security` verde sem alteração; nenhum arquivo chega ao parser sem passar pelo Gate
- [ ] Funciona e tem teste em Windows, Linux e macOS (CRLF, caminhos com espaço e acento, `core.quotepath`)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Rodada sem mudança, 20.000 arquivos sintéticos (varredura) | ~3.700 ms (`scripts/medir_varredura.py`: 2,97 a 3,09 s só o `iter_candidates`) | medir |
| `git status` no mesmo repositório | **138 ms** (3 execuções), `git diff --name-only HEAD` 133 ms, `git ls-files -s` 182 ms | medir no real |
| Repositório do RAGX (~850 arquivos) | 0,21 s | medir |
| `sturdy-bassoon` (3.480 arquivos) | ~2,1 s (`ragx index .`, incremental) | medir |

## Testes

- [ ] Equivalência caminho rápido × varredura em repositório de teste (novo, apagado, renomeado, ignorado, binário, grande, segredo)
- [ ] Cada recuo: sem git, `git` que falha ou demora, commit sumido, regras mudadas, submódulo, link simbólico, `--full-scan`
- [ ] Negação em `.gitignore` e regra só do `.ragignore`
- [ ] Caminhos com espaço, acento e `core.quotepath`; fim de linha CRLF

## Andamento

- 2026-10-02 — Registrada. Origem: pergunta da pessoa depois de a RAGX-0196 fechar em `review` sem otimização segura ("não dá para usar o git para ver o hash do arquivo, sem passar por tudo?"). A medição do `git status` (138 ms contra ~3.700 ms) mostra que o caminho vale a tarefa; não foi implementado nada ainda. Para a rotina da pessoa o ganho é pequeno (no `sturdy-bassoon` a atualização leva ~2 s, em segundo plano, no hook), então fica como P3.
