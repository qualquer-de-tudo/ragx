"""Instruções do usuário para clientes sem hook (RAGX-0202).

Codex e Gemini CLI não têm a dica de início de sessão nem o lembrete de busca do Claude Code: só recebem o servidor
MCP, cujas instruções o modelo costuma ignorar. Os dois leem um arquivo de instruções do usuário em toda sessão
(`~/.codex/AGENTS.md` e `~/.gemini/GEMINI.md`). Ao registrar o RAGX num deles, um bloco curto e delimitado entra
nesse arquivo; ao remover, sai. Tudo o que a pessoa escreveu fora do bloco fica como estava.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

INICIO = "<!-- ragx:inicio (gerenciado pelo RAGX; some quando você desliga o RAGX neste cliente) -->"
FIM = "<!-- ragx:fim -->"
_BLOCO = re.compile(r"\n*<!-- ragx:inicio[^\n]*-->.*?<!-- ragx:fim -->\n?", re.S)

TEXTO = """## RAGX

Quando o projeto tiver uma pasta `.ragx/` (índice do RAGX), consulte o índice antes de buscar ou ler arquivos:

- localizar código: a ferramenta MCP `search_hybrid` devolve arquivo e linhas;
- entender um assunto: `build_context` devolve só os trechos relevantes, com arquivo e linhas;
- depois de editar arquivos: `refresh`.

Sai mais barato do que grep e leitura de arquivos inteiros. Fora de um projeto indexado, ignore esta seção."""


def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())


def instruction_file(client_id: str, home: Path | None = None) -> Path | None:
    """O arquivo de instruções do usuário do cliente, ou `None` se ele não tem um que o RAGX saiba editar.

    Cursor e Windsurf guardam as regras do usuário nas próprias configurações, não num arquivo: ficam de fora.
    """
    base = home or _home()
    return {"codex": base / ".codex" / "AGENTS.md", "gemini": base / ".gemini" / "GEMINI.md"}.get(client_id)


def _bloco() -> str:
    return f"{INICIO}\n{TEXTO}\n{FIM}\n"


def _escrever(path: Path, texto: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".ragx.tmp")
    temp.write_text(texto, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def apply(client_id: str, home: Path | None = None) -> str | None:
    """Põe (ou atualiza) o bloco. Devolve o caminho alterado, ou `None` se nada mudou ou o cliente não tem arquivo."""
    path = instruction_file(client_id, home)
    if path is None:
        return None
    atual = path.read_text(encoding="utf-8") if path.is_file() else ""
    sem = _BLOCO.sub("\n", atual).rstrip("\n")
    novo = (sem + "\n\n" if sem else "") + _bloco()
    if novo == atual:
        return None
    _escrever(path, novo)
    return str(path)


def remove(client_id: str, home: Path | None = None) -> str | None:
    """Tira só o bloco. Arquivo que só tinha o bloco é apagado (foi o RAGX que o criou)."""
    path = instruction_file(client_id, home)
    if path is None or not path.is_file():
        return None
    atual = path.read_text(encoding="utf-8")
    if not _BLOCO.search(atual):
        return None
    sem = _BLOCO.sub("\n", atual).strip("\n")
    if sem:
        _escrever(path, sem + "\n")
    else:
        path.unlink()
    return str(path)


def present(client_id: str, home: Path | None = None) -> bool | None:
    """O bloco está no arquivo? `None` quando o cliente não tem arquivo de instruções."""
    path = instruction_file(client_id, home)
    if path is None:
        return None
    try:
        return bool(_BLOCO.search(path.read_text(encoding="utf-8")))
    except OSError:
        return False
