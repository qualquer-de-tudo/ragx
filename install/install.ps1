<#
.SYNOPSIS
    Instalador do RAGX para Windows.

.DESCRIPTION
    irm https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.ps1 | iex

    Ou, a partir do repositório clonado:

        .\install\install.ps1

    O que ele faz, nesta ordem:
      1. instala o `uv` se não houver (ele resolve Python sozinho)
      2. instala o `ragx` como ferramenta isolada
      3. GARANTE que `ragx` esteja no PATH do usuário — inclusive em janela nova
      4. registra o servidor MCP nos clientes que encontrar
      5. verifica que tudo funciona, em vez de prometer

.PARAMETER SemMcp
    Não registra o servidor MCP nos clientes.

.PARAMETER Extra
    Extra do pacote a instalar. Padrão: all (MCP + busca semântica + tokens).

.PARAMETER Python
    Versão do interpretador. Padrão: 3.12. O RAGX exige 3.11 ou mais novo.
#>
[CmdletBinding()]
param(
    [switch]$SemMcp,
    [string]$Extra = 'all',
    [string]$Python = '3.12'
)

$ErrorActionPreference = 'Stop'

<#
.SYNOPSIS
    Executa um programa nativo sem que stderr vire exceção.

.DESCRIPTION
    Com $ErrorActionPreference = 'Stop', o PowerShell trata qualquer escrita em
    stderr de um .exe como erro terminante. O `uv` escreve o progresso lá —
    então o instalador abortava no meio de uma instalação que deu certo.

    Devolve o código de saída, que é o que realmente diz se funcionou.
#>
function Invoke-Nativo {
    param([Parameter(Mandatory)][string]$Exe, [string[]]$Argumentos = @())
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Argumentos 2>&1 | Out-String | Write-Verbose
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $anterior
    }
}

function Escreva-Ok    { param($m) Write-Host "[OK] $m" -ForegroundColor Green }
function Escreva-Aviso { param($m) Write-Host "[!]  $m" -ForegroundColor Yellow }
function Escreva-Erro  { param($m) Write-Host "[X]  $m" -ForegroundColor Red }
function Escreva-Nota  { param($m) Write-Host "     $m" -ForegroundColor DarkGray }

Write-Host ''
Write-Host 'RAGX — instalação' -ForegroundColor White
Write-Host ''

# ── 1. uv ───────────────────────────────────────────────────────────────
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Escreva-Aviso 'uv não encontrado; instalando'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    # O instalador do uv grava o PATH do usuário, mas o processo ATUAL não
    # recebe isso — por isso a recomposição manual abaixo.
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'Machine')
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Escreva-Erro 'uv não ficou disponível no PATH desta sessão'
    Escreva-Nota 'Abra um PowerShell novo e rode o instalador de novo.'
    exit 1
}
$versaoUv = (& { $ErrorActionPreference = 'Continue'; uv --version 2>&1 }) -join ' '
Escreva-Ok "uv $(($versaoUv -split ' ')[1])"

# ── 2. RAGX ─────────────────────────────────────────────────────────────
$Aqui = Split-Path -Parent $PSScriptRoot
$Local = Join-Path $Aqui 'pyproject.toml'

if ((Test-Path $Local) -and (Select-String -Path $Local -Pattern 'name = "ragx"' -Quiet)) {
    Escreva-Nota "instalando a partir deste repositório: $Aqui"
    $Origem = $Aqui
} else {
    $Repo = if ($env:RAGX_REPO) { $env:RAGX_REPO } else { 'https://github.com/qualquer-de-tudo/ragx' }
    Escreva-Nota "instalando a partir de $Repo"
    $Origem = "git+$Repo"
}

# `uv tool install` cria um ambiente isolado: o RAGX não polui o Python do
# sistema nem briga com as dependências de outro projeto.
#
# `--python` é explícito de propósito. Sem ele, o uv pode reaproveitar um
# interpretador antigo que já esteja por perto — e o RAGX usa `StrEnum`, que só
# existe a partir do 3.11. Testando o instalador neste Windows, o uv escolheu
# 3.10 e a falha apareceu como um ImportError de `pydantic_core`, longe da
# causa real.
$comExtra = $false
$instalou = $false

if ((Invoke-Nativo uv @('tool', 'install', '--force', '--python', $Python, "$Origem[$Extra]")) -eq 0) {
    $instalou = $true
    $comExtra = $true
}

if (-not $instalou) {
    if ((Invoke-Nativo uv @('tool', 'install', '--force', '--python', $Python, $Origem)) -eq 0) {
        $instalou = $true
    }
}

if (-not $instalou) {
    Escreva-Erro 'falha ao instalar o ragx'
    Escreva-Nota "Rode a mao para ver o erro: uv tool install --python $Python $Origem"
    exit 1
}

if ($comExtra) {
    Escreva-Ok "ragx instalado (Python $Python, com extra '$Extra')"
} else {
    Escreva-Aviso "instalado SEM o extra '$Extra'"
    Escreva-Nota 'Sem ele faltam o servidor MCP e a busca semantica: rode ragx doctor.'
}

# ── 3. PATH ─────────────────────────────────────────────────────────────
# `uv tool` instala em %USERPROFILE%\.local\bin, que NÃO está no PATH por
# padrão no Windows. O sintoma clássico é "instalei e o comando não existe".
$Bin = (& { $ErrorActionPreference = 'Continue'; uv tool dir --bin 2>$null }) | Select-Object -First 1
if (-not $Bin -or -not (Test-Path $Bin)) {
    $Bin = Join-Path $env:USERPROFILE '.local\bin'
}
$Bin = $Bin.Trim()

$PathUsuario = [Environment]::GetEnvironmentVariable('Path', 'User')
$jaTem = ($PathUsuario -split ';' | Where-Object { $_.TrimEnd('\') -ieq $Bin.TrimEnd('\') })

if (-not $jaTem) {
    $novo = if ([string]::IsNullOrWhiteSpace($PathUsuario)) { $Bin } else { "$PathUsuario;$Bin" }
    [Environment]::SetEnvironmentVariable('Path', $novo, 'User')
    Escreva-Nota "PATH do usuário atualizado com $Bin"
    Escreva-Nota 'Vale a partir da PRÓXIMA janela de terminal.'
}
# Sessão atual, para que a verificação abaixo seja real e não uma promessa.
$env:Path = "$Bin;$env:Path"
Escreva-Ok "PATH: $Bin"

# ── 4. MCP ──────────────────────────────────────────────────────────────
function Registrar-Mcp {
    param([string]$Nome, [string]$Arquivo)

    $pasta = Split-Path -Parent $Arquivo
    if (-not (Test-Path $pasta)) { return }

    try {
        $dados = if (Test-Path $Arquivo) {
            Get-Content $Arquivo -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
        } else {
            [PSCustomObject]@{}
        }
    } catch {
        # Config corrompida: não sobrescrever o que a pessoa tem. Melhor avisar
        # que apagar a configuração dela.
        Escreva-Aviso "$Nome tem configuração ilegível; registre o MCP à mão"
        return
    }

    if (-not $dados.PSObject.Properties.Name.Contains('mcpServers')) {
        $dados | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([PSCustomObject]@{})
    }
    $servidor = [PSCustomObject]@{ command = 'ragx'; args = @('mcp', 'serve') }
    if ($dados.mcpServers.PSObject.Properties.Name.Contains('ragx')) {
        $dados.mcpServers.ragx = $servidor
    } else {
        $dados.mcpServers | Add-Member -NotePropertyName ragx -NotePropertyValue $servidor
    }

    $dados | ConvertTo-Json -Depth 20 | Set-Content -Path $Arquivo -Encoding utf8
    Escreva-Nota "MCP registrado em $Nome"
}

if (-not $SemMcp) {
    Registrar-Mcp 'Claude Desktop' (Join-Path $env:APPDATA 'Claude\claude_desktop_config.json')
    Registrar-Mcp 'Claude Code'    (Join-Path $env:USERPROFILE '.claude.json')
    Escreva-Ok 'servidor MCP disponível: ragx mcp serve'
}

# ── 5. verificação ──────────────────────────────────────────────────────
Write-Host ''
if (-not (Get-Command ragx -ErrorAction SilentlyContinue)) {
    Escreva-Erro 'ragx não está no PATH desta sessão'
    Escreva-Nota "Abra um PowerShell novo, ou rode: `$env:Path = '$Bin;' + `$env:Path"
    exit 1
}

$versao = (& { $ErrorActionPreference = 'Continue'; ragx --version 2>&1 }) | Select-Object -First 1
Escreva-Ok $versao

if ((Invoke-Nativo ragx @('doctor')) -eq 0) {
    Escreva-Ok 'ambiente verificado (ragx doctor)'
} else {
    Escreva-Aviso 'ragx doctor apontou ressalvas — rode para ver o detalhe'
}

Write-Host ''
Write-Host 'Pronto.' -ForegroundColor Green
Write-Host ''
Write-Host '  cd seu-projeto'
Write-Host '  ragx init'
Write-Host '  ragx index .'
Write-Host '  ragx search "como funciona a autenticacao"'
Write-Host ''
Escreva-Nota 'Se o comando nao for encontrado, abra um terminal novo — o PATH'
Escreva-Nota 'foi gravado no ambiente do usuario e vale na proxima sessao.'
Write-Host ''
