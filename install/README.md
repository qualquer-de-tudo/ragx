# Instalação do RAGX

Há dois caminhos, e a diferença entre eles importa:

| | O que instala | Traz a extensão do VS Code? |
|---|---|---|
| **Comando único** | o `main` do repositório | **não** |
| **Baixar a release** | a versão exata daquela tag | **sim** |

O comando único é o mais rápido e serve para experimentar. Para pregar uma
versão, ou para usar a extensão do VS Code, baixe os arquivos da release — o
instalador encontra o wheel e o `.vsix` na pasta sozinho.

---

## Comando único

```bash
curl -fsSL https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.ps1 | iex
```

Pule para [Conferir](#3-conferir).

---

## 1. Baixar

### Pelo terminal, com o `gh` (recomendado)

O [GitHub CLI](https://cli.github.com) resolve download e autenticação numa
linha.

```bash
gh release download v1.0.0-beta.2 --repo qualquer-de-tudo/ragx --dir ragx
```

Windows é idêntico:

```powershell
gh release download v1.0.0-beta.2 --repo qualquer-de-tudo/ragx --dir ragx
```

### Pelo navegador

Abra a página da release e baixe os arquivos para uma pasta:

```text
install.sh                                  instalador Linux/macOS
install.ps1                                 instalador Windows
ragx-1.0.0b1-py3-none-any.whl               o RAGX
ragx-knowledge-explorer-1.0.0-beta.2.vsix   extensão do VS Code
SHA256SUMS.txt                              para conferir o download
```

### Conferir o download (opcional)

```bash
cd ragx && sha256sum -c SHA256SUMS.txt
```

```powershell
cd ragx
Get-Content SHA256SUMS.txt | ForEach-Object {
    $esperado, $arquivo = $_ -split '\s+', 2
    $real = (Get-FileHash $arquivo.Trim() -Algorithm SHA256).Hash.ToLower()
    "{0}  {1}" -f $(if ($real -eq $esperado) { 'OK  ' } else { 'FALHA' }), $arquivo.Trim()
}
```

---

## 2. Instalar

Entre na pasta e rode. **Um comando.**

### Linux e macOS

```bash
cd ragx
bash install.sh
```

### Windows

```powershell
cd ragx
.\install.ps1
```

> Se o PowerShell recusar por política de execução:
> `powershell -ExecutionPolicy Bypass -File .\install.ps1`

O instalador:

1. instala o `uv`, se não houver (ele resolve o Python sozinho);
2. **encontra o `ragx-*.whl` na pasta** e instala com o extra `all`
   (servidor MCP, busca semântica, contagem de tokens);
3. grava o diretório no **PATH** do seu perfil;
4. **encontra o `.vsix` na pasta** e instala a extensão, se o `code` existir;
5. registra o servidor MCP no Claude Desktop e no Claude Code;
6. verifica com `ragx --version` e `ragx doctor`.

---

## 3. Conferir

**Abra um terminal novo** — o PATH só vale a partir da próxima sessão. É a
causa número um de "instalei e o comando não existe".

```bash
ragx --version          # ragx 1.0.0b1
ragx mcp tools --json   # 33 ferramentas
```

## 4. Usar

```bash
cd seu-projeto
ragx init
ragx index .
ragx search "como funciona a autenticação"
```

---

## Sem o instalador, comando a comando

Se preferir fazer à mão, ou automatizar:

### Linux e macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

uv tool install --python 3.12 "$PWD/ragx-1.0.0b1-py3-none-any.whl[all]"

echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc     # ou ~/.zshrc

code --install-extension ./ragx-knowledge-explorer-1.0.0-beta.2.vsix
```

### Windows

```powershell
irm https://astral.sh/uv/install.ps1 | iex

uv tool install --python 3.12 "$PWD\ragx-1.0.0b1-py3-none-any.whl[all]"

$bin = (uv tool dir --bin).Trim()
$p = [Environment]::GetEnvironmentVariable('Path','User')
if (-not ($p -split ';' | Where-Object { $_.TrimEnd('\') -ieq $bin.TrimEnd('\') })) {
    [Environment]::SetEnvironmentVariable('Path', "$p;$bin", 'User')
}

code --install-extension .\ragx-knowledge-explorer-1.0.0-beta.2.vsix
```

> `--python 3.12` **não é decoração**. Sem ele o `uv` pode reaproveitar um
> interpretador antigo, e o RAGX usa `StrEnum`, que exige 3.11+. A falha
> aparece muito depois, como `ModuleNotFoundError: pydantic_core`.
>
> `[all]` também não. Sem esse extra, o `ragx mcp serve` falha com
> `ModuleNotFoundError: No module named 'mcp'` — depois de uma instalação que
> se declarou bem-sucedida.

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

## Opções

| Variável / parâmetro | Padrão | Para quê |
|---|---|---|
| `RAGX_ORIGEM` / `-Origem` | acha sozinho | Wheel, caminho ou `git+url` |
| `RAGX_PYTHON` / `-Python` | `3.12` | Versão do interpretador |
| `RAGX_EXTRA` / `-Extra` | `all` | Conjunto de dependências |
| `RAGX_INSTALL_MCP=0` / `-SemMcp` | — | Não registrar o MCP |
| `RAGX_INSTALL_VSCODE=0` / `-SemVsCode` | — | Não instalar a extensão |
| `RAGX_REPO` | GitHub | Instalar de outro repositório |

Onde o instalador procura o wheel, nesta ordem: o que você passar em
`-Origem`, a pasta do próprio script, a pasta atual, e `~/Downloads`.

---

## Registrar o MCP à mão

O instalador tenta registrar sozinho, mas pula uma configuração que não
consegue ler — não sobrescreve o que é seu. Em `~/.claude.json` (Claude Code)
ou no `claude_desktop_config.json`:

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

Acrescente `"--write"` aos argumentos para que o agente possa reindexar e
sincronizar. Isso **não** dá acesso ao filesystem nem afrouxa o Security Gate —
ver [ADR-0012](../docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md).

---

## Quando o repositório for público

Aí o comando único passa a funcionar:

```bash
curl -fsSL https://github.com/qualquer-de-tudo/ragx/releases/download/v1.0.0-beta.2/install.sh | bash
```

```powershell
[Net.ServicePointManager]::SecurityProtocol = 3072
irm https://github.com/qualquer-de-tudo/ragx/releases/download/v1.0.0-beta.2/install.ps1 | iex
```

A primeira linha do Windows **não é opcional** no PowerShell 5.1, que ainda é o
padrão: ele negocia TLS 1.0 e o GitHub recusa. O erro é `A conexão foi fechada
de modo inesperado`, que não diz nada sobre TLS.

---

## Cinco armadilhas que este instalador resolve

Todas encontradas testando de verdade — neste Windows e num container Ubuntu
24.04 — não previstas no papel.

**A versão do Python é fixada.** Ver acima.

**O extra `all` inclui o `mcp`.** Servir agentes por MCP é o propósito do RAGX;
uma instalação que termina dizendo "pronto" e depois falha no `ragx mcp serve`
é a pior surpresa possível.

**O `.ps1` é ASCII puro, sem BOM.** O `Invoke-RestMethod` do PowerShell 5.1 não
recebe charset num asset de release (`application/octet-stream`) e decodifica o
corpo como Latin-1. Com acentos, o script chega corrompido e o parser cospe
dezenas de "Token inesperado".

**Os scripts sobrevivem a `curl | bash` e `irm | iex`.** Nesse modo não existe
arquivo em disco: `$PSScriptRoot` e `${BASH_SOURCE[0]}` vêm vazios. A versão
anterior morria em `Split-Path -Parent ''` logo depois de instalar o `uv`.

**O instalador sai com código 0 quando dá certo.** O `ragx doctor` sai com
código diferente de zero enquanto não há índice — o que é esperado numa
instalação nova. Sem zerar isso no fim, o código dele vazava como resultado do
instalador e qualquer automação concluía que tinha falhado.

## Desinstalar

```bash
uv tool uninstall ragx
code --uninstall-extension ragx.ragx-knowledge-explorer
```

A linha de PATH no perfil e o registro do MCP ficam — o instalador não apaga o
que não criou sozinho.
