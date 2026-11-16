"""O caminho do índice pelo git não é um atalho em volta do Security Gate (RAGX-0198).

O git só diz QUAIS arquivos olhar; cada um deles passa por `gate.admit` antes do parser, como na
varredura. Segredo novo, `.env` e arquivo de nome sensível que o git aponta continuam fora do índice.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.models import Verdict
from ragx.indexing import parsers
from ragx.indexing.pipeline import index_project
from ragx.security.gate import SecurityGate
from ragx.storage.db import open_db

pytestmark = pytest.mark.security

TOML = (
    '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n\n'
    "[index]\njobs = 1\n"
)
# segredo falso de propósito (padrão AWS de documentação)
SEGREDO = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'


def _git(raiz: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=raiz, check=True, capture_output=True)


def test_arquivo_apontado_pelo_git_passa_pelo_gate_antes_do_parser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz = tmp_path / "p"
    raiz.mkdir()
    if subprocess.run(["git", "init", "-q"], cwd=raiz, capture_output=True).returncode != 0:
        pytest.skip("git indisponível")
    _git(raiz, "config", "user.email", "t@t")
    _git(raiz, "config", "user.name", "t")
    (raiz / "ragx.toml").write_text(TOML, encoding="utf-8")
    (raiz / ".gitignore").write_text(".ragx/\n", encoding="utf-8")
    (raiz / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    _git(raiz, "add", "-A")
    _git(raiz, "commit", "-qm", "c1")
    index_project(load_config(raiz))

    (raiz / ".env").write_text("DB_PASSWORD=hunter2hunter2\n", encoding="utf-8")
    (raiz / "config.py").write_text(SEGREDO, encoding="utf-8")
    (raiz / "a.py").write_text("def a():\n    return 2\n", encoding="utf-8")

    admitidos: set[str] = set()
    admit_original = SecurityGate.admit
    parse_original = parsers.parse

    def admit(self: SecurityGate, rel: str, raw: bytes):  # type: ignore[no-untyped-def]
        decisao = admit_original(self, rel, raw)
        if decisao.verdict in (Verdict.ALLOW, Verdict.ALLOW_REDACTED):
            admitidos.add(rel)
        return decisao

    def parse(rel: str, text: str, **kw):  # type: ignore[no-untyped-def]
        assert rel in admitidos, f"{rel} chegou ao parser sem passar pelo Gate"
        return parse_original(rel, text, **kw)

    monkeypatch.setattr(SecurityGate, "admit", admit)
    monkeypatch.setattr(parsers, "parse", parse)
    r = index_project(load_config(raiz))

    assert r.scan_mode == "git"
    assert r.stats.indexed == 1 and r.stats.blocked == 2
    with open_db(load_config(raiz).db_path, read_only=True) as conn:
        caminhos = {row[0] for row in conn.execute("SELECT rel_path FROM documents")}
        conteudo = "\n".join(row[0] for row in conn.execute("SELECT content FROM chunks"))
    assert ".env" not in caminhos and "config.py" not in caminhos
    assert "hunter2" not in conteudo and "wJalrXUtnFEMI" not in conteudo
