# Instalador multi-cliente MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `install.sh` and `install.ps1` register the `ragx` MCP server automatically in Cursor, Windsurf and Gemini CLI (same JSON shape Claude already uses) and in Codex CLI (different format: TOML), not just Claude Desktop/Claude Code.

**Architecture:** The existing `registrar_mcp` (bash) / `Registrar-Mcp` (PowerShell) functions already do generic read-merge-write on a `{"mcpServers": {...}}` JSON file, refusing to touch a file it can't parse. Cursor, Windsurf and Gemini CLI use that exact shape, just at different paths — so they need **only new call sites, zero new logic**. Codex CLI uses `~/.codex/config.toml` with a `[mcp_servers.ragx]` TOML table (verified against `openai/codex`'s `codex-rs/config/src/mcp_edit.rs` source, not guessed), which needs one new function per platform, following the same "never touch what you can't safely parse" rule: if `[mcp_servers.ragx]` already exists as a literal heading, leave it alone (editing an existing arbitrary TOML table without a writer library risks corrupting it); if it's absent, append a new table at end-of-file (always valid TOML, no reordering risk).

**Tech Stack:** Bash (`install.sh`), PowerShell 5.1+ (`install.ps1`), Python 3 standard library only (`json`, `tomllib` — no new dependency), GitHub Actions (CI verification).

**Spec:** This plan's Architecture section. Verified file paths and formats:
- Cursor: `~/.cursor/mcp.json`, key `mcpServers` (JSON) — confirmed via cursor.com/docs.
- Windsurf: `~/.codeium/windsurf/mcp_config.json`, key `mcpServers` (JSON) — confirmed via docs.devin.ai/desktop/cascade/mcp.
- Gemini CLI: `~/.gemini/settings.json`, key `mcpServers` (JSON, shares the file with other settings) — confirmed via github.com/google-gemini/gemini-cli docs.
- Codex CLI: `~/.codex/config.toml`, table `[mcp_servers.<name>]` with `command`/`args` (TOML) — confirmed by reading `openai/codex` source (`codex-rs/config/src/mcp_edit.rs`, `load_global_mcp_servers`).

## Global Constraints

- Never overwrite a config file that fails to parse — warn and skip, exactly like the existing `registrar_mcp` does for Claude's configs.
- Never touch content in a shared settings file (Gemini CLI's `settings.json`) other than the `mcpServers.ragx` entry.
- No new runtime dependency (`tomllib` is stdlib since Python 3.11, which this project already requires — see `pyproject.toml` `requires-python = ">=3.11"`).
- Match the existing message style exactly: `nota "MCP registrado em $nome"` (bash) / the equivalent `Escreva-Ok`/`Escreva-Aviso` calls (PowerShell) — do not invent a new log format.

---

### Task 1: Extend `install.sh` — Cursor, Windsurf, Gemini CLI (JSON, zero new logic)

**Files:**
- Modify: `install/install.sh:186-191`

**Interfaces:**
- Consumes: the existing `registrar_mcp` function (`install/install.sh:167-184`) — no signature change.
- Produces: nothing new consumed elsewhere in this task; Task 2 adds a sibling function in the same file.

- [ ] **Step 1: Manual verification (no automated test for a shell installer's file-write side effect beyond what CI already does in Task 4)**

Before editing, confirm the current block:

```bash
if [ "$COM_MCP" = "1" ]; then
  # ...python3 guard from the earlier fix...
  if command -v python3 >/dev/null 2>&1; then
    registrar_mcp "Claude Desktop" "$HOME/.config/Claude/claude_desktop_config.json"
    registrar_mcp "Claude Desktop (macOS)" "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    registrar_mcp "Claude Code" "$HOME/.claude.json"
    ok "servidor MCP disponível: ragx mcp serve"
  else
    ...
  fi
fi
```

- [ ] **Step 2: Add the three new call sites**

Replace the three `registrar_mcp` lines (inside the `if command -v python3` branch) with:

```bash
    registrar_mcp "Claude Desktop" "$HOME/.config/Claude/claude_desktop_config.json"
    registrar_mcp "Claude Desktop (macOS)" "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    registrar_mcp "Claude Code" "$HOME/.claude.json"
    registrar_mcp "Cursor" "$HOME/.cursor/mcp.json"
    registrar_mcp "Windsurf" "$HOME/.codeium/windsurf/mcp_config.json"
    registrar_mcp "Gemini CLI" "$HOME/.gemini/settings.json"
    ok "servidor MCP disponível: ragx mcp serve"
```

- [ ] **Step 3: Syntax-check**

Run: `bash -n install/install.sh`
Expected: no output (valid syntax)

- [ ] **Step 4: Commit**

```bash
git add install/install.sh
git commit -m "feat(install): registra o MCP tambem em Cursor, Windsurf e Gemini CLI"
```

---

### Task 2: Codex CLI (TOML) in `install.sh`

**Files:**
- Modify: `install/install.sh` (add a new function right after `registrar_mcp`'s closing `}`, before the `if [ "$COM_MCP" = "1" ]` block)

**Interfaces:**
- Consumes: nothing from Task 1 beyond sharing the same `if command -v python3` guard block.
- Produces: `registrar_mcp_toml` function, called once for Codex CLI here, and mirrored (as `Registrar-Mcp-Toml`) in Task 3 for Windows.

- [ ] **Step 1: Add the function**

Insert after the existing `registrar_mcp` function (`install/install.sh:184`, right after its closing `}`):

```bash
# Codex CLI usa TOML, nao JSON: `[mcp_servers.<nome>]` em vez de "mcpServers".
# Sem biblioteca de ESCRITA de TOML na stdlib (so leitura, via tomllib desde o
# Python 3.11), editar uma tabela EXISTENTE sem quebrar o resto do arquivo nao
# e seguro de fazer as cegas. Por isso: se `[mcp_servers.ragx]` ja existe,
# nao mexe — a pessoa que edite a mao se o caminho do binario mudou. Se nao
# existe, so ANEXA uma tabela nova no fim do arquivo, que e sempre TOML valido
# independente do que vier antes.
registrar_mcp_toml() {
  local nome="$1" arquivo="$2"
  [ -d "$(dirname "$arquivo")" ] || return 0
  python3 - "$arquivo" <<'PY' 2>/dev/null && nota "MCP registrado em $nome" || true
import pathlib, sys, tomllib

p = pathlib.Path(sys.argv[1])
texto = p.read_text(encoding="utf-8") if p.is_file() else ""
if texto.strip():
    try:
        tomllib.loads(texto)
    except tomllib.TOMLDecodeError:
        sys.exit(1)
if "[mcp_servers.ragx]" in texto:
    sys.exit(0)
bloco = "\n[mcp_servers.ragx]\ncommand = \"ragx\"\nargs = [\"mcp\", \"serve\"]\n"
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    if texto and not texto.endswith("\n"):
        f.write("\n")
    f.write(bloco)
PY
}
```

- [ ] **Step 2: Call it for Codex CLI**

In the same block edited in Task 1, add one more line after the Gemini CLI one:

```bash
    registrar_mcp_toml "Codex CLI" "$HOME/.codex/config.toml"
```

- [ ] **Step 3: Syntax-check**

Run: `bash -n install/install.sh`
Expected: no output

- [ ] **Step 4: Manual smoke test**

```bash
mkdir -p /tmp/codex-test/.codex
HOME=/tmp/codex-test bash -c '
  registrar_mcp_toml() { : ; }  # no-op placeholder not needed — run the real install.sh function directly instead:
'
# Simpler: source just the function and call it directly.
bash -c '
  source <(sed -n "/^registrar_mcp_toml()/,/^}/p" install/install.sh)
  registrar_mcp_toml "Codex CLI" "/tmp/codex-test/.codex/config.toml"
  cat /tmp/codex-test/.codex/config.toml
'
```

Expected output: a file containing `[mcp_servers.ragx]`, `command = "ragx"`, `args = ["mcp", "serve"]`. Run it a second time and confirm the file is unchanged (idempotent — no duplicate table).

- [ ] **Step 5: Commit**

```bash
git add install/install.sh
git commit -m "feat(install): registra o MCP no Codex CLI (config.toml)"
```

---

### Task 3: Mirror both in `install.ps1`

**Files:**
- Modify: `install/install.ps1:400-412` (add the three JSON call sites)
- Modify: `install/install.ps1` (add a `Registrar-Mcp-Toml` function near `Registrar-Mcp`, defined around line 224)

**Interfaces:**
- Consumes: the existing `Registrar-Mcp` function (`install/install.ps1:224-254`) for the JSON clients — no signature change.
- Produces: `Registrar-Mcp-Toml` function, same contract as Task 2's bash version (idempotent append-only).

- [ ] **Step 1: Add the JSON call sites**

In the block at `install/install.ps1:407-411`:

```powershell
        Registrar-Mcp 'Claude Desktop' `
            (Join-Path $env:APPDATA 'Claude\claude_desktop_config.json') $exe
        Registrar-Mcp 'Claude Code' `
            (Join-Path $env:USERPROFILE '.claude.json') $exe
        Registrar-Mcp 'Cursor' `
            (Join-Path $env:USERPROFILE '.cursor\mcp.json') $exe
        Registrar-Mcp 'Windsurf' `
            (Join-Path $env:USERPROFILE '.codeium\windsurf\mcp_config.json') $exe
        Registrar-Mcp 'Gemini CLI' `
            (Join-Path $env:USERPROFILE '.gemini\settings.json') $exe
        Escreva-Ok 'servidor MCP disponivel: ragx mcp serve'
```

- [ ] **Step 2: Add `Registrar-Mcp-Toml`**

Insert right after the `Registrar-Mcp` function's closing `}` (around `install/install.ps1:254`, after the block that writes JSON — check the function's actual end brace before inserting):

```powershell
function Registrar-Mcp-Toml {
    param([string]$Nome, [string]$Arquivo, [string]$Comando)

    $pasta = Split-Path -Parent $Arquivo
    if (-not (Test-Path $pasta)) { return }

    $texto = ''
    if (Test-Path $Arquivo) {
        $texto = Get-Content $Arquivo -Raw -Encoding UTF8
    }
    if ($texto -match [regex]::Escape('[mcp_servers.ragx]')) {
        return
    }

    $bloco = "`n[mcp_servers.ragx]`ncommand = ""$Comando""`nargs = [""mcp"", ""serve""]`n"
    if ($texto -and -not $texto.EndsWith("`n")) { $texto += "`n" }
    New-Item -ItemType Directory -Force -Path $pasta | Out-Null
    # Sem BOM: o mesmo motivo do restante do arquivo — [System.IO.File]::AppendAllText
    # evita o BOM que Out-File/Set-Content acrescentam por padrao no PS 5.1.
    [System.IO.File]::AppendAllText($Arquivo, $texto + $bloco, [System.Text.Encoding]::UTF8)
    Escreva-Ok "MCP registrado em $Nome"
}
```

- [ ] **Step 3: Call it for Codex CLI**

Add after the Gemini CLI line from Step 1:

```powershell
        Registrar-Mcp-Toml 'Codex CLI' `
            (Join-Path $env:USERPROFILE '.codex\config.toml') $exe
```

- [ ] **Step 4: Syntax-check**

Run: `powershell -NoProfile -Command "$null = Get-Content install/install.ps1 -Raw | Out-String; [System.Management.Automation.PSParser]::Tokenize((Get-Content install/install.ps1 -Raw), [ref]$null)"`
Expected: no parser errors (if `PSParser` is unavailable in the runtime, `powershell -File install/install.ps1 -SemMcp -WhatIf`-style dry run is not supported by this script; instead just run `pwsh -NoProfile -Command "Get-Command install/install.ps1 -Syntax"` or simplest: `pwsh -NoProfile -File install/install.ps1 -SemMcp` in a throwaway temp `HOME`/`USERPROFILE` to smoke-test end to end, matching Task 5).

- [ ] **Step 5: Commit**

```bash
git add install/install.ps1
git commit -m "feat(install): espelha o registro multi-cliente no Windows, incluindo Codex CLI"
```

---

### Task 4: Atualizar a documentação de instalação

**Files:**
- Modify: `install/README.md` (the "Registrar o MCP à mão" section and the installer step-5 list)
- Modify: `README.md` (root) — the "servidor MCP" line, if it names Claude specifically

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Update `install/README.md`**

In the "O instalador:" numbered list, change the line `5. registra o servidor MCP no Claude Desktop e no Claude Code;` to:

```markdown
5. registra o servidor MCP no Claude Desktop, Claude Code, Cursor, Windsurf,
   Gemini CLI e Codex CLI — nos que encontrar, sem sobrescrever configuração
   que não conseguir ler;
```

In the "Registrar o MCP à mão" section, add a note right after the existing JSON example:

```markdown
Codex CLI usa TOML, não JSON, em `~/.codex/config.toml`:

```toml
[mcp_servers.ragx]
command = "ragx"
args = ["mcp", "serve"]
```
```

- [ ] **Step 2: Commit**

```bash
git add install/README.md
git commit -m "docs(install): documenta os novos clientes MCP suportados"
```

---

### Task 5: Prova em CI real (não só leitura de código)

**Files:**
- Modify: `.github/workflows/ci.yml` (`instalador` job, "Ciclo completo num projeto novo" step or a new step right after "Verificar que o comando existe e funciona")

**Interfaces:**
- Consumes: the `instalador` job's existing structure (`.github/workflows/ci.yml:78-142`).
- Produces: nothing — this is the plan's verification task, run on real `ubuntu-latest`/`windows-latest`/`macos-latest` runners exactly as the macOS support was proven in the earlier PR.

- [ ] **Step 1: Add a verification step (Linux/macOS)**

Insert a new step in the `instalador` job, right after "Instalar (Linux/macOS)" (`.github/workflows/ci.yml:91-93`) — pre-create the target directories so the installer's `[ -d "$(dirname "$arquivo")" ]` guard doesn't skip registration on a bare CI runner, matching how a real machine with Cursor/Windsurf already installed would look:

```yaml
      - name: Preparar diretorios de clientes MCP (Linux/macOS)
        if: runner.os != 'Windows'
        run: |
          mkdir -p "$HOME/.cursor" "$HOME/.codeium/windsurf" "$HOME/.gemini" "$HOME/.codex"
```

Add this step **before** "Instalar (Linux/macOS)" so the directories exist when `install.sh` runs.

- [ ] **Step 2: Assert the registrations happened**

Add a new step after "Verificar que o comando existe e funciona" (`.github/workflows/ci.yml:112-120`):

```yaml
      - name: Verificar registro multi-cliente (Linux/macOS)
        if: runner.os != 'Windows'
        shell: bash
        run: |
          set -euo pipefail
          grep -q '"ragx"' "$HOME/.cursor/mcp.json"
          grep -q '"ragx"' "$HOME/.codeium/windsurf/mcp_config.json"
          grep -q '"ragx"' "$HOME/.gemini/settings.json"
          grep -q '\[mcp_servers.ragx\]' "$HOME/.codex/config.toml"
          echo "MCP registrado em Cursor, Windsurf, Gemini CLI e Codex CLI"
```

- [ ] **Step 3: Same for Windows**

Add a matching pair of steps guarded by `if: runner.os == 'Windows'`, using `$env:USERPROFILE` paths and `New-Item -ItemType Directory -Force` / `Select-String -Quiet` in place of `mkdir -p` / `grep -q`:

```yaml
      - name: Preparar diretorios de clientes MCP (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.cursor" | Out-Null
          New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codeium\windsurf" | Out-Null
          New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.gemini" | Out-Null
          New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex" | Out-Null
```

(insert before "Instalar (Windows)")

```yaml
      - name: Verificar registro multi-cliente (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          $ok = $true
          $ok = $ok -and (Select-String -Path "$env:USERPROFILE\.cursor\mcp.json" -Pattern '"ragx"' -Quiet)
          $ok = $ok -and (Select-String -Path "$env:USERPROFILE\.codeium\windsurf\mcp_config.json" -Pattern '"ragx"' -Quiet)
          $ok = $ok -and (Select-String -Path "$env:USERPROFILE\.gemini\settings.json" -Pattern '"ragx"' -Quiet)
          $ok = $ok -and (Select-String -Path "$env:USERPROFILE\.codex\config.toml" -Pattern '\[mcp_servers\.ragx\]' -Quiet)
          if (-not $ok) { throw "MCP nao registrado em algum cliente" }
          Write-Host "MCP registrado em Cursor, Windsurf, Gemini CLI e Codex CLI"
```

(insert after "Instalar (Windows)")

- [ ] **Step 4: Push and watch CI**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: prova o registro multi-cliente do MCP nos 3 sistemas operacionais"
git push
```

Watch the `instalador` job on all three OSes go green (`gh run watch`, same as the macOS CI PR).

- [ ] **Step 5: Commit is already Step 4 — no additional commit needed here.**
