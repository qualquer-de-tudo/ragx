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

set -euo pipefail

VERDE=$'\033[32m'; AMARELO=$'\033[33m'; VERMELHO=$'\033[31m'; CINZA=$'\033[90m'; FIM=$'\033[0m'
ok()    { printf '%s✓%s %s\n' "$VERDE" "$FIM" "$1"; }
aviso() { printf '%s!%s %s\n' "$AMARELO" "$FIM" "$1"; }
erro()  { printf '%s✗%s %s\n' "$VERMELHO" "$FIM" "$1" >&2; }
nota()  { printf '  %s%s%s\n' "$CINZA" "$1" "$FIM"; }

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

if [ -n "${RAGX_ORIGEM:-}" ]; then
  nota "instalando a partir de $RAGX_ORIGEM"
  ORIGEM="$RAGX_ORIGEM"
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
      nota "se o repositório for privado, o clone precisa de credencial"
      nota "alternativa: baixe o .whl e rode"
      nota "  RAGX_ORIGEM=/caminho/ragx-1.0.0-py3-none-any.whl ./install.sh"
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
registrar_mcp() {
  local nome="$1" arquivo="$2"
  [ -d "$(dirname "$arquivo")" ] || return 0
  python3 - "$arquivo" <<'PY' 2>/dev/null && nota "MCP registrado em $nome" || true
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
try:
    dados = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
except json.JSONDecodeError:
    # Config corrompida: não sobrescrever o que a pessoa tem. Melhor falhar
    # e deixar ela registrar à mão que apagar a configuração dela.
    sys.exit(1)
servidores = dados.setdefault("mcpServers", {})
servidores["ragx"] = {"command": "ragx", "args": ["mcp", "serve"]}
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

if [ "$COM_MCP" = "1" ]; then
  registrar_mcp "Claude Desktop" "$HOME/.config/Claude/claude_desktop_config.json"
  registrar_mcp "Claude Desktop (macOS)" "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
  registrar_mcp "Claude Code" "$HOME/.claude.json"
  ok "servidor MCP disponível: ragx mcp serve"
fi

# ── 5. verificação ──────────────────────────────────────────────────────
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
