# 22 — VS Code e desempenho da conexão

Como a extensão do VS Code encontra o RAGX, sobe o processo, fica pronta e se
recupera quando algo cai — e onde o tempo realmente vai.

> A referência da extensão para quem a **usa** é
> [vscode-plugin/README.md](../vscode-plugin/README.md). Este documento é sobre
> o mecanismo: quem mede desempenho ou mexe na conexão começa aqui.

---

## O caminho completo

```text
VS Code abre a janela
   ↓  activationEvents: workspaceContains ragx.toml | knowledge/manifest.json | .ragx/knowledge.db
activate()                       registra comandos, barra de status, webview — sem bloquear
   ↓
discover()                       procura os marcadores; só stat, nunca abre arquivo   ~1 ms
   ↓
spawn `ragx mcp serve --read-only`
   ↓
boot do Python + import do SDK de MCP                                            ~1,5 s
   ↓
handshake MCP (initialize)
   ↓
listTools()                                                                       ~8 ms
   ↓
get_playbook()                   prova que o índice responde, não só que o processo subiu   ~2 ms
   ↓
READY
```

A extensão **nunca bloqueia o VS Code**: `activate()` devolve imediatamente e a
conexão corre em segundo plano, com a interface em `connecting`.

---

## Onde o tempo vai

Medido neste repositório com `vscode-plugin/scripts/bench-connect.mjs`
(Windows, 7 rodadas, mediana):

| Etapa | Antes | Depois |
|---|---:|---:|
| spawn + boot do Python + handshake | 1736 ms | 1457 ms |
| `listTools` | 7 ms | 9 ms |
| primeira chamada (`get_playbook`) | 2 ms | 7 ms |
| chamada seguinte | 2 ms | 2 ms |
| **total até READY** | **1747 ms** | **1482 ms** |

A conclusão que importa é a repartição, não o total: **mais de 98% do tempo é
boot de processo Python.** Transporte, handshake, listagem de ferramentas e as
consultas em si somam ~15 ms. Qualquer otimização de protocolo, cache de
resposta ou timeout mexe nesses 15 ms.

Decompondo o boot (`python -X importtime`):

| O que | Custo |
|---|---:|
| interpretador Python vazio | ~78 ms |
| import do SDK `mcp` | ~1,4 s |
| `ragx.mcp.server` + CLI | ~150 ms |

O SDK de MCP domina, e é de terceiros: ele constrói os modelos pydantic de
todas as versões do protocolo e puxa `starlette`/`sse_starlette` mesmo quando
o transporte é stdio. Não há como evitá-lo servindo MCP.

O que **era** nosso e foi corrigido: `ragx/cli/main.py` importa os 21 módulos
de comando para registrá-los, e cada um importava seu subsistema no topo.
`ragx mcp serve` carregava `numpy`, o motor de contexto e o avaliador de
agentes — nada disso necessário para responder. Os imports pesados passaram
para dentro das funções:

| Comando | Antes | Depois |
|---|---:|---:|
| `ragx --version` | 882 ms | 523 ms |
| `ragx documents --limit 5` | 1086 ms | 597 ms |
| `ragx entities --limit 5` | 938 ms | 537 ms |
| `ragx search --mode keyword` | 917 ms | 674 ms |
| `import ragx.cli.main` | 899 ms | 484 ms |

Isso vale para **toda** invocação da CLI — inclusive o transporte de reserva
da extensão, que roda um processo por consulta.

### A lição

O ganho real não vem de encurtar 1,5 s: vem de **pagá-la uma vez só**. Por
isso o transporte padrão é um processo quente, e por isso as proteções da
seção seguinte existem.

Para medir na sua máquina:

```bash
cd vscode-plugin
node scripts/bench-connect.mjs --cmd ragx --cwd /caminho/do/projeto -n 5
```

---

## Uma conexão, um processo

Três eventos podem pedir conexão quase ao mesmo tempo: a ativação, uma troca de
pasta no workspace e uma mudança de configuração. Sem fila, cada um sobe o seu
processo Python, e só o último fica referenciado — os outros viram processos
órfãos de ~100 MB que ninguém fecha.

`conectar()` mantém uma promessa única em `conexaoEmCurso`; quem chega durante
uma conexão em andamento espera por ela em vez de começar outra.

Pelo mesmo motivo, **trocar de pasta só reconecta se a raiz do projeto mudar**.
Adicionar uma pasta de anotações ao workspace não muda nada para o RAGX, e
derrubava a conexão para pagar o boot de novo.

---

## Prontidão

"O processo subiu" e "o RAGX pode responder" não são a mesma coisa. Um processo
Python vivo num diretório sem índice aceita a conexão e recusa toda consulta.

Por isso o handshake termina com `get_playbook()`: é uma chamada barata (~2 ms)
que só responde se houver projeto e índice do outro lado. É a diferença entre
*process alive* e *RAGX ready*.

Os estados que a barra de status mostra:

| Estado | Significa |
|---|---|
| `connecting` | processo subindo ou handshake em curso |
| `ready` | conectado e com índice respondendo |
| `outdated` | conectado, mas há configuração sem índice — falta `ragx index .` |
| `syncing` / `indexing` | operação em andamento |
| `warning` | conexão perdida; reconexão agendada |
| `error` | não foi possível conectar, ou as tentativas acabaram |
| `disconnected` | não há projeto RAGX neste workspace |

Sempre com texto e ícone, nunca só cor.

---

## Quando cai

O processo pode morrer sem avisar: crash do Python, pipe fechado, `kill` de
fora, a máquina voltando do sleep. Antes, a extensão só descobria na consulta
seguinte — que falhava com um erro de transporte enquanto a barra de status
ainda dizia `Ready`.

Agora o transporte tem `onclose`/`onerror` e a extensão reage na hora:

```text
queda detectada
   ↓
estado vira `warning`
   ↓
reconexão agendada:  1 s → 2 s → 4 s → 8 s → 16 s → 32 s   (teto 60 s, 6 tentativas)
   ↓
conectou?  zera o contador
não conectou em 6 tentativas?  estado `error`, e o comando "RAGX: Reconnect" continua ali
```

A espera crescente não é detalhe: um RAGX não instalado falha em ~50 ms, e
tentar de novo imediatamente vira um laço de `spawn` a 100% de CPU. Já
`dispose()` **não** conta como queda — desligar de propósito não pode disparar
reconexão contra um cliente que acabou de ser trocado.

"RAGX: Reconnect" zera o contador: quem acabou de instalar o RAGX não deve
esperar o próximo passo do backoff para o comando parecer funcionar.

---

## Transporte

**stdio**, via `@modelcontextprotocol/sdk`. Continua sendo a escolha certa:

- não abre porta, não aceita conexão de fora, não precisa de autenticação;
- o isolamento é o do processo — um RAGX por projeto, com o `cwd` do projeto;
- funciona igual em Linux, macOS e Windows, sem named pipe nem socket de
  domínio;
- o custo medido é ~8 ms de `listTools` e ~2 ms por chamada. Trocar por socket
  ou HTTP disputaria esses milissegundos e traria porta, autenticação e mais
  superfície de ataque.

O transporte de reserva é a **CLI**: um processo por consulta. Mais lento por
natureza, e é por isso que a queda de ~40% no tempo de import da CLI importa
tanto para quem cai nele.

---

## Diagnóstico

`RAGX: Open Logs` abre o canal da extensão. Uma conexão bem-sucedida imprime a
repartição:

```text
[09:14:02] [RAGX VSCode] Discovering RAGX — 1ms
[09:14:02] projeto detectado: E:\projeto (ragx.toml, .ragx/knowledge.db)
[09:14:04] MCP pronto em 1482ms — 33 ferramentas (spawn+boot+handshake 1457ms · listTools 9ms · playbook 7ms)
[09:14:04] [RAGX VSCode] Ready — por mcp em 1485ms
```

Ler essa linha responde "por que demorou?" sem profiler: se
`spawn+boot+handshake` domina, o custo é boot de Python (esperado); se
`listTools` ou `playbook` disparam, o problema é o índice, não o processo.

O log **não** registra conteúdo de chunk, valor de segredo, token nem caminho
absoluto além da raiz do projeto.

### Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `Disconnected` sempre | não há `ragx.toml` nem índice no workspace — rode `ragx init` |
| `Error` logo na ativação | `ragx` fora do PATH; ajuste `ragx.command` para o caminho absoluto |
| `Outdated` | há configuração, falta índice — rode `ragx index .` |
| conexão cai repetidamente | veja o `stderr` do RAGX no canal de log, prefixado por `[ragx]` |
| grafo sem arestas | RAGX antigo com extensão nova, ou o contrário — ver [06 — Grafo](06-grafo.md#contrato-de-uma-relação) |

---

## O que não foi feito, e por quê

- **Servidor compartilhado entre janelas do VS Code.** Um processo por
  projeto, por janela, é o que mantém o isolamento simples: cada RAGX tem o
  `cwd` do seu projeto e morre com a janela. Compartilhar exigiria descoberta,
  lock de arquivo, contagem de referências e limpeza de processo obsoleto — e
  economizaria 1,6 s na segunda janela do mesmo projeto, que é raro.
- **Trocar o stdio por socket.** Disputaria os ~15 ms que não são o gargalo, em
  troca de porta aberta e autenticação.
- **Pré-aquecer o RAGX na ativação de todo workspace.** Subir Python em
  projeto que talvez não seja consultado troca latência por memória, em todas
  as janelas abertas.
