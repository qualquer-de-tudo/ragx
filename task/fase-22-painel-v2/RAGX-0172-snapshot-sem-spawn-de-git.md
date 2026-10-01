# RAGX-0172 — Snapshot sem spawn de `git`

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-02) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P2, S11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

`readGitHead` (`src/app/electron/data/git.ts:10-12`) dispara **dois** `git` por projeto a cada snapshot (`rev-parse HEAD` e `symbolic-ref`), e o snapshot roda a cada 5 s. Medido na auditoria: 24 processos por ciclo com 12 projetos, **~290 por minuto**, 50–120 ms por ciclo em lote e 440–550 ms por chamada isolada. O branch e o commit estão em arquivos de texto pequenos (`.git/HEAD`, `.git/refs/heads/...`, `.git/packed-refs`): ler arquivo não cria processo.

## Entregáveis

- [ ] **Linha de base**: do relatório da `RAGX-0177`, anotar `git` criados por minuto e a duração de `buildSnapshot` com 12 projetos
- [ ] `electron/data/git-files.ts`: `readGitHeadFromFiles(projectPath, fs)` devolve `GitHead` (`{ branch, commit }`), `null` (não é repositório ou ainda sem commit) ou `'unsupported'` (não deu para decidir). Resolve `.git` como pasta **ou** como arquivo `gitdir: <caminho>` (worktree, submódulo) e segue `commondir` quando existir; `HEAD` `ref: refs/heads/<nome>` (o nome pode ter `/`, ex. `feat/v2`) ou hash solto (HEAD destacado, `branch: null`); o commit vem do arquivo de ref solto, ou de `packed-refs` quando a ref foi empacotada
- [ ] Endurecimento: ler no máximo 64 KB por arquivo; aceitar só hash hexadecimal de 40 ou 64 caracteres; tirar `\r\n`; recusar `..` e caminho absoluto dentro de `ref:`; qualquer dúvida (ref que aponta para outra `ref:`, `extensions.refStorage=reftable`, arquivo ilegível) vira `'unsupported'`
- [ ] `readGitHead` (linha 10) tenta primeiro os arquivos e só chama `exec('git', ...)` quando o resultado é `'unsupported'`; a assinatura continua `(projectPath, exec = execFileText)` com um terceiro parâmetro opcional para o `fs`, para os testes atuais (`data/__tests__/git.test.ts`) seguirem válidos
- [ ] Cache por projeto: assinatura = `mtimeMs` e tamanho de `HEAD`, do arquivo de ref e de `packed-refs`; com a assinatura igual, devolve **o mesmo objeto** (a `RAGX-0175` usa a identidade para não re-renderizar)
- [ ] `isInsideGitWorkTree` (usado no `add-project`, ação do usuário) continua com `git`: fora de escopo trocar
- [ ] Atualizar a regra de leitura em `src/app/README.md` ("De onde vêm os dados"): hoje a lista de arquivos do projeto lidos é fechada em `status.json`, `knowledge.db`, `mcp.jsonl` e a existência de `ragx.toml`/`.git`; passam a constar `.git/HEAD`, `.git/refs/**`, `.git/packed-refs`, `.git/commondir` (só metadado, nenhum conteúdo de código) e a nota de que o `git` só roda como último recurso

## Fora de escopo

- Pausar o polling com a janela oculta (`RAGX-0171`) e baratear as conexões (`RAGX-0173`)
- O `git` que a CLI Python usa (`gitinfo.py`); o painel não muda a CLI
- Ler objetos do git (`.git/objects`), `index` ou estado sujo (`dirty`): o snapshot nunca precisou disso
- Remover `sql.js` (`RAGX-0176`)

## Critérios de aceite

- [ ] Com 12 projetos, o snapshot cria **0** processos `git` no estado estável (S11: o total visível fica ≤ 20/min, somado às conexões da `RAGX-0173`)
- [ ] Para branch comum, branch com `/`, ref empacotada, HEAD destacado, worktree e repositório sem commit, `readGitHeadFromFiles` devolve **exatamente** o que `git rev-parse HEAD` e `git symbolic-ref --short HEAD` devolvem (teste de integração contra `git` real)
- [ ] `buildSnapshot` com 12 projetos cai para **< 30 ms** (estimativa: só `stat` e arquivos pequenos; a meta é confirmada na medição)
- [ ] Repositório com formato de ref desconhecido (`reftable`) continua mostrando branch e commit, via `git`

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Processos `git` por minuto, 12 projetos, visível | ≈290 (auditoria) | |
| Duração de `buildSnapshot`, 12 projetos | 50–120 ms em lote (auditoria) | |
| CPU média do conjunto Electron, visível e parado | (0177) | |

Comando: `node scripts/measure-runtime.mjs --plan visible:3` (da `RAGX-0177`, em `src/app`)

## Testes

- [ ] `electron/data/__tests__/git-files.test.ts`: pasta temporária com `.git` montado à mão (HEAD com ref, ref solta, `packed-refs`, HEAD destacado, `.git` como arquivo `gitdir:`, `commondir`, hash inválido, `ref:` com `..`, arquivo maior que 64 KB) e as respostas esperadas; cache devolve o mesmo objeto sem mudança e um novo depois de `HEAD` mudar
- [ ] `electron/data/__tests__/git-vs-real.test.ts`: cria repositórios com `git init` (pula o teste se não houver `git`), faz commit, branch `feat/x`, `git pack-refs --all`, `git checkout --detach`, `git worktree add`, e compara com `git rev-parse`
- [ ] `electron/data/__tests__/git.test.ts` atual segue verde; novo caso: `'unsupported'` cai no `exec` e fora de repositório devolve `null` **sem** chamar `exec`
- [ ] `electron/data/__tests__/snapshot.test.ts` verde (a dependência `readGit` não muda de forma)

## Notas

Windows: finais de linha e caminhos com `\` dentro de `gitdir:`; normalizar antes de juntar. Um `HEAD` que acabou de ser reescrito pelo git pode estar momentaneamente vazio: tratar como `'unsupported'` e cair no `git`, nunca como erro. Se a premissa de custo não se confirmar (por exemplo, o `git` ser muito mais barato que o medido), manter a tarefa mesmo assim: processo a menos continua sendo CPU a menos, mas registrar o número real na tabela.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Commit `tipo(escopo): descrição (RAGX-0172)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
