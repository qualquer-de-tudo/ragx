"""`refresh` é incremental de verdade, e `sync` só faz o que precisa.

A descrição, o playbook e o hint diziam que `refresh` era "barato quando nada
mudou", mas ele rodava `sync` completo: reidratava o projeto inteiro só para um
relatório descartado (13,7 s), regravava todo `knowledge/` e levava de 26 s (em
processo) a 91 s (via MCP sob carga). Medir `refresh` chegou a sujar 155 arquivos
rastreados e a criar 422.

Ver `task/fase-19-velocidade-e-frescor/RAGX-0131-*.md`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.mcp.operations import WriteAPI
from ragx.storage.db import open_db
from ragx.sync import serialize
from ragx.sync import service as sync_service

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Servico de autenticacao."""

    def login(self, credentials):
        return credentials
'''

DOC = "# Autenticacao\n\n## Fluxo\n\nO sistema valida a sessao no provedor.\n"


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "auth.py").write_text(AUTH, encoding="utf-8")
    (tmp_path / "doc.md").write_text(DOC, encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    rebuild(cfg)
    sync_service.sync(cfg)  # cria knowledge/ e fixa o estado "em dia"
    return tmp_path


#: Regravados a cada `sync` com `generated_at` novo, hoje: é a RAGX-0148. Ficam de
#: fora da comparação de "o serialize não mexeu em nada".
_COM_TIMESTAMP = {"knowledge/dictionary.json", "knowledge/federation/service.json"}


def _arvore(raiz: Path, sem_timestamp: bool = False) -> dict[str, str]:
    """Hash dos BYTES de cada arquivo de knowledge/ (no Windows, texto mentiria)."""
    out = {
        p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((raiz / "knowledge").rglob("*")) if p.is_file()
    }
    if sem_timestamp:
        out = {k: v for k, v in out.items() if k not in _COM_TIMESTAMP}
    return out


class _Espiao:
    """Conta chamadas a funções do caminho de consolidação."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.chamadas: dict[str, int] = {}
        for nome, alvo, attr in (
            ("sync", "ragx.sync.service", "sync"),
            ("rehydrate", "ragx.sync.rehydrate", "rehydrate"),
            ("serialize", "ragx.sync.serialize", "serialize"),
            ("rebuild", "ragx.graph.service", "rebuild"),
        ):
            self._envolve(monkeypatch, nome, alvo, attr)

    def _envolve(self, monkeypatch: pytest.MonkeyPatch, nome: str, alvo: str, attr: str) -> None:
        import importlib

        modulo = importlib.import_module(alvo)
        original = getattr(modulo, attr)

        def espia(*a: object, **k: object):  # type: ignore[no-untyped-def]
            self.chamadas[nome] = self.chamadas.get(nome, 0) + 1
            return original(*a, **k)

        monkeypatch.setattr(modulo, attr, espia)


def test_refresh_nao_consolida_nada_e_nao_toca_em_knowledge(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config(proj)
    antes = _arvore(proj)
    espiao = _Espiao(monkeypatch)
    (proj / "doc.md").write_text(DOC + "\nParagrafo novo sobre tokens.\n", encoding="utf-8")

    r = WriteAPI(cfg, True).refresh()

    assert r["ok"], r
    assert r["data"]["indexed"] >= 1
    assert r["data"]["consolidated"] is False
    assert espiao.chamadas == {}, f"refresh consolidou: {espiao.chamadas}"
    assert _arvore(proj) == antes, "refresh alterou knowledge/"


def test_refresh_sem_mudanca_nao_toca_em_knowledge(proj: Path) -> None:
    antes = _arvore(proj)
    r = WriteAPI(load_config(proj), True).refresh()
    assert r["ok"] and r["data"]["indexed"] == 0
    assert _arvore(proj) == antes


def test_sync_padrao_nao_reidrata_e_com_flag_reidrata(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config(proj)
    espiao = _Espiao(monkeypatch)
    sync_service.sync(cfg)
    assert espiao.chamadas.get("rehydrate", 0) == 0

    r = sync_service.sync(cfg, rehydrate=True)
    assert espiao.chamadas.get("rehydrate", 0) == 1
    assert r.rehydrate.total > 0


def test_segundo_sync_sem_mudanca_nao_serializa_e_knowledge_fica_igual(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config(proj)
    sync_service.sync(cfg)  # grava o token do estado atual
    antes = _arvore(proj, sem_timestamp=True)
    espiao = _Espiao(monkeypatch)
    sync_service.sync(cfg)
    assert espiao.chamadas.get("serialize", 0) == 0
    assert _arvore(proj, sem_timestamp=True) == antes


def test_depois_de_uma_edicao_o_sync_serializa(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    sync_service.sync(cfg)
    (proj / "auth.py").write_text(AUTH + "\n    def logout(self):\n        return None\n",
                                  encoding="utf-8")
    espiao = _Espiao(monkeypatch)
    sync_service.sync(cfg)
    assert espiao.chamadas.get("serialize", 0) == 1


def test_full_sempre_serializa(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    sync_service.sync(cfg)
    espiao = _Espiao(monkeypatch)
    sync_service.sync(cfg, full=True)
    assert espiao.chamadas.get("serialize", 0) == 1


def test_um_unico_sync_ja_reflete_o_grafo_novo_em_knowledge(proj: Path) -> None:
    """O grafo era refeito DEPOIS de `serialize`: `knowledge/entities` saía um `sync` atrás."""
    cfg = load_config(proj)
    (proj / "auth.py").write_text(
        AUTH + "\n\nclass NovaClasseDoGrafo:\n    def metodo(self):\n        return 1\n",
        encoding="utf-8",
    )
    sync_service.sync(cfg)

    no_arquivo: set[str] = set()
    for f in (proj / "knowledge" / "entities").glob("*.json"):
        no_arquivo |= {e["name"] for e in json.loads(f.read_text(encoding="utf-8"))}
    with open_db(cfg.db_path, read_only=True) as conn:
        no_banco = {r["name"] for r in conn.execute("SELECT name FROM entities")}
    assert "NovaClasseDoGrafo" in no_banco
    assert no_arquivo == no_banco


def test_segredo_novo_nao_chega_ao_banco_nem_a_knowledge_pelo_refresh(proj: Path) -> None:
    segredo = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    (proj / ".env").write_text(f"AWS_SECRET_ACCESS_KEY={segredo}\n", encoding="utf-8")
    (proj / "novo.py").write_text(f"aws_secret_access_key = '{segredo}'\n", encoding="utf-8")
    cfg = load_config(proj)
    WriteAPI(cfg, True).refresh()
    sync_service.sync(cfg)
    with open_db(cfg.db_path, read_only=True) as conn:
        for (conteudo,) in conn.execute("SELECT content FROM chunks"):
            assert segredo not in conteudo
    for p in (proj / "knowledge").rglob("*"):
        if p.is_file():
            assert segredo not in p.read_text(encoding="utf-8", errors="replace"), p
    assert serialize.read_manifest(cfg, "knowledge") is not None
