"""`index_paths`: reindexar só os arquivos tocados, sem varrer a árvore nem chamar o git.

Reindexar um arquivo editado custava 0,7 s (varredura, gate, git e embedder) mesmo depois de
a poda e o embedder preguiçoso terem sido consertados; o que se quer, para uma edição
feita no meio de uma sessão do Claude, é o custo do arquivo e nada mais.

Ver `task/fase-19-velocidade-e-frescor/RAGX-0140-*.md`.
"""

from __future__ import annotations

import random
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import IndexBusyError
from ragx.indexing import lock
from ragx.indexing.pipeline import index_paths, index_project

pytestmark = pytest.mark.integration

TOML = (
    '[project]\nname = "t"\nid = "t"\n\n'
    '[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n'
)


def _escrever(raiz: Path, arquivos: dict[str, str]) -> None:
    for rel, texto in arquivos.items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    raiz = tmp_path / "p"
    _escrever(raiz, {
        "ragx.toml": TOML,
        ".gitignore": "ignorada/\n*.log\n",
        "src/a.py": "def a():\n    return 1\n",
        "src/b.py": "def b():\n    return 2\n",
        "docs/d.md": "# D\n\n## S\n\ntexto sobre sessoes\n",
        "ignorada/x.py": "def x():\n    return 0\n",
    })
    index_project(load_config(raiz))
    return raiz


def _docs(raiz: Path) -> dict[str, str]:
    conn = sqlite3.connect(load_config(raiz).db_path)
    try:
        return dict(conn.execute("SELECT rel_path, content_hash FROM documents"))
    finally:
        conn.close()


def _chunks(raiz: Path) -> set[tuple[str, str]]:
    conn = sqlite3.connect(load_config(raiz).db_path)
    try:
        return set(conn.execute(
            "SELECT d.rel_path, c.id FROM chunks c JOIN documents d ON d.id = c.document_id"))
    finally:
        conn.close()


def test_arquivo_novo_alterado_e_apagado(proj: Path) -> None:
    cfg = load_config(proj)
    _escrever(proj, {"src/novo.py": "def novo():\n    return 3\n"})
    (proj / "src" / "a.py").write_text("def a():\n    return 100\n", encoding="utf-8")
    (proj / "src" / "b.py").unlink()

    r = index_paths(cfg, ["src/novo.py", "src/a.py", "src/b.py"])

    docs = _docs(proj)
    assert "src/novo.py" in docs and "src/b.py" not in docs
    assert r.new_documents == 1 and r.modified_documents == 1 and r.stats.removed == 1
    assert "return 100" in sqlite3.connect(cfg.db_path).execute(
        "SELECT group_concat(content) FROM chunks c JOIN documents d ON d.id=c.document_id "
        "WHERE d.rel_path='src/a.py'").fetchone()[0]


def test_renomeado_sao_dois_caminhos_um_some_o_outro_entra(proj: Path) -> None:
    cfg = load_config(proj)
    (proj / "src" / "a.py").rename(proj / "src" / "renomeado.py")
    index_paths(cfg, ["src/a.py", "src/renomeado.py"])
    docs = _docs(proj)
    assert "src/a.py" not in docs and "src/renomeado.py" in docs


def test_arquivo_travado_permanece_no_indice(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    original = Path.read_bytes

    def trava(self: Path) -> bytes:
        if self.name == "a.py":
            raise PermissionError(32, "violação de compartilhamento")
        return original(self)

    (proj / "src" / "a.py").write_text("def a():\n    return 7\n", encoding="utf-8")
    monkeypatch.setattr(Path, "read_bytes", trava)
    r = index_paths(cfg, ["src/a.py"])
    assert r.unreadable == 1 and r.stats.removed == 0
    assert "src/a.py" in _docs(proj)


def test_caminhos_com_barra_invertida_do_windows_sao_aceitos(proj: Path) -> None:
    cfg = load_config(proj)
    (proj / "src" / "a.py").write_text("def a():\n    return 9\n", encoding="utf-8")
    r = index_paths(cfg, ["src\\a.py", ".\\src/a.py"])
    assert r.modified_documents == 1  # os dois são o mesmo arquivo


def test_lote_acima_do_teto_e_arquivo_de_regra_caem_no_incremental(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.indexing.pipeline as pipe

    chamadas: list[str] = []
    original = pipe.index_project

    def espia(cfg, *a, **k):  # type: ignore[no-untyped-def]
        chamadas.append(k.get("source", "?"))
        return original(cfg, *a, **k)

    monkeypatch.setattr(pipe, "index_project", espia)
    cfg = load_config(proj)
    cfg.watch.max_batch = 2
    index_paths(cfg, ["src/a.py", "src/b.py", "docs/d.md"])  # 3 > 2
    assert len(chamadas) == 1
    cfg.watch.max_batch = 500
    index_paths(cfg, [".gitignore"])  # arquivo de regra muda o que é visitado
    index_paths(cfg, ["ragx.toml"])
    assert len(chamadas) == 3
    index_paths(cfg, ["src/a.py"])  # o caso comum NÃO cai no incremental
    assert len(chamadas) == 3


def test_trava_ocupada_devolve_busy_e_deixa_pedido_pendente(proj: Path) -> None:
    cfg = load_config(proj)
    assert lock.try_acquire(cfg.state_dir, "index", "outro")
    try:
        with pytest.raises(IndexBusyError):
            index_paths(cfg, ["src/a.py"])
        assert lock.is_pending(cfg.state_dir)
    finally:
        lock.release(cfg.state_dir)
        lock.take_pending(cfg.state_dir)


def test_nao_percorre_a_arvore_nem_chama_o_git(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ragx.gitinfo as gi
    import ragx.walk as walk

    cfg = load_config(proj)
    # o pipeline pergunta uma vez por `hooks_dir` ao escrever o status; o resto não pode tocar no git
    chamadas: dict[str, int] = {"walk": 0, "git": 0}

    def varre(*a, **k):  # type: ignore[no-untyped-def]
        chamadas["walk"] += 1
        raise AssertionError("percorreu a árvore")

    monkeypatch.setattr(walk, "_walk", varre)
    original = gi.run_quiet

    def espia(cmd, *a, **k):  # type: ignore[no-untyped-def]
        chamadas["git"] += 1
        return original(cmd, *a, **k)

    monkeypatch.setattr(gi, "run_quiet", espia)
    (proj / "src" / "a.py").write_text("def a():\n    return 55\n", encoding="utf-8")
    index_paths(cfg, ["src/a.py"])
    assert chamadas == {"walk": 0, "git": 0}


def test_registra_uma_run_mode_paths_e_nao_vira_a_ultima_run_completa(proj: Path) -> None:
    import subprocess

    from ragx.indexing import status_file

    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=proj).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=proj, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=proj, check=True)
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-qm", "c1"], cwd=proj, check=True)
    cfg = load_config(proj)
    index_project(cfg)  # agora a última run COMPLETA tem branch e commit
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    antes = status_file._last_finished(conn)
    conn.close()
    (proj / "src" / "a.py").write_text("def a():\n    return 66\n", encoding="utf-8")
    index_paths(cfg, ["src/a.py"])
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    try:
        ultima = conn.execute("SELECT * FROM index_runs ORDER BY id DESC LIMIT 1").fetchone()
        assert ultima["mode"] == "paths" and ultima["finished_at"] and ultima["git_dirty"] == 1
        assert ultima["git_branch"] == "main" and len(ultima["git_commit"]) == 40  # copiados, sem git
        depois = status_file._last_finished(conn)
    finally:
        conn.close()
    # uma rodada parcial não pode ser tomada por "a última indexação que refletiu a árvore"
    assert antes is not None and depois is not None and depois["id"] == antes["id"]


# ── equivalência com index_project ──────────────────────────────────────
def _sortear(rng: random.Random, raiz: Path) -> list[str]:
    candidatos = {
        "src/a.py": lambda: f"def a():\n    return {rng.randint(0, 9999)}\n",
        "src/b.py": lambda: f"class B:\n    def m(self):\n        return {rng.randint(0, 9999)}\n",
        "docs/d.md": lambda: f"# D\n\n## S\n\nsessao numero {rng.randint(0, 9999)}\n",
        "src/novo1.py": lambda: f"def n1():\n    return {rng.randint(0, 9999)}\n",
        "src/novo2.py": lambda: f"X = {rng.randint(0, 9999)}\n",
        "ignorada/y.py": lambda: "def y():\n    return 1\n",  # pasta ignorada: não pode entrar
        "debug.log": lambda: "log ignorado\n",
        ".env": lambda: "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n",
        "grande.txt": lambda: "x" * 2_000_000,  # maior que o teto de tamanho
        "bin.dat": lambda: "a\x00b",
    }
    tocados: list[str] = []
    for rel, gera in candidatos.items():
        r = rng.random()
        if r < 0.45:
            (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
            (raiz / rel).write_text(gera(), encoding="utf-8", newline="\n")
            tocados.append(rel)
        elif r < 0.55 and (raiz / rel).exists():
            (raiz / rel).unlink()
            tocados.append(rel)
    return tocados


def test_equivale_a_index_project_em_rodadas_sorteadas(tmp_path: Path, proj: Path) -> None:
    rng = random.Random(1405)
    por_caminho = proj
    por_projeto = tmp_path / "copia"
    shutil.copytree(proj, por_projeto)
    cfg_a = load_config(por_caminho)
    cfg_b = load_config(por_projeto)
    for rodada in range(12):
        # as MESMAS mudanças nas duas árvores
        rng_estado = rng.getstate()
        tocados = _sortear(rng, por_caminho)
        rng.setstate(rng_estado)
        _sortear(rng, por_projeto)
        index_paths(cfg_a, tocados)
        index_project(cfg_b)
        assert _docs(por_caminho) == _docs(por_projeto), f"documentos divergiram na rodada {rodada}"
        assert _chunks(por_caminho) == _chunks(por_projeto), f"chunks divergiram na rodada {rodada}"


def test_um_arquivo_alterado_custa_bem_menos_que_a_varredura(proj: Path) -> None:
    cfg = load_config(proj)
    (proj / "src" / "a.py").write_text("def a():\n    return 4242\n", encoding="utf-8")
    index_paths(cfg, ["src/a.py"])  # aquece o que for preciso (embedder, caches)
    (proj / "src" / "a.py").write_text("def a():\n    return 4243\n", encoding="utf-8")
    t = time.perf_counter()
    index_paths(cfg, ["src/a.py"])
    ms = (time.perf_counter() - t) * 1000
    assert ms < 400, f"index_paths levou {ms:.0f} ms (meta: <= 400 ms)"
