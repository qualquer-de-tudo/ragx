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
| `build_context` | `query`, `tokens`, `format?` | `ContextPack` pronto | Fase 4 |
| `list_projects` | — | projetos no hub, estado e integrações | Fase 11 |
| `get_contract` | `kind`, `name` | contrato de endpoint/evento + projeto que o provê | Fase 11 |
| `list_base_sources` | — | fontes `@base/` ativas nesta máquina | Fase 12 |

### Escrita no ÍNDICE (Fase 12)

Habilitadas por padrão em `ragx mcp serve`; `--read-only` as desliga. Ver
[ADR-0012](adr/ADR-0012-poder-do-agente-sobre-o-indice.md).

| Ferramenta | Entrada | Efeito | Custo |
|------------|---------|--------|-------|
| `refresh` | — | aplica ao índice o que mudou no disco | barato quando nada mudou |
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

O que a escrita **não** concede: ler o filesystem, escapar do Security Gate,
indexar fora da raiz do projeto, executar comando arbitrário, ou escolher a
origem de uma fonte base — essa vem de arquivo versionado, revisado por humano.

A partir da Fase 11, toda ferramenta de consulta aceita `scope`
(`current` — padrão · `all` · `project:<nome>`) e **todo item de resposta carrega
`project`**. Detalhes em [17 — Multiprojeto](17-multiprojeto-e-federacao.md).

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

## Execução

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

Toda chamada gera uma linha em `.ragx/logs/mcp.jsonl`:

```json
{"ts":"2026-09-15T12:31:02Z","tool":"search_hybrid","ms":84,"hits":10,"query_hash":"a3f1..."}
```

A query é gravada por **hash** por padrão (`mcp.log_queries = false`); em modo
debug explícito, o texto é gravado. Isso evita que o log vire uma cópia do que o
time está perguntando sobre o próprio código.

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
