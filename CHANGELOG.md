# Changelog

Formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
versionamento [SemVer](https://semver.org/lang/pt-BR/).

## [0.3.1] — 2026-09-15

Instalação de verdade e interface visual.

### Adicionado

- **Extensão do VS Code** `ragx-knowledge-explorer` 1.0.0-beta.1
  ([vscode-plugin/](vscode-plugin/README.md)) — busca semântica, grafo
  navegável com expansão progressiva, dicionário, Context Builder, monitor e
  status de segurança, dentro do editor. React + Tailwind sobre as variáveis de
  tema do VS Code: Light, Dark e High Contrast saem de graça.
- **Instaladores** para Windows (`install/install.ps1`) e Linux/macOS
  (`install/install.sh`). Colocam o `ragx` no PATH, registram o servidor MCP e
  **verificam** o resultado.
- Extra `all` no pacote: servidor MCP, busca semântica e contagem de tokens.

### Corrigido

Três bugs de instalação achados testando os instaladores de verdade — o do
Windows neste Windows, o do Linux num container Ubuntu 24.04:

- **`uv` escolhia Python 3.10** e o RAGX usa `StrEnum` (3.11+). A falha
  aparecia depois, como `ModuleNotFoundError: pydantic_core._pydantic_core`,
  longe da causa. `--python` agora é explícito.
- **`ragx mcp serve` falhava após instalar com sucesso**: o pacote `mcp` era um
  extra que o instalador não pedia. Servir agentes por MCP é o propósito do
  RAGX, não um acessório — daí o extra `all`.
- **PowerShell 5.1** (padrão do Windows) tratava o stderr do `uv` como exceção
  e lia o `.ps1` sem BOM como ANSI. Corrigido com um helper para chamada nativa
  e BOM no arquivo.

Há testes para os três: `tests/unit/test_documentacao.py` verifica que o extra
`all` carrega `mcp`, que os instaladores fixam o Python e registram o MCP, e
que o `.ps1` tem BOM.

No plugin, dois bugs achados pelos próprios testes:

- `humanize()` ecoava a mensagem crua do RAGX — um traceback de Python chegaria
  à tela, exatamente o que a §39 do pedido proíbe.
- `isBlocked()` só olhava a raiz do objeto; um resultado de busca com marcação
  de bloqueio dentro de `content` passava direto para a UI.

### Segurança

- A webview roda sob CSP restrita: sem `eval`, sem script inline,
  `connect-src 'none'`. Nenhum `dangerouslySetInnerHTML`.
- A lista de arquivos bloqueados **nunca** chega à tela — só a contagem
  agregada por regra. A agregação acontece no cliente, antes da webview.
- Zero rede, zero telemetria, zero CDN: a extensão empacota tudo que usa.

## [0.3.0] — 2026-09-15

Task Analyzer e orquestração. O RAGX deixa de só responder perguntas e passa a
decidir **se vale executar agora ou documentar e decompor antes** — e a manter
a fila de trabalho que sai disso. Fase 13 em
[`task/fase-13-task-analyzer-orquestracao/`](task/fase-13-task-analyzer-orquestracao/).

### Adicionado

- **Task Analyzer** (`ragx task analyze`) — classifica toda solicitação em 7
  dimensões e decide a estratégia. Determinístico e offline: sinais declarados
  em `signals.yaml`, mais duas dimensões **medidas no índice real** (quantos
  módulos já tocam o assunto, e se existe documento cobrindo). Ver
  [docs/20](docs/20-task-analyzer.md).
- **Documentation Planner** — decide QUAIS documentos o trabalho exige, em
  ordem topológica entre 15 tipos, e produz esqueletos já fundamentados no
  conhecimento existente. Lacuna vira `> **Pendente:**` explícito; o RAGX não
  inventa texto.
- **Task Decomposer** — 12 trilhas (análise, documentação, banco, backend,
  frontend, integração, testes, segurança, performance, deploy,
  observabilidade, validação) com DAG, critérios de aceite e escopo de arquivos
  derivado do grafo.
- **Banco de orquestração** `.ragx/ragx.sqlite` — 18 tabelas, máquina de
  estados com 11 estados, lease atômico, retry com backoff. Separado do
  `knowledge.db` ([ADR-0014](docs/adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md)).
- **Dispatcher e validação** — `claim`/`report`/`release` com contexto montado
  por tarefa; validação determinística (escopo, evidência, gate), sem juízo
  sobre qualidade de código.
- **Worker e scheduler** — `ragx worker` para cron; parser de cron de 5 campos
  sem dependência nova; agendamento `once|cron|interval|dependency|event|manual`.
- **13 ferramentas MCP novas** — `analyze_request`, `plan_work`, `claim_task`,
  `report_task_result`, `release_task`, `next_task`, `list_tasks`, `get_task`,
  `task_graph`, `task_status`, `set_task_status`, `add_task_dependency`,
  `run_worker`. Total: 32.
- **Board versionado** — `knowledge/tasks/` viaja no Git; execução não.
  Conflito de `status` resolve por precedência declarada.
- `ragx task` (17 subcomandos), `ragx worker`, `ragx schedule` (5 subcomandos).

### Alterado

- `ragx sync` reidrata o board de tarefas antes de regravá-lo, e **avisa**
  quando o histórico de execução local não voltou.
- `docs/09-mcp.md` e `docs/roadmap.md` atualizados com a fase 13.

### Segurança

- O contexto entregue ao agente vem do índice, que não contém segredo —
  verificado por teste com um `.env` real no projeto de teste.
- `ragx.tasks` entrou na lista de módulos que leem artefatos próprios, com um
  teste novo garantindo que ele **não varre o projeto**: `rglob`, `walk`,
  `scandir` e `read_bytes` são proibidos ali. O teste já pegou um `glob` em
  `docs/adr/` no planner, trocado por consulta ao índice.
- As invariantes do ADR-0006 seguem verificadas e não relaxadas.

### Notas de desenho

- O RAGX **não executa** a tarefa. Ele é a fila e o árbitro; quem executa é o
  agente conectado por MCP
  ([ADR-0015](docs/adr/ADR-0015-quem-executa-a-tarefa.md)). Embutir um cliente
  de LLM traria rede e credencial para dentro de um sistema cujo argumento é
  rodar offline.
- Pedido trivial **não** vira projeto. Metade do valor do analisador está em
  não criar burocracia: typo, renomear variável e ajuste visual continuam
  sendo execução direta.

## [0.2.0] — 2026-09-15

Autonomia do agente e conhecimento compartilhado entre projetos. Fase 12 em
[`task/fase-12-autonomia-e-conhecimento-base/`](task/fase-12-autonomia-e-conhecimento-base/).

### Adicionado

- **Conhecimento base** (`ragx base`) — fontes externas de regras, baixadas uma
  vez por máquina em `~/.ragx/base/`, indexadas sob `@base/<fonte>/` em cada
  projeto que as **declara** em `[base] sources`. Conteúdo de terceiro passa
  pelo mesmo Security Gate; `knowledge/base.json` carrega a receita (origem,
  ref, commit), não os arquivos. Ver
  [ADR-0013](docs/adr/ADR-0013-conhecimento-base-compartilhado.md).
- **`ragx watch`** — o índice acompanha o working tree por polling de
  `size+mtime`, com debounce e duas velocidades (reindexa a cada mudança,
  consolida a cada N). Zero dependência nova.
- **Escrita no índice via MCP** — `refresh`, `reindex`, `sync`,
  `rebuild_graph`, `generate_dictionary`, `base_sync`, `publish_contract`.
  Habilitadas por padrão em `ragx mcp serve`; `--read-only` desliga. Ver
  [ADR-0012](docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md).
- **`get_playbook`** — procedimento operacional que o agente lê uma vez:
  ordem das ferramentas, quando reindexar, e o que o índice deliberadamente
  não faz.
- `list_base_sources` no MCP.
- `ragx.walk.scan_fingerprints` — enumeração sem abrir arquivo, para o watcher.
- Testes de documentação: todo comando da CLI documentado, todo link relativo
  resolvendo.

### Alterado

- **`ragx` é o comando primário**; `rag` continua funcionando como alias
  histórico. 417 ocorrências em documentação, 85 em código.
  [ADR-0007](docs/adr/ADR-0007-nome-do-binario.md) revisado.
- `iter_files` aceita `prefix`, para namespaciar uma árvore no índice sem que o
  gate deixe de ver o caminho real.
- Serialização de `knowledge/` exclui `@base/` de documentos, chunks,
  embeddings, entidades e relações.
- `docs/09-mcp.md` não diz mais que "indexação é operação de CLI, não de
  agente" — a decisão foi revista, com o motivo registrado.

### Corrigido

- `publish_contract` chamava `hub.push`, que não existe (é `hub.sync`), e
  `generate_dictionary` tratava um `DictionaryReport` como dict. Ambos achados
  por um cliente MCP real, não pela suíte — que agora exercita **toda**
  ferramenta de escrita, parametrizada, para que ferramenta nova nasça coberta.
- `docs/06-grafo.md` e `docs/14-cli.md` documentavam `ragx graph <entidade>`;
  o comando real é `ragx graph show <entidade>`.

### Segurança

- Conteúdo de fonte base entra por `iter_files` → `SecurityGate.admit`, igual
  ao código do projeto. Teste garante que `ragx.base` nunca chama `read_bytes`
  nem `open`.
- Fonte instalada mas **não declarada** pelo projeto não é indexada — evita que
  um `ragx base add` mude em silêncio o índice de todos os projetos da máquina.
  A regra nasceu de sete testes que quebraram exatamente assim.
- As invariantes do ADR-0006 seguem verificadas e **não foram relaxadas**: o
  pacote `ragx.mcp` continua sem `open`, sem `pathlib`, sem rede, e abrindo o
  banco só em leitura.

## [0.1.0] — 2026-09-15

Primeira versão. MVP completo das 12 fases planejadas em [`task/`](task/).

### Segurança

- `SecurityGate` entre o leitor de arquivos e o parser: nenhum componente fora de
  `ragx.security` recebe bytes que não tenham passado por `admit()` (ADR-0008).
- 28 regras declarativas em YAML — auditáveis sem ler Python.
- Deny-list por nome de arquivo avaliada **antes** de qualquer leitura.
- Detecção em conteúdo: padrões de provedor, atribuição + entropia de Shannon,
  allowlist de placeholder e ajuste de severidade por contexto.
- `Redactor`: o valor do segredo nunca é persistido, logado ou impresso.
- `safe_echo`: entrada do chamador que pareça segredo volta mascarada — evita que
  uma query com a chave da AWS seja ecoada em mensagem de erro ou cabeçalho.
- Suíte de **8 superfícies** de vazamento (database, embeddings, graph, mcp,
  export, knowledge, federation, hub) — zero `xfail`.
- Testes arquiteturais: MCP sem filesystem/rede, só dois módulos leem o
  projeto-alvo, `core` não importa infraestrutura.

### Indexação

- Chunking estrutural por AST (Python) e por heading (Markdown); JSON, YAML,
  TOML, XML e SQL por estrutura nativa; fallback por parágrafo.
- IDs determinísticos e estáveis entre Windows e Linux.
- Indexação incremental com atalho por `size`+`mtime` e cache de embeddings.
- Transação por lote: `Ctrl+C` deixa o banco consistente.

### Busca e contexto

- Busca semântica em dois estágios (int8@256 grosseira → float32 rescoring),
  keyword FTS5/BM25 com pesos por coluna, fusão RRF.
- Grafo de conhecimento em duas camadas determinísticas, sem LLM.
- Context Engine: dedup literal/quase-duplicata/MMR, compressão extrativa em
  quatro estratégias, orçamento com reserva por fonte e `--explain`.

### Colaboração

- `knowledge/` versionado sem conteúdo de chunk (reidratado e conferido por hash)
  e com embeddings int8 shardados por prefixo de ID (ADR-0010).
- `ragx sync` com delta por Git e fallback por hash.
- Pacote `.rag` com re-scan obrigatório, verificação de integridade, checksums,
  proteção contra zip-slip e matriz de compatibilidade.

### Multiprojeto

- Fatia de federação versionada e autossuficiente: contratos por valor.
- Hub local agregando N projetos, clonados ou só pela fatia.
- Resolução de vínculos `consumes` ⟷ `provides` com normalização de rota entre
  stacks; consumo sem provedor e divergência de método são reportados.
- Busca cross-project com `--scope all` e atribuição obrigatória de `project`.

### Agentes

- Servidor MCP com 10 ferramentas, casca fina sobre a API interna (ADR-0006).
- Perfis de agente versionáveis; regras curadas à mão preservadas no retreino.
- `ragx agent eval` mede recuperação — não geração, e diz isso.

### Conhecido

- A qualidade da busca semântica **não está validada**: sem Ollama na máquina de
  desenvolvimento, os testes usam o provider `hashing`, de qualidade semântica
  nula. Ver `task/fase-02-busca/RAGX-0031-*.md`.
- Camada semântica do grafo (`--semantic`) e enriquecimento do dicionário por LLM
  ainda não implementados — ambos opt-in por design.
