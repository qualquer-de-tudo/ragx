# Instalação do RAGX

Três caminhos. Escolha pelo seu caso:

| Situação | Vá para |
|---|---|
| Baixei os arquivos da página de release | [A partir dos arquivos baixados](#a-partir-dos-arquivos-baixados) |
| Tenho o repositório clonado | [A partir do clone](#a-partir-do-clone) |
| O repositório é **público** | [Comando único](#comando-único) |

> **Repositório privado?** O comando único **não funciona** — a URL do asset
> devolve 404 para quem não está autenticado, e o `irm` recebe uma página de
> erro em vez do script. Use um dos dois primeiros caminhos.

---

## A partir dos arquivos baixados

Baixe da página de release (logado no GitHub):

```text
ragx-1.0.0-py3-none-any.whl
ragx-knowledge-explorer-1.0.0-beta.1.vsix
```

### Windows

```powershell
# 1. uv, se ainda não tiver (resolve o Python sozinho)
irm https://astral.sh/uv/install.ps1 | iex

# 2. RAGX, do arquivo baixado. Ajuste o caminho.
uv tool install --python 3.12 "$HOME\Downloads\ragx-1.0.0-py3-none-any.whl[all]"

# 3. PATH do usuário — é o passo que quase todo mundo esquece
$bin = (uv tool dir --bin).Trim()
$p = [Environment]::GetEnvironmentVariable('Path','User')
if (-not ($p -split ';' | Where-Object { $_.TrimEnd('\') -ieq $bin.TrimEnd('\') })) {
    [Environment]::SetEnvironmentVariable('Path', "$p;$bin", 'User')
}

# 4. Extensão do VS Code
code --install-extension "$HOME\Downloads\ragx-knowledge-explorer-1.0.0-beta.1.vsix"
```

**Abra um PowerShell novo** e confira:

```powershell
ragx --version
ragx mcp tools --json     # tem que listar 32 ferramentas
```

### Linux e macOS

```bash
# 1. uv, se ainda não tiver
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# 2. RAGX, do arquivo baixado
uv tool install --python 3.12 "$HOME/Downloads/ragx-1.0.0-py3-none-any.whl[all]"

# 3. PATH permanente
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc   # ou ~/.zshrc

# 4. Extensão do VS Code
code --install-extension "$HOME/Downloads/ragx-knowledge-explorer-1.0.0-beta.1.vsix"
```

**Abra um terminal novo** e confira com `ragx --version`.

### Ou use o instalador com o arquivo baixado

Baixe também o `install.sh` ou `install.ps1` da release e aponte para o wheel —
ele cuida do PATH e do registro do MCP:

```powershell
.\install.ps1 -Origem "$HOME\Downloads\ragx-1.0.0-py3-none-any.whl"
```

```bash
RAGX_ORIGEM="$HOME/Downloads/ragx-1.0.0-py3-none-any.whl" bash install.sh
```

---

## A partir do clone

Com o repositório na máquina, o instalador detecta sozinho:

```bash
./install/install.sh
```

```powershell
.\install\install.ps1
```

---

## Comando único

**Só funciona com o repositório público.** Substitua `vX.Y.Z` pela tag.

### Linux e macOS

```bash
curl -fsSL https://github.com/qualquer-de-tudo/ragx/releases/download/vX.Y.Z/install.sh | bash
```

### Windows

```powershell
[Net.ServicePointManager]::SecurityProtocol = 3072
irm https://github.com/qualquer-de-tudo/ragx/releases/download/vX.Y.Z/install.ps1 | iex
```

A primeira linha **não é opcional** no PowerShell 5.1, que ainda é o padrão do
Windows: ele negocia TLS 1.0 por default e o GitHub recusa. O erro é
`A conexão foi fechada de modo inesperado`, que não diz nada sobre TLS.

---

## Depois de instalar

```bash
cd seu-projeto
ragx init
ragx index .
ragx search "como funciona a autenticação"
```

## O que o instalador faz

1. **Instala o `uv`** se não houver. Ele resolve o Python sozinho.
2. **Instala o `ragx`** isolado, com o extra `all` (MCP, busca semântica,
   contagem de tokens). O RAGX não polui o Python do sistema.
3. **Grava o PATH** no perfil — `.bashrc`, `.zshrc`, `.profile`, `fish`, ou o
   ambiente do usuário no Windows.
4. **Registra o MCP** em `claude_desktop_config.json` e `.claude.json`.
5. **Verifica**: roda `ragx --version` e `ragx doctor` e reporta o real.

## Opções

| Variável / parâmetro | Padrão | Para quê |
|---|---|---|
| `RAGX_ORIGEM` / `-Origem` | auto | Wheel, caminho local ou `git+url` |
| `RAGX_PYTHON` / `-Python` | `3.12` | Versão do interpretador |
| `RAGX_EXTRA` / `-Extra` | `all` | Conjunto de dependências |
| `RAGX_INSTALL_MCP=0` / `-SemMcp` | — | Não registrar o MCP |
| `RAGX_REPO` | GitHub | Instalar de outro repositório |

## Registrar o MCP à mão

Em `~/.claude.json` (Claude Code) ou no `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ragx": {
      "command": "ragx",
      "args": ["mcp", "serve"]
    }
  }
}
```

Acrescente `"--write"` para que o agente possa reindexar e sincronizar. Isso
**não** dá acesso ao filesystem nem afrouxa o Security Gate — ver
[ADR-0012](../docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md).

---

## Quatro armadilhas que este instalador resolve

Todas encontradas testando de verdade — neste Windows e num container Ubuntu
24.04 — não previstas no papel.

**A versão do Python é fixada.** Sem `--python`, o `uv` pode reaproveitar um
interpretador antigo. O RAGX usa `StrEnum`, que exige 3.11+, e a falha aparece
muito depois como `ModuleNotFoundError: pydantic_core._pydantic_core`.

**O extra `all` inclui o `mcp`.** Servir agentes por MCP é o propósito do RAGX.
Uma instalação que termina dizendo "pronto" e depois falha no `ragx mcp serve`
é a pior surpresa possível.

**O `.ps1` é ASCII puro, sem BOM.** O `Invoke-RestMethod` do PowerShell 5.1 não
recebe charset num asset de release (`application/octet-stream`) e decodifica o
corpo como Latin-1. Com acentos, o script chega corrompido e o parser cospe
dezenas de "Token inesperado". O custo é comentário sem acento — menor que um
instalador que não instala.

**Os scripts sobrevivem a `curl | bash` e `irm | iex`.** Nesse modo não existe
arquivo em disco: `$PSScriptRoot` e `${BASH_SOURCE[0]}` vêm vazios. A versão
anterior morria em `Split-Path -Parent ''` logo depois de instalar o `uv`.

## Desinstalar

```bash
uv tool uninstall ragx
```

A linha de PATH no perfil e o registro do MCP ficam — o instalador não apaga o
que não criou sozinho.
