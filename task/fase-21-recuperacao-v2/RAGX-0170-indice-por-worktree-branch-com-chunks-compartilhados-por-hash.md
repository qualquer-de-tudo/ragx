# RAGX-0170 — Índice por worktree/branch com chunks compartilhados por hash

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0138` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #12) · [04-indexacao.md](../../docs/04-indexacao.md) · [12-git-sync.md](../../docs/12-git-sync.md) · [adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `todo` |

## Objetivo

Agentes em paralelo trabalham em `git worktree`s do mesmo repositório (o próprio `walk.py:150` e o `IgnoreEngine` já citam worktrees em `.claude/worktrees/`), e **cada worktree sobe um índice do zero**: `state_dir` é `<raiz>/.ragx` (`config.py:208`), então o banco, o cache de embedding (`indexing/embed.py:90`, `state_dir/cache`) e o cache de modelos (251 MB neste repo, `embeddings/__init__.py:81`) são por pasta. O primeiro índice custa 30 s para 3,6 mil chunks e 155 s para 18,5 mil (auditoria 24, seção 5), quase tudo de conteúdo **idêntico** ao do worktree irmão. Não há suporte a worktree no código (`grep worktree src/ragx` só acha comentários). A aposta 12 não tem fonte consolidada **[I]**: o primeiro entregável é medir.

## Entregáveis

- [ ] **Medir primeiro**, em um clone local temporário (`git clone --local`, **nunca** no repo real): tempo e chunks embutidos do primeiro `ragx index` num `git worktree add` novo, o custo de trocar de branch no mesmo worktree, e se o `post-checkout` de um worktree dispara a indexação da raiz **principal** (o bloco do hook usa `--root` da raiz onde foi instalado, `githooks.py:63-71`). Registrar em Andamento
- [ ] `gitinfo.py`: `common_dir(root)` (`git rev-parse --git-common-dir`) e `worktrees(root)` (`git worktree list --porcelain`); ambos devolvem `None`/lista vazia fora de git, como o resto do módulo
- [ ] Cache de embedding compartilhado: `EmbeddingCache` (`embeddings/base.py:73`) passa a gravar em `<common_dir>/ragx/cache` quando houver git, **lendo** também do local antigo para não perder os vetores já gravados; fora de git ou em erro, comportamento atual. A chave é o hash do texto embutido (a mesma da `RAGX-0166`; se ela ainda não entrou, a chave atual por `content_hash`)
- [ ] Semente do índice: `ragx index` numa raiz **sem documentos** e com worktree irmão do mesmo `project.id`, mesma `chunker_version` e mesma `SCHEMA_VERSION` copia o banco irmão com a API de backup do SQLite, apaga `index_runs` e `security_events`, e segue o índice incremental normal
- [ ] A primeira rodada de um banco semeado **ignora o atalho de size+mtime** (`fingerprints=None`, `pipeline.py:173`): todo arquivo passa pelo Security Gate e pelo hash; um arquivo que o gate bloqueia aqui sai do banco (ramo `BLOCK`, `pipeline.py:197-206`), e um arquivo que o irmão tinha e este não tem sai por `gone` (`:271`)
- [ ] Hash igual não deixa o fingerprint velho: no ramo "mesmo hash" (`pipeline.py:213-220`) atualizar `size_bytes`/`mtime_ns` do documento. Hoje um arquivo com `mtime` novo e conteúdo igual é relido e reavaliado em **toda** rodada; sem isto, o banco semeado releria o repositório inteiro para sempre. Conferir antes se a `RAGX-0140` já cobriu
- [ ] `ragx worktree status` (ou `--json` no `ragx status`) mostra, por worktree, quantos chunks compartilha com o irmão; documentar em `docs/04-indexacao.md` e `docs/14-cli.md`

## Fora de escopo

- **Um banco por branch** dentro do mesmo worktree: o índice por hash + incremental já torna a troca de branch barata (medir); não criar `.ragx/<branch>/`
- Registrar worktrees no hub: `hub.register` faz upsert por `project.id` (`federation/hub.py:109,159`), então dois worktrees do mesmo projeto se sobrescrevem; decidir isso é outra tarefa
- Cache de modelos por usuário e trava com PID reutilizado (`RAGX-0153`)
- Mudar IDs de chunk ou `CHUNKER_VERSION`; mudar o conteúdo de `knowledge/`

## Critérios de aceite

- [ ] No clone de teste, o primeiro `ragx index` do worktree semeado embute **≤ 5%** dos chunks (só os que diferem do irmão) e leva **≤ 25%** do índice a frio do mesmo worktree sem semente; ambos os tempos na tabela
- [ ] Mesmo sem semente (cache compartilhado apenas), o reembed do worktree novo é **0** para chunk de conteúdo idêntico
- [ ] Segurança: arquivo que está no banco do irmão e é bloqueado no worktree novo **não** existe em `documents` depois do primeiro índice (teste em `tests/security`); nenhum segredo novo entra
- [ ] Um repositório sem git, ou com `common_dir` ilegível, indexa exatamente como hoje (testes atuais verdes)
- [ ] O índice do worktree irmão não é alterado (compara `embeddings` e `documents` antes e depois)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Primeiro `ragx index` em worktree novo (tempo) | (medir; referência 30 s/3,6 mil chunks) | |
| Chunks embutidos no worktree novo | (medir; hoje todos) | |
| Rodada seguinte, sem mudança, com 100 arquivos "tocados" | (medir) | |

Comando: `git clone --local . $TMP/r && cd $TMP/r && git worktree add ../w1 HEAD~5 && cd ../w1 && time uv run ragx index .`

## Testes

- [ ] `tests/unit/test_gitinfo.py`: `common_dir` e `worktrees` num repo temporário com um `git worktree add`; fora de git devolvem vazio
- [ ] `tests/unit/test_embedder_cache.py`: cache compartilhado lido por duas raízes; fallback local intacto
- [ ] `tests/integration/test_pipeline.py`: semente copia o banco irmão, limpa `index_runs`, indexa só o que mudou e remove o que saiu
- [ ] `tests/security/test_gate.py`: arquivo permitido no irmão e bloqueado no novo worktree some do banco semeado

## Notas

Armadilha: `.git` num worktree é um **arquivo** (`gitdir: ...`), nunca assuma pasta; use `git rev-parse`. O cache em `.git/ragx/` não é versionado nem sai do clone. A semente só vale com o mesmo `chunker_version`; opções de chunk diferentes entre branches (`[chunk]` no `ragx.toml`) podem deixar chunks fora do tamanho novo, risco já existente no incremental e aceito aqui. Se a medição mostrar que o cache compartilhado sozinho já leva o índice novo a ≤ 25% do tempo, entregar só ele e pular a semente (registrar o motivo).

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0170)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
