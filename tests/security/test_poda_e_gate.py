"""Podar pasta ignorada não pode mudar o que o Security Gate admite.

A poda (`IgnoreEngine.can_prune`) só deixa de DESCER numa pasta ignorada: nada
dentro dela seria lido antes e nada passa a ser lido agora. Estes testes provam
isso pelo resultado: o conjunto de arquivos que o walker entrega ao índice, com
o veredito de cada um, é idêntico com a poda e sem ela. Se um dia a poda afrouxar
o Gate (entregar um arquivo que antes era bloqueado) ou esconder um arquivo que
antes entrava, a igualdade quebra.

Ver `task/fase-19-velocidade-e-frescor/RAGX-0129-*.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ragx.security.gate import SecurityGate
from ragx.walk import iter_files

pytestmark = pytest.mark.security

# Segredo falso, de propósito (fixture do próprio Gate).
_SEGREDO = "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"


def _arvore(raiz: Path) -> Path:
    (raiz / ".gitignore").write_text(
        "node_modules/\ndist/\nbuild/\n!sub/build/\n!sub/keep/\n", encoding="utf-8"
    )
    (raiz / "sub").mkdir()
    (raiz / "sub" / ".gitignore").write_text(".vscode/*\n!.vscode/extensions.json\n", encoding="utf-8")
    arquivos = {
        "app.py": "print('ok')\n",
        "sub/src/d.py": "print('d')\n",
        "sub/build/c.py": "print('c')\n",
        "sub/keep/k.py": "print('k')\n",
        "sub/.vscode/extensions.json": "{}\n",
        "sub/.vscode/settings.json": "{}\n",
        "sub/node_modules/pkg/index.js": "x\n",
        "sub/dist/bundle.js": "x\n",
        # segredo DENTRO de pasta podada e FORA dela
        "sub/node_modules/pkg/.env": _SEGREDO,
        "sub/dist/.env": _SEGREDO,
        "sub/src/.env": _SEGREDO,
        ".env": _SEGREDO,
    }
    for rel, conteudo in arquivos.items():
        alvo = raiz / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")
    return raiz


def _entregues(raiz: Path, *, com_poda: bool) -> dict[str, str]:
    gate = SecurityGate(raiz, policy="strict")
    if not com_poda:
        gate.ignore.can_prune = lambda _d: False  # type: ignore[method-assign]
    return {w.rel_path: w.decision.verdict.value for w in iter_files(raiz, gate)}


def test_poda_nao_muda_o_que_o_gate_admite(tmp_path: Path) -> None:
    raiz = _arvore(tmp_path)
    com = _entregues(raiz, com_poda=True)
    sem = _entregues(raiz, com_poda=False)
    # `skip` é só ruído de pasta ignorada; o que importa é o que não é skip
    assert {p: v for p, v in com.items() if v != "skip"} == {
        p: v for p, v in sem.items() if v != "skip"
    }


def test_poda_efetivamente_nao_desce_nos_irmaos(tmp_path: Path) -> None:
    raiz = _arvore(tmp_path)
    com = _entregues(raiz, com_poda=True)
    sem = _entregues(raiz, com_poda=False)
    assert not any(p.startswith(("sub/node_modules/", "sub/dist/")) for p in com), sorted(com)
    assert any(p.startswith("sub/node_modules/") for p in sem)  # sem a poda, desce


def test_nenhum_segredo_chega_ao_indice(tmp_path: Path) -> None:
    raiz = _arvore(tmp_path)
    for p, v in _entregues(raiz, com_poda=True).items():
        if p.endswith(".env"):
            # `skip` (pasta ignorada) ou `block` (Gate): nunca admitido
            assert v in ("block", "skip"), (p, v)
    admitidos = [p for p, v in _entregues(raiz, com_poda=True).items() if v in ("allow", "redact")]
    for p in admitidos:
        assert "wJalrXUtnFEMI" not in (raiz / p).read_text(encoding="utf-8")
    # o que deve continuar entrando, entra: pasta reincluída por negação com caminho
    assert "sub/build/c.py" in admitidos
    assert "sub/keep/k.py" in admitidos
    assert "sub/.vscode/extensions.json" in admitidos


# ── RAGX-0133: arquivo ilegível nunca vira conteúdo novo, e o nome continua valendo ──
def _lista_sem_stat(root, follow_symlinks, visited, can_prune=None, on_unreadable_dir=None):  # type: ignore[no-untyped-def]
    import os

    for dp, _dn, fn in os.walk(root):
        for f in sorted(fn):
            yield Path(dp) / f


def test_arquivo_travado_nao_entrega_conteudo_e_nome_sensivel_continua_bloqueado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.walk as walk

    (tmp_path / ".env").write_text(_SEGREDO, encoding="utf-8")
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    original = Path.stat

    def negado(self: Path, *a: object, **k: object):  # type: ignore[no-untyped-def]
        if self.name in (".env", "app.py"):
            raise PermissionError(5, "acesso negado")
        return original(self, *a, **k)

    monkeypatch.setattr(walk, "_walk", _lista_sem_stat)
    monkeypatch.setattr(Path, "stat", negado)
    gate = SecurityGate(tmp_path, policy="strict")
    vistos = {w.rel_path: w for w in iter_files(tmp_path, gate)}

    # o nome é checado SEM abrir o arquivo: travado ou não, `.env` é bloqueado
    assert vistos[".env"].decision.verdict.value == "block"
    assert vistos[".env"].unreadable is False
    # o comum fica como "ilegível": sem conteúdo, nada para indexar
    assert vistos["app.py"].unreadable is True
    assert vistos["app.py"].decision.content is None


def test_env_ja_indexado_por_engano_e_travado_sai_do_indice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.walk as walk
    from ragx.config import load_config
    from ragx.core.models import DocKind, Document
    from ragx.indexing.pipeline import index_project
    from ragx.storage.db import open_db
    from ragx.storage.repositories import DocumentRepo

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(_SEGREDO, encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)  # cria o banco; o Gate bloqueia o .env
    with open_db(cfg.db_path) as conn:  # estado indevido: o .env entrou "por engano"
        DocumentRepo(conn).upsert(Document(
            id="docenv", rel_path=".env", doc_kind=DocKind.CONFIG, size_bytes=1, mtime_ns=1,
            content_hash="h", chunker_version="x", lang=None, title=None, redacted=False,
        ))
        conn.commit()

    original = Path.stat

    def negado(self: Path, *a: object, **k: object):  # type: ignore[no-untyped-def]
        if self.name == ".env":
            raise PermissionError(5, "acesso negado")
        return original(self, *a, **k)

    monkeypatch.setattr(walk, "_walk", _lista_sem_stat)
    monkeypatch.setattr(Path, "stat", negado)
    r = index_project(cfg)
    assert r.unreadable == 0
    with open_db(cfg.db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM documents WHERE rel_path = '.env'").fetchone()[0]
    assert n == 0, "o .env travado precisa sair do índice pelo nome"


# ── RAGX-0138: o diff de chunks não contorna o Gate ─────────────────────
def test_arquivo_que_ganha_segredo_e_removido_sem_sobrar_chunk_nem_vetor(tmp_path: Path) -> None:
    import sqlite3

    from ragx.config import load_config
    from ragx.indexing.pipeline import index_project

    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n',
        encoding="utf-8",
    )
    (tmp_path / "svc.py").write_text("def limpo():\n    return 1\n\n\ndef outro():\n    return 2\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    # o mesmo arquivo ganha um segredo em OUTRO trecho; os chunks limpos teriam ids estáveis
    (tmp_path / "svc.py").write_text(
        "def limpo():\n    return 1\n\n\ndef outro():\n    return 2\n\n\n"
        "def vaza():\n    aws_secret_access_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'\n",
        encoding="utf-8",
    )
    index_project(cfg)

    conn = sqlite3.connect(cfg.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE rel_path = 'svc.py'").fetchone()[0] == 0
        # o `ragx.toml` do projeto também é indexado: conta só o que era do svc.py
        assert conn.execute("SELECT COUNT(*) FROM chunks WHERE content LIKE '%def %'").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM embeddings e JOIN chunks c ON c.id = e.chunk_id "
            "WHERE c.content LIKE '%def %'"
        ).fetchone()[0] == 0
        for (conteudo,) in conn.execute("SELECT content FROM chunks"):
            assert "wJalrXUtnFEMI" not in conteudo
    finally:
        conn.close()
