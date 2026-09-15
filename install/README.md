# Instalação do RAGX

Um comando por sistema. Os dois instaladores fazem a mesma coisa: colocam o
`ragx` no PATH, registram o servidor MCP nos clientes que encontrarem, e
**verificam** — em vez de prometer.

## Linux e macOS

```bash
curl -fsSL https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.sh | bash
```

Ou, com o repositório clonado:

```bash
./install/install.sh
```

## Windows

```powershell
irm https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.ps1 | iex
```

Ou, com o repositório clonado:

```powershell
.\install\install.ps1
```

## Depois de instalar

**Abra um terminal novo.** O PATH foi gravado no seu perfil, e um shell já
aberto não enxerga isso. É a causa número um de "instalei e o comando não
existe".

```bash
ragx --version
cd seu-projeto
ragx init
ragx index .
ragx search "como funciona a autenticação"
```

## O que o instalador faz

1. **Instala o `uv`** se não houver. Ele resolve o Python sozinho — você não
   precisa ter um instalado.
2. **Instala o `ragx`** como ferramenta isolada, com o extra `all` (servidor
   MCP, busca semântica, contagem de tokens). Ambiente separado: o RAGX não
   polui o Python do sistema nem briga com as dependências de outro projeto.
3. **Grava o PATH** no seu perfil — `.bashrc`, `.zshrc`, `.profile`, `fish`, ou
   o ambiente do usuário no Windows.
4. **Registra o MCP** em `claude_desktop_config.json` e `.claude.json`, se
   existirem.
5. **Verifica**: roda `ragx --version` e `ragx doctor` e reporta o resultado
   real.

## Opções

| Variável / parâmetro | Padrão | Para quê |
|---|---|---|
| `RAGX_PYTHON` / `-Python` | `3.12` | Versão do interpretador |
| `RAGX_EXTRA` / `-Extra` | `all` | Conjunto de dependências |
| `RAGX_INSTALL_MCP=0` / `-SemMcp` | — | Não registrar o MCP |
| `RAGX_REPO` | GitHub | Instalar de outro repositório |

```bash
RAGX_PYTHON=3.13 RAGX_INSTALL_MCP=0 ./install/install.sh
```

```powershell
.\install\install.ps1 -Python 3.13 -SemMcp
```

## Duas armadilhas que o instalador resolve

**A versão do Python é fixada.** Sem `--python`, o `uv` pode reaproveitar um
interpretador antigo que já esteja na máquina. O RAGX usa `StrEnum`, que só
existe a partir do 3.11 — e a falha aparece muito depois, como um
`ModuleNotFoundError: pydantic_core._pydantic_core` que não diz nada sobre a
causa. Isso aconteceu ao testar este instalador.

**O extra `all` inclui o `mcp`.** Servir agentes por MCP é o propósito do
RAGX, não um acessório. Uma instalação que termina dizendo "pronto" e depois
falha no `ragx mcp serve` é a pior surpresa possível. Há teste garantindo que
esse extra não perca o pacote.

## Instalação manual

Se preferir controlar tudo:

```bash
uv tool install --python 3.12 "ragx[all]"
```

Ou de um wheel local:

```bash
uv tool install --python 3.12 release/ragx-1.0.0-py3-none-any.whl
```

O diretório dos executáveis sai de `uv tool dir --bin` — acrescente ao PATH.

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

Acrescente `"--write"` aos argumentos para que o agente possa reindexar e
sincronizar. Isso **não** dá acesso ao filesystem e não afrouxa o Security Gate
— ver [ADR-0012](../docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md).

## Extensão do VS Code

```bash
code --install-extension vscode-plugin/ragx-knowledge-explorer-1.0.0-beta.1.vsix
```

Detalhes em [vscode-plugin/README.md](../vscode-plugin/README.md).

## Desinstalar

```bash
uv tool uninstall ragx
```

A linha de PATH no seu perfil e o registro do MCP ficam — remova à mão se
quiser. O instalador não apaga o que não criou sozinho.
