# RAGX-0194 — CSP e menu mínimo

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,25d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-14) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

O painel não tem Content-Security-Policy (`src/app/index.html` tem só `charset`, `viewport` e o `<script type="module">`) e não define menu de aplicação: o Electron usa o menu padrão, escondido por `autoHideMenuBar: true` (`electron/main.ts:456`) mas acessível com Alt, com itens como DevTools e recarregar. A superfície que o painel precisa é pequena: ele não carrega nada de fora (uma busca por `http(s)://`, `fetch(`, `WebSocket`, `@import` e `url(` em `src/` e `index.html` volta vazia). Esta tarefa fecha isso com uma política restritiva, um menu mínimo e DevTools desligadas em produção, sem quebrar o Vite em desenvolvimento.

## Entregáveis

- [ ] CSP restritiva **só no build de produção**: plugin do Vite em `vite.config.ts` (`transformIndexHtml`, `apply: 'build'`) que injeta o `<meta http-equiv="Content-Security-Policy">` no `dist/index.html`. A política vive num único módulo importável pelo plugin e pelo teste. Ponto de partida: `default-src 'none'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. O `style-src-attr` existe porque há largura dinâmica em `style={{ ... }}` (`ProjectCard.tsx:137,153`, `QueueIndicator.tsx:69`, `ProjectPage.tsx:316`, `TokenSavings.tsx:114`).
- [ ] Em desenvolvimento (`npm run dev:electron`), o `index.html` servido pelo Vite **não** recebe essa política: o plugin do React injeta script inline e o HMR usa WebSocket para `localhost:5173`. Se quiser CSP em dev, é uma segunda política, mais frouxa, e não uma exceção na de produção.
- [ ] `src/app/electron/menu.ts` (novo): `buildMenuTemplate({ devTools })` devolve o menu em português: Edição (`undo`, `redo`, `cut`, `copy`, `paste`, `selectAll`), Exibir (`resetZoom`, `zoomIn`, `zoomOut`, `togglefullscreen`) e Sair. **Mantenha o zoom**: sem menu, os atalhos Ctrl+= e Ctrl+- somem, e a RAGX-0181 testa o painel sob zoom de 200%. Sem `reload`, `forceReload` nem `toggleDevTools` quando `devTools` é falso. `Menu.setApplicationMenu` chamado em `app.whenReady`, antes de `createWindow`.
- [ ] DevTools: `webPreferences.devTools` em `createWindow` (`main.ts:458-462`) verdadeiro só em dev (`isDev`, linha 40) ou com `RAGX_DEVTOOLS=1`; o `openDevTools` de `main.ts:477` continua restrito a `isDev`. Em produção, F12 e Ctrl+Shift+I não abrem nada.
- [ ] Teste de varredura de recurso remoto, no estilo de `src/__tests__/no-em-dash.test.ts` (mesmos auxiliares de arquivos e de comentários): nenhum `http://`, `https://`, `ws://`, `@import` nem `url(http` em `src/**` e em `index.html`, fora de comentários e de `__tests__`.
- [ ] `src/app/README.md`: seção curta "Segurança do renderer" com a CSP, o menu e `RAGX_DEVTOOLS`.

## Fora de escopo

- Trava de instância única (RAGX-0171), bandeja (0191) e auto-update (0192).
- Política de permissões (`setPermissionRequestHandler`), `sandbox` explícito e assinatura de código: tarefa própria se a pessoa quiser.
- Aplicar CSP por cabeçalho HTTP: o build de produção carrega `file://` (`main.ts:479`), onde cabeçalho não vale.
- Menu para macOS (o painel é só Windows, fase 17).

## Critérios de aceite

- [ ] `npm run build` gera `dist/index.html` com o `<meta>` de CSP; teste lê a saída do plugin e confirma `default-src 'none'`, ausência de `'unsafe-eval'`, ausência de `'unsafe-inline'` em `script-src` e `style-src`, e nenhum host `http:`/`https:`/`*`.
- [ ] Abrir o build de produção (`npx electron-builder --dir` depois de `npm run build` e `npm run build:electron:ts`; executar `release/win-unpacked/RAGX Painel.exe`) e percorrer Projetos, Detalhe (as quatro abas), Atividade e Conexões: o console do renderer não registra nenhum `Refused to ...`. Como a produção não tem DevTools, rode uma vez com `RAGX_DEVTOOLS=1` para ler o console. Registrar em Andamento.
- [ ] `npm run dev:electron` continua abrindo e recarregando a quente, sem CSP bloqueando o Vite.
- [ ] Em produção: Alt não mostra os itens Recarregar nem Ferramentas do desenvolvedor, F12 e Ctrl+Shift+I não abrem DevTools; copiar e colar em campos de texto e zoom (Ctrl+= e Ctrl+-) funcionam.
- [ ] A varredura de recurso remoto passa hoje sem alterar nenhuma tela (a premissa já foi conferida: busca vazia).

## Testes

- [ ] `src/app/electron/__tests__/menu.test.ts` (novo, no padrão de `navigation.test.ts`): sem `toggleDevTools`, `reload` e `forceReload` com `devTools: false`; com `true` o item existe; papéis de edição e de zoom sempre presentes; rótulos em português sem travessão.
- [ ] `src/app/src/__tests__/csp.test.ts` (novo): política do módulo único e saída do plugin de `transformIndexHtml`.
- [ ] `src/app/src/__tests__/no-remote-resources.test.ts` (novo): a varredura acima.
- [ ] `src/app/src/__tests__/no-em-dash.test.ts` (existente) continua verde: ele varre `index.html` e `electron/`, então o texto do menu e do comentário da CSP não leva travessão.

## Notas

- Confirmado: `electron/main.ts:456` (`autoHideMenuBar`), `:477` (`openDevTools` só em dev), `:479` (`loadFile` em produção); nenhuma chamada a `Menu`, `setApplicationMenu`, `requestSingleInstanceLock` ou `session.` em `electron/`. Ainda não confirmado: o conteúdo exato do menu padrão do Electron empacotado; abrir o `.exe` atual e apertar Alt antes de começar, para registrar o "antes".
- O Vite constrói o CSS como arquivo externo; por isso `style-src 'self'` basta para folhas de estilo e só o atributo `style` precisa de `style-src-attr`. Se o build passar a embutir `<style>`, a política precisa de ajuste e o teste de saída do plugin tem de pegar isso.
- A RAGX-0193 (tema) aplica o tema em `src/main.tsx`, não por `<script>` inline, justamente por causa de `script-src 'self'`.
- Em dev, `isDev` é `!app.isPackaged` (`main.ts:40`): `electron .` direto também é "dev"; por isso o teste do build de produção usa o `.exe` desempacotado.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0194)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
