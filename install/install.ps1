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

.PARAMETER SemVsCode
    Nao instala a extensao do VS Code, mesmo que o .vsix esteja junto.

.PARAMETER Extra
    Extra do pacote a instalar. Padrao: all (MCP + busca semantica + tokens).

.PARAMETER Python
    Versao do interpretador. Padrao: 3.12. O RAGX exige 3.11 ou mais novo.

.PARAMETER Origem
    De onde instalar. Por padrao o instalador procura, nesta ordem:

      1. o que voce passar aqui (ou $env:RAGX_ORIGEM)
      2. um `ragx-*.whl` NA PASTA DESTE SCRIPT  <- e o caso do download
      3. um `ragx-*.whl` na pasta atual
      4. um `ragx-*.whl` em ~\Downloads
      5. o repositorio clonado, se este script estiver dentro dele
      6. `git+$env:RAGX_REPO` (exige repositorio publico ou credencial)
#>
[CmdletBinding()]
param(
    [switch]$SemMcp,
    [switch]$SemVsCode,
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

<#
.SYNOPSIS
    Procura um wheel do RAGX nos lugares onde ele costuma estar.

.DESCRIPTION
    O caso que importa: a pessoa baixou os arquivos da release para uma pasta e
    abriu o terminal ali. Fazer ela digitar o caminho do .whl e um passo a mais
    para errar - o instalador acha sozinho.

    Se houver mais de um, pega o de nome mais alto (ordem alfabetica), que para
    versoes com o mesmo numero de digitos e a mais nova.
#>
function Encontrar-Wheel {
    param([string]$PastaDoScript)

    $lugares = @()
    if ($PastaDoScript) { $lugares += $PastaDoScript }
    $lugares += (Get-Location).Path
    $lugares += (Join-Path $env:USERPROFILE 'Downloads')

    foreach ($pasta in $lugares) {
        if (-not $pasta -or -not (Test-Path $pasta)) { continue }
        $achado = Get-ChildItem -Path $pasta -Filter 'ragx-*.whl' -File -ErrorAction SilentlyContinue |
                  Sort-Object Name -Descending | Select-Object -First 1
        if ($achado) { return $achado.FullName }
    }
    return ''
}

<#
.SYNOPSIS
    Instala a extensao do VS Code, se o .vsix estiver por perto.

.DESCRIPTION
    Sem `code` no PATH nao ha o que fazer, e isso NAO e erro: muita gente usa
    outro editor. Avisa e segue.
#>
function Instalar-Extensao {
    param([string]$PastaDoScript)

    $lugares = @()
    if ($PastaDoScript) { $lugares += $PastaDoScript }
    $lugares += (Get-Location).Path
    $lugares += (Join-Path $env:USERPROFILE 'Downloads')

    $vsix = ''
    foreach ($pasta in $lugares) {
        if (-not $pasta -or -not (Test-Path $pasta)) { continue }
        $achado = Get-ChildItem -Path $pasta -Filter '*.vsix' -File -ErrorAction SilentlyContinue |
                  Sort-Object Name -Descending | Select-Object -First 1
        if ($achado) { $vsix = $achado.FullName; break }
    }
    if (-not $vsix) { return }

    if (-not (Get-Command code -ErrorAction SilentlyContinue)) {
        Escreva-Nota "extensao encontrada mas `code` nao esta no PATH:"
        Escreva-Nota "  code --install-extension `"$vsix`""
        return
    }

    if ((Invoke-Nativo code @('--install-extension', $vsix, '--force')) -eq 0) {
        Escreva-Ok "extensao do VS Code instalada"
    } else {
        Escreva-Aviso 'falha ao instalar a extensao; instale a mao:'
        Escreva-Nota "  code --install-extension `"$vsix`""
    }
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
    param([switch]$SemMcp, [switch]$SemVsCode, [string]$Extra,
          [string]$Python, [string]$Origem)

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
    $pastaScript = ''
    if ($PSCommandPath) { $pastaScript = Split-Path -Parent $PSCommandPath }

    if (-not $Origem -and $env:RAGX_ORIGEM) { $Origem = $env:RAGX_ORIGEM }

    if (-not $Origem) {
        # O wheel baixado vem PRIMEIRO. Com repositorio privado ele e o unico
        # caminho que funciona sem credencial, e e o que a pessoa acabou de
        # fazer: baixou os arquivos e abriu o terminal na pasta deles.
        $wheel = Encontrar-Wheel -PastaDoScript $pastaScript
        if ($wheel) {
            Escreva-Nota "wheel encontrado: $wheel"
            $Origem = $wheel
        }
    }

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
            Escreva-Nota 'O repositorio e privado: o clone precisa de credencial.'
            Escreva-Nota 'Baixe os arquivos da release e rode este script na pasta deles:'
            Escreva-Nota '  gh release download v1.0.0 --repo OWNER/REPO --dir ragx'
            Escreva-Nota '  cd ragx; .\install.ps1'
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

    # -- 6. extensao do VS Code, se o .vsix veio junto --------------------
    if (-not $SemVsCode) {
        Instalar-Extensao -PastaDoScript $pastaScript
    }

    # -- 7. verificacao --------------------------------------------------
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
    Invoke-InstalacaoRagx -SemMcp:$SemMcp -SemVsCode:$SemVsCode -Extra $Extra `
                          -Python $Python -Origem $Origem
    # O `ragx doctor` sai com codigo != 0 quando ainda nao ha indice, que e o
    # esperado numa instalacao nova. Sem zerar isto, o codigo dele vaza como
    # resultado do INSTALADOR e qualquer automacao conclui que a instalacao
    # falhou - depois de ela ter dado certo.
    $global:LASTEXITCODE = 0
} catch {
    Write-Host ''
    Escreva-Erro "instalacao interrompida: $($_.Exception.Message)"
    Escreva-Nota 'Nada foi deixado pela metade: o `uv tool install` e atomico.'
    $global:LASTEXITCODE = 1
} finally {
    $ErrorActionPreference = $prefAnterior
}
