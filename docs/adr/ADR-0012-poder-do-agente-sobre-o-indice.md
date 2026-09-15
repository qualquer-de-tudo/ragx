# ADR-0012 — Poder do agente sobre o índice

- **Status:** aceito
- **Data:** 2026-09-15
- **Contexto:** Fase 11
- **Relacionado:** [ADR-0006](ADR-0006-mcp-casca-fina.md), [ADR-0008](ADR-0008-security-gate-antes-do-parser.md)

## Contexto

O ADR-0006 definiu o servidor MCP como casca fina e **somente leitura**: o
agente consultava o índice, e quem o mantinha atualizado era um humano rodando
`ragx index` e `ragx sync` na mão.

Na prática isso produziu a pior falha possível de um sistema de conhecimento:
**respostas confiantes sobre código que não existe mais.** O agente não tinha
como saber que o índice estava atrás do working tree, e não tinha como
consertar. O humano precisava lembrar de sincronizar — e não lembrava.

O pedido foi direto: *"quero que o agent de IA tenha total poder em cima do
rag"*.

## Decisão

**O agente controla o ÍNDICE. Não controla o filesystem, e não controla o
Security Gate.**

Ferramentas de escrita expostas via MCP (`ragx.mcp.operations`):

| Ferramenta | Efeito |
|---|---|
| `refresh` | aplica ao índice o que mudou no disco |
| `reindex` | varredura incremental ou completa |
| `sync` | reidrata, reindexa, grafo, dicionário, `knowledge/` |
| `rebuild_graph` | reconstrói entidades e relações |
| `generate_dictionary` | regenera o Knowledge Dictionary |
| `base_sync` | instala o conhecimento base DECLARADO pelo projeto |
| `publish_contract` | republica a superfície pública no hub |

O que **continua impossível**, exatamente como antes:

- ler um arquivo do filesystem
- obter conteúdo de arquivo bloqueado pelo gate
- indexar fora da raiz do projeto
- executar comando arbitrário
- escolher a origem de uma fonte base (vem de arquivo versionado)

## Por que isso não afrouxa a segurança

A fronteira do ADR-0006 nunca foi "o agente não pode fazer nada". Era **que
caminho o byte percorre**. Esse caminho não mudou:

```
disco -> iter_files -> SecurityGate.admit -> parser -> store -> agente
```

`reindex` faz o índice percorrer esse caminho de novo. Ele não cria um caminho
alternativo. Um agente com escrita liberada, pedindo `reindex` mil vezes,
continua sem conseguir extrair uma linha do `.env`: não existe função que
devolva isso.

As invariantes verificadas por teste arquitetural permanecem:

- `ragx.mcp` não importa `os`, `subprocess`, `pathlib`, `shutil`, rede
- `ragx.mcp` não chama `open`, `exec`, `eval`
- `ragx.mcp` só abre o banco com `read_only=True` (escrita é delegada ao
  serviço, nunca feita no módulo)

A tentação durante a implementação foi ler `knowledge/base.json` dentro de
`operations.py`. O teste arquitetural barrou, e a leitura foi para
`ragx.base.declared_for`. A regra continua valendo para o código novo.

## Consequências

**Positivas**

- O agente pode garantir frescor antes de raciocinar (`refresh` no início da
  tarefa) em vez de depender da memória do humano.
- Erro de índice desatualizado deixa de ser silencioso: o agente percebe e
  corrige.
- CLI e MCP passam a ter a mesma superfície, chamando os mesmos serviços — não
  há divergência possível entre o que o humano e o agente conseguem fazer.

**Negativas aceitas**

- Um agente em laço pode reindexar repetidamente. Mitigado por lock exclusivo
  (`_LOCK`), `write_timeout_s` e rate limit. O custo é CPU, não corrupção.
- `sync` é caro. Mitigado pelo playbook, que diz explicitamente quando usar
  `refresh` (barato) e quando usar `sync`.
- Escrita habilitada por padrão em `ragx mcp serve`. É o comando que o usuário
  roda para o próprio agente; a biblioteca (`McpCfg.allow_write`) continua
  `False`, para quem embute o servidor em outro contexto.

## Alternativas descartadas

**Manter somente leitura e exigir `ragx watch`.** O watcher resolve o frescor,
mas não resolve o resto: o agente continua sem poder reconstruir o grafo depois
de um merge, nem instalar a base que o projeto declara. E depende de o humano
ter deixado um processo rodando.

**Esconder as ferramentas de escrita no modo leitura.** Ferramenta ausente faz
o agente concluir que a operação não existe e inventar um contorno. Ferramenta
que responde `write_disabled` com a instrução de como habilitar diz a verdade.
Há teste garantindo que elas continuam listadas.

**Expor um `run_command` genérico.** Seria "total poder" no sentido literal e
destruiria toda a garantia do projeto. O pedido era poder sobre o RAG, não
sobre a máquina.
