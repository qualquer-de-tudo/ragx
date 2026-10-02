"""Conjunto-ouro derivado do git: a lógica pura (RAGX-0167)."""

from __future__ import annotations

import pytest

from ragx.gitinfo import Commit
from ragx.search.gold import clean_subject, derive_cases, render_yaml

pytestmark = pytest.mark.unit

INDEXADOS = {
    "src/a.py": "code",
    "src/b.py": "code",
    "docs/guia.md": "doc",
    "README.md": "doc",
    "config.toml": "config",
}


def _c(short: str, subject: str, *files: str, date: int = 0) -> Commit:
    return Commit(short, subject, tuple(files), date)


def test_prefixo_e_sufixo_do_assunto_saem() -> None:
    assert clean_subject("fix(watch): arquivo travado nao some do indice (RAGX-0133)") == "arquivo travado nao some do indice"
    assert clean_subject("feat: nova busca por palavra-chave") == "nova busca por palavra-chave"
    assert clean_subject("perf(context): MMR vetorizado (RAGX-0146, 0147)") == "MMR vetorizado"
    assert clean_subject("sem prefixo nenhum aqui") == "sem prefixo nenhum aqui"


def test_arquivo_inexistente_no_indice_sai_do_gabarito_e_ruido_tambem() -> None:
    r = derive_cases(
        [_c("a1", "fix: corrige o parser de markdown", "src/a.py", "src/apagado_depois.py", "CHANGELOG.md", "knowledge/x.json", "uv.lock")],
        INDEXADOS,
    )
    (caso,) = r.cases
    assert caso.relevant_paths == ("src/a.py",)
    assert r.funnel.arquivos_ruido == 3


def test_commit_grande_consulta_curta_e_release_sao_descartados_e_contados() -> None:
    muitos = tuple(f"src/m{i}.py" for i in range(9))
    indexados = {**INDEXADOS, **dict.fromkeys(muitos, "code")}
    commits = [
        _c("g1", "feat: reorganiza tudo de uma vez", *muitos),
        _c("c1", "fix: curto mas passa", "src/a.py"),  # 3 palavras: passa
        _c("c2", "fix: wip", "src/a.py"),  # 1 palavra
        _c("r1", "chore(release): v1.0.0", "src/a.py"),
        _c("s1", "docs: só muda o changelog hoje", "CHANGELOG.md"),
    ]
    r = derive_cases(commits, indexados, max_files=8)
    assert [c.commit for c in r.cases] == ["c1"]
    f = r.funnel
    assert (f.total, f.grande_demais, f.consulta_curta, f.release, f.sem_arquivo_indexado, f.aceitos) == (5, 1, 1, 1, 1, 1)


def test_kind_e_a_mistura_dos_documentos() -> None:
    r = derive_cases(
        [
            _c("k1", "fix: ajusta o código da busca", "src/a.py", "src/b.py"),
            _c("k2", "docs: escreve o guia de uso", "docs/guia.md", "README.md"),
            _c("k3", "feat: nova busca e sua documentação", "src/a.py", "docs/guia.md"),
        ],
        INDEXADOS,
    )
    assert {c.commit: c.kind for c in r.cases} == {"k1": "code", "k2": "doc", "k3": "mixed"}


def test_a_ordem_e_estavel_por_data_e_hash() -> None:
    commits = [
        _c("b2", "fix: segundo caso mesmo dia", "src/a.py", date=100),
        _c("a1", "fix: primeiro caso mesmo dia", "src/b.py", date=100),
        _c("z9", "fix: caso mais antigo de todos", "src/a.py", date=50),
    ]
    ordem = [c.commit for c in derive_cases(commits, INDEXADOS).cases]
    assert ordem == ["z9", "a1", "b2"]
    assert ordem == [c.commit for c in derive_cases(list(reversed(commits)), INDEXADOS).cases]


def test_o_yaml_e_deterministico_e_sem_autor_nem_data() -> None:
    r = derive_cases([_c("a1", "fix: corrige o parser de markdown", "src/a.py", date=123)], INDEXADOS)
    y1, y2 = render_yaml(r, "abc1234"), render_yaml(r, "abc1234")
    assert y1 == y2
    assert "HEAD de origem: abc1234" in y1 and "123" not in y1.replace("abc1234", "")
    assert "autor" not in y1.lower() and "@" not in y1
    assert "commit: a1" in y1 and "kind: code" in y1
