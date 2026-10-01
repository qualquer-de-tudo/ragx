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
  problema"; a busca no topo ignora maiúsculas e acentos. No topo, o
  resumo do hub (projetos, chamadas MCP em 24 h, tokens economizados em 14
  dias, quantos pedem atenção); cada card mostra economia, chamadas em 24 h
  e documentos. "Ordenar por" (nome, uso recente, estado) e "Grade/Lista"
  (tabela compacta com a mesma ação do card) ficam lembrados enquanto o
  painel estiver aberto. "Adicionar
  projeto" pede uma pasta, lista os projetos do RAGX encontrados dentro
  dela e instala os hooks de git por padrão.
- **Detalhe do projeto**: quatro abas. **Visão geral**: os números do
  índice com a cobertura de embeddings, "o índice está em dia?" com os
  motivos exatos de `ragx status --json` e o uso pelos agentes nas últimas
  24 horas. **Economia de tokens**: o uso real dos últimos 14 dias e a
  simulação sob demanda (`ragx trial`). **Histórico**: a linha do tempo das
  indexações (quando, quem disparou, o modo, a branch e o commit), com
  "Carregar mais". **Manutenção**: "Atualizar agora", "Gerar embeddings
  faltantes" e "Reindexar do zero" (com segundo clique), o interruptor dos
  hooks de git, os achados de segurança sob demanda (`ragx security scan`),
  as ações que alteram `knowledge/` versionado e "Remover do hub" (com
  segundo clique; nada é apagado no disco). A aba escolhida vale para o
  próximo projeto aberto; as outras ficam montadas e ocultas, então trocar
  de aba não perde estado.
- **Atividade**: o que os agentes e a CLI estão fazendo, ao vivo. No topo, o
  resumo das últimas 24 h (chamadas MCP, sessões do Claude, comandos no
  terminal, tokens economizados, projetos em uso); depois "Em andamento", com
  as indexações rodando agora (por hook, CLI ou fila do painel); e o feed dos
  eventos, do mais novo ao mais antigo: hora, projeto, o que foi (ferramenta
  MCP, `ragx search`, sessão aberta), quem (`Claude Code · empresa`, `Terminal
  do Claude · padrão`, `Terminal`), tokens com a economia e o tempo. Filtra
  por tipo e por projeto. Vem de `.ragx/logs/mcp.jsonl` e `cli.jsonl` de cada
  projeto local: o processo principal lê só o que foi acrescentado, a cada
  1,5 s, e empurra os eventos por `ragx:activity`. O card e o detalhe do
  projeto mostram "em uso agora", e o item do menu acende, quando houve
  evento no último minuto. Nunca mostra a consulta: o log não a tem.
- **Conexões**: uma faixa por peça (RAGX CLI, Claude Code e Ollama), na
  largura toda: ícone, nome, selo ("Conectado", "Atenção" ou "Não
  conectado") e resumo à esquerda, as correções de um clique à direita
  ("Registrar para todos os projetos", "Iniciar container", "Baixar
  nomic-embed-text", "Medir velocidade"...), e os fatos da checagem em
  blocos compactos embaixo. No topo, o resumo ("3 de 3 conectadas" ou
  quantas pedem atenção) ao lado de "Verificar agora". A faixa do Ollama
  mostra o modo (Docker ou local), o processador (GPU ou CPU, depois de
  medir) e a velocidade em chunks/s (ver "Ollama: Docker ou local"). A do
  Claude Code traz os **perfis** (contas): uma linha por `CLAUDE_CONFIG_DIR`
  (o padrão, os `~/.claude-*` com `.claude.json` e as pastas adicionadas à
  mão), com a pasta, se foi detectada ou adicionada, um aviso quando está
  ligada sem a dica de início de sessão e um interruptor próprio (`ragx
  claude on|off --profile`). "Adicionar perfil" escolhe a pasta e já liga o
  RAGX nela; "Remover" (só nos adicionados, com segundo clique) desliga
  antes de tirar da lista. O painel confere as três peças a cada 30
  segundos, na hora com "Verificar agora" e logo depois que uma correção
  termina.
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

## Medindo o consumo

O painel mede o próprio consumo (RAM, CPU e processos filhos por minuto) sem nenhum canal IPC novo e
sem custo quando desligado: o amostrador só existe com `RAGX_PANEL_METRICS=<arquivo.jsonl>`. Para uma
medição completa, com a janela visível, minimizada e oculta:

```bash
npm run build && npm run build:electron:ts        # a casca de produção (dist/ e dist-electron/)
node scripts/measure-runtime.mjs --plan visible:5,minimized:5,hidden:5 --label baseline-1.0.0-beta.5 \
     [--exe <caminho>] [--projects fixture12|real]
```

O script sobe o Electron com `--user-data-dir` temporário, leva a janela a cada estado pelo tempo
pedido, lê o JSONL (em `%TEMP%`, **não** versionado) e **acrescenta** uma seção a
`docs/medicao-runtime.md`: RAM (working set e privada), CPU por tipo de processo e filhos criados por
minuto por executável (`git`, `ragx`, `docker`...), mais o tempo da reconstrução do snapshot. A 1ª
amostra de cada execução é descartada (o CPU do Electron é medido desde a chamada anterior).
`fixture12` cria 12 repositórios `git init` e um hub de 12 projetos numa pasta temporária (o
`USERPROFILE` aponta para ela; nada da sua máquina é tocado); `real` lê o hub da máquina, somente
leitura. Em modo de medição o painel carrega `dist/index.html` (sem DevTools), para medir a casca de
produção mesmo sem empacotar.

A medição do Electron **não** empacotado difere pouco da do `.exe`; para medir o `.exe`:
`npm run build && npm run build:electron:ts && npx electron-builder --dir`, depois
`--exe "release/win-unpacked/RAGX Painel.exe"`. Meça com a fila de tarefas vazia: uma indexação em
andamento distorce a CPU. O contador de filhos (`electron/system/spawn-counter.ts`) cobre os três
pontos de criação de processo (`execFileText`, a fila de tarefas e `runRagxCommand`); os processos do
próprio Chromium aparecem pelas métricas do Electron.

## Empacotando

```bash
npm run package
```

Gera o instalador Windows (`.exe`, NSIS) em `release/`
(`RAGX-Painel-Setup-<versão>.exe`). O comando roda antes `npm run bundle`
(`scripts/prepare-bundle.mjs`), depois o build do renderer, compila o processo
principal e chama `electron-builder` (config em `electron-builder.yml`).
Precisa de rede, `uv` e `tar` (vem no Windows 10+).

**Na release.** Ninguém precisa gerar o `.exe` à mão para distribuir: o push de
uma tag `v*` roda o `.github/workflows/release.yml`, que testa, empacota o
painel, instala e desinstala o `.exe` num Windows limpo e o anexa à release,
com a versão no nome. Commit comum não gera instalador. A versão do painel
(`package.json`) acompanha a do produto; `scripts/versao.py` sobe as duas
juntas, e a release recusa a tag se alguma divergir:

```bash
uv run python scripts/versao.py 1.0.0-beta.4 --tag   # versão, CHANGELOG, commit e tag
git push origin main v1.0.0-beta.4                    # dispara a release
```

`npm run bundle` monta `resources/ragx-bundle/` (ignorado pelo Git), que o
`electron-builder` copia para `<instalação>
esources
agx-bundle`:

- `ragx-<versão>-py3-none-any.whl`, de `uv build --wheel` na raiz do repositório;
- `uv.exe`, extraído do zip oficial da Astral numa versão **fixa** (constante
  `UV_VERSION` no script), com o SHA256 publicado ao lado do zip conferido;
- `bundle.json` com `version`, `python` e o SHA256 de cada arquivo final.

### Como o painel instala a CLI

Ao terminar de copiar os arquivos, `build/installer.nsh` (`customInstall`)
executa `RAGX Painel.exe --bootstrap`. É a mesma rotina do botão "Instalar /
Tentar de novo" do card RAGX CLI: valida os hashes do bundle e roda
`uv tool install --force --python 3.12 <wheel>[all]` (com fallback sem o extra),
garante `~\.local\bin` no PATH do usuário e registra o MCP no Claude Code se ele
estiver instalado. O log fica em `%APPDATA%\app\bootstrap.log`. Falha do
bootstrap nunca falha a instalação (só avisa, e nada é exibido em `/S`): o
painel refaz na primeira abertura se `ragx` não for encontrado.

### Desinstalando

O desinstalador faz duas perguntas:

1. **Remover também a CLI ragx e o registro no Claude Code?** (padrão Sim)
2. **Remover também os dados do hub (`~\.ragx`)?** (padrão Não)

Em modo silencioso o padrão é não remover nada; peça na linha de comando:

```powershell
& "Uninstall RAGX Painel.exe" /S --remove-cli              # CLI + MCP + PATH
& "Uninstall RAGX Painel.exe" /S --remove-cli --remove-data # e ~\.ragx
```

A remoção roda `--uninstall-cli` **antes** de o NSIS apagar a pasta do painel
(por isso o hook é `customRemoveFiles`, e não `customUnInstall`, que só roda
depois). Ollama e os `.ragx/` dos projetos nunca são tocados. Atualizar o
painel por cima não pergunta nada nem remove a CLI. Desinstalar sem marcar a
CLI deixa o `ragx` instalado.

## De onde vêm os dados

O processo principal lê, para cada projeto do hub, `.ragx/status.json`. Se o
arquivo não existir (índice de uma versão antiga do RAGX, ou arquivo apagado), o
painel **nunca abre o `.ragx/knowledge.db`**: o projeto aparece como "Defasado"
com o motivo "Sem .ragx/status.json: reindexe este projeto (Atualizar agora)", e
o botão enfileira um `update`, que gera o arquivo (RAGX-0176; antes o painel
lia o banco inteiro para a memória a cada 5 s, via `sql.js`, só para três
`COUNT(*)`). A branch e o
commit atuais vêm dos **arquivos do git** (`.git/HEAD`, a ref solta ou
`.git/packed-refs`, e `.git/commondir` em worktree e submódulo; só metadado,
nenhum objeto nem conteúdo de código), sem criar processo: o snapshot rodava
`git rev-parse` e `git symbolic-ref` por projeto a cada 5 s (~290 processos
por minuto com 12 projetos). O resultado fica em cache por projeto (assinatura
de `mtime` e tamanho dos três arquivos) e devolve o mesmo objeto enquanto nada
muda. O `git --no-optional-locks` só roda como último recurso (`reftable`,
formato de ref desconhecido, pasta que não existe), para nunca disputar o
`.git/index` com um `git` do usuário. O painel monta
esse retrato (o "snapshot") por polling a cada 5 segundos e também logo
depois que uma tarefa termina, sem esperar o próximo tick. Um `running` em
`status.json` só conta enquanto o processo dono (`pid`) existe: um índice
cancelado ou um hook que morreu não deixam o card preso em "Indexando…".

O renderer só re-renderiza o que mudou (RAGX-0175). O snapshot chega com `generatedAt` novo a cada 5 s;
`shareSnapshot` (`src/snapshotShare.ts`) devolve o objeto anterior quando só ele mudou e, quando algo mudou,
reaproveita a referência de cada projeto inalterado, e o processo principal nem manda `ragx:snapshot` se o conteúdo
(sem `generatedAt`) é igual ao último enviado (`createSnapshotGate`; `getSnapshot` segue atualizado). A fila e as
conexões passam pela mesma comparação. O tempo vem de **um** relógio compartilhado por intervalo (`useClock`,
`useSyncExternalStore`): `useLiveIds` recalcula "em uso agora" a cada 5 s mas só renderiza quando a pertença muda, e
os rótulos "há N min" são a folha `<RelativeTime>` (relógio de 60 s), então só ela re-renderiza por minuto.
`ProjectCard`, a linha da lista e `ConnectionCard` são `memo`, com handlers estáveis (`onAction(project, kind)`).
Com 12 projetos e dados parados, 60 s custam 12 renders de card (a montagem) e 0 do `App`, contra 300 e 24.

As conexões (RAGX CLI, Claude Code, Ollama) também são checadas só pelo
processo principal: a cada 30 segundos, no startup, logo depois de uma
correção de conexão e no "Verificar agora". Cada resultado vai ao renderer
pelo evento `ragx:connections`; checagens pedidas ao mesmo tempo viram uma só.
Os três pollers (snapshot a cada 5 s, conexões a cada 30 s, atividade a cada
1,5 s) **pausam com a janela fora da vista**: minimizada, oculta, tela
bloqueada ou computador suspendendo (`powerMonitor` e os eventos `show`,
`hide`, `minimize`, `restore`). Fora da vista nada roda; na volta, um snapshot
na hora (se algo mudou ou já passou o intervalo) e uma passada de atividade, e
conexões só se a última checagem tem mais de 30 s. Uma tarefa que termina com
a janela fora da vista só marca o snapshot como sujo; a fila e as tarefas
**não** pausam. O painel é de **instância única**: abrir de novo foca a janela
que já existe (`RAGX_PANEL_ALLOW_MULTI=1` desliga a trava, para dev e medição;
`--bootstrap` e `--uninstall-cli`, chamados pelo instalador, nunca a pegam).
O tick de 30 s é **leve** (um handler interno do processo principal, sem canal
de IPC): a versão do `ragx` fica em cache pela assinatura (`mtime` e tamanho)
do executável, o Docker é consultado por UM `docker ps` (não mais `--version`,
`info` e `ps -a`), a API do Ollama é consultada primeiro (HTTP, sem processo) e
`docker ps`/`tasklist` só rodam quando precisam: `docker ps` se o Docker estava
de pé na última detecção completa (senão, no máximo a cada 5 minutos) e
`tasklist` só com suspeita de conflito (API no ar e container rodando) ou com a
API fora do ar e um Ollama nativo instalado; com a API no ar e nenhum container
rodando, "Ollama local rodando" é inferido. A detecção **completa** continua no
startup, no fim de tarefa, no "Verificar agora" e em toda condição de passo da
fila: o dado inferido nunca decide uma tarefa.

A telemetria do MCP de cada projeto (`.ragx/logs/mcp.jsonl`) é lida de forma
**incremental** (`createTelemetryTail`): cada arquivo tem um deslocamento, e sem
crescimento o snapshot só faz um `stat` e devolve o mesmo objeto; com
crescimento lê apenas o que foi acrescentado, até a última quebra de linha. A
primeira leitura pega só os últimos 4 MB (e o `mcp.jsonl.1` da rotação, se o
arquivo for menor que isso); arquivo que encolheu ou trocou de `ino` +
`birthtimeMs` é relido do zero. O resumo é idêntico ao da leitura completa
(`readTelemetryFull`, mantida como referência). O servidor Python rotaciona o
log aos 5 MiB. `node scripts/measure-telemetry.mjs` reproduz a medição.

A resposta completa de `ragx status --json` (com os motivos de defasagem e o
histórico de indexações) só é pedida para o projeto aberto no momento na
tela de Detalhe, nunca para todos de uma vez.

Leitura de arquivo do projeto do usuário fica restrita a
`.ragx/status.json`, `.ragx/knowledge.db`, `.ragx/logs/mcp.jsonl`, aos
arquivos de metadado do git (`.git/HEAD`, `.git/refs/**`, `.git/packed-refs`,
`.git/commondir`, `.git/config` só para detectar `reftable`; no máximo 64 KB
cada) e à existência de `ragx.toml` e `.git` (a busca de "Adicionar projeto" também
oferece repositórios git sem `ragx.toml`, marcados "novo"); nenhum conteúdo
de código-fonte é lido. Depois de um `add-project`, `name` e `visibility`
da seção `[project]` do `ragx.toml` são lidos só para explicar por que o
projeto não entrou no hub (colisão de nome ou projeto privado).

## Larguras suportadas

O painel funciona de **450 px** (zoom de 200% numa janela de 900 DIP, o mínimo da janela) a **3440 px** de CSS, e 60
medições (10 telas x 6 larguras: 450, 480, 600, 900, 1280, 3440) dão 0 elemento fora da janela. Breakpoints, só estes
(`src/breakpoints.ts`, conferido por `css-breakpoints.test.ts`): **640** (barra superior em duas linhas, barra lateral
de 56 px), **900** (barra superior compacta: "RAGX no Claude", a fila e "Conexões" ficam só com trilho/contador/ponto,
o texto continua para o leitor de tela) e **1200** (a largura máxima do conteúdo e da barra superior vira
`clamp(1200px, 55vw, 1800px)`, e as duas têm as mesmas bordas). A economia, o feed de atividade e o cartão de
projeto reagem ao espaço que têm (`@container`), não à janela.

Para repetir a medição: `npm run build && node scripts/visual-check.mjs` (usa o Microsoft Edge pelo `playwright-core`,
sem baixar navegador, com `window.ragx` simulado em `scripts/visual-fixtures/bridge.js`; `--widths`, `--screens`,
`--shots <pasta>` para salvar capturas, `--json`). Sai com 2 se não achar o Edge ou o `dist/`. Nunca roda no
`npm test`. `node scripts/visual-probe.mjs --screen atividade --width 450 --selector ".activity-feed"` lista a
largura de cada ancestral, para achar quem alarga uma coluna (a causa de quase todo estouro foi uma grade sem
`grid-template-columns: minmax(0, 1fr)`).

## Tokens de design e contraste

Toda cor, tamanho de fonte, camada e duração do renderer vem de um token em `src/index.css` (`:root`): superfícies e
tinta (`--bg`, `--surface*`, `--ink*`), estado semântico com variantes de texto, preenchimento, fundo e borda
(`--accent-text/-solid/-wash/-line`, `--good-*`, `--warning-*`, `--critical-*`), `--scrim`, `--line-control` (borda de
campo, seletor e interruptor, >= 3:1), `--series-*` (gráfico), escala de espaço `--sp-2..32`, de tipografia
`--fs-xs..stat`, de camadas `--z-*` e `--dur`. Botão primário e perigo usam `--accent-solid` e `--critical-solid`
com texto branco (>= 4,5:1); texto colorido usa `--accent-text` e `--critical-text`. Quatro testes seguram isso:
`contrast.test.ts` (matriz WCAG AA calculada a partir do CSS, por tema, com `src/test/wcag.ts`),
`no-hardcoded-color.test.ts` (nenhum `#hex` nem `rgb()` fora do `:root`), `no-em-dash.test.ts` e
`css-ratchet.test.ts` (`gap`/`padding`/`margin` com `px` literal só podem diminuir; baixe o número em
`css-ratchet.json` ao migrar mais para `--sp-*`). Só o rótulo da logo (`.brand-name`, 10 px) fica fora da escala.

## Primitivos de UI

Os padrões repetidos moram em `src/components/ui/` (reexportados por `ui/index.ts`), sem biblioteca: `Segmented`
(grupo de rádio com setas, Home e End e só o marcado no Tab), `Switch` e `SwitchButton`/`SwitchTrack` (`role="switch"`),
`Modal` (foco preso, Esc, clique fora, devolve o foco), `Icon` (mapa `ICONS` em `ui/icons.ts`, sempre `aria-hidden`),
`IconButton` (`label` obrigatório no tipo), `EmptyState` (`role="status"`) e `Tooltip` (no lugar do atributo
`title`, que teclado e toque não alcançam: abre no foco e no mouse com atraso, `aria-describedby`, Esc fecha, balão
fixo na janela por portal, sem wrapper: `{(tip) => <elemento {...tip} />}`). `ui-primitives.test.ts` falha se
`role="radio"`, `role="switch"` ou `<svg` aparecerem fora de `ui/` (salvo `RagxMark` e o gráfico de `TokenSavings`).
Só o `<abbr title="Documentos">` da lista continua com `title`.

## Avisos (toasts)

Toda falha de ação aparece (RAGX-0180). `src/toast.ts` é um store de módulo (`notify.error/success/info`, no máximo 3
na tela, o mesmo texto em 3 s não duplica, sucesso some em 4 s e erro em 8 s) e `ui/Toaster` o mostra, montado uma vez
em `App` (no shell e no onboarding): a região `aria-live` fica sempre no DOM, erro é `role="alert"`, sucesso é
`role="status"`, o prazo pausa com ponteiro ou foco e "Fechar aviso" tira na hora. `enqueue` e `enqueueConnectionAction`
(`src/jobs.ts`), cancelar tarefa, copiar o texto de ajuda, escolher pasta e salvar o fim do onboarding avisam com o
motivo, que `ipcErrorMessage` limpa do prefixo `Error invoking remote method '...'` que o Electron põe. Uma tarefa que
passa a `failed` também avisa (`useJobFailureToasts`; o que já tinha falhado antes da primeira lista e o `cancelled`
não). Falha de **leitura** (snapshot, conexões, atividade) continua só no console: é da `RAGX-0182`.

## Segurança do renderer

O painel não carrega nada de fora (um teste, `no-remote-resources.test.ts`, falha se aparecer `http(s)://`, `ws://`
ou `@import` no código do renderer). Por isso o build de **produção** leva uma Content-Security-Policy restritiva,
injetada em `dist/index.html` como `<meta>` pelo plugin de `csp.ts` (cabeçalho HTTP não vale em `file://`):
`default-src 'none'`, `script-src 'self'`, `style-src 'self'`, `img-src 'self' data:`, `connect-src 'self'`,
`base-uri 'none'`, `form-action 'none'`, e `style-src-attr 'unsafe-inline'` só para a largura dinâmica das barras
(`style={{ ... }}`). Sem `'unsafe-eval'` e sem `'unsafe-inline'` em script ou estilo. `frame-ancestors` fica de fora:
o navegador o ignora em `<meta>`. Em desenvolvimento (`npm run dev:electron`) o Vite serve o `index.html` **sem**
essa política, porque o plugin do React injeta script inline e o HMR usa WebSocket.

O menu da aplicação é mínimo (`electron/menu.ts`): Edição (copiar e colar), Exibir (só o zoom e a tela cheia) e
Sair. As DevTools, o F12 e os itens de recarregar só existem em desenvolvimento ou com `RAGX_DEVTOOLS=1`
(`webPreferences.devTools`); empacotado e sem a variável, não abrem.

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
`{"phase":"busy"}` emitida por `ragx index --progress` vira uma nota na
tarefa, não um erro, e a nota diz o que de fato acontece com cada tipo (o
pedido agendado roda como indexação incremental, então "Reindexar do zero"
pede para ser repetido). O código de saída 4 (índice ocupado) também vira
nota. A linha `{"phase":"done"}` com `embed_error` marca a tarefa como
falha ("Os embeddings não foram gerados: ..."), porque `ragx index` sai com 0
mesmo quando o embedder falha. Um `add-project` que termina sem a pasta no
registro do hub também falha, com o motivo. O texto de erro vem do bloco
`erro:` do stderr (os processos rodam com `COLUMNS=500` para o Rich não
quebrar a mensagem), e comandos globais rodam na pasta do usuário.

O catálogo é fechado: só estes 16 tipos existem, e cada um sabe qual
comando roda.

| `kind`            | Comando                                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `add-project`     | `ragx init <pasta>`, depois `ragx index <pasta> --progress --source panel` (e `ragx hooks install <pasta>` se marcado e a pasta for um repositório git) |
| `update`          | `ragx index <pasta> --progress --source panel`                                                                         |
| `embed`           | `ragx index <pasta> --embed-only --progress --source panel`                                                            |
| `reindex-full`    | `ragx index <pasta> --full --progress --source panel`                                                                  |
| `sync`            | `ragx sync` (cwd = pasta do projeto)                                                                                    |
| `graph`           | `ragx graph rebuild` (cwd = pasta do projeto)                                                                           |
| `dictionary`      | `ragx dictionary generate` (cwd = pasta do projeto)                                                                     |
| `hooks-install`   | `ragx hooks install <pasta>`                                                                                            |
| `hooks-uninstall` | `ragx hooks uninstall <pasta>`                                                                                          |
| `remove-from-hub` | `ragx project unregister -- <nome>`                                                                                    |
| `mcp-register`    | `ragx mcp install --client claude-code`                                                                                |
| `ollama-start`    | `docker start ollama` (Docker) ou `ollama serve` destacado e espera da API (local); qual dos dois é decidido por `chooseStartMode` (ver abaixo) |
| `ollama-pull`     | segue o modo: `docker exec ollama ollama pull <modelo>` (Docker) ou `ollama pull <modelo>` (local)                     |
| `ollama-use-native` | `winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements` (se não estiver instalado), `docker stop ollama` (se estiver rodando), `ollama serve` destacado (se não estiver rodando), espera da API e `ollama pull <modelo>` para cada modelo em uso. Instala antes de parar o container: se o `winget` falhar, o Docker continua servindo |
| `ollama-use-docker` | recusa com "O Docker não está instalado nesta máquina." ou "Abra o Docker Desktop e aguarde ele iniciar." (Docker parado); senão `docker pull ollama/ollama` (se o container não existe), encerra o Ollama local (ver `ollama-stop`), `docker start ollama` (se o container existe) ou `docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama --restart unless-stopped [--gpus all] ollama/ollama` (se não existe), espera da API e `docker exec ollama ollama pull <modelo>` para cada modelo em uso. A imagem é baixada antes de encerrar o Ollama local |
| `ollama-stop`     | `docker stop ollama` (se estiver rodando) e o encerramento do Ollama local: no Windows, `powershell -NoProfile -NonInteractive -Command <script>`, que encerra só `ollama.exe` e `ollama app.exe` cujo executável fica na pasta do Ollama detectado (a pasta vai pela variável de ambiente `OLLAMA_DIR` do processo, nunca dentro do comando; sem pasta conhecida, o passo não existe); em macOS e Linux, `pkill -x ollama` |

## Ollama: Docker ou local

O RAGX fala com o Ollama em `http://localhost:11434` (`/api/embed`,
`/api/tags`), seja um container Docker ou uma instalação na máquina, então
nada muda na configuração do RAGX entre os modos. Toda a novidade fica no
painel, no processo principal (`electron/ollama/`).

**Detecção.** O painel detecta, a cada checagem de conexões, o Docker
(instalado, rodando, container `ollama` existente ou parado), a placa de
vídeo (`nvidia`, `amd`, `intel`, `apple`, `none` ou `unknown`), o Ollama
local (instalado ou respondendo) e a API na porta 11434. O modo é um fato
detectado, não uma preferência: `docker` (container rodando), `native`
(Ollama local respondendo), `none` (nada responde) ou `conflict` (os dois de
pé, disputando a porta). "Conectado" significa API respondendo e modelos
baixados, não "existe um container".

**Recomendação.** Sempre substituível, com o motivo mostrado no card:

| Situação | Recomendado |
| --- | --- |
| macOS | local (o Docker não usa a GPU no macOS) |
| GPU NVIDIA e Docker instalado | Docker (container com `--gpus all`) |
| GPU NVIDIA sem Docker | local |
| GPU AMD, em qualquer sistema | local (o Docker não repassa GPU AMD) |
| GPU Intel, nenhuma ou desconhecida | Docker se instalado, senão local |

**Tarefas.** Trocar de modo é uma tarefa da fila: `ollama-use-native` e
`ollama-use-docker` param o outro modo, instalam, criam ou iniciam o
escolhido, esperam a API e baixam os modelos que os projetos usam (cada
passo só roda se ainda for necessário, decidido na hora); `ollama-stop`
para os dois modos e não apaga nada (o container, o volume dos modelos e a
instalação local ficam). `ollama-start` e `ollama-pull`, que já existiam,
agora seguem o modo detectado. O modo escolhido por último fica guardado nas
configurações do painel. O renderer pede só o tipo de tarefa (mais o modelo,
validado por `MODEL_PATTERN`); nenhum comando ou argumento livre.

**O que o "Iniciar" liga.** Uma função só (`electron/ollama/choose-start.ts`)
decide, e tanto o texto do botão ("Iniciar container" ou "Iniciar o Ollama
local") quanto a tarefa `ollama-start` usam a mesma resposta. Ordem: o modo
escolhido por último, se existir na máquina (container criado ou Ollama
local instalado); depois o recomendado, se existir; depois o container, se
existir; depois o Ollama local, se instalado. O card também não sugere
trocar para o modo recomendado quando o modo atual é o que a pessoa escolheu.

**Encerrar o Ollama local nem sempre é definitivo.** No Windows, o app de
bandeja do Ollama se registra para abrir no login: depois de trocar para o
Docker, ele pode voltar a subir no próximo login e disputar a porta com o
container (o card mostra o conflito). Para evitar, desligue o Ollama em
Configurações > Aplicativos > Inicialização. Em macOS e Linux, um
gerenciador de serviços (launchd, o serviço `ollama` do systemd) pode
reiniciar um servidor que o `pkill` encerrou; nesse caso, pare o serviço
por ele. Durante uma troca (`ollama-use-native` ou `ollama-use-docker` na
fila ou rodando), todas as ações do card do Ollama ficam desabilitadas.

**Benchmark.** "Medir velocidade" não é tarefa da fila: manda 64 textos para
`/api/embed`, consulta `/api/ps` e mostra chunks/s e o processador (`gpu`
quando o modelo está na VRAM, `cpu` quando não, `unknown` quando não deu para
saber). Só roda quando a pessoa pede, e o painel guarda o último resultado
em memória, com o modo em que foi medido, para mostrá-lo no card. Se o modo
muda, ou quando uma troca, parada ou início do Ollama termina, o resultado é
esquecido: a velocidade do Docker não diz nada sobre o Ollama local.

O Ollama tira o modelo da VRAM sozinho depois de alguns minutos sem uso
(5 minutos por padrão, ajustável por `OLLAMA_KEEP_ALIVE`). Por isso a GPU
não fica ocupada com o painel parado. O benchmark manda um texto de
aquecimento antes de medir, então o tempo de carregar o modelo de volta não
entra na velocidade.

**Instalação automática.** Só existe no Windows: `ollama-use-native` roda
`winget install -e --id Ollama.Ollama --silent`, por usuário, sem
elevação. Em macOS e Linux o painel recusa a instalação e mostra o link
https://ollama.com/download.

## Estrutura

- `src/`: UI React (renderer process): páginas em `src/pages/`, componentes
  em `src/components/`, hooks de dados em `src/hooks/` e o tipo do bridge
  IPC em `src/types/ragx-bridge.d.ts`.
- `electron/`: processo principal: janela e IPC (`main.ts`, `ipc.ts`,
  `preload.ts`), snapshot do hub (`data/`), checagem das conexões
  (`connections/checks.ts`), catálogo e fila de tarefas (`jobs/`) e busca de
  projetos numa pasta (`projects/discovery.ts`).
