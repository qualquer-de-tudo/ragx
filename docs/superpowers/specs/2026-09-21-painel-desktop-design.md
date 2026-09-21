# Painel Desktop RAGX — Design

**Status:** Backlog — aprovado em brainstorm, implementação adiada para outro momento.

## O problema

O usuário tem 11+ projetos indexados pelo RAGX em máquinas de desenvolvimento
diferentes (aivonlabs, bigbot, fullstackclub, gsisten, socix) e não tem
nenhuma visão consolidada: quantos documentos/chunks/embeddings cada um tem,
quantas chamadas MCP aconteceram, quantos tokens o `build_context` entregou,
e o que o último `security scan` bloqueou. Hoje isso só é visível rodando
comandos `ragx` um por um, projeto por projeto.

## Objetivo

Um app desktop local (Windows `.exe`, sem instalador de servidor, sem login)
que abre e mostra, por projeto: documentos/chunks/embeddings, chamadas MCP por
ferramenta, tokens entregues (real) + economia estimada (proxy, rotulado como
tal), e achados de segurança do último scan. Atualização por polling simples.
"Simples e rápido" é requisito explícito do usuário — não da forma de UI
polida, da forma de menos partes móveis possível.

## Não-objetivos

- Não é um dashboard multiusuário nem tem autenticação — é local, de um
  usuário, uma máquina.
- Não substitui `ragx doctor`/`ragx status` — é uma visão agregada, não um
  diagnóstico profundo.
- Não tenta calcular "tokens economizados" como número exato — isso não é
  computável ao vivo (ver ADR implícito abaixo). É proxy, e o painel deixa
  isso explícito na UI, nunca mistura com o número real.
- Sem tempo real via file-watch nesta primeira versão — polling é suficiente
  e muito mais simples de implementar e depurar.

## Por que "tokens economizados" não é um número real

`ragx trial` (já existe, ver `docs/07-context-engine.md`) já documenta isto:
comparar "tokens que o `build_context` entregou" contra "tokens que o agente
teria lido sem o RAGX" só é possível como PROXY — usando o corpus de avaliação
(`tests/eval/queries.yaml`), não durante uso real, porque o RAGX não sabe o
que o agente teria feito na ausência dele. O painel usa exatamente esse
mesmo proxy, rotulado como estimativa, recalculado sob demanda — nunca como
"tokens economizados: 4.231" sem qualificação.

## Duas partes, dois ciclos de implementação

Este design cobre dois sub-projetos que se conectam mas são implementáveis
(e testáveis) separadamente:

1. **Telemetria no RAGX** (Parte 1) — escopo **bounded**: um ponto de
   instrumentação já existe (`_guarded` em `src/ragx/mcp/server.py`), só
   precisa logar. Pode ser implementado e revisado sozinho, sem o painel.
2. **App Electron** (Parte 2) — escopo **architectural**: projeto novo,
   consome o que a Parte 1 produz mais o que já existe hoje (hub, `.ragx/knowledge.db`).

---

## Parte 1 — Telemetria real no RAGX

### O que existe hoje (verificado no código, não suposto)

- `src/ragx/mcp/server.py:52-86` — `_guarded(fn, tool, cfg)` já envolve
  **toda** chamada de ferramenta MCP (confirmado: todos os ~20
  `@server.tool()` em `build_server()`, linhas 524-650+, passam por ele). É o
  único ponto de instrumentação necessário — não precisa tocar em cada
  ferramenta individualmente.
- `docs/09-mcp.md` já documenta o formato `{"ts":...,"tool":"search_hybrid","ms":84,"hits":10,"query_hash":"a3f1..."}`
  em `.ragx/logs/mcp.jsonl` — **mas isso nunca foi implementado** (confirmado:
  zero ocorrências de `mcp.jsonl` em `src/ragx/`). Só existe log de erro
  (`src/ragx/diagnostics.py`, `errors.log`).
- `cfg.state_dir / "logs"` já é criado por `ragx init`
  (`src/ragx/cli/commands/init.py:89`) — o diretório existe, só falta escrever
  nele.
- `ContextPack.estimated_tokens` (`src/ragx/context/engine.py`) já é o número
  real de tokens que `build_context` entrega — não precisa calcular nada
  novo, só capturar o que já existe no retorno.

### Mudança proposta

Estender `_guarded` para medir e logar, sem mudar sua assinatura nem o
comportamento de erro existente:

```python
def _guarded(fn: Any, tool: str, cfg: Config) -> Any:
    inicio = time.monotonic()
    try:
        resultado = fn()
        _log_call(cfg, tool, inicio, resultado)
        return resultado
    except ValidationError as exc:
        ...  # inalterado
    except Exception as exc:
        ...  # inalterado
```

`_log_call` (nova função, mesmo arquivo ou `src/ragx/mcp/telemetry.py` se
`server.py` já estiver grande demais — verificar tamanho atual antes de
decidir) escreve UMA linha JSON em `cfg.state_dir / "logs" / "mcp.jsonl"`:

```json
{"ts": "2026-09-21T18:03:00Z", "tool": "search_hybrid", "ms": 84, "project": "ragx"}
```

Para `build_context` especificamente, quando `resultado["ok"]` é `true`,
adiciona `"tokens_delivered": resultado["data"]["estimated_tokens"]`.

### Decisões de escopo (honestas, para não inflar o log)

- Escreve mesmo quando a ferramenta falha (`ok: false`)? **Sim** — uma
  ferramenta que falha repetidamente é um dado de telemetria relevante
  (`tool`, `ms`, sem `tokens_delivered`).
- Rotaciona o arquivo? **Fora de escopo desta primeira versão** — um projeto
  de uso normal não gera volume que justifique rotação agora; se virar
  problema real, é uma tarefa separada, não uma suposição antecipada aqui.
- Grava a query/argumentos? **Não** — mesma política que `docs/09-mcp.md` já
  define para queries (só hash, nunca texto), e aqui nem hash: telemetria de
  uso não precisa do conteúdo da chamada, só do fato dela ter acontecido.

### Auto-registro no hub (a pedido explícito do usuário)

`ragx init` (`src/ragx/cli/commands/init.py`) passa a chamar
`ragx.federation.hub.register(cfg, path=root)` ao final, best-effort (nunca
falha o `init` se o registro no hub falhar — por exemplo, projeto marcado
`visibility = "private"`, que `hub.register` já recusa de propósito). Isso é
o que o usuário pediu: "ele deveria receber o caminho na indexação inicial".

Projetos já indexados antes desta mudança (os 11 desta sessão) precisam de
`ragx project register <caminho>` manual, uma vez cada — comando que já
existe (`src/ragx/cli/commands/federation_cmd.py:97`), não é trabalho novo.

### Testes (Parte 1)

- `.ragx/logs/mcp.jsonl` recebe uma linha por chamada, incluindo chamadas que
  falham.
- `build_context` bem-sucedido inclui `tokens_delivered`; outras ferramentas
  não têm essa chave.
- `ragx init` registra o projeto no hub quando ele não é `private`; não
  quebra o `init` quando o registro falha.
- Teste arquitetural existente (`ragx.mcp` não importa `os`/`subprocess`/
  cliente HTTP) continua passando — `_log_call` só usa `pathlib`/`json`,
  já disponíveis no módulo.

---

## Parte 2 — App Electron

### Stack

- Electron + React + TypeScript + Vite, dentro do scaffold já existente em
  `src/app/` (confirmado: `npm create vite -- --template react-ts` puro,
  `package.json` com React 19, nada customizado ainda).
- `electron-builder` para empacotar o `.exe` (NSIS installer, padrão Windows)
  — mais usado e mais documentado que `electron-forge` para este caso de uso.

### Arquitetura de dados — sem servidor

O processo principal do Electron (Node, tem acesso a filesystem) lê
diretamente, sem abrir porta nenhuma:

| Fonte | Conteúdo | Formato |
|---|---|---|
| `~/.ragx/hub/registry.json` | lista de projetos conhecidos (id, nome, caminho, chunks, status) | JSON, já existe (`hub.py:_write_registry`) |
| `<projeto>/.ragx/knowledge.db` | contagem real de documentos/chunks/embeddings | SQLite — `better-sqlite3` (síncrono, mais simples que async para leitura local) |
| `<projeto>/.ragx/logs/mcp.jsonl` | chamadas MCP, tokens entregues (Parte 1) | JSONL, um `tail` incremental |

O processo de **renderer** (React) nunca toca filesystem direto — recebe os
dados via IPC (`ipcMain.handle`/`ipcRenderer.invoke`), que é o padrão de
segurança do Electron (renderer sem `nodeIntegration`, `contextIsolation:
true`).

### Polling

O processo principal relê as três fontes a cada N segundos (configurável,
padrão 5s) e empurra o resultado pro renderer via `webContents.send`. Sem
file-watch nesta versão — ler um SQLite pequeno e um JSONL a cada 5s é
barato o bastante para não justificar a complexidade de um watcher.

### Telas

Uma tela só, duas colunas:

- **Esquerda** — lista de projetos (do `registry.json`), nome + badge de
  status (`ok`/`degraded`/`stale`, já existe no hub).
- **Direita** — projeto selecionado:
  - Documentos / Chunks / Embeddings (contagem direta do `knowledge.db`)
  - Chamadas MCP por ferramenta, últimas 24h (agregado do `mcp.jsonl`)
  - Tokens entregues (soma real de `tokens_delivered`) + link/botão "ver
    economia estimada" que roda `ragx trial --json` sob demanda (processo
    filho, não é polling contínuo — é caro, só quando pedido)
  - Achados de segurança do último `ragx security scan` (relendo a saída do
    comando sob demanda, mesmo botão de "atualizar")

Sem login, sem configuração na primeira tela — abre e já mostra o que o hub
conhece. Se o hub estiver vazio, mensagem simples apontando pro
`ragx project register`.

### Testes (Parte 2)

- Leitura do `registry.json` com hub vazio não quebra a UI (mostra estado
  vazio, não crash).
- Leitura de `knowledge.db` de um projeto cujo caminho no registro não existe
  mais no disco (usuário moveu/apagou a pasta) — mostra status "indisponível"
  para aquele projeto, não derruba os outros.
- `mcp.jsonl` ausente (projeto nunca usado via MCP ainda) — mostra zero
  chamadas, não erro.

## Auto-review da spec

- Placeholder scan: nenhum "TBD" — toda decisão em aberto foi resolvida
  explicitamente (rotação de log: fora de escopo, por quê; telemetria em
  falha: sim, por quê).
- Consistência interna: Parte 1 e Parte 2 usam os mesmos nomes de campo
  (`tokens_delivered`, `ms`, `tool`) — conferido, sem divergência.
- Escopo: as duas partes são implementáveis e testáveis separadamente; cada
  uma vira sua própria tarefa no plano de implementação.
- Ambiguidade: "tempo real ou polling" do pedido original foi resolvido para
  polling explicitamente, com a razão (simplicidade) documentada — não fica
  em aberto para quem for implementar decidir sozinho.
