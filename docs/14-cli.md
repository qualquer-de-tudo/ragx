# 14 — Referência da CLI

Binário: **`ragx`**. `rag` continua funcionando como alias histórico.
Ver [ADR-0007](adr/ADR-0007-nome-do-binario.md).

Convenções globais:

```text
--project PATH     raiz do projeto (padrão: diretório atual, subindo até achar ragx.toml)
--json             saída estruturada (todo comando suporta)
--quiet            só erros
--verbose / -v     detalhamento (repetível: -vv)
--no-color
--config PATH      arquivo de configuração alternativo
```

Exit codes padronizados:

| Código | Significado |
|--------|-------------|
| `0` | sucesso |
| `1` | achado bloqueante (segurança) ou falha de validação esperada |
| `2` | erro de uso (argumento inválido) |
| `3` | erro de ambiente (banco corrompido, embedder indisponível) |
| `4` | índice ocupado: outra indexação está rodando e o pedido ficou agendado |
| `130` | interrompido pelo usuário |

---

## Fase 0 — fundação

```bash
ragx init [PATH]
    --force                 sobrescreve ragx.toml existente
    --git-hooks             instala post-checkout/post-commit/post-merge (ragx hooks install)
    --profile minimal|full  conjunto inicial de configuração
```

`ragx init` agora registra automaticamente o projeto no hub local, best-effort —
falhas de registro (projeto privado, colisão de nome) nunca fazem `init` falhar.

```bash
ragx hooks install [PATH]       hooks que reindexam ao trocar de branch, commitar e fazer merge
ragx hooks uninstall [PATH]     remove só o bloco do RAGX deste projeto
ragx hooks status [PATH] [--json]
ragx hook-run EVENTO --root PATH [ARGS]   uso interno dos hooks; não chame à mão
```

Os hooks convivem com hooks de outras ferramentas (o RAGX só mexe no bloco
entre `# ragx-hook-start` e `# ragx-hook-end`), respeitam `core.hooksPath` e
nunca bloqueiam o git: a indexação roda destacada e o log fica em
`.ragx/logs/hooks.log`. `RAGX_SKIP_HOOK=1` desliga por comando.

**Entrada leve (RAGX-0143).** `ragx` e `rag` apontam para `ragx.entry:main`, que olha o primeiro
argumento antes de importar a CLI (typer, rich, pydantic e 25 módulos de comando custavam ~480 ms). Três
comandos, os que os hooks rodam a cada sessão, edição e commit, são atendidos por `ragx.hooklight`, só
com a stdlib: `ragx claude hint` (**493 → 86 ms**), `ragx touch --stdin-json` e `ragx hook-run EVENTO
--root PATH` (**509 → 114 ms**). O texto da dica sai idêntico, byte a byte; qualquer variação que a
entrada leve não reconheça vai para a CLI completa, com as mesmas mensagens de erro. Instalações
editáveis só enxergam o novo ponto de entrada depois de `uv tool install --editable --force --python 3.12
".[all]"`; as antigas continuam funcionando pelo caminho lento.

```bash
ragx doctor
    # valida: python, sqlite+FTS5, pathspec, embedder acessível, ruleset carregável,
    #         permissão de escrita em .ragx/, versão de schema

ragx security scan [PATH]
    --json
    --fail-on critical|high|medium|low
    --staged                só arquivos no stage do Git (para pre-commit)
    --rule ID               testa uma regra isolada

ragx security rules
    --show-disabled

ragx config show
ragx config get <chave>
ragx config set <chave> <valor>
```

## Fase 1 — indexação

```bash
ragx index [PATH]
    --full                  ignora cache, reindexa tudo
    --dry-run               relatório sem escrever
    --embed-only            (re)gera apenas embeddings faltantes
    --include GLOB          adiciona padrão de inclusão
    --exclude GLOB          adiciona padrão de exclusão
    # paralelismo do primeiro índice: chave `index.jobs` do ragx.toml (0 = min(cpu_count, 4); sem flag)
    --source ORIGEM         quem disparou: cli, panel, watch, sync, mcp:refresh,
                            mcp:index, hook:post-checkout, hook:post-commit, hook:post-merge
    --progress              progresso em linhas JSON no stdout (fases scan, chunk,
                            embed; linha final "done"; "busy" se outra indexação roda)

Só uma indexação roda por projeto (`.ragx/index.lock`). Quem chega com a trava
ocupada deixa o pedido agendado e quem está rodando repete a passada ao
terminar (até 3 vezes). Na origem `cli` o comando espera até 30 s antes de
desistir com exit 4; nas outras origens sai na hora com 0.

A trava guarda o PID do dono e a identidade do processo (`proc`: instante de criação). Se o PID existe mas é de
OUTRO processo (o Windows recicla PIDs em segundos), o dono morreu e a trava é assumida sozinha: não é preciso
apagar `index.lock` à mão (RAGX-0153). Trava de versão anterior, sem `proc`, continua valendo só pelo número.

ragx status
    --json
    # --json inclui freshness {state, current, reasons} e recent_runs (últimas 10)

ragx runs                        histórico de indexações, do mais novo ao mais antigo
    --limit N  --offset M        paginação (padrão: 10 a partir do 0)
    --json                       {runs, total, offset, limit}

ragx documents
    --lang LANG  --kind KIND  --path GLOB  --limit N

ragx chunks
    --document PATH  --symbol NOME  --limit N

ragx chunk <chunk_id>
    --with-context          inclui chunk pai e vizinhos
```

## Fase 2 — busca

```bash
ragx search "<query>"
    --mode hybrid|semantic|keyword      (padrão: hybrid)
    --limit N                           (padrão: 10)
    --lang LANG  --kind KIND  --path GLOB
    --min-score X
    --scope current|all|project:<nome>  (padrão: current; ver Fase 11)
    --raw                               interpreta sintaxe FTS5 crua
    --json

ragx eval
    --queries tests/eval/queries.yaml
    --mode all|hybrid|semantic|keyword

ragx trial
    --queries tests/eval/queries.yaml
    --budget N                          (padrão: 3000)
    --json
```

## Fase 3 — grafo

```bash
ragx entities
    --type TIPO  --name NOME  --limit N

ragx graph show <entidade>
    --depth N               (padrão: 1, máx: 2)
    --relations TIPO,TIPO
    --json

ragx graph-search "<query>"
    --depth N  --limit N

ragx graph rebuild
    --semantic              habilita camada 3 (exige LLM configurado)
    --layers 1,2
```

## Fase 4 — contexto

```bash
ragx context "<query>"
    --tokens N              (padrão: `[context] default_tokens`, 3000; 200 a 200000)
    --format markdown|json|xml
    --include-graph / --no-graph
    --depth N
    --scope current|all|project:<nome>
    --explain               mostra por que cada fragmento entrou/saiu
    --out FILE
    --query-stdin           lê a consulta do stdin (UTF-8) em vez do argumento; nunca vai ao argv nem ao
                            cache (`use_cache` forçado a falso); exclusivo com o argumento `<query>`

Com `--format json` e nenhum fragmento, `ragx context` imprime o JSON com `fragments: []` e sai 0 (o painel lê assim);
no modo markdown o texto e o código de saída 1 não mudam. É o caminho do preview do painel (RAGX-0187): a pergunta
só entra por stdin, e o processo principal descarta `query` e `content` da resposta antes de entregá-la ao renderer.

ragx trial "<query>"
    --tokens N              orçamento do contexto (padrão: 3000)
    --scope sources|project basal: só os arquivos usados, ou o projeto inteiro
    --path GLOB             basal explícito (repetível)
    --json

ragx ab                             # só o PLANO (padrão): nada é executado
    --arms without,full,slim  --reps N  --limit N  --model M  --max-turns N  --isolate
    --queries FILE  --out DIR  --json
    --simulate              roda o harness com números SINTÉTICOS (marcados `simulated`)
    --execute --max-calls N roda `claude -p` DE VERDADE (exige RAGX_AB_REAL=1)
```

**`ragx ab` (RAGX-0162, S14).** "O RAGX economiza X%" não é afirmável: o baseline do painel e do `trial` é o
arquivo inteiro, e um agente com `Grep` não leria 16 arquivos inteiros. A única medição honesta é um **A/B**:
as mesmas tarefas por `claude -p` em três braços (`without`: sem MCP, com `--strict-mcp-config` e nenhum
servidor; `full` e `slim`: o servidor do RAGX em cada perfil, por `RAGX_MCP_PROFILE`), com o mesmo modelo,
as mesmas ferramentas nativas e a ordem dos braços girando por tarefa. Cada tarefa pede os caminhos dos
arquivos relevantes; **a economia só conta onde os dois braços acharam o arquivo certo**, e o relatório
traz tokens faturáveis (`input + cache_creation + output`, a manchete), a soma bruta, custo e turnos, a
mediana e os quartis dos deltas pareados, o intervalo de 95% por bootstrap e o rótulo **inconclusivo**
(menos de 10 tarefas ou intervalo que cruza zero). O prompt vai pelo stdin (sem aspas no `claude.cmd` do
Windows) e o texto da resposta **nunca é gravado**: só `hit`, os caminhos citados e contagens. O
relatório vai para `.ragx/ab/<data>.json` e `latest.json`.

**Custo.** Por padrão `ragx ab` não executa nada: imprime as chamadas planejadas e o total. `--execute`
gasta a cota da sua conta e só vale com `RAGX_AB_REAL=1` **e** `--max-calls N` (recusa se o plano passar do
teto, dizendo quantas chamadas seriam). `--simulate` serve para testar o harness: tudo sai marcado
`simulated` e nunca é apresentado como economia real. Confundidor: se o `CLAUDE.md`/`AGENTS.md` do projeto
manda usar o RAGX, o braço `without` fica sem a ferramenta mas com o texto pedindo-a (é o caso deste
repositório); meça num projeto cujo `CLAUDE.md` não cite o RAGX, ou use `--isolate` (`--bare`, sem hooks
nem `CLAUDE.md`; exige `ANTHROPIC_API_KEY`).

`ragx trial` compara o contexto montado com **dois baselines** (os arquivos certos lidos
inteiros, o oráculo; e um "Grep + Read" simulado, `--grep-files K`) e mostra a economia
**conservadora**, contra o menor dos dois. São proxies, não a economia real (ver
[07](07-context-engine.md#trial--economia-de-tokens-honesta)).

Sem `--queries` e sem `tests/eval/queries.yaml` no projeto, o `trial` gera 8
consultas do próprio índice ("como funciona <nome>", com o arquivo que o define
como fonte esperada): classes e funções mais conectadas do grafo, ou, sem grafo,
nomes de arquivos de código de tamanho médio, sempre fora de testes. O JSON
marca `auto_generated: true`. Um `--queries` explícito que não existe continua
sendo erro.

> **O número é uma ESTIMATIVA de ordem de grandeza, não uma previsão de custo.**
> Os tokens são contados por um tokenizador aproximado — `tiktoken` quando
> instalado, heurística quando não —, e nenhum dos dois é o tokenizador do
> modelo que você usa. O basal supõe leitura integral dos arquivos, que não é
> como um agente realmente trabalha: ele busca, abre pedaços e desiste. E a
> comparação mede TAMANHO, não suficiência — contexto que falta gera uma
> segunda volta, que pode custar mais do que a leitura inteira custaria.

O basal nunca conta o que o RAGX não serviria: arquivo bloqueado pelo Security
Gate, coberto por `.gitignore`/`.dockerignore`/`.ragignore`, binário ou acima de
`index.max_file_bytes` fica de fora e é reportado por motivo. Contar um `.env`
inflaria a economia com tokens que nenhuma ferramenta entregaria — e exigiria
ler o segredo para contá-lo. Arquivo grande é excluído, nunca truncado:
truncar inventaria um número, excluir **subestima** a economia, que é o lado
seguro do erro.

## Fase 5 — dicionário

```bash
ragx dictionary generate
    --semantic              enriquece concepts/glossary/summaries com LLM
    --out DIR               (padrão: knowledge/)

ragx dictionary show
    --section technologies|services|modules|concepts|entrypoints|conventions
    --json
```

## Fase 6 — MCP

```bash
ragx mcp serve
    --project PATH
    --transport stdio
    --write / --read-only   escrita no ÍNDICE pelo agente (padrão: --write)
    --allow-index           habilita ferramenta de reindexação (padrão: off)
    --log-queries           grava texto das queries (padrão: só hash)

ragx mcp tools
    --json                  imprime os JSON Schemas
    --read-only             lista como ficaria sem escrita

ragx mcp install
    --client NOME           só nestes (repetível): claude-desktop, claude-code,
                            cursor, windsurf, gemini, codex
    --command CAMINHO       executável gravado na configuração (padrão: `ragx`)
    --dry-run               mostra o que mudaria, sem escrever
    --json

ragx mcp uninstall
    --client NOME           só destes (repetível); mesmos nomes do install
    --dry-run               mostra o que mudaria, sem escrever
    --json
```

`ragx mcp uninstall` faz o caminho inverso: retira só a entrada `ragx` (ou a
tabela `[mcp_servers.ragx]` no Codex), com as mesmas garantias abaixo —
backup datado, idempotente (já ausente = sem mudança) e recusa de
configuração ilegível.

`ragx mcp install` registra o RAGX como servidor MCP nos clientes que encontra
na máquina. É o que os instaladores chamam, e pode ser rodado à mão depois.

O que ele garante, porque escrever na configuração de outro programa é a
operação mais arriscada do instalador:

- **alteração mínima** — mexe só na entrada `ragx`; os outros servidores MCP e
  todo o resto do arquivo ficam como estavam;
- **idempotente** — rodar de novo não duplica nada, e se já estiver correto não
  escreve nem gera backup;
- **backup datado** antes de qualquer mudança real;
- **recusa configuração ilegível** em vez de sobrescrevê-la — JSON quebrado
  pode ser o arquivo que você está editando agora;
- **escrita atômica**, sem BOM: uma queda no meio não deixa o arquivo truncado.

Cliente não instalado é reportado como ausente, não como erro, e nenhuma pasta
de cliente é criada por conta própria. Use `--command` com caminho absoluto
quando o cliente for um aplicativo gráfico: eles não herdam o PATH do shell de
forma confiável.

Depois de registrar, **reinicie o cliente** — ele lê a configuração ao subir.

`--write` dá ao agente controle sobre o índice — `refresh`, `reindex`, `sync`,
`rebuild_graph`, `generate_dictionary`, `base_sync`, `publish_contract`. Não dá
acesso ao filesystem e não afrouxa o Security Gate; ver
[ADR-0012](adr/ADR-0012-poder-do-agente-sobre-o-indice.md) e
[19 — Watch e autonomia](19-watch-e-autonomia-do-agente.md).

## Fase 7 — agentes

```bash
ragx agent create <nome>
    --template backend|frontend|reviewer|docs
    --scope GLOB

ragx agent train <nome>
    --tokens N              orçamento do instructions.md
    --with-examples         propõe exemplos a partir do histórico Git

ragx agent list
ragx agent show <nome> [--section rules|skills]
ragx agent eval <nome> [--case ID]
ragx agent promote-example <nome> <id>   promove um exemplo de _proposed/
ragx agent export <nome> --out FILE
```

`ragx agent eval` mede **recuperação**, não geração: verifica se o contexto certo
foi entregue, não se a resposta do modelo ficou boa. Exit 1 quando algum caso falha.

## Fase 8 — portabilidade

```bash
ragx export <arquivo.rag>
    --include-embeddings
    --include-agents
    --scope GLOB

ragx import <arquivo.rag>
    --replace | --merge     (padrão: --replace)
    --skip-embeddings

ragx inspect <arquivo.rag>
    --json
```

## Fase 9 — sync

```bash
ragx sync
    --quiet
    --from-commit SHA
    --resolve                   rederiva artefatos em conflito
    --resolve-file PATH         usado pelo merge driver do Git
    --full                      equivalente a ragx index --full + regenerar knowledge/
```

Num clone novo (sem `.ragx/`), `ragx sync` cria o índice e importa os embeddings versionados em vez de
recalculá-los; os importados ficam só grosseiros até `ragx index --embed-only`. Sem banco mas com
`knowledge/`, os comandos de consulta mandam rodar `ragx sync`.

```bash
```

## Fase 10 — manutenção

```bash
ragx vacuum                      VACUUM + optimize + remove órfãos
ragx reset [--hard]              apaga .ragx/ (--hard também apaga knowledge/)
ragx version
ragx doctor --full               inclui checagem de integridade do banco
ragx doctor --json               as mesmas checagens em JSON, saindo com 0
```

> Com o provider `ollama` respondendo e o modelo baixado, o `doctor` acrescenta a
> linha `Ollama` (lida de `GET /api/ps`): "GPU (N MB de VRAM)", "CPU" ou
> "processador ainda não medido (nenhum modelo carregado)". É só informação:
> a linha nunca falha o `doctor`, e uma consulta que falha vira "não foi
> possível consultar o processador".

> `ragx doctor --json` **sai com código 0 mesmo havendo problema**: o veredito
> está em `ok` e `problems`, dentro do payload. Quem pede JSON quer ler o
> diagnóstico, e um código de saída diferente de zero faz o chamador descartar
> a saída e ficar sem diagnóstico nenhum. O modo humano mantém os códigos 1 e 3,
> que o instalador usa.

## Medir e desligar o RAGX no Claude Code

```bash
ragx perf [--days 7] [--project NOME] [--top 5] [--json]
ragx claude status [--json]      o RAGX está ligado no Claude Code agora? (por perfil)
ragx claude off [--dry-run]      tira o RAGX do Claude Code, em todos os projetos e perfis
ragx claude on [--dry-run] [--no-hint] [--no-touch] [--no-nudge]   põe de volta, com a dica, o aviso de edição e o lembrete
ragx touch [ARQUIVO...] [--stdin-json] [--root R]    avisa o RAGX de arquivos editados (reindexa só eles)
ragx claude on|off --profile empresa     só num perfil (id ou nome)
ragx claude hint                 o texto que a dica entrega ao agente nesta pasta
ragx claude nudge                lembrete do índice no 1º Grep/Glob da sessão (uso do hook PreToolUse)
ragx claude agent install [--dry-run] [--profile X]   instala o subagente ragx-explorer (opt-in)
ragx claude agent remove [--dry-run] [--profile X]    remove só o arquivo com o marcador do RAGX
ragx claude agent status [--json]                      o subagente está instalado, por perfil?
ragx claude profiles list [--json]       perfis que o RAGX enxerga, detectados e adicionados
ragx claude profiles add PASTA [--on]    adiciona uma pasta de perfil (qualquer lugar)
ragx claude profiles remove PASTA        tira da lista, sem mexer na configuração dela
```

`ragx perf` lê os transcripts do Claude Code (`~/.claude/projects`), que carimbam
cada mensagem, e separa o tempo das voltas do modelo e das ferramentas que foram
do RAGX do tempo total ativo da sessão (o seu tempo lendo e digitando não conta).
Mostra, por ferramenta, a espera vista pelo Claude e o tempo que o servidor diz
ter gasto (`.ragx/logs/mcp.jsonl`, do projeto atual), e o custo fixo em tokens
do schema das ferramentas. É estimativa e erra para menos: chamadas em paralelo
com ferramenta de fora não são atribuídas ao RAGX, e pausas de mais de 15 minutos
contam como ociosidade. Lê só números de tempo; o conteúdo das mensagens não é
guardado nem impresso.

`ragx claude off|on` é o interruptor global: usa o mesmo registro do
`ragx mcp install/uninstall --client claude-code` (só a entrada `ragx` muda,
com backup datado e recusa de configuração ilegível). Vale a partir da próxima
sessão do Claude Code; uma sessão já aberta continua com as ferramentas que
carregou. `on` regrava a entrada padrão (`ragx mcp serve`).

`on` e `off` aceitam `--json` (`{enabled, changed, detail, profiles}`, e `error` quando
falha, saindo com 1): é o que o interruptor do header do painel usa. `enabled` só é
verdadeiro quando **todos** os perfis estão ligados.

**Perfis.** Quem separa contas roda o Claude Code com `CLAUDE_CONFIG_DIR` (ex.:
`~/.claude-empresa`), e aí a configuração do perfil, MCP incluído, mora em
`<dir>/.claude.json`. `ragx claude` e `ragx mcp install --client claude-code`
tratam cada perfil como um Claude Code: o padrão (`~/.claude.json`), cada
`~/.claude-*` que já tenha `.claude.json`, o diretório de `CLAUDE_CONFIG_DIR`, se
estiver definido, e as pastas adicionadas com `ragx claude profiles add`, guardadas
em `~/.ragx/claude-profiles.json` (para quem mantém a conta de um cliente fora de
`~/.claude-*`). Cada perfil tem id `claude-code:<nome>`; duas pastas com o mesmo
nome viram `cliente` e `cliente-2`. `--profile` liga ou desliga um só; sem ele,
todos. `profiles remove` só tira a pasta da lista: se o RAGX estava ligado lá,
desligue antes com `off --profile`.

**Dica de início de sessão.** Registrar o servidor não basta: as ferramentas do
RAGX chegam ao agente como *deferred* (só o nome), e Grep/Read já estão
carregados. `on` instala, no `settings.json` de cada perfil, um hook
`SessionStart` que roda `ragx claude hint`. Num projeto indexado, o agente lê a regra (RAGX antes
de Grep/Glob/Read para "onde está", "como funciona", "o que chama o quê"), as três ferramentas
(`build_context`, `search_hybrid`, `get_chunk`) e como carregá-las com ToolSearch: **~140 tokens**
(eram ~350 com o resumo de documentos, data e branch do índice; o frescor agora vem na própria busca,
com `stale_paths`). Numa pasta acima de projetos indexados (um monorepo com front e back separados),
a dica lista o `scope="project:<nome>"` de cada um. Fora de projeto RAGX, não diz nada. O hook
nunca falha: um erro ali atrasaria toda sessão. `off` remove só esse hook; os
seus ficam. `--no-hint` liga o MCP sem a dica.

**Uma vez por sessão (RAGX-0164).** O Claude Code roda o hook de `SessionStart` também em subagentes, e
repetir a dica (e contar a sessão de novo no painel) a cada um só gasta token. O hook lê o JSON do stdin
(`session_id`, `source`), cria um marcador `.ragx/cache/hint/<session_id>` de forma atômica (`O_EXCL`;
na pasta do hub, quando a pasta não tem índice próprio) e, na repetição da mesma sessão, não imprime
nada e não grava o evento `session_start`. Com `source` igual a `clear` ou `compact` (o contexto foi
perdido) a dica volta e o marcador é renovado. O `session_id` vira nome de arquivo só com
`[A-Za-z0-9_-]` (até 64): um id hostil não escapa da pasta. Sem `session_id` (uso manual no terminal, stdin
vazio ou inválido) a dica sai sempre. O stdin nunca bloqueia o hook (espera até 0,5 s). Marcadores
com mais de 7 dias são apagados ao criar um novo.

**Subagente `ragx-explorer` (RAGX-0161, opt-in).** Explorar código num repositório grande enche o contexto
do agente principal com leituras que ele não vai reusar. `ragx claude agent install` (ou `ragx claude on
--agent`; **desligado por padrão**, porque um subagente novo aparece na lista da pessoa) grava
`<perfil>/agents/ragx-explorer.md`: só leitura (`mcp__ragx__build_context`, `search_hybrid`, `get_chunk`,
`get_entity`, `Read`, `Grep`, `Glob`; sem `Edit`, `Write` nem `Bash`), que usa o RAGX primeiro, abre só os
arquivos apontados e **responde curto** (caminhos com linhas e 3 a 6 frases). A `description`, que entra no
contexto principal em toda sessão, tem ~44 tokens. O arquivo leva o marcador `<!-- ragx:managed v1 -->`:
só o arquivo com o marcador é atualizado (com backup) ou removido (`agent remove`, `claude off`); um
arquivo seu com o mesmo nome nunca é sobrescrito. Sem `model:` (herda o do agente principal); para fixar
um mais barato, acrescente a linha `model:` ao frontmatter; rodar `agent install` de novo reescreve o
arquivo (com backup `.ragx-backup-*`), então a edição precisa ser refeita.
`agent status [--json]` e `claude status --json` (`agent`, por perfil) mostram o estado. Instala na pasta do
perfil, nunca no repositório do usuário. Subagentes usam o mesmo servidor MCP do agente principal, então
o que o explorador recebeu não está no contexto do principal (relevante para o dedupe de sessão, 0159).

**Lembrete no `Grep`/`Glob` (RAGX-0160).** O hint de `SessionStart` é lido uma vez e esquecido, e
`Grep`/`Glob` já estão carregados: o modelo vai no que está à mão. `on` instala também um hook `PreToolUse`
com matcher `Grep|Glob` que roda `ragx claude nudge`: no **primeiro** `Grep`/`Glob` da sessão, num projeto
indexado, ele devolve `hookSpecificOutput.additionalContext` (~50 tokens: o projeto está indexado e
`mcp__ragx__build_context(query)` devolve trechos com arquivo e linhas). **Sugere, nunca bloqueia** (nem
nega nem reescreve o `Grep`), e cala em todo o resto: projeto sem índice, sessão já avisada, stdin vazio ou
inválido, qualquer erro (sempre sai com 0). O projeto vem do `cwd` do stdin; a sessão, de `session_id`,
com marcador `.ragx/cache/nudge/<session_id>` criado com `O_EXCL` (vários `Grep` em paralelo: só um
imprime). Não ecoa nem grava o `tool_input` (o padrão buscado pode ser um segredo); cada lembrete mostrado
vira uma linha `command: "nudge"` em `.ragx/logs/cli.jsonl`, para medir adoção. `--no-nudge` liga o MCP
sem ele (e tira o que havia); `status --json` mostra `nudge` por perfil. O `PreToolUse` aceita
`additionalContext` e entrega `agent_id` quando o hook dispara dentro de um subagente (conferido na
documentação do Claude Code); a chave continua sendo só o `session_id`, então um subagente não repete
o lembrete.

**Aviso de edição (`ragx touch`, RAGX-0141).** O índice só via uma edição não commitada no
`refresh` (26 a 91 s) ou no próximo commit. `on` instala também um hook `PostToolUse`
(`Edit|Write|MultiEdit`, `async`, `timeout` 10 s) que roda `ragx touch --stdin-json`: o comando lê o
caminho editado do JSON do hook, o enfileira em `.ragx/touch.queue` e dispara, destacado, a
drenagem que reindexa só aqueles arquivos (`index_paths`). A raiz vem do próprio arquivo (a sessão
pode estar numa pasta-pai), pasta sem índice é ignorada, e o comando sai sempre com 0. Várias
edições em sequência (`[watch] touch_debounce_ms`, 400 ms) viram uma só reindexação. `--no-touch`
liga o MCP sem o hook (e tira o que já estava); `off` o remove, e os seus `PostToolUse` ficam.
`ragx touch ARQUIVO...` faz o mesmo à mão.

## Orçamento de tamanho (Fases 1 e 9)

```bash
ragx size                        relatório do orçamento de knowledge/
    --check                     exit 1 se estourar (uso em CI)
    --projection                projeta o tamanho antes de indexar
    --history                   crescimento ao longo dos commits
    --json
```

## Fase 11 — multiprojeto e federação

```bash
ragx federation build            gera knowledge/federation/ do projeto atual
ragx federation show [--direction provides|consumes]
ragx federation export <arquivo.fed.json>   fatia avulsa, para quem não clona o repo

ragx contract "<nome>" [--kind http|event] [--json]
    # contrato de um endpoint ou evento + o projeto que o provê;
    # funciona para projeto registrado só pela fatia

ragx project register [PATH]
    --name NOME
    --from-federation FILE      registra projeto NÃO clonado, só pela fatia
    --visibility workspace|private
ragx project list [--json]
ragx project unregister <nome>

ragx hub sync [--project NOME]   atualiza o hub a partir dos registrados
ragx hub status [--json]         idade, estado e degradação por projeto
ragx hub link                    resolve vínculos consumes ⟷ provides
ragx hub dictionary [--json]     dicionário de workspace
ragx hub graph <projeto> [--depth N]
ragx hub reset                   apaga ~/.ragx/hub/ (reconstruível)
```

## Fase 11 — conhecimento base

```bash
ragx base add <url-ou-caminho>
    --name NOME             nome curto (padrão: último segmento da origem)
    --ref BRANCH            branch ou tag
    --declare / --no-declare    grava em [base] sources do ragx.toml (padrão: grava)
    --index / --no-index

ragx base list [--json]
ragx base sync [--index/--no-index]     instala o que o projeto declara e falta
ragx base update [NOME]                 rebaixa e reindexa se o commit mudou
ragx base enable <nome>
ragx base disable <nome>                para de indexar sem apagar do disco
ragx base remove <nome> [--yes]
```

Instalar **não** indexa: o projeto precisa declarar a fonte em `[base] sources`
(ver [18 — Conhecimento base](18-conhecimento-base.md)).

## Fase 11 — watch

```bash
ragx watch
    --interval SEG              entre varreduras      (padrão: [watch] interval_s)
    --debounce SEG              quietude antes de aplicar
    --consolidate-every N       mudanças até regravar knowledge/
    --once                      uma passada e sai (scripts, hook de Git, CI)
    --plain                     uma linha por evento / JSON com --once
```

## Fase 13 — Task Analyzer e orquestração

```bash
ragx task analyze "<pedido>"        classifica; NÃO escreve nada
    --json

ragx task plan "<pedido>"           monta o plano
    --apply                         cria projeto, documentos e tarefas
    --docs / --no-docs              gravar os esqueletos em knowledge/
    --json

ragx task list [--project P] [--status S] [--json]
ragx task show TASK-001 [--json]
ragx task next [--project P] [--json]        a próxima executável; não reivindica
ragx task context TASK-001 [--tokens N] [--out arquivo.md]
ragx task run [TASK-001] [--project P]       reivindica e imprime o pacote
ragx task result TASK-001 --file r.json      entrega o resultado
    --summary "..." --status completed       forma curta
ragx task validate TASK-001 [--json]         revalida sem mudar estado
ragx task retry TASK-001                     devolve à fila agora
ragx task cancel TASK-001                    decisão humana; não se desfaz
ragx task block TASK-001 [--reason "..."]
ragx task unblock TASK-001
ragx task dependencies TASK-001 [--add TASK-000] [--kind depends_on]
ragx task graph [--project P] [--json]
ragx task status [--json]                    painel de monitoramento
ragx task logs TASK-001 [--limit N] [--events]
```

O worker mantém a fila; **não executa tarefa** — quem executa é o agente
([ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md)).

```bash
ragx worker [--once] [--json]
    # expira lease, promove prontas, aplica retry, dispara agendamento

ragx schedule list [--json]
ragx schedule add <nome> --type cron --cron "*/5 * * * *"
    --type once|cron|interval|dependency|event|manual
    --interval SEGUNDOS  --project P  --task T  --event TIPO
ragx schedule remove <nome>
ragx schedule enable <nome>
ragx schedule disable <nome>
```

Para cron:

```cron
*/5 * * * * cd /caminho/do/projeto && ragx worker
```

---

## Fluxos comuns

Primeiro uso:

```bash
ragx init
ragx security scan .            # confira o que será bloqueado ANTES de indexar
ragx index .
ragx search "como funciona autenticação"
```

Preparar contexto para um agente:

```bash
ragx context "implementar refund parcial" --tokens 4000 --out contexto.md
```

Onboarding de novo dev (time já usa RAGX):

```bash
git clone <repo> && cd <repo>
ragx sync                       # reidrata conteúdo e reconstrói .ragx/
ragx base sync                  # instala as regras compartilhadas que o projeto exige
ragx search "autenticação"      # já funciona, offline, com os vetores int8 do repo
ragx mcp serve                  # ou configure no cliente MCP
```

Desenvolvimento no dia a dia:

```bash
ragx watch                      # em um terminal: o índice acompanha o que você edita
ragx mcp serve                  # no cliente MCP: o agente consulta E mantém o índice
```

Trabalho grande, do pedido à entrega:

```bash
ragx task analyze "Implementar módulo de assinaturas"   # o que é isto?
ragx task plan "Implementar módulo de assinaturas" --apply
ragx task next                  # o que dá para fazer agora
ragx task context TASK-001      # o contexto da tarefa, no orçamento
# ... o agente executa ...
ragx task result TASK-001 --file resultado.json
ragx worker                     # libera as dependentes
```

Ambiente com vários repositórios (microsserviços):

```bash
ragx project register ../order-service
ragx project register ../payment-service
ragx project register --from-federation ./contratos/shipping.fed.json
ragx hub sync && ragx hub link

ragx search "como criar um pagamento" --scope all
ragx context "integrar checkout com pagamento" --scope all --tokens 6000
```

Dia a dia em ambiente multiprojeto:

```bash
git pull && ragx sync           # projeto atual (gera federation/ se auto_federation)
ragx hub sync && ragx hub link   # workspace enxerga a mudança
```

Uso em CI:

```bash
ragx security scan . --json --fail-on high || exit 1
ragx index . --quiet
ragx dictionary generate && ragx federation build
ragx size --check
git diff --exit-code knowledge/
```
