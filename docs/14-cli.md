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
| `130` | interrompido pelo usuário |

---

## Fase 0 — fundação

```bash
ragx init [PATH]
    --force                 sobrescreve ragx.toml existente
    --git-hooks             instala pre-commit/post-merge/post-checkout
    --profile minimal|full  conjunto inicial de configuração

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
    --jobs N                paralelismo (padrão: cpu_count)

ragx status
    --json

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
    --tokens N              (padrão: 3000)
    --format markdown|json|xml
    --include-graph / --no-graph
    --depth N
    --scope current|all|project:<nome>
    --explain               mostra por que cada fragmento entrou/saiu
    --out FILE
```

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
```

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

## Fase 10 — manutenção

```bash
ragx vacuum                      VACUUM + optimize + remove órfãos
ragx reset [--hard]              apaga .ragx/ (--hard também apaga knowledge/)
ragx version
ragx doctor --full               inclui checagem de integridade do banco
```

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
