# Instalador completo do RAGX Painel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** só com o `RAGX Painel Setup.exe`, instalar CLI `ragx` + PATH + MCP no Claude Code, e permitir desinstalar tudo.

**Architecture:** o `.exe` leva `uv.exe` + wheel em `resources/ragx-bundle/` (com `bundle.json` de hashes). Um job `ragx-install` (fila existente) roda `uv tool install` e `ragx mcp install`. NSIS só dispara `--bootstrap` / `--uninstall-cli`; toda a lógica é TypeScript. Desinstalar a CLI usa o novo `ragx mcp uninstall`.

**Tech Stack:** Electron + TypeScript (vitest), electron-builder/NSIS, Python (typer, pytest), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-23-instalador-completo-design.md`

## Global Constraints

- Windows apenas. Python do `uv`: `3.12`. Comandos de processo sem shell (lista de argumentos).
- Convenções do repo: comentários em português, commits `tipo(escopo): descrição` em português, CHANGELOG `[Não lançado]` na mesma PR.
- Config de terceiros: só remover/alterar a chave `ragx`; JSON/TOML ilegível nunca é sobrescrito; backup antes de mudar.
- Falha do bootstrap nunca falha a instalação do `.exe`.
- Não tocar em `.ragx/` de projetos do usuário nem no Ollama.

## Review Focus

- `ragx.exe` travado por MCP aberto → mensagem manda fechar o Claude Code (teste em Task 4).
- Hash do wheel/uv diferente → aborta antes de executar (Task 2).
- `~\.local\bin` já no PATH por outro programa → desinstalar não remove (Task 3).
- Config MCP ilegível → `ragx mcp uninstall` não toca (Task 5).
- `--remove-data` só apaga exatamente `~\.ragx` (Task 3).

---

### Task 1: `ragxCommand()` não pode fixar `null` em cache
**Files:** Modify `src/app/electron/system/ragx-exe.ts`; Test `src/app/electron/system/__tests__/ragx-exe.test.ts`
**Produces:** `ragxCommand()` re-resolve enquanto o resultado for `null`.
- [ ] Teste: após `resolveRagx` retornar null e depois um caminho, `ragxCommand()` devolve o caminho (usar `resetRagxCache` + mock de fs via `resolveRagx` deps não basta; extrair `let cached` e testar via env PATH temporário).
- [ ] Trocar `if (cached === undefined)` por `if (cached === undefined || cached === null)`.
- [ ] `npx vitest run electron/system` verde.

### Task 2: Bundle (`bundle.ts`)
**Files:** Create `src/app/electron/bootstrap/bundle.ts`; Test `src/app/electron/bootstrap/__tests__/bundle.test.ts`
**Produces:**
```ts
export interface BundleInfo { dir: string; uvPath: string; wheelPath: string; version: string; python: string }
export class BundleError extends Error { code: 'missing' | 'hash' }
export function findBundleDir(deps?: {resourcesPath?: string; devDir?: string; exists?: (p:string)=>boolean}): string | null
export function loadBundle(deps?: {...; readFile; sha256File}): BundleInfo   // lança BundleError
export function uvCommand(): string   // caminho do uv.exe do bundle ou 'uv'
```
`bundle.json`: `{ "version": "1.0.0b3", "python": "3.12", "uv": {"file":"uv.exe","sha256":"…"}, "wheel": {"file":"ragx-….whl","sha256":"…"} }`.
- [ ] Testes: dir ausente → `missing`; hash errado → `hash`; ok → BundleInfo com caminhos absolutos.
- [ ] Implementar (sha256 via `crypto`, leitura de arquivo síncrona).

### Task 3: PATH do usuário, estado e desinstalação
**Files:** Create `bootstrap/path-user.ts`, `bootstrap/state.ts`, `bootstrap/uninstall.ts` (+ `__tests__/`)
**Produces:**
```ts
// state.ts: %APPDATA%/RAGX Painel/bootstrap-state.json → { pathAdded: boolean, binDir: string|null }
export function readState(deps?): BootstrapState;  export function writeState(s, deps?): void
// path-user.ts
export interface PathDeps { getUserPath(): Promise<string>; setUserPath(v: string): Promise<void> }
export function ensureUserPath(binDir: string, deps?: PathDeps): Promise<{ added: boolean }>  // grava state.pathAdded=true só se adicionou
export function removeFromUserPath(binDir: string, deps?: PathDeps): Promise<{ removed: boolean }>
// uninstall.ts
export interface UninstallOptions { removeData: boolean }
export function uninstallCli(opts: UninstallOptions, deps?): Promise<{ steps: string[]; errors: string[] }>
```
Ordem em `uninstallCli`: `ragx mcp uninstall` → `uv tool uninstall ragx` → `removeFromUserPath` só se `state.pathAdded` → se `removeData`, `fs.rm` **apenas** de `path.join(homedir, '.ragx')`. Cada erro vira item em `errors` sem interromper o resto. Implementação real de PathDeps via `powershell` `[Environment]::Get/SetEnvironmentVariable('Path',…,'User')` (faz o broadcast).
- [ ] Testes: adiciona; já existe (sem `pathAdded`); remove só se `pathAdded`; `removeData` false não apaga; `removeData` true apaga só `~/.ragx`; erro num passo não impede os seguintes.
- [ ] Implementar.

### Task 4: Job `ragx-install`
**Files:** Modify `electron/jobs/catalog.ts`, `electron/jobs/queue.ts` (`resolveSpawnCommand` aceita `'uv'`), `electron/jobs/transitions.ts`, `src/types/ragx-bridge.d.ts` (`JobKind`, `ConnectionAction.kind`); Test `electron/jobs/__tests__/catalog.test.ts`, `queue` tests existentes
**Interfaces:** `Step.cmd` ganha `'uv'`; `CatalogContext.bundle?: () => BundleInfo` (lança `BundleError`).
Passos do job (`label: 'Instalar o RAGX'`, `dedupeKey('ragx-install', null)`):
1. `{cmd:'uv', args:['tool','install','--force','--no-config','--python', b.python, `${b.wheelPath}[all]`]}`
2. `{cmd:'ragx', args:['mcp','install','--client','claude-code']}`
Falha do `BundleError` vira `JobRejected('Pacote de instalação do RAGX ausente ou corrompido. Baixe o instalador de novo.')`. Falha do passo 1 com "acesso negado"/"os error 5"/"being used" vira erro `"O ragx está em uso. Feche o Claude Code e tente de novo."` (mapeamento no ponto onde a queue monta o texto de erro de passo — localizar em `queue.ts` `spawnErrorText`/fail).
- [ ] Testes de catálogo: passos e args; bundle ausente → `JobRejected`; kind conhecido; `CONNECTION_JOB_KINDS` inclui.
- [ ] Teste de `resolveSpawnCommand('uv')` → caminho do bundle.
- [ ] Teste do mapeamento de "em uso".
- [ ] Implementar.

### Task 5: `ragx mcp uninstall` (Python)
**Files:** Modify `src/ragx/clients/registry.py`, `src/ragx/cli/commands/mcp_cmd.py`; Test `tests/unit/` (seguir o padrão dos testes de `clients`)
**Produces:** `Outcome.REMOVED`; `unregister(client, dry_run=False) -> Result`; `unregister_all(dry_run=False, only=None) -> list[Result]`; CLI `ragx mcp uninstall [--client X]... [--dry-run] [--json]`.
Regras: JSON remove só `key[SERVER_NAME]`; TOML remove só a tabela `[mcp_servers.ragx]`; ausente → `UNCHANGED`; cliente não instalado → `ABSENT`; ilegível → `FAILED` sem escrever; backup antes de alterar; escrita atômica (`_escrever`).
- [ ] Testes: JSON com outros servidores preservados; TOML idem; ilegível intocado; ausente; dry-run não grava.
- [ ] Implementar espelhando `register`/`register_all` e o `install` do CLI.

### Task 6: Cards, renderer e `main.ts`
**Files:** Modify `electron/connections/checks.ts` (RAGX não encontrado → ação `{kind:'ragx-install', label:'Instalar o RAGX'}`, help atualizado), `electron/main.ts`, `electron/ipc.ts` se necessário, renderer que despacha ações (`src/state.ts`/`ConnectionsPage`); Create `bootstrap/post-install.ts`
**Produces:** `afterRagxInstall(): Promise<void>` = `resetRagxCache()` + `ensureUserPath(dirname(resolveRagx()))`.
`main.ts`: argv `--bootstrap` (headless: enfileira `ragx-install`, espera terminar, `afterRagxInstall`, grava `bootstrap.log`, `app.exit(0|1)`); `--uninstall-cli [--remove-data]` (headless: `uninstallCli`, exit 0|1); startup normal: `resolveRagx()===null` e bundle presente → enfileira `ragx-install`; ao terminar (qualquer modo) roda `afterRagxInstall` e refaz `getConnections`.
- [ ] Atualizar testes de `checks.test.ts` e `ConnectionsPage.test.tsx`; adicionar teste da nova ação.
- [ ] Implementar.

### Task 7: Empacotamento, NSIS e CI
**Files:** Create `src/app/scripts/prepare-bundle.mjs`, `src/app/build/installer.nsh`; Modify `src/app/electron-builder.yml` (`extraResources`, `nsis.include`), `src/app/package.json` (`bundle`, `package` roda `bundle` antes), `.github/workflows/release.yml` (job `painel-windows` com smoke), `.gitignore` (`src/app/resources/`)
`prepare-bundle.mjs`: `uv build --wheel` no repo → copia wheel; baixa `uv-x86_64-pc-windows-msvc.zip` de versão fixa + confere o `.sha256` publicado; extrai `uv.exe`; escreve `bundle.json`.
`installer.nsh`: `customInstall` → `ExecWait '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" --bootstrap'` (código ≠ 0 só avisa, `MessageBox` ignorado em `/S`); `customUnInstall` → se não `/S`, dois `MessageBox MB_YESNO` (CLI padrão Sim; dados padrão Não); em `/S` lê `--remove-cli`/`--remove-data`; chama `--uninstall-cli` **antes** dos arquivos serem apagados (confirmar ordem no template `node_modules/app-builder-lib/templates/nsis/uninstaller.nsh`; se a macro roda depois, usar a macro que roda antes).
CI smoke (`windows-latest`): `npm ci`, `npm run package`, `& installer /S`, `ragx --version` e `ragx mcp serve --help` com PATH atualizado de `~\.local\bin`, desinstalação `/S --remove-cli`, confirma que `ragx.exe` sumiu.
- [ ] Implementar e validar localmente `node scripts/prepare-bundle.mjs`.

### Task 8: Docs e changelog
**Files:** `CHANGELOG.md` (`[Não lançado]`), `src/app/README.md`, `install/README.md`, `docs/adr/ADR-00NN-instalador-completo.md`, `task/fase-16-instalador-completo.md` (com "Fora de escopo")
- [ ] Escrever, apontando o spec.

### Task 9: Validação final
- [ ] Suítes: `cd src/app && npx vitest run && npm run lint && npx tsc -p tsconfig.electron.json --noEmit && npx tsc -p tsconfig.app.json --noEmit`; raiz: `uv run pytest -m "not slow"`, `uv run ruff check .`, `uv run mypy src/ragx/core src/ragx/security`.
- [ ] Playwright: abrir o painel (Electron via `_electron.launch`), passo 2 do assistente, confirmar RAGX CLI verde após o bootstrap.
