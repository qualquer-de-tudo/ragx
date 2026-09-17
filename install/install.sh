#!/usr/bin/env bash
#
# Instalador do RAGX para Linux e macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/qualquer-de-tudo/ragx/main/install/install.sh | bash
#
# Ou, a partir do repositório clonado:
#
#   ./install/install.sh
#
# O que ele faz, nesta ordem:
#   1. instala o `uv` se não houver (ele resolve Python sozinho)
#   2. instala o `ragx` como ferramenta isolada, com o extra `embed`
#   3. GARANTE que `ragx` esteja no PATH — inclusive em shell novo
#   4. registra o servidor MCP nos clientes que encontrar
#   5. verifica que tudo funciona, em vez de prometer

# O `-E` faz o `trap ERR` valer TAMBEM dentro de funcao. Sem ele, o `set -e`
# mata o instalador em silencio quando o erro acontece dentro de uma funcao
# — que foi exatamente o que aconteceu no passo da extensao do VS Code: o
# CI reportou "exit code 2" depois de tres linhas de sucesso, sem uma
# palavra sobre onde parou.
set -Eeuo pipefail

VERDE=$'\033[32m'; AMARELO=$'\033[33m'; VERMELHO=$'\033[31m'; CINZA=$'\033[90m'; FIM=$'\033[0m'
ok()    { printf '%s✓%s %s\n' "$VERDE" "$FIM" "$1"; }
aviso() { printf '%s!%s %s\n' "$AMARELO" "$FIM" "$1"; }
erro()  { printf '%s✗%s %s\n' "$VERMELHO" "$FIM" "$1" >&2; }
nota()  { printf '  %s%s%s\n' "$CINZA" "$1" "$FIM"; }

# Uma parada inesperada tem de DIZER onde parou. Um instalador que sai mudo
# ensina quem o roda a nao confiar nem no sucesso.
ao_falhar() {
  local codigo=$?
  erro "o instalador parou na linha ${1:-?} (codigo $codigo)"
  nota "nada foi desfeito; o que ja instalou continua instalado"
  exit "$codigo"
}
trap 'ao_falhar $LINENO' ERR

RAGX_REPO="${RAGX_REPO:-https://github.com/qualquer-de-tudo/ragx}"
COM_MCP="${RAGX_INSTALL_MCP:-1}"
EXTRA="${RAGX_EXTRA:-all}"

printf '\n%sRAGX%s — instalação\n\n' $'\033[1m' "$FIM"

# ── 1. uv ───────────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  aviso "uv não encontrado; instalando"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # O instalador do uv coloca o binário aqui, mas só exporta no PRÓXIMO shell.
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || { erro "uv não ficou disponível no PATH"; exit 1; }
ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"

# ── 2. RAGX ─────────────────────────────────────────────────────────────
# Por `curl | bash` NÃO existe arquivo em disco: `${BASH_SOURCE[0]}` vem vazio,
# `dirname ""` devolve "." e o script passaria a procurar um `pyproject.toml`
# no diretório de onde a pessoa chamou — instalando o projeto errado, em
# silêncio. Só tratamos como repositório local quando há mesmo um arquivo.
AQUI=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# Procura um wheel do RAGX onde ele costuma estar. O caso que importa: a
# pessoa baixou os arquivos da release para uma pasta e abriu o terminal ali.
# Fazer ela digitar o caminho do .whl é um passo a mais para errar.
encontrar_wheel() {
  local pasta
  for pasta in "${1:-}" "$PWD" "$HOME/Downloads" "$HOME/Descargas"; do
    [ -n "$pasta" ] && [ -d "$pasta" ] || continue
    # `ls | sort -r | head` em vez de glob: com zero arquivos o glob viraria
    # o próprio padrão e o teste `-f` daria falso negativo silencioso.
    local achado
    # `|| true` pelo mesmo motivo de `instalar_extensao`. Hoje esta função é
    # chamada dentro de um `elif`, onde o `set -e` fica suspenso, e por isso
    # escapou; depender do ponto de chamada para não derrubar o script é
    # armadilha para quem mexer depois.
    achado="$(ls -1 "$pasta"/ragx-*.whl 2>/dev/null | sort -r | head -1 || true)"
    if [ -n "$achado" ] && [ -f "$achado" ]; then
      printf '%s' "$achado"
      return 0
    fi
  done
  return 1
}

PASTA_SCRIPT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  PASTA_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -n "${RAGX_ORIGEM:-}" ]; then
  nota "instalando a partir de $RAGX_ORIGEM"
  ORIGEM="$RAGX_ORIGEM"
elif WHEEL="$(encontrar_wheel "$PASTA_SCRIPT")"; then
  # O wheel baixado vem ANTES do clone: quem baixou os arquivos de uma release
  # quer AQUELA versão, não o que estiver no `main` hoje.
  nota "wheel encontrado: $WHEEL"
  ORIGEM="$WHEEL"
elif [ -n "$AQUI" ] && [ -f "$AQUI/pyproject.toml" ]      && grep -q 'name = "ragx"' "$AQUI/pyproject.toml" 2>/dev/null; then
  nota "instalando a partir deste repositório: $AQUI"
  ORIGEM="$AQUI"
else
  nota "instalando a partir de $RAGX_REPO"
  ORIGEM="git+$RAGX_REPO"
fi

# `uv tool install` cria um ambiente isolado: o RAGX não polui o Python do
# sistema nem briga com as dependências de outro projeto.
#
# `--python` é explícito de propósito. Sem ele, o uv pode reaproveitar um
# interpretador antigo que já esteja por perto — e o RAGX usa `StrEnum`, que só
# existe a partir do 3.11. Testando este instalador, o uv escolheu 3.10 e a
# falha apareceu como um ImportError de `pydantic_core`, longe da causa real.
PY="${RAGX_PYTHON:-3.12}"

if uv tool install --force --python "$PY" "$ORIGEM[$EXTRA]" 2>/dev/null; then
  ok "ragx instalado (Python $PY, com extra '$EXTRA')"
elif uv tool install --force --python "$PY" "$ORIGEM"; then
  aviso "instalado SEM o extra '$EXTRA'"
  nota "sem ele faltam o servidor MCP e a busca semântica; rode: ragx doctor"
else
  erro "falha ao instalar o ragx"
  nota "rode à mão para ver o erro: uv tool install --python $PY '$ORIGEM'"
  case "$ORIGEM" in
    git+*)
      nota "instalar do git precisa do próprio git instalado e de rede"
      nota "se falhar, baixe os arquivos da release e rode este script na"
      nota "pasta deles — ele encontra o wheel sem precisar clonar:"
      nota "  gh release download <tag> --repo qualquer-de-tudo/ragx --dir ragx"
      nota "  cd ragx && bash install.sh"
      ;;
  esac
  exit 1
fi

# ── 3. PATH ─────────────────────────────────────────────────────────────
# `uv tool` instala em ~/.local/bin. Em muitas distribuições isso NÃO está no
# PATH de um shell novo — e o sintoma é "instalei e o comando não existe".
BIN="$(uv tool dir --bin 2>/dev/null || echo "$HOME/.local/bin")"
export PATH="$BIN:$PATH"

adicionar_ao_perfil() {
  local arquivo="$1"
  local linha="export PATH=\"$BIN:\$PATH\"  # RAGX"
  [ -f "$arquivo" ] || return 0
  grep -qF "$BIN" "$arquivo" && return 0
  printf '\n# RAGX — adicionado pelo instalador\n%s\n' "$linha" >> "$arquivo"
  nota "PATH gravado em $arquivo"
}

if ! printf '%s' "${PATH_ORIGINAL:-$PATH}" | tr ':' '\n' | grep -qx "$BIN"; then
  for perfil in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    adicionar_ao_perfil "$perfil"
  done
  # Fish guarda o PATH de outro jeito.
  if command -v fish >/dev/null 2>&1; then
    fish -c "fish_add_path -g $BIN" 2>/dev/null && nota "PATH gravado no fish"
  fi
fi
ok "PATH: $BIN"

# ── 4. MCP ──────────────────────────────────────────────────────────────
# Quem registra é o próprio RAGX: `ragx mcp install`.
#
# Este passo já foi um script Python embutido entre aspas aqui dentro, com um
# gêmeo reescrito em PowerShell no install.ps1 — duas implementações, nenhuma
# testada, e só uma delas sabia fazer backup. Agora existe uma, coberta por
# `tests/integration/test_mcp_install.py`, e ela cobre Claude Desktop, Claude
# Code, Cursor, Windsurf, Gemini CLI e Codex CLI.
#
# Também não precisa mais de `python3` no PATH: o interpretador que interessa
# é o que o `uv` usou para instalar o RAGX.
if [ "$COM_MCP" = "1" ]; then
  # Caminho ABSOLUTO no `--command`: aplicativo grafico (o Claude Desktop, por
  # exemplo) nao herda o PATH do shell de forma confiavel, e `ragx` sozinho
  # pode nao ser encontrado pelo cliente.
  if "$BIN/ragx" mcp install --command "$BIN/ragx"; then
    ok "servidor MCP registrado nos clientes encontrados"
  else
    # Falhar aqui não invalida a instalação: o RAGX está no lugar e funciona.
    # Registrar em cliente nenhum é inconveniente, não é motivo para desfazer
    # tudo que já deu certo.
    aviso "não consegui registrar em algum cliente MCP — rode 'ragx mcp install' para ver o motivo"
  fi
fi

# ── 5. extensão do VS Code, se o .vsix veio junto ───────────────────────
instalar_extensao() {
  local pasta vsix=""
  for pasta in "$PASTA_SCRIPT" "$PWD" "$HOME/Downloads" "$HOME/Descargas"; do
    [ -n "$pasta" ] && [ -d "$pasta" ] || continue
    # O `|| true` NÃO é decoração: sem correspondência o `ls` sai com 2, o
    # `pipefail` propaga isso pelo pipe e o `set -e` mata o instalador inteiro
    # — depois de já ter instalado tudo, sem imprimir uma linha de erro. Foi
    # assim que o job de instalação do CI passou a sair com código 2.
    vsix="$(ls -1 "$pasta"/*.vsix 2>/dev/null | sort -r | head -1 || true)"
    [ -n "$vsix" ] && break
  done
  [ -n "$vsix" ] || return 0

  # Sem `code` no PATH não há o que fazer, e isso NÃO é erro: muita gente usa
  # outro editor. Avisa e segue.
  if ! command -v code >/dev/null 2>&1; then
    nota "extensão encontrada, mas \`code\` não está no PATH:"
    nota "  code --install-extension \"$vsix\""
    return 0
  fi
  if code --install-extension "$vsix" --force >/dev/null 2>&1; then
    ok "extensão do VS Code instalada"
  else
    aviso "falha ao instalar a extensão; instale à mão:"
    nota "  code --install-extension \"$vsix\""
  fi
}

if [ "${RAGX_INSTALL_VSCODE:-1}" = "1" ]; then
  instalar_extensao
fi

# ── 6. verificação ──────────────────────────────────────────────────────
printf '\n'
if ! command -v ragx >/dev/null 2>&1; then
  erro "ragx não está no PATH deste shell"
  nota "abra um terminal novo, ou rode: export PATH=\"$BIN:\$PATH\""
  exit 1
fi

VERSAO="$(ragx --version 2>&1 | head -1)"
ok "$VERSAO"

# Numa instalação nova o `doctor` acusa "banco ausente", que é o esperado:
# ainda não houve `ragx init`. Alarmar com isso ensina a pessoa a ignorar o
# aviso — e aí o aviso que importa também passa batido.
SAIDA_DOCTOR="$(ragx doctor 2>&1 || true)"
if printf '%s' "$SAIDA_DOCTOR" | grep -q "0 problema"; then
  ok "ambiente verificado (ragx doctor)"
elif printf '%s' "$SAIDA_DOCTOR" | grep -qi "banco.*ausente"; then
  ok "ambiente verificado — falta só indexar um projeto"
else
  aviso "ragx doctor apontou ressalvas; rode para ver o detalhe"
fi

cat <<EOF

${VERDE}Pronto.${FIM}

  cd seu-projeto
  ragx init
  ragx index .
  ragx search "como funciona a autenticação"

${CINZA}Se o comando não for encontrado, abra um terminal novo — o PATH foi
gravado no seu perfil e só vale a partir da próxima sessão.${FIM}
EOF
