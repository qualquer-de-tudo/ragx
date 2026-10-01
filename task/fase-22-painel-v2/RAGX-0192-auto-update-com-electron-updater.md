# RAGX-0192 — Auto-update com `electron-updater`

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0171 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-14, seção 7.4) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P11, seção 4.2) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

Hoje atualizar o painel é baixar o instalador novo na página da release e rodá-lo por cima (`docs/GUIA-DE-USO.md`, `src/app/README.md`). Não há checagem de versão nem aviso de que existe uma nova. Esta tarefa liga o `electron-updater` contra o GitHub Releases do repositório. **Ressalva decisiva:** o `.exe` não é assinado (RAGX-0124 adiada), então o Windows pode alertar no update e a integridade fica a cargo do hash do `latest.yml`. Por isso a entrega fica **desligada por padrão** (configuração) e a tarefa termina em `review`: quem decide ligar é uma pessoa, depois de testar uma atualização real, que o loop não pode fazer (sem push, tag nem release).

## Entregáveis

- [ ] `electron-updater` em `dependencies` de `src/app/package.json` (runtime, não `devDependencies`), versão **6.3.0 ou posterior** por causa da CVE-2024-39698 (auditoria 24, seção 7.4); conferir compatibilidade com o `electron-builder` 25.1.8 já instalado.
- [ ] `src/app/electron-builder.yml`: bloco `publish` com `provider: github`, `owner` e `repo` do remoto (`git remote -v` hoje: `qualquer-de-tudo/ragx`; conferir de novo) e `channel: latest` explícito.
- [ ] `src/app/package.json:17`: o script `package` passa a chamar `electron-builder --publish never`. Com `publish` configurado, o `electron-builder` em CI de tag tentaria publicar sozinho; quem publica é o `softprops/action-gh-release`.
- [ ] `src/app/electron/updater.ts` (novo): módulo com dependências injetadas (o `autoUpdater` e o relógio) e estados `idle | checking | available | downloading | downloaded | error`. `autoDownload = false`, `autoInstallOnAppQuit = false`, `channel = 'latest'` e `allowPrerelease` definido por código (verdadeiro enquanto a versão do painel tiver `-beta`; a release beta sai marcada como prerelease em `release.yml`). Não faz nada se `!app.isPackaged`.
- [ ] Configuração `autoUpdate` (padrão `false`) em `electron/settings.ts`, validada em `readSettings` (monta o objeto campo a campo e descartaria um campo novo) e exposta ao renderer. Desligada: **zero** chamadas de rede.
- [ ] IPC sem argumentos: `ragx:getUpdateState`, `ragx:checkForUpdates`, `ragx:installUpdate`, mais `ragx:update` (evento de estado) em `electron/main.ts`, `preload.ts` e `RagxBridge`. Instalar só roda se o estado for `downloaded`.
- [ ] Seção "Atualizações" na página "Preferências" (`src/pages/PreferencesPage.tsx`; a primeira das tarefas 0191, 0192 e 0193 a rodar cria a página, as outras acrescentam seção): interruptor, versão atual, "Verificar agora", e o aviso fixo "O instalador não é assinado: o Windows pode mostrar o aviso do SmartScreen ao atualizar".
- [ ] `.github/workflows/release.yml` anexa os metadados do updater **sem voltar a publicar wheel, sdist nem vsix**: (1) o upload do artefato `painel-windows` (hoje `path: src/app/release/*Setup*.exe`, linhas 323-327) inclui o `*.yml` do updater e o `*.exe.blockmap`; (2) o passo "Reunir os artefatos" (linhas 341-355) os copia para `release/`; (3) o comentário do cabeçalho (linhas 9-13) e as ressalvas das notas passam a dizer que dois arquivos extras são metadados de atualização. `fail_on_unmatched_files: true` e o `exe="$(ls *Setup*.exe | head -1)"` continuam valendo.

## Fora de escopo

- Assinar o `.exe` (RAGX-0124) e configurar `publisherName` para o updater verificar assinatura.
- Atualização automática e silenciosa sem consentimento; baixar só depois de a pessoa pedir.
- Linux e macOS; canais alfa; servidor próprio de atualização.
- Rodar uma atualização real de ponta a ponta: exige duas tags publicadas, e o loop nunca faz push, tag nem release.

## Critérios de aceite

- [ ] Depois de `npm run package` (em `src/app`), `release/` contém o `.exe`, o `.exe.blockmap` e o `*.yml` do updater; o nome do `.yml` conferido de verdade (o `electron-builder` 25.1.8 usa `channel || "latest"` para GitHub em `app-builder-lib/out/publish/updateInfoBuilder.js:37-39`, ou seja `latest.yml`) e a `url`/`path` dentro dele bate com `artifactName` (`RAGX-Painel-Setup-${version}.exe`, `electron-builder.yml:45`).
- [ ] `release.yml` continua YAML válido (carregar com `yaml.safe_load` ou `actionlint`, o que houver na máquina) e a lista de `files:` do passo "Publicar" não inclui wheel, sdist nem vsix (conferir com `git diff`).
- [ ] Com `autoUpdate` desligado, teste com `autoUpdater` simulado comprova 0 chamadas a `checkForUpdates`; com `app.isPackaged` falso, idem, mesmo ligado.
- [ ] Máquina de estados: `available` não baixa sozinho; `installUpdate` fora de `downloaded` é recusado; erro de rede vira `error` com mensagem em português e não derruba o painel.
- [ ] Status final da tarefa: `review`, com o que falta (atualização real em duas versões) escrito em Notas.

## Testes

- [ ] `src/app/electron/__tests__/updater.test.ts` (novo): estados, `autoDownload` falso, guarda `isPackaged`, padrão desligado, canal e prerelease.
- [ ] `src/app/electron/__tests__/settings.test.ts` (existente): `autoUpdate` com padrão `false` e valor inválido descartado.
- [ ] `src/app/electron/__tests__/preload.test.ts`: acrescentar os métodos novos à lista exata; atualizar os quatro mocks completos de `RagxBridge` (`src/test/snap.ts`, `App.test.tsx`, `useSnapshot.test.ts`, `useJobsConnections.test.ts`).
- [ ] `src/app/src/pages/__tests__/PreferencesPage.test.tsx`: o aviso de assinatura aparece sempre, e o botão "Instalar e reiniciar" só quando `downloaded`.

## Notas

- Confirmado: `electron-builder.yml` não tem bloco `publish` (arquivo inteiro lido) e o remoto é `https://github.com/qualquer-de-tudo/ragx.git`. A release hoje anexa só `release/*` montado em `release.yml:346-355` a partir de `*.exe` e `GUIA-DE-USO.md`: **nem `latest.yml` nem `.blockmap` chegam à release**, então sem o ajuste do workflow o updater não acharia nada.
- Premissa a conferir na instalação do pacote: em versões `-beta`, o `electron-updater` pode procurar um arquivo de canal (`beta.yml`) em vez de `latest.yml`. Fixar `channel: latest` dos dois lados (builder e código) evita a dúvida; leia o código do pacote em `node_modules/electron-updater` para confirmar.
- Interação com o instalador: `build/installer.nsh` roda `--bootstrap` em todo `customInstall` (inclusive na atualização, o que atualiza a CLI junto) e preserva CLI e dados em `isUpdated` (linhas 24 e 54). Esse `--bootstrap` é uma **segunda instância** do painel (`main.ts:43,46`): a RAGX-0171 já exclui os modos `HEADLESS` da trava de instância única (`acquireSingleInstance`); confirme isso no código dela antes de ligar o updater.
- `oneClick: false` (`electron-builder.yml:42`) é instalador assistido; verifique manualmente se `quitAndInstall` silencioso se comporta como se espera. Fica para a pessoa.
- Sem `publisherName`, o updater não confere assinatura; a proteção é o `sha512` do `latest.yml`, servido pelo mesmo GitHub. Escrever isso no `src/app/README.md`.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0192)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
