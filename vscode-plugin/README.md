# RAGX Knowledge Explorer

Interface visual para o conhecimento que o [RAGX](../README.md) indexou do seu
projeto: busca semântica, grafo de entidades, dicionário e montagem de contexto
para agentes — tudo local, sem internet, sem enviar nada para lugar nenhum.

## Instalação

```bash
code --install-extension ragx-knowledge-explorer-1.0.0-beta.1.vsix
```

Depois abra um projeto que tenha `ragx.toml`, `knowledge/` ou `.ragx/`. A
extensão detecta sozinha e conecta.

Pré-requisito: o RAGX instalado e no PATH. Confira com `ragx --version`.

## O que dá para fazer

| Tela | Para quê |
|---|---|
| **Overview** | O que existe neste projeto, e se o índice está saudável |
| **Search** | Onde está essa informação — híbrida, semântica ou palavra-chave |
| **Graph** | Como as partes se relacionam, expandindo nó a nó |
| **Dictionary** | Que conhecimento o RAGX tem: tecnologias, serviços, conceitos |
| **Documents** | Do arquivo para o conhecimento e de volta |
| **Context** | Que contexto entregar ao agente, dentro de um orçamento de tokens |
| **Monitor** | O que mudou |
| **Security** | O que o gate bloqueou — sem revelar o que era |

## Comandos

Todos no Command Palette com o prefixo `RAGX:`.

```
RAGX: Open Knowledge Explorer
RAGX: Search Knowledge              (Ctrl+Alt+K)
RAGX: Build Context
RAGX: Explore Graph
RAGX: Open Dictionary
RAGX: Sync Knowledge
RAGX: Run Security Scan
RAGX: Show RAGX Status
RAGX: View RAGX Knowledge for This File
```

## Arquitetura

A extensão **não toca no banco do RAGX**. Toda leitura passa por um adaptador:

```
VS Code Extension  →  RagClient  →  MCP (processo quente) ou CLI  →  RAGX
```

O transporte padrão é MCP porque a primeira busca do RAGX carrega o modelo de
embeddings (~2s). Num processo quente isso acontece uma vez; com um processo
por consulta, acontece em toda consulta.

Trocar MCP por HTTP ou por uma API embutida é escrever outra implementação de
`RagClient` — nenhuma tela muda.

## Segurança

A extensão **não tem uma segunda implementação de segurança**. O Security Gate
do RAGX roda antes do parser, e o que ele bloqueia nunca entra no índice — não
é filtro de saída, é ausência.

O que o plugin garante, por cima disso:

- a webview roda sob CSP restrita: sem `eval`, sem script inline, `connect-src 'none'`
- nenhum `dangerouslySetInnerHTML`
- a lista de arquivos bloqueados **nunca** vai para a tela (é um mapa de onde
  estão os segredos); só a contagem agregada por regra
- nenhuma requisição de rede, nenhuma telemetria, nenhum CDN

## Configuração

| Chave | Padrão | O que faz |
|---|---|---|
| `ragx.connection` | `auto` | `mcp`, `cli` ou tenta os dois |
| `ragx.command` | `ragx` | Caminho do executável |
| `ragx.autoSync` | `off` | `onSave` usa o sync **incremental** |
| `ragx.searchMode` | `hybrid` | Modo padrão da busca |
| `ragx.graphMaxDepth` | `2` | Profundidade máxima do grafo |
| `ragx.maxVisibleNodes` | `120` | Teto de nós desenhados |
| `ragx.contextTokenBudget` | `4000` | Orçamento do Context Builder |
| `ragx.cacheEnabled` | `true` | Cache com TTL (nunca de conteúdo bloqueado) |

## Desenvolvimento

```bash
npm install
npm run build       # extensão + webview
npm test            # 39 testes
npm run typecheck
npm run package     # gera o .vsix
```

## Limitações conhecidas

- **Agent Training** não está no plugin. O MVP deixou isso para depois de
  propósito; use `ragx agent --help`.
- **Knowledge Gaps** e **Coverage** dependem de métricas que o RAGX ainda não
  expõe. Inventar número seria pior que não mostrar.
- A tela de segurança usa `ragx security scan`, disponível só pelo transporte
  CLI — o MCP não serve essa informação, de propósito.

## Licença

MIT
