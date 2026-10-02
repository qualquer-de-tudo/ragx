# 09 — MCP (Fase 6)

O servidor MCP entra **depois** que o núcleo está sólido, e é deliberadamente uma
**casca fina** sobre a API interna. Zero lógica de negócio, zero acesso a filesystem.

```text
              AI Agent
                 │
                MCP  ◄── só tradução de protocolo + validação de schema
                 │
          ┌──────▼──────┐
          │  RAGX Core  │  ◄── toda a lógica vive aqui
          └──────┬──────┘
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
    Vector     Graph     SQLite
```

## A regra

```text
PERMITIDO                          PROIBIDO
MCP → KnowledgeAPI → Store         MCP → open(path)
                                   MCP → subprocess
                                   MCP → requests.get(url)
```

O servidor MCP **não importa** `pathlib.Path.open`, `os`, `subprocess` nem qualquer
cliente HTTP. Isso é verificado por teste arquitetural que inspeciona os imports do
pacote `ragx.mcp` (ver [13 — Testes](13-testes-hardening.md)).

Consequência prática: se um agente pedir "leia o arquivo `.env`", não existe caminho
de código que atenda. A única coisa que o MCP sabe fazer é consultar o store — e o
store, por construção, não tem segredo dentro.

## Ferramentas

### Consulta

| Ferramenta | Entrada | Saída | Camada |
|------------|---------|-------|--------|
| `get_playbook` | — | procedimento operacional + estado desta instalação | Fase 12 |
| `get_dictionary` | `section?` | visão estruturada do projeto | Fase 5 |
| `search_knowledge` | `query`, `limit?`, `filters?` | resultados semânticos | Fase 2 |
| `search_hybrid` | `query`, `limit?`, `filters?` | resultados fundidos | Fase 2 |
| `get_document` | `path` | metadados + lista de chunks | Fase 1 |
| `list_documents` | `path_glob?`, `lang?`, `kind?`, `limit?` | inventário do índice + contagem por origem | Fase 14 |
| `get_chunk` | `chunk_id` | conteúdo completo de um chunk | Fase 1 |
| `get_entity` | `name` ou `id` | entidade + relações diretas (com `confidence`, `source` e `tier`) | Fase 3 |
| `search_graph` | `query`, `depth?` | subgrafo relevante | Fase 3 |
| `build_context` | `query`, `tokens`, `format?` | o contexto pronto, em **uma** representação: `markdown` (padrão: só `markdown`, sem `fragments`) ou `json` (só `fragments`, com `chunk_id` e `tokens`, sem `markdown`). `estimated_tokens` conta o markdown entregue | Fase 4 |
| `list_projects` | — | projetos no hub, estado e integrações | Fase 11 |
| `get_contract` | `kind`, `name` | contrato de endpoint/evento + projeto que o provê | Fase 11 |
| `list_base_sources` | — | fontes `@base/` ativas nesta máquina | Fase 12 |

### Escrita no ÍNDICE (Fase 12)

Habilitadas por padrão em `ragx mcp serve`; `--read-only` as desliga. Ver
[ADR-0012](adr/ADR-0012-poder-do-agente-sobre-o-indice.md).

| Ferramenta | Entrada | Efeito | Custo |
|------------|---------|--------|-------|
| `refresh` | — | reindexa o que mudou no disco (só o índice: não consolida nem toca em `knowledge/`) | ~0,6 s sem mudança, ~1,2 s com 4 arquivos; consolidar é `sync` |
| `reindex` | `full?`, `embed?` | varredura do projeto | médio |
| `sync` | `full?`, `write_knowledge?` | reidrata, reindexa, grafo, dicionário, `knowledge/` | **caro** |
| `rebuild_graph` | — | reconstrói entidades e relações | médio |
| `generate_dictionary` | — | regenera o Knowledge Dictionary | barato |
| `base_sync` | — | instala o conhecimento base DECLARADO pelo projeto | rede |
| `publish_contract` | — | republica a superfície pública no hub | barato |

Em modo `--read-only` elas **continuam listadas** e respondem `write_disabled`
com a instrução de como habilitar. Ferramenta ausente faz o agente concluir que
a operação não existe e inventar um contorno; ferramenta que recusa diz a
verdade.

### Orquestração de trabalho (Fase 13)

O ciclo completo de uma tarefa, do pedido à entrega. Ver
[21 — Orquestração de tarefas](21-orquestracao-de-tarefas.md) e
[20 — Task Analyzer](20-task-analyzer.md).

Só `analyze_request`, `list_tasks`, `get_task`, `task_graph`, `next_task` e
`task_status` são de leitura pura. As demais escrevem no banco de orquestração
e seguem a mesma regra das outras: em `--read-only` continuam listadas e
respondem `write_disabled`.

| Ferramenta | Entrada | Efeito | Escreve? |
|------------|---------|--------|----------|
| `analyze_request` | `request` | classifica: executar agora ou documentar e decompor antes | não |
| `plan_work` | `request`, `apply?` | monta o plano (documentos, tarefas, dependências); `apply=true` cria | com `apply` |
| `list_tasks` | `project_id?`, `status?`, `limit?` | tarefas, com filtro | não |
| `get_task` | `task_id` | critérios, escopo, dependências e último resultado | não |
| `task_graph` | `project_id?` | o DAG de tarefas: nós e arestas | não |
| `next_task` | `project_id?` | a próxima tarefa executável, SEM reivindicar | não |
| `task_status` | — | painel: tarefas por estado, projetos, conhecimento, agendamentos | não |
| `claim_task` | `task_id?`, `project_id?`, `tokens?` | reivindica com lease e devolve o contexto já montado | sim |
| `report_task_result` | `task_id`, `result` | entrega o resultado, valida e libera as dependentes | sim |
| `release_task` | `task_id`, `reason?` | devolve uma tarefa reivindicada sem executá-la | sim |
| `set_task_status` | `task_id`, `status`, `reason?` | muda o estado, respeitando a matriz de transições | sim |
| `add_task_dependency` | `task_id`, `depends_on`, `kind?` | cria dependência; ciclo é recusado com o caminho completo | sim |
| `run_worker` | — | um ciclo do worker: expira leases, promove prontas, aplica retry | sim |

`claim_task` é o ponto de entrada do agente executor: ele devolve a tarefa
**e** o contexto, numa chamada só, para não obrigar a uma segunda ida ao
índice entre pegar o trabalho e começá-lo.

> A lista acima é verificada contra o servidor por
> `tests/unit/test_documentacao_mcp.py`. Ferramenta registrada e não
> documentada — ou documentada e não registrada — quebra a suíte.

O que a escrita **não** concede: ler o filesystem, escapar do Security Gate,
indexar fora da raiz do projeto, executar comando arbitrário, ou escolher a
origem de uma fonte base — essa vem de arquivo versionado, revisado por humano.

A partir da Fase 11, `search_knowledge`, `search_hybrid` e `build_context` aceitam
`scope` (`current` — padrão · `all` · `project:<nome>`) e **todo item de resposta carrega
`project`**. `search_graph`, `get_dictionary` e as demais **não** têm `scope`. Detalhes em
[17 — Multiprojeto](17-multiprojeto-e-federacao.md).

O `scope` é **honrado ou recusado, nunca ignorado** (RAGX-0137):

| Ferramenta | `all` | `project:<nome>` |
|---|---|---|
| `search_hybrid`, `search_knowledge` | busca em todos os projetos visíveis; a resposta ganha `scope` e `projects` | restringe ao projeto |
| `build_context` | `scope_unsupported` (modelos de embedding diferentes não se combinam num pack) | monta o pack com o índice e a configuração DESSE projeto |

`project:<nome>` inexistente **ou privado** devolve o mesmo `not_found`; projeto registrado só
por federação (sem clone local) devolve `scope_unsupported` em `build_context`, porque só tem
contratos (use `get_contract`).

### Orquestração de tarefas (Fase 13)

O RAGX é a fila e o árbitro; o agente é o executor
([ADR-0015](adr/ADR-0015-quem-executa-a-tarefa.md)). Implementação em
`src/ragx/mcp/orchestration.py`. Modelo completo, com o ciclo de vida do
lease e a máquina de estados, em
[21 — Orquestração de tarefas](21-orquestracao-de-tarefas.md).

Leitura, sempre disponível:

| Ferramenta | Entrada | Saída |
|------------|---------|-------|
| `analyze_request` | `request` | classificação da solicitação — não escreve nada |
| `list_tasks` | `project_id?`, `status?`, `limit?` | tarefas, forma enxuta (`_slim`) |
| `get_task` | `task_id` | tarefa completa + dependências + último resultado |
| `task_graph` | `project_id?` | nós e arestas do DAG de dependências |
| `next_task` | `project_id?` | a próxima executável, **sem** reivindicar |
| `task_status` | — | painel consolidado (usado por `stats`/`monitor`) |

Escrita, exige `--write` (mesma flag do índice — ver "Escrita no ÍNDICE" acima):

| Ferramenta | Entrada | Efeito |
|------------|---------|--------|
| `plan_work` | `request`, `apply?` | monta o plano; `apply=true` cria projeto, documentos e tarefas |
| `claim_task` | `task_id?`, `project_id?`, `tokens?` | reivindica com lease **e devolve o contexto já pronto**, dentro do orçamento de tokens — o agente não remonta contexto sozinho |
| `report_task_result` | `task_id`, `result` | entrega o resultado; dispara validação e libera as tarefas dependentes |
| `release_task` | `task_id`, `reason?` | devolve a tarefa sem executar (desistência ou interrupção) |
| `set_task_status` | `task_id`, `status`, `reason?` | bloquear, desbloquear, cancelar — respeita a matriz de transições |
| `add_task_dependency` | `task_id`, `depends_on`, `kind?` | adiciona dependência; recusa se formar ciclo |
| `run_worker` | — | um ciclo do worker (lease, promoção, retry, agendamento) — não executa tarefa |

`claim_task` e as demais de escrita retornam `write_disabled` em modo
`--read-only`, seguindo a mesma convenção das ferramentas de índice.

Ordem de uso recomendada, documentada na descrição de cada ferramenta para que o
agente aprenda sozinho:

```text
get_playbook    →  como operar este servidor (uma vez por sessão)
       ↓
refresh         →  garantir que o índice reflete o disco (início da tarefa)
       ↓
list_projects   →  em que ambiente estou? (só se multiprojeto)
       ↓
get_dictionary  →  orientação barata
       ↓
search_hybrid   →  localizar
       ↓
build_context   →  montar o contexto de trabalho
       ↓
get_chunk       →  aprofundar em um trecho específico
get_contract    →  contrato exato de uma integração entre projetos
```

## Contratos

Schemas em Pydantic, exportados como JSON Schema pelo SDK.

> **Nota de versão.** O SDK `mcp` 2.x renomeou `FastMCP` para `MCPServer`. A implementação usa a API atual; documentação anterior que citava `FastMCP` está desatualizada.

```python
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)
    lang: str | None = None
    kind: Literal["file","class","function","method","section","block"] | None = None
    path_glob: str | None = Field(default=None, max_length=200)
    scope: str = Field(default="current", pattern=r"^(current|all|project:[\w.-]{1,64})$")

class SearchHit(BaseModel):
    project: str              # obrigatório — conhecimento sem origem não é entregue
    chunk_id: str
    document_path: str
    symbol: str | None
    heading_path: str | None
    lines: tuple[int, int]
    score: float
    content: str
    matched_by: list[str]

class BuildContextRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    tokens: int = Field(default=3000, ge=200, le=32000)
    format: Literal["markdown","json"] = "markdown"
    include_graph: bool = True
```

Toda resposta é `{ "ok": true, "data": ... }` ou
`{ "ok": false, "error": { "code": ..., "message": ... } }`. O agente nunca recebe
stack trace: erro interno vira `code = "internal"` com mensagem genérica, e o
detalhe vai para `.ragx/logs/`.

## Limites e proteção

| Limite | Valor padrão | Motivo |
|--------|--------------|--------|
| `limit` máximo | 50 | evitar dump do índice via paginação agressiva |
| `tokens` máximo | 32.000 | teto de contexto |
| tamanho da resposta | 1 MiB | proteção de transporte |
| `path_glob` | sem `..`, sem caminho absoluto | não é acesso a arquivo, mas o filtro não deve sugerir que é |
| rate | 60 chamadas/min por sessão | proteção contra loop de agente |

### Saber o que existe, e de qual origem

`list_documents` responde “O QUE há neste índice” — pergunta diferente de
“o que casa com esta consulta”, que é o que a busca responde. Devolve só
metadado (caminho, linguagem, tipo, título, se foi redigido); conteúdo tem
ferramenta própria, com id de chunk.

O campo `by_source` separa o que é deste repositório do que veio de fora:

```json
{ "by_source": { "ragx": 312, "@base/agents": 36 } }
```

A regra sai do próprio caminho: `@base/<fonte>/…` é conhecimento base
compartilhado, instalado na máquina e **declarado** por este projeto; o resto
é o repositório aberto. A distinção importa na prática — um arquivo `@base/`
não está no working tree, e procurá-lo no repositório não adianta.

`path_glob` aceita tanto um trecho (`auth`) quanto um glob (`src/*.py`); sem
curinga, o trecho é envolvido em `*…*`. Ver [18-conhecimento-base.md](18-conhecimento-base.md).

`get_document` recebe um **caminho relativo já indexado**. Se o caminho não existir
no store, a resposta é `not_found` — e não uma tentativa de leitura no disco. Essa
distinção é a fronteira inteira.

Com `scope` diferente de `current`, a fronteira continua a mesma: o MCP consulta o
hub e os stores dos projetos registrados, nunca o filesystem deles. Projeto marcado
`visibility = "private"` é invisível a qualquer `scope`, inclusive `project:<nome>`
explícito.

## Formato das respostas

Tudo que o agente lê custa token, então o fio é enxuto (RAGX-0155, `response_format: 2`,
declarado em `get_playbook`):

- **JSON compacto**, sem indentação e com acentos como estão. As ferramentas são
  registradas com `structured_output=False`: o SDK não repete a resposta em
  `structuredContent` nem anexa `outputSchema` a cada ferramenta (o `tools/list` perdeu
  ~830 tokens, e cada resposta, a metade que vinha duplicada).
- **Ausência significa `null`.** Chaves nulas (`symbol`, `heading_path`, `degraded`...) não
  vão no fio; `0`, `false`, `""` e `[]` vão.
- **`project` uma vez**, em `data.project`, e não repetido em cada hit. A busca federada
  (`scope` diferente de `current`) mantém `project` por hit, porque lá cada um tem a sua origem.
- **`score` com 4 casas** e **`chunk_id` de 12 hex** (o id completo tem 32). `get_chunk`
  aceita o id completo ou um prefixo hexadecimal de **8 caracteres ou mais**; prefixo
  ambíguo devolve `invalid_id`.
- `build_context` entrega **uma** representação por `format` (ver acima) e o texto do
  markdown sem o título.

### Frescor: fila de edição e `stale_paths` (RAGX-0141)

`search_knowledge`, `search_hybrid` e `build_context` (escopo `current`) reindexam, ANTES de buscar, os
arquivos que o hook de edição deixou em `.ragx/touch.queue` (só um `stat` quando a fila está vazia, e
sem espera de debounce). Se algo não puder ser reindexado agora (índice ocupado por outra indexação,
falha), a resposta traz `stale_paths` (até 20 caminhos) e `stale_count`: aqueles arquivos podem estar
defasados, e o agente chama `refresh`. Sem fila pendente a resposta não ganha nenhum campo.

### Teto e `response_format` (RAGX-0165)

- **Teto do `build_context`:** o pedido é limitado a `[mcp] max_context_tokens` (padrão **5.000**).
  Um pedido acima dele **não é cortado em silêncio**: a resposta traz `tokens_capped` com o teto
  aplicado. `tokens` continua validando até 32.000. Uso real medido (45 chamadas): máximo 3.239 tokens,
  p95 2.601, nenhuma acima de 5.000.
- **`response_format`** (`concise` | `detailed`; padrão `[mcp] response_format`, hoje `concise`) em
  `search_hybrid`, `search_knowledge` e `build_context`. Na **busca**, `concise` devolve um `snippet`
  (os primeiros `snippet_chars` = 140 do conteúdo, cortados em fim de linha ou de palavra, com `…`) no
  lugar de `content`; `detailed` devolve `content`, como antes. O agente abre o trecho inteiro com
  `get_chunk`. No **`build_context`**, `concise` entrega só o contexto; `detailed` acrescenta `intent`,
  `fragments_meta` (id, linhas, tokens, estratégia, motivo, score, **sem** conteúdo), `dropped`
  agrupado por motivo e `stats`.

| `format` | `response_format` | O que vem em `build_context` |
|---|---|---|
| `markdown` | `concise` | `markdown` |
| `markdown` | `detailed` | `markdown` + `intent`, `fragments_meta`, `dropped`, `stats` |
| `json` | `concise` | `fragments` (com conteúdo) |
| `json` | `detailed` | `fragments` + `intent`, `fragments_meta`, `dropped`, `stats` |

Medido (tiktoken, este repositório): `search_hybrid` com 10 hits, **2.915 → 1.108 tokens (−62%)** com
`snippet_chars = 140` (com 200, −56,8%); `build_context(tokens=20000)` entrega 5.083 tokens no fio
(`estimated_tokens` 4.503, `budget` 5.000). O VS Code pede `detailed`, porque mostra o conteúdo.

Medido com `scripts/medir_fio.py` (tiktoken, este repositório; antes → depois, texto da resposta,
sem contar o `structuredContent` que deixou de existir): `search_hybrid` (10 hits) 11.864 → 9.679
chars (−18,4%); `get_dictionary` 36.713 → 21.530 (−41,4%); `get_document` 2.610 → 1.436 (−45%);
`get_entity` 23.679 → 17.419 (−26,4%); `build_context(3000)` 7.983 → 2.947 tokens.

## Perfis (RAGX-0157)

O servidor expõe 33 ferramentas (perfil `full`, o padrão), mas só `build_context`, `search_hybrid`,
`get_dictionary`, `get_playbook` e `sync` aparecem nos logs e nos transcripts de uso real: as outras 28
custam tokens em todo turno e quase nunca são chamadas. O custo fixo (nome + descrição + schema de
entrada de cada ferramenta, no prompt de TODA requisição ao modelo) é **~2.600 tokens** no `full`.

O perfil **`slim`** expõe 6, com os mesmos nomes e argumentos do `full`, e custa **~370 tokens**
(−86%):

| Ferramenta | Para quê |
|---|---|
| `get_dictionary` | o mapa barato do projeto; por onde começar |
| `search_hybrid` | localizar |
| `build_context` | montar o contexto de uma tarefa dentro de um orçamento de tokens |
| `get_chunk` | abrir o texto completo de um resultado |
| `get_entity` | quem chama / de quem depende um símbolo |
| `refresh` | reindexar o que mudou (em modo leitura responde `write_disabled`) |

No `slim` as descrições são curtas (a função primeiro) e os schemas não trazem `title`, `default` nem
`anyOf` com `null`: a validação dos argumentos continua a da função, só o que o modelo lê encolhe.
`get_playbook` vira as `instructions` do servidor e `sync` fica na CLI. As `instructions` do `slim` só
citam ferramentas que ele expõe.

Como ligar (o padrão **não** muda): `[mcp] profile = "slim"` no `ragx.toml` ou em
`~/.config/ragx/config.toml`, `RAGX_MCP_PROFILE=slim`, ou `ragx mcp serve --profile slim`;
`ragx mcp tools --profile slim` lista e mostra o custo. O plugin do VS Code usa ferramentas que só o
`full` tem (`task_status`, `list_projects`): não o aponte para o `slim`. As contagens ("33 ferramentas")
nos READMEs são as do `full`.

### Como escrever a descrição de uma ferramenta, e por que a lista é estável (RAGX-0158)

O cliente (Claude Code) descobre ferramentas por **Tool Search**, que lê o nome e a descrição, e perde o
cache de prompt quando a lista de ferramentas muda. Duas consequências, ambas cobertas por
`tests/integration/test_mcp_estavel.py`:

- **A descrição começa por um verbo e diz o que a ferramenta faz** ("Localiza código e documentação...",
  "Mostra as relações diretas de um símbolo: quem o chama..."), com os termos de quem procura
  ("localizar", "onde", "quem chama", "reindexar"), em **no máximo 200 caracteres** e sem valor que mude
  (contagem, nome do projeto, data). Verbo novo na lista de verbos do teste, de propósito.
- **A lista é estável.** A ordem de registro é fixa e nada em `list_tools()` nem nas `instructions`
  depende do estado da sessão (a escrita ligada ou não também não muda a lista). Os arquivos
  `tests/fixtures/mcp_tools_full.json` e `mcp_tools_slim.json` guardam o `list_tools()` serializado: mudar
  uma descrição ou um schema passa a exigir regravá-los de propósito
  (`RAGX_REGRAVAR_OURO=1 uv run pytest tests/integration/test_mcp_estavel.py`). Trocar de perfil muda a
  lista entre sessões, não dentro de uma.

As `instructions` do servidor cabem em **2.048 bytes** (o Claude Code trunca em ~2 KB; hoje 531 no `full`
e 356 no `slim`, com escrita ligada) e só citam ferramentas que o perfil expõe: no `slim` não há
`get_playbook` nem `sync`.

## Execução

**Aquecimento (RAGX-0142).** A primeira busca de um processo pagava o carregamento do modelo de
embedding (ONNX, tokenizer, imports) e do `tiktoken`. Ao subir, o servidor dispara, numa thread
`daemon`, a construção do embedder (com uma consulta de verdade), do contador de tokens e a carga da
matriz de vetores, enquanto espera o primeiro pedido. Medido neste repositório (fastembed): a primeira
`search_hybrid` depois de 5 s ociosos caiu de **1.447 ms para 42 ms**, e o `initialize` ficou igual
(910 → 922 ms). Uma busca que chega DURANTE o aquecimento espera a mesma construção (nunca monta dois
modelos). Só aquece pasta com índice (o servidor global em pasta sem projeto não carrega nada), e
`[mcp] warmup = false` desliga. Falha no aquecimento vai para `.ragx/logs/errors.log` e não derruba o
servidor. `scripts/medir_mcp_frio.py` reproduz a medição.

```bash
ragx mcp serve                 # stdio (padrão)
ragx mcp serve --project /caminho/do/projeto
ragx mcp tools                 # lista ferramentas e schemas
```

Configuração no cliente (exemplo genérico de `mcpServers`):

```json
{
  "mcpServers": {
    "ragx": {
      "command": "rag",
      "args": ["mcp", "serve", "--project", "E:/RAGPAG/meu-projeto"]
    }
  }
}
```

O módulo `ragx.mcp` abre o SQLite **sempre** em modo somente leitura
(`file:...?mode=ro`) — há teste arquitetural verificando cada chamada a
`open_db` no arquivo. As ferramentas de escrita não contradizem isso: elas
delegam ao mesmo serviço que a CLI usa, e a escrita acontece lá, não aqui.

> **Revisão da Fase 12.** Até a Fase 11 este documento dizia "indexação é
> operação de CLI, não de agente". Deixou de valer: a decisão foi revista no
> [ADR-0012](adr/ADR-0012-poder-do-agente-sobre-o-indice.md) porque um índice
> que só um humano atualiza acaba desatualizado, e um índice desatualizado não
> dá erro — ele responde com confiança sobre código que não existe mais.

## Observabilidade

Toda chamada MCP feita a um projeto já inicializado gera uma linha em
`.ragx/logs/mcp.jsonl` — uma pasta sem índice (o estado normal de qualquer
diretório que não é um projeto RAGX) não gera log nem cria `.ragx/` só por
causa de uma chamada:

```json
{"v":2,"ts":"2026-10-01T12:31:02Z","tool":"build_context","ms":84,"project":"ragx","proc":"ec301f6f","ok":true,"resp_chars":9583,"resp_tokens":2947,"tokens_delivered":2601,"baseline_tokens":26290,"client":"claude-code","profile":"empresa","session":"0c1f9a2e"}
{"v":2,"ts":"2026-10-01T12:31:09Z","tool":"get_chunk","ms":3,"project":"ragx","proc":"ec301f6f","ok":false,"err_code":"not_found","resp_chars":88,"resp_tokens":24}
```

Formato **v2** (RAGX-0156). Campos de toda linha: `v` (versão do formato), `ts`, `tool`, `ms`,
`project`, `ok` (a chamada deu certo?), `resp_chars` e `resp_tokens` (o texto **exato** que o cliente
recebeu, em caracteres e em tokens estimados), e `proc` (8 hex por processo do servidor: agrupa as
linhas quando não há `session`, e cada sessão sobe o seu servidor). Com `ok: false` entra
`err_code` (`not_found`, `invalid_argument`, `rate_limited`, `internal`...), nunca a mensagem, que
pode ecoar o argumento. `tokens_delivered` (só `build_context`) é o **conteúdo** que o contexto
entregou (os tokens do markdown); `resp_tokens` é a **resposta inteira**, envelope incluso. Linha
antiga (v1, sem `v` nem `ok`) continua legível e é tratada como resultado "desconhecido": não conta
como erro. `ragx perf` mostra `n` e a taxa de erro por ferramenta.

Cada linha registra `ts` (timestamp), `tool` (ferramenta chamada), `ms` (latência em
milissegundos), `project` (projeto), e para `build_context` (quando bem-sucedido)
`tokens_delivered` (tokens entregues ao agente) e `baseline_tokens` (o tamanho dos
arquivos inteiros de onde o contexto saiu). Quando quem chama é o Claude Code, entram
também `client`, `profile` (o perfil, pelo `CLAUDE_CONFIG_DIR`: `padrão`, `empresa`
de `~/.claude-empresa`...) e `session` (os 8 primeiros caracteres da sessão). Essa
origem vem do ambiente do processo e é gravada fora do pacote MCP
(`ragx.diagnostics`), que não lê o ambiente. Fora do Claude Code esses campos não
aparecem: sem as variáveis dele não dá para saber quem chamou. Query e argumentos
nunca são gravados, evitando que o log vire uma cópia do que o time está
perguntando sobre o próprio código.

Os comandos de consulta da CLI rodados à mão (`search`, `context`, `graph-search`,
`chunk`, `trial`) e o início de uma sessão do Claude Code num projeto indexado (pela
dica de `ragx claude hint`) vão para `.ragx/logs/cli.jsonl`, no mesmo formato:
`command` no lugar de `tool`, e `ok`. O que o próprio painel roda (`status`, `trial`
pelo botão) leva `RAGX_CALLER=painel` e não entra. É o que alimenta a tela de
atividade do painel.

## Critério de aceite da Fase 6

1. Um agente externo consegue, usando **somente** ferramentas MCP: consultar o
   dicionário, buscar conhecimento, navegar o grafo e montar contexto — sem saber
   nada da implementação interna.
2. Teste arquitetural confirma: `ragx.mcp` não importa `os`, `subprocess`, `open`,
   nem cliente HTTP.
3. Nenhuma ferramenta aceita caminho absoluto ou `..`.
4. Teste de segurança: para cada segredo da fixture, todas as ferramentas são
   chamadas com o segredo como query e com o caminho do arquivo bloqueado —
   0 ocorrências nas respostas (`xfail` de "0 resultados MCP" vira `pass`).
5. Servidor sobe em < 1 s e responde `search_hybrid` em < 300 ms em índice de 10k chunks.
6. (Fase 11) Toda resposta carrega `project`; projeto `private` não aparece em
   nenhum `scope`; segredo de um projeto não retorna em consulta feita a partir de outro.
