# RAGX-0172 — Snapshot sem spawn de `git`

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-02) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P2, S11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

`readGitHead` (`src/app/electron/data/git.ts:10-12`) dispara **dois** `git` por projeto a cada snapshot (`rev-parse HEAD` e `symbolic-ref`), e o snapshot roda a cada 5 s. Medido na auditoria: 24 processos por ciclo com 12 projetos, **~290 por minuto**, 50–120 ms por ciclo em lote e 440–550 ms por chamada isolada. O branch e o commit estão em arquivos de texto pequenos (`.git/HEAD`, `.git/refs/heads/...`, `.git/packed-refs`): ler arquivo não cria processo.

## Entregáveis

- [x] **Linha de base**: do relatório da `RAGX-0177`, anotar `git` criados por minuto e a duração de `buildSnapshot` com 12 projetos
- [x] `electron/data/git-files.ts`: `readGitHeadFromFiles(projectPath, fs)` devolve `GitHead` (`{ branch, commit }`), `null` (não é repositório ou ainda sem commit) ou `'unsupported'` (não deu para decidir). Resolve `.git` como pasta **ou** como arquivo `gitdir: <caminho>` (worktree, submódulo) e segue `commondir` quando existir; `HEAD` `ref: refs/heads/<nome>` (o nome pode ter `/`, ex. `feat/v2`) ou hash solto (HEAD destacado, `branch: null`); o commit vem do arquivo de ref solto, ou de `packed-refs` quando a ref foi empacotada
- [x] Endurecimento: ler no máximo 64 KB por arquivo; aceitar só hash hexadecimal de 40 ou 64 caracteres; tirar `\r\n`; recusar `..` e caminho absoluto dentro de `ref:`; qualquer dúvida (ref que aponta para outra `ref:`, `extensions.refStorage=reftable`, arquivo ilegível) vira `'unsupported'`
- [x] `readGitHead` (linha 10) tenta primeiro os arquivos e só chama `exec('git', ...)` quando o resultado é `'unsupported'`; a assinatura continua `(projectPath, exec = execFileText)` com um terceiro parâmetro opcional para o `fs`, para os testes atuais (`data/__tests__/git.test.ts`) seguirem válidos
- [x] Cache por projeto: assinatura = `mtimeMs` e tamanho de `HEAD`, do arquivo de ref e de `packed-refs`; com a assinatura igual, devolve **o mesmo objeto** (a `RAGX-0175` usa a identidade para não re-renderizar)
- [x] `isInsideGitWorkTree` (usado no `add-project`, ação do usuário) continua com `git`: fora de escopo trocar
- [x] Atualizar a regra de leitura em `src/app/README.md` ("De onde vêm os dados"): hoje a lista de arquivos do projeto lidos é fechada em `status.json`, `knowledge.db`, `mcp.jsonl` e a existência de `ragx.toml`/`.git`; passam a constar `.git/HEAD`, `.git/refs/**`, `.git/packed-refs`, `.git/commondir` (só metadado, nenhum conteúdo de código) e a nota de que o `git` só roda como último recurso

## Fora de escopo

- Pausar o polling com a janela oculta (`RAGX-0171`) e baratear as conexões (`RAGX-0173`)
- O `git` que a CLI Python usa (`gitinfo.py`); o painel não muda a CLI
- Ler objetos do git (`.git/objects`), `index` ou estado sujo (`dirty`): o snapshot nunca precisou disso
- Remover `sql.js` (`RAGX-0176`)

## Critérios de aceite

- [x] Com 12 projetos, o snapshot cria **0** processos `git` no estado estável (S11: o total visível fica ≤ 20/min, somado às conexões da `RAGX-0173`)
- [x] Para branch comum, branch com `/`, ref empacotada, HEAD destacado, worktree e repositório sem commit, `readGitHeadFromFiles` devolve **exatamente** o que `git rev-parse HEAD` e `git symbolic-ref --short HEAD` devolvem (teste de integração contra `git` real)
- [x] `buildSnapshot` com 12 projetos cai para **< 30 ms** (estimativa: só `stat` e arquivos pequenos; a meta é confirmada na medição)
- [x] Repositório com formato de ref desconhecido (`reftable`) continua mostrando branch e commit, via `git`

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Processos `git` por minuto, 12 projetos, visível | ≈290 (auditoria); **290,8 medido (0177)** | **0** |
| Duração de `buildSnapshot`, 12 projetos | 50–120 ms (auditoria); **141,9 ms** medido (0177) | **2,9 ms** (< 30 ✓) |
| CPU média do conjunto Electron, visível e parado | 0,1 (0177) | 0,1 (p95 0,2): o CPU do painel nunca foi o problema; os filhos caíram de **16,8 para 6,5 s/min** |

Comando: `node scripts/measure-runtime.mjs --plan visible:3 --label depois-0172-git-por-arquivos` (da `RAGX-0177`, em `src/app`; a seção está em `src/app/docs/medicao-runtime.md`)

## Testes

- [x] `electron/data/__tests__/git-files.test.ts`: pasta temporária com `.git` montado à mão (HEAD com ref, ref solta, `packed-refs`, HEAD destacado, `.git` como arquivo `gitdir:`, `commondir`, hash inválido, `ref:` com `..`, arquivo maior que 64 KB) e as respostas esperadas; cache devolve o mesmo objeto sem mudança e um novo depois de `HEAD` mudar
- [x] `electron/data/__tests__/git-vs-real.test.ts`: cria repositórios com `git init` (pula o teste se não houver `git`), faz commit, branch `feat/x`, `git pack-refs --all`, `git checkout --detach`, `git worktree add`, e compara com `git rev-parse`
- [x] `electron/data/__tests__/git.test.ts` atual segue verde; novo caso: `'unsupported'` cai no `exec` e fora de repositório devolve `null` **sem** chamar `exec`
- [x] `electron/data/__tests__/snapshot.test.ts` verde (a dependência `readGit` não muda de forma)

## Notas

Windows: finais de linha e caminhos com `\` dentro de `gitdir:`; normalizar antes de juntar. Um `HEAD` que acabou de ser reescrito pelo git pode estar momentaneamente vazio: tratar como `'unsupported'` e cair no `git`, nunca como erro. Se a premissa de custo não se confirmar (por exemplo, o `git` ser muito mais barato que o medido), manter a tarefa mesmo assim: processo a menos continua sendo CPU a menos, mas registrar o número real na tabela.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] Commit `tipo(escopo): descrição (RAGX-0172)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `electron/data/git-files.ts` (`readGitHeadFromFiles` com `.git` pasta ou arquivo `gitdir:`, `commondir`, ref solta, `packed-refs`, HEAD destacado, hash de 40 ou 64 caracteres, no máximo 64 KB por arquivo, `ref:` com `..`/absoluto/barra invertida recusado, `reftable` (pasta ou `refStorage` no `config`) e ref encadeada = `'unsupported'`; sobe até achar `.git`, como o `git rev-parse` fazia numa subpasta; `readGitHeadCached` com assinatura de `mtime`+tamanho de `HEAD`, da ref e de `packed-refs`, devolvendo o MESMO objeto sem mudança) e `readGitHead` tenta primeiro os arquivos (`git` só em `'unsupported'`; assinatura com o 3º parâmetro `io` opcional). `isInsideGitWorkTree` ficou com `git`. README do painel atualizado ("De onde vêm os dados"). Testes: `git-files.test.ts` (22), `git-vs-real.test.ts` (9, contra o `git` real: comum, `feat/x`, `pack-refs --all`, `--detach`, worktree, sem commit, subpasta, e "nenhum processo"/`reftable` via git) e +1 em `git.test.ts`; `npm test` 901+ verdes.
- Uma pasta que NÃO existe devolve `'unsupported'` (cai no `git`, como antes); só uma pasta que existe sem `.git` em nenhum ancestral devolve `null` sem processo. Foi o que manteve válidos os testes atuais (que passam `C:/p`, inexistente, com `exec` simulado).
- Medido (`measure-runtime.mjs --plan visible:3`, 12 projetos): **`git` 290,8 → 0 por minuto**; `buildSnapshot` 141,9 → **2,9 ms**; o que sobra de filhos (6,5 s/min: `docker` 6,2/min, `ragx` 2,4/min, `tasklist` 2,1/min, `powershell` 0,3/min) é a checagem de conexões, da 0173. S11 ainda não fecha (≈ 11 filhos/min, meta ≤ 20: fecha; o que falta é a janela minimizada, da 0171).
