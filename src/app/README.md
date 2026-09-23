# RAGX Painel

Painel desktop (Electron) para o RAGX. Mostra os projetos registrados no hub
(`~/.ragx/hub/registry.json`), o estado de cada índice, a fila de tarefas em
andamento e o estado das três conexões de que o RAGX depende (CLI, Claude
Code, Ollama). Roda 100% local: sem login, sem telemetria enviada para fora
da máquina, só leitura de arquivos locais e execução do CLI `ragx` já
instalado no sistema. Tema sempre escuro; título da janela "RAGX Painel".

## Telas

- **Projetos**: grade de cards, um por projeto do hub. Cada card mostra o
  selo de estado ("Atualizado", "Defasado", "Embeddings faltando", "Sem
  hooks", "Com problema", "Pasta ausente" ou "Indexando…"), a pasta, a
  branch atual (com aviso quando o índice é de outra branch), há quanto
  tempo foi indexado, a cobertura de embeddings e um botão que faz o que o
  estado pede. Um filtro segmentado separa "Todos", "Defasados" e "Com
  problema"; a busca no topo ignora maiúsculas e acentos. "Adicionar
  projeto" pede uma pasta, lista os projetos do RAGX encontrados dentro
  dela e instala os hooks de git por padrão.
- **Detalhe do projeto**: responde "o índice está em dia?" com os motivos
  exatos de `ragx status --json` e mostra a linha do tempo das últimas 10
  indexações (quando, quem disparou, o modo, a branch e o commit). Também
  traz os números do índice com a cobertura de embeddings, o interruptor
  dos hooks de git, os botões "Atualizar agora", "Gerar embeddings
  faltantes" e "Reindexar do zero" (com segundo clique), as ações que
  alteram `knowledge/` versionado (sincronizar, reconstruir grafo, gerar
  dicionário), o uso pelos agentes nas últimas 24 horas, a economia
  estimada sob demanda (`ragx trial`), os achados de segurança sob demanda
  (`ragx security scan`) e "Remover do hub" (com segundo clique; nada é
  apagado no disco).
- **Conexões**: três cards (RAGX CLI, Claude Code e Ollama no Docker), cada
  um com o selo "Conectado", "Atenção" ou "Não conectado", os fatos da
  checagem e as correções de um clique ("Registrar para todos os
  projetos", "Iniciar container", "Baixar nomic-embed-text"). O painel
  confere as três a cada 30 segundos, na hora com "Verificar agora" e logo
  depois que uma correção termina.
- **Como funciona**: repete a explicação do primeiro passo da configuração
  inicial e permite refazê-la.
- **Configuração inicial (onboarding)**: tela cheia, sem barra lateral, com
  quatro passos (como o RAGX funciona, conexões, escolher os projetos,
  indexar). Aparece na primeira abertura ou quando o hub está vazio;
  "Começar" enfileira a indexação dos projetos marcados, "Pular
  configuração" só marca o onboarding como feito.

Uma barra superior comum às telas (exceto onboarding) traz a busca de
projeto, o indicador da fila ("2 tarefas", com progresso, previsão e botão
"Cancelar" por tarefa) e um ponto de saúde das conexões em texto, nunca só
pela cor.

## Rodando em desenvolvimento

```bash
npm install
npm run dev:electron   # Vite (renderer) + Electron com hot reload
```

## Testes e checagens

```bash
npm test                                    # suíte vitest
npm run lint                                # eslint
npx tsc -p tsconfig.app.json --noEmit       # tipos do renderer
npx tsc -p tsconfig.electron.json --noEmit  # tipos do processo principal
```

## Empacotando

```bash
npm run package
```

Gera o instalador Windows (`.exe`, NSIS) em `release/`. O comando roda o
build do renderer, compila o processo principal e chama `electron-builder`
(config em `electron-builder.yml`).

## De onde vêm os dados

O processo principal lê, para cada projeto do hub, `.ragx/status.json`; se o
arquivo não existir, cai para contagens lidas direto de
`.ragx/knowledge.db` (SQLite, via `sql.js`) como aproximação. A branch e o
commit atuais vêm de `git --no-optional-locks`, para nunca disputar o
`.git/index` com um `git` do usuário rodando ao mesmo tempo. O painel monta
esse retrato (o "snapshot") por polling a cada 5 segundos e também logo
depois que uma tarefa termina, sem esperar o próximo tick.

A resposta completa de `ragx status --json` (com os motivos de defasagem e o
histórico de indexações) só é pedida para o projeto aberto no momento na
tela de Detalhe, nunca para todos de uma vez.

Leitura de arquivo do projeto do usuário fica restrita a
`.ragx/status.json`, `.ragx/knowledge.db`, `.ragx/logs/mcp.jsonl` e à
existência de `ragx.toml`; nenhum conteúdo de código-fonte é lido.

## A regra de IPC

O renderer nunca manda caminho de disco nem argumento livre para o processo
principal. Toda ação é pedida por **tipo de tarefa (`kind`) e id de
projeto** (`enqueueJob({ kind, projectId })`); um `projectId` desconhecido é
recusado antes de qualquer processo nascer. Quando o usuário escolhe uma
pasta (diálogo nativo ou "Adicionar projeto"), o caminho vira um **token
opaco** guardado só no processo principal; o renderer só volta a ver esse
token, nunca o caminho em si. Comandos externos rodam sempre por
`spawn`/`execFile` com lista de argumentos, nunca com `shell: true`.

## A fila de tarefas

Uma fila serial: no máximo uma tarefa `running` por vez, porque o Ollama é
compartilhado entre projetos. Pedidos duplicados (mesmo tipo, projeto e,
quando faz sentido, mesmo modelo ou pasta) são deduplicados: o segundo
pedido devolve a tarefa já enfileirada em vez de empilhar outra. Uma linha
`{"phase":"busy"}` emitida por `ragx index --progress` vira uma nota
"agendado" na tarefa, não um erro.

O catálogo é fechado: só estes 13 tipos existem, e cada um sabe qual
comando roda.

| `kind`            | Comando                                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `add-project`     | `ragx init <pasta>`, depois `ragx index <pasta> --progress --source panel` (e `ragx hooks install <pasta>` se marcado) |
| `update`          | `ragx index <pasta> --progress --source panel`                                                                         |
| `embed`           | `ragx index <pasta> --embed-only --progress --source panel`                                                            |
| `reindex-full`    | `ragx index <pasta> --full --progress --source panel`                                                                  |
| `sync`            | `ragx sync` (cwd = pasta do projeto)                                                                                    |
| `graph`           | `ragx graph rebuild` (cwd = pasta do projeto)                                                                           |
| `dictionary`      | `ragx dictionary generate` (cwd = pasta do projeto)                                                                     |
| `hooks-install`   | `ragx hooks install <pasta>`                                                                                            |
| `hooks-uninstall` | `ragx hooks uninstall <pasta>`                                                                                          |
| `remove-from-hub` | `ragx project unregister <nome>`                                                                                       |
| `mcp-register`    | `ragx mcp install --client claude-code`                                                                                |
| `ollama-start`    | `docker start ollama`                                                                                                  |
| `ollama-pull`     | `docker exec ollama ollama pull <modelo>`                                                                              |

## Estrutura

- `src/`: UI React (renderer process): páginas em `src/pages/`, componentes
  em `src/components/`, hooks de dados em `src/hooks/` e o tipo do bridge
  IPC em `src/types/ragx-bridge.d.ts`.
- `electron/`: processo principal: janela e IPC (`main.ts`, `ipc.ts`,
  `preload.ts`), snapshot do hub (`data/`), checagem das conexões
  (`connections/checks.ts`), catálogo e fila de tarefas (`jobs/`) e busca de
  projetos numa pasta (`projects/discovery.ts`).
