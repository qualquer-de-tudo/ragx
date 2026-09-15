# ADR-0006 — MCP sem acesso a filesystem

**Status:** aceito · 2026-09-15

## Contexto

Servidores MCP de "acesso a arquivos" são comuns e resolvem o problema errado para
este produto: eles dão ao agente a capacidade de ler qualquer arquivo do projeto.
Isso anula, em uma única chamada, todo o investimento em Security Gate — o agente
pede `.env`, recebe `.env`, e o segredo vai para o log, para o histórico da conversa
e para o provedor do modelo.

Há também um risco de arquitetura: se o MCP puder ler arquivos, a tentação de
implementar lógica ali ("busca rápida sem passar pelo índice") é grande, e a camada
deixa de ser fina.

## Decisão

O servidor MCP é uma **casca de tradução de protocolo**. Duas restrições duras:

1. **Nenhum acesso a filesystem, rede ou processo.** O pacote `ragx.mcp` não importa
   `os`, `subprocess`, `pathlib`, `open`, `socket`, `requests`, `httpx`.
2. **Nenhuma lógica de negócio.** Toda ferramenta é: validar entrada (Pydantic) →
   chamar um serviço de `application/` → serializar saída.

```text
PERMITIDO                          PROIBIDO
MCP → KnowledgeAPI → Store         MCP → open(path)
                                   MCP → subprocess.run(...)
                                   MCP → requests.get(...)
```

`get_document` recebe um caminho relativo e o usa como **chave de consulta no store**,
não como caminho de arquivo. Caminho não indexado → `not_found`. Nunca uma leitura.

O banco é aberto em modo somente leitura (`file:...?mode=ro`) por padrão. Indexar é
operação de CLI. A ferramenta `reindex` existe atrás de `--allow-index`, desligada
por padrão.

Cumprimento verificado por teste arquitetural que inspeciona a AST dos módulos de
`ragx.mcp` — não por revisão de código, que esquece.

## Consequências

Positivas:
- A garantia de segurança do índice se estende automaticamente ao agente: se o
  segredo não está no store, não existe caminho de código que o entregue.
- Superfície de ataque mínima. Não há como induzir *path traversal* em uma camada
  que não abre arquivos.
- A lógica fica testável sem protocolo MCP no meio.
- CLI e MCP compartilham exatamente o mesmo comportamento, porque compartilham o
  mesmo serviço.

Negativas:
- O agente não consegue ler um arquivo que o RAGX não indexou. **Isso é a feature**,
  não uma limitação a contornar. Se o arquivo deve ser legível, ele deve ser indexado.
- Uma camada extra de indireção para adicionar funcionalidade: primeiro o serviço,
  depois a ferramenta. Aceitável, e é o que mantém o contrato honesto.

## Alternativas rejeitadas

- **MCP com ferramenta `read_file`** — conveniente, e destrói o modelo de segurança.
- **MCP com filtro de caminho** ("pode ler, menos `.env`") — blocklist em superfície
  de leitura arbitrária é uma corrida perdida: `.env.bak`, `env/.env`, symlink,
  `..%2f`, encoding alternativo. Deny-by-default sobre um store limpo é
  categoricamente mais forte.
- **MCP com lógica própria de busca** — duplicaria comportamento entre CLI e MCP,
  e a divergência apareceria como bug relatado por agente.
