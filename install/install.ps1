<#
.SYNOPSIS
    Instalador do RAGX para Windows.

.DESCRIPTION
    Funciona de duas formas:

      1. A partir do repositorio clonado:

             .\install\install.ps1

      2. Baixado e executado direto (PowerShell 5.1 precisa do TLS 1.2 antes,
         senao a conexao com o GitHub cai antes de baixar qualquer coisa):

             [Net.ServicePointManager]::SecurityProtocol = 3072
             irm https://github.com/OWNER/REPO/releases/download/vX.Y.Z/install.ps1 | iex

    O que ele faz, nesta ordem:
      1. instala o `uv` se nao houver (ele resolve Python sozinho)
      2. instala o `ragx` como ferramenta isolada
      3. GARANTE que `ragx` esteja no PATH do usuario - inclusive em janela nova
      4. registra o servidor MCP nos clientes que encontrar
      5. verifica que tudo funciona, em vez de prometer

.PARAMETER SemMcp
    Nao registra o servidor MCP nos clientes.

.PARAMETER Extra
    Extra do pacote a instalar. Padrao: all (MCP + busca semantica + tokens).

.PARAMETER Python
    Versao do interpretador. Padrao: 3.12. O RAGX exige 3.11 ou mais novo.

.PARAMETER Origem
    De onde instalar: caminho local, URL de wheel, ou `git+https://...`.
    Por padrao usa o repositorio clonado, se houver; senao, $env:RAGX_REPO.
#>
[CmdletBinding()]
param(
    [switch]$SemMcp,
    [string]$Extra = 'all',
    [string]$Python = '3.12',
    [string]$Origem = ''
)

# TLS 1.2. O PowerShell 5.1 ainda negocia SSL3/TLS1.0 por padrao em muitas
# instalacoes, e o GitHub recusa - o erro e "a conexao foi fechada de modo
# inesperado", que nao diz nada sobre TLS. Isto cobre o download que ESTE
# script faz; quem baixou o script ja precisou fazer o mesmo antes.
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor 3072
} catch {
    # Em PowerShell 7 o tipo pode nao aceitar a atribuicao; la o padrao ja e
    # TLS 1.2 e nao ha nada a corrigir.
}

function Escreva-Ok    { param($m) Write-Host "[OK] $m" -ForegroundColor Green }
function Escreva-Aviso { param($m) Write-Host "[!]  $m" -ForegroundColor Yellow }
function Escreva-Erro  { param($m) Write-Host "[X]  $m" -ForegroundColor Red }
function Escreva-Nota  { param($m) Write-Host "     $m" -ForegroundColor DarkGray }

<#
.SYNOPSIS
    Executa um programa nativo sem que stderr vire excecao.

.DESCRIPTION
    Com $ErrorActionPreference = 'Stop', o PowerShell trata qualquer escrita em
    stderr de um .exe como erro terminante. O `uv` escreve o progresso la -
    entao o instalador abortava no meio de uma instalacao que deu certo.

    Devolve o codigo de saida, que e o que realmente diz se funcionou.
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

<#
.SYNOPSIS
    Saida de um programa nativo, sem transformar stderr em excecao.
#>
function Ler-Nativo {
    param([Parameter(Mandatory)][string]$Exe, [string[]]$Argumentos = @())
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        return (& $Exe @Argumentos 2>&1 | Out-String)
    } finally {
        $ErrorActionPreference = $anterior
    }
}

<#
.SYNOPSIS
    Raiz do repositorio, quando o script esta num arquivo em disco.

.DESCRIPTION
    Por `irm | iex` nao existe arquivo: `$PSScriptRoot` e `$PSCommandPath`
    ficam VAZIOS. Sem este guarda, `Split-Path -Parent ''` levanta "nao e
    possivel associar o argumento ao parametro 'Path'" logo depois de instalar
    o uv - e a mensagem nao tem nenhuma relacao com a causa.
#>
function Obter-RaizLocal {
    $arquivo = $PSCommandPath
    if (-not $arquivo -and $PSScriptRoot) {
        $arquivo = Join-Path $PSScriptRoot 'install.ps1'
    }
    if (-not $arquivo) { return '' }
    $pasta = Split-Path -Parent $arquivo
    if (-not $pasta) { return '' }
    return (Split-Path -Parent $pasta)
}

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
        # Config corrompida: nao sobrescrever o que a pessoa tem. Melhor avisar
        # que apagar a configuracao dela.
        Escreva-Aviso "$Nome tem configuracao ilegivel; registre o MCP a mao"
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

<#
.SYNOPSIS
    O instalador.

.DESCRIPTION
    Corpo inteiro numa funcao para que a falha seja `throw`, e nao `exit`. Por
    `irm | iex` o script roda DENTRO da sessao da pessoa: um `exit` fecharia o
    terminal dela no meio do trabalho.
#>
function Invoke-InstalacaoRagx {
    param([switch]$SemMcp, [string]$Extra, [string]$Python, [string]$Origem)

    Write-Host ''
    Write-Host 'RAGX - instalacao' -ForegroundColor White
    Write-Host ''

    # -- 1. uv -----------------------------------------------------------
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Escreva-Aviso 'uv nao encontrado; instalando'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        # O instalador do uv grava o PATH do usuario, mas o processo ATUAL nao
        # recebe isso - por isso a recomposicao manual abaixo.
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'Machine')
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Escreva-Erro 'uv nao ficou disponivel no PATH desta sessao'
        Escreva-Nota 'Abra um PowerShell novo e rode o instalador de novo.'
        throw 'uv indisponivel'
    }
    $versaoUv = (Ler-Nativo uv @('--version')).Trim()
    Escreva-Ok "uv $((($versaoUv -split '\s+') | Select-Object -Index 1))"

    # -- 2. de onde instalar ---------------------------------------------
    if (-not $Origem) {
        $raiz = Obter-RaizLocal
        $local = if ($raiz) { Join-Path $raiz 'pyproject.toml' } else { '' }

        if ($local -and (Test-Path $local) -and
            (Select-String -Path $local -Pattern 'name = "ragx"' -Quiet)) {
            Escreva-Nota "instalando a partir deste repositorio: $raiz"
            $Origem = $raiz
        } else {
            $repo = if ($env:RAGX_REPO) { $env:RAGX_REPO } else { 'https://github.com/qualquer-de-tudo/ragx' }
            Escreva-Nota "instalando a partir de $repo"
            $Origem = "git+$repo"
        }
    } else {
        Escreva-Nota "instalando a partir de $Origem"
    }

    # -- 3. RAGX ---------------------------------------------------------
    # `uv tool install` cria um ambiente isolado: o RAGX nao polui o Python do
    # sistema nem briga com as dependencias de outro projeto.
    #
    # `--python` e explicito de proposito. Sem ele, o uv pode reaproveitar um
    # interpretador antigo que ja esteja por perto - e o RAGX usa `StrEnum`,
    # que so existe a partir do 3.11. Testando este instalador, o uv escolheu
    # 3.10 e a falha apareceu como ImportError de `pydantic_core`, longe da
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
        Escreva-Nota "Rode a mao para ver o erro:"
        Escreva-Nota "  uv tool install --python $Python `"$Origem`""
        if ($Origem -like 'git+*') {
            Escreva-Nota 'Se o repositorio for privado, o clone precisa de credencial.'
            Escreva-Nota 'Alternativa: baixe o .whl e rode com -Origem caminho\do\arquivo.whl'
        }
        throw 'instalacao falhou'
    }

    if ($comExtra) {
        Escreva-Ok "ragx instalado (Python $Python, com extra '$Extra')"
    } else {
        Escreva-Aviso "instalado SEM o extra '$Extra'"
        Escreva-Nota 'Sem ele faltam o servidor MCP e a busca semantica: rode ragx doctor.'
    }

    # -- 4. PATH ---------------------------------------------------------
    # `uv tool` instala em %USERPROFILE%\.local\bin, que NAO esta no PATH por
    # padrao no Windows. O sintoma classico e "instalei e o comando nao existe".
    $bin = (Ler-Nativo uv @('tool', 'dir', '--bin')).Trim()
    if (-not $bin -or -not (Test-Path $bin)) {
        $bin = Join-Path $env:USERPROFILE '.local\bin'
    }

    $pathUsuario = [Environment]::GetEnvironmentVariable('Path', 'User')
    $jaTem = ($pathUsuario -split ';' | Where-Object { $_.TrimEnd('\') -ieq $bin.TrimEnd('\') })

    if (-not $jaTem) {
        $novo = if ([string]::IsNullOrWhiteSpace($pathUsuario)) { $bin } else { "$pathUsuario;$bin" }
        [Environment]::SetEnvironmentVariable('Path', $novo, 'User')
        Escreva-Nota "PATH do usuario atualizado com $bin"
        Escreva-Nota 'Vale a partir da PROXIMA janela de terminal.'
    }
    # Sessao atual, para que a verificacao abaixo seja real e nao uma promessa.
    $env:Path = "$bin;$env:Path"
    Escreva-Ok "PATH: $bin"

    # -- 5. MCP ----------------------------------------------------------
    if (-not $SemMcp) {
        Registrar-Mcp 'Claude Desktop' (Join-Path $env:APPDATA 'Claude\claude_desktop_config.json')
        Registrar-Mcp 'Claude Code'    (Join-Path $env:USERPROFILE '.claude.json')
        Escreva-Ok 'servidor MCP disponivel: ragx mcp serve'
    }

    # -- 6. verificacao --------------------------------------------------
    Write-Host ''
    if (-not (Get-Command ragx -ErrorAction SilentlyContinue)) {
        Escreva-Erro 'ragx nao esta no PATH desta sessao'
        Escreva-Nota "Abra um PowerShell novo, ou rode: `$env:Path = '$bin;' + `$env:Path"
        throw 'ragx fora do PATH'
    }

    $versao = (Ler-Nativo ragx @('--version')).Trim()
    Escreva-Ok $versao

    # Numa instalacao nova o `doctor` acusa "banco ausente", que e o esperado:
    # ainda nao houve `ragx init`. Alarmar com isso ensina a pessoa a ignorar o
    # aviso - e ai o aviso que importa tambem passa batido.
    $saidaDoctor = Ler-Nativo ragx @('doctor')
    if ($saidaDoctor -match '0 problema') {
        Escreva-Ok 'ambiente verificado (ragx doctor)'
    } elseif ($saidaDoctor -match '(?i)banco.*ausente') {
        Escreva-Ok 'ambiente verificado - falta so indexar um projeto'
    } else {
        Escreva-Aviso 'ragx doctor apontou ressalvas; rode para ver o detalhe'
    }

    Write-Host ''
    Write-Host 'Pronto.' -ForegroundColor Green
    Write-Host ''
    Write-Host '  cd seu-projeto'
    Write-Host '  ragx init'
    Write-Host '  ragx index .'
    Write-Host '  ragx search "como funciona a autenticacao"'
    Write-Host ''
    Escreva-Nota 'Se o comando nao for encontrado, abra um terminal novo - o PATH'
    Escreva-Nota 'foi gravado no ambiente do usuario e vale na proxima sessao.'
    Write-Host ''
}

# `$ErrorActionPreference` local: por `irm | iex` o script roda dentro da
# sessao da pessoa, e mudar a preferencia dela em definitivo seria invasivo.
$prefAnterior = $ErrorActionPreference
$ErrorActionPreference = 'Stop'
try {
    Invoke-InstalacaoRagx -SemMcp:$SemMcp -Extra $Extra -Python $Python -Origem $Origem
} catch {
    Write-Host ''
    Escreva-Erro "instalacao interrompida: $($_.Exception.Message)"
    Escreva-Nota 'Nada foi deixado pela metade: o `uv tool install` e atomico.'
} finally {
    $ErrorActionPreference = $prefAnterior
}
