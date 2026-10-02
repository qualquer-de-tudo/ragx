# RAGX-0170 — Índice por worktree/branch com chunks compartilhados por hash

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0138` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #12) · [04-indexacao.md](../../docs/04-indexacao.md) · [12-git-sync.md](../../docs/12-git-sync.md) · [adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `review` |

## Objetivo

Agentes em paralelo trabalham em `git worktree`s do mesmo repositório (o próprio `walk.py:150` e o `IgnoreEngine` já citam worktrees em `.claude/worktrees/`), e **cada worktree sobe um índice do zero**: `state_dir` é `<raiz>/.ragx` (`config.py:208`), então o banco, o cache de embedding (`indexing/embed.py:90`, `state_dir/cache`) e o cache de modelos (251 MB neste repo, `embeddings/__init__.py:81`) são por pasta. O primeiro índice custa 30 s para 3,6 mil chunks e 155 s para 18,5 mil (auditoria 24, seção 5), quase tudo de conteúdo **idêntico** ao do worktree irmão. Não há suporte a worktree no código (`grep worktree src/ragx` só acha comentários). A aposta 12 não tem fonte consolidada **[I]**: o primeiro entregável é medir.

## Entregáveis

- [x] **Medir primeiro**, em um clone local temporário (`git clone --local`, **nunca** no repo real): tempo e chunks embutidos do primeiro `ragx index` num `git worktree add` novo, o custo de trocar de branch no mesmo worktree, e se o `post-checkout` de um worktree dispara a indexação da raiz **principal** (o bloco do hook usa `--root` da raiz onde foi instalado, `githooks.py:63-71`). Registrar em Andamento
- [x] `gitinfo.py`: `common_dir(root)` (`git rev-parse --git-common-dir`) e `worktrees(root)` (`git worktree list --porcelain`); ambos devolvem `None`/lista vazia fora de git, como o resto do módulo
- [x] Cache de embedding compartilhado: `EmbeddingCache` (`embeddings/base.py:73`) passa a gravar em `<common_dir>/ragx/cache` quando houver git, **lendo** também do local antigo para não perder os vetores já gravados; fora de git ou em erro, comportamento atual. A chave é o hash do texto embutido (a mesma da `RAGX-0166`; se ela ainda não entrou, a chave atual por `content_hash`)
- [ ] **NÃO FEITO, de propósito** (a nota da tarefa manda pular se o cache sozinho passar do alvo: passou, 7,4 s = 5% do índice a frio contra o corte de 25%). Semente do índice: `ragx index` numa raiz **sem documentos** e com worktree irmão do mesmo `project.id`, mesma `chunker_version` e mesma `SCHEMA_VERSION` copia o banco irmão com a API de backup do SQLite, apaga `index_runs` e `security_events`, e segue o índice incremental normal
- [ ] **NÃO FEITO** (depende da semente). A primeira rodada de um banco semeado **ignora o atalho de size+mtime** (`fingerprints=None`, `pipeline.py:173`): todo arquivo passa pelo Security Gate e pelo hash; um arquivo que o gate bloqueia aqui sai do banco (ramo `BLOCK`, `pipeline.py:197-206`), e um arquivo que o irmão tinha e este não tem sai por `gone` (`:271`)
- [ ] **NÃO FEITO** (só existia por causa da semente; não medi se o ramo "mesmo hash" já atualiza `size`/`mtime`). Hash igual não deixa o fingerprint velho: no ramo "mesmo hash" (`pipeline.py:213-220`) atualizar `size_bytes`/`mtime_ns` do documento. Hoje um arquivo com `mtime` novo e conteúdo igual é relido e reavaliado em **toda** rodada; sem isto, o banco semeado releria o repositório inteiro para sempre. Conferir antes se a `RAGX-0140` já cobriu
- [x] `ragx worktree status [--json]` mostra, por worktree, quantos chunks distintos compartilha com a raiz consultada e o tamanho do cache; documentar em `docs/04-indexacao.md` e `docs/14-cli.md`

## Fora de escopo

- **Um banco por branch** dentro do mesmo worktree: o índice por hash + incremental já torna a troca de branch barata (medir); não criar `.ragx/<branch>/`
- Registrar worktrees no hub: `hub.register` faz upsert por `project.id` (`federation/hub.py:109,159`), então dois worktrees do mesmo projeto se sobrescrevem; decidir isso é outra tarefa
- Cache de modelos por usuário e trava com PID reutilizado (`RAGX-0153`)
- Mudar IDs de chunk ou `CHUNKER_VERSION`; mudar o conteúdo de `knowledge/`

## Critérios de aceite

- [x] No clone de teste, o primeiro `ragx index` de um worktree novo leva **≤ 25%** do índice a frio (7,4 s contra 150,6 s = 5%) e não reembute chunk igual ao do irmão; sem semente, pelo cache compartilhado. O "≤ 5% embutidos" vale só como "0 chamadas ao modelo para chunk idêntico" (teste com embedder contado); o campo `embedded` do `ragx index --json` conta vetores gravados, inclusive os vindos do cache
- [x] Mesmo sem semente (cache compartilhado apenas), o reembed do worktree novo é **0** para chunk de conteúdo idêntico
- [ ] Segurança: arquivo que está no banco do irmão e é bloqueado no worktree novo **não** existe em `documents` depois do primeiro índice (teste em `tests/security`); nenhum segredo novo entra. **Sem semente o cenário não existe** (o banco do worktree novo nasce do zero e passa pelo Gate inteiro); o que o cache compartilhado leva entre worktrees são vetores por hash de texto JÁ admitido pelo Gate
- [x] Um repositório sem git, ou com `common_dir` ilegível, indexa exatamente como hoje (testes atuais verdes)
- [x] O índice do worktree irmão não é alterado (compara `embeddings` e `documents` antes e depois)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Primeiro `ragx index` em worktree novo (tempo) | 127,3 s (clone local, fastembed, 9 mil chunks; índice a frio do clone 118,5 s = 107%) | 7,4 s (índice a frio do clone nessa rodada 150,6 s = 5%) |
| Chunks embutidos no worktree novo | 9.025 de 9.025 (todos) | 0 chamadas ao modelo para chunk idêntico ao do irmão (teste com embedder contado) |
| Rodada seguinte, sem mudança, com 100 arquivos "tocados" | 1,0 s (840 `unchanged`); troca de branch no mesmo worktree: 11,3 s (ida, 317 chunks embutidos) e 4,7 s (volta) | 0,9 s; troca de branch 7,2 s e 4,6 s. Não medi "100 arquivos tocados" (só a rodada sem mudança) |

Comando: `git clone --local . $TMP/r && cd $TMP/r && git worktree add ../w1 HEAD~5 && cd ../w1 && time uv run ragx index .`

## Testes

- [x] `tests/unit/test_gitinfo.py`: `common_dir` e `worktrees` num repo temporário com um `git worktree add`; fora de git devolvem vazio
- [x] `tests/unit/test_embedder_cache.py`: cache compartilhado lido por duas raízes; fallback local intacto
- [ ] **NÃO FEITO** (semente). `tests/integration/test_pipeline.py`: semente copia o banco irmão, limpa `index_runs`, indexa só o que mudou e remove o que saiu
- [ ] **NÃO FEITO** (semente). `tests/security/test_gate.py`: arquivo permitido no irmão e bloqueado no novo worktree some do banco semeado

## Notas

Armadilha: `.git` num worktree é um **arquivo** (`gitdir: ...`), nunca assuma pasta; use `git rev-parse`. O cache em `.git/ragx/` não é versionado nem sai do clone. A semente só vale com o mesmo `chunker_version`; opções de chunk diferentes entre branches (`[chunk]` no `ragx.toml`) podem deixar chunks fora do tamanho novo, risco já existente no incremental e aceito aqui. Se a medição mostrar que o cache compartilhado sozinho já leva o índice novo a ≤ 25% do tempo, entregar só ele e pular a semente (registrar o motivo).

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0170)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **Medido primeiro** (`scripts/medir_worktree.py`, novo; clone local temporário, HOME redirecionado, cache de modelos do repo só para leitura): índice a frio do clone 118,5 s (9.121 chunks); primeiro índice de um `git worktree add HEAD~5` 127,3 s com TODOS os 9.025 chunks reembutidos (107% do a frio); rodada seguinte sem mudança 1,0 s; troca de branch no mesmo worktree 11,3 s (ida) e 4,7 s (volta). **O `post-checkout` de um `git worktree add` indexa a raiz PRINCIPAL e não o worktree novo** (o bloco do hook usa o `--root` de onde foi instalado): confirmado, o `knowledge.db` do worktree novo não foi criado e o `status.json` da principal mudou. Documentado; não corrigi (fora do escopo).
- **Decisão pela nota da tarefa**: entreguei só o cache de embedding compartilhado e pulei a semente de banco. Depois: worktree novo 7,4 s contra 150,6 s a frio (5%, alvo ≤ 25%), sem reembutir chunk idêntico. A semente também traria o risco de herdar um documento que o Gate do worktree novo bloquearia, e exigiria `fingerprints=None` na primeira rodada: complexidade que o número não pede. Se um dia o custo de ler/Gate/parse do worktree novo importar (7,4 s), é outra tarefa.
- **Feito**: `gitinfo.common_dir` e `gitinfo.worktrees` (via `git`; testados num worktree real, onde `.git` é arquivo); `EmbeddingCache(..., also_read=[...])` (lê SQLite alheio em modo `ro` e o formato antigo por arquivo, importa o achado, ignora a própria raiz e cache ilegível); `indexing.embed.shared_cache_root` / `_abrir_cache` (`<.git comum>/ragx/cache` lendo também o local; se a pasta comum não abrir, o cache local de sempre; fora de git, igual a hoje); `ragx.worktrees.report` e `ragx worktree status [--json]`. A pasta `.git` comum no caminho de indexação é lida dos metadados do git (`_pasta_git_comum`: `.git` pasta, ou arquivo `gitdir:` + `commondir`), SEM subprocesso, porque `test_index_paths` proíbe o `git` na reindexação por caminho (RAGX-0140); um teste confere que bate com `git rev-parse --git-common-dir` no principal, num worktree e numa subpasta.
- **Testes**: `test_worktree_cache.py` (13: cache com `also_read`, dois worktrees se ajudando, formato antigo, cache alheio corrompido, worktree real com 0 chamadas ao modelo, chunk editado embute só ele, índice do irmão intacto, fora de git, pasta comum sem permissão cai no local, `worktree status` com chunks em comum e a CLI, pasta comum sem subprocesso), `test_gitinfo.py` (+3). Dois testes de arquitetura reclamaram e foram ajustados: `ragx.worktrees` entrou na lista de leitores de artefatos próprios (só abre `.ragx/knowledge.db` e lista `emb/*.sqlite`) e o caminho por arquivo continua sem git. Suíte `-m "not slow"` 1945 passed, `tests/security` verde, `ruff`, `mypy`.
- **Achado fora do escopo**: `test_editar_uma_funcao_toca_poucos_arquivos_e_atualiza_o_generated_at` (da 0148) falhava às vezes porque `generated_at` tem resolução de 1 s e os dois `sync` caíam no mesmo segundo; o teste agora espera 1,1 s.
- **Não verificado**: Linux e macOS; mais de dois worktrees concorrentes escrevendo no mesmo cache (SQLite com WAL e `busy_timeout`, como o cache local, mas não testei concorrência entre processos); `ragx worktree status` num repo grande com muitos worktrees (abre o banco de cada um em leitura).

