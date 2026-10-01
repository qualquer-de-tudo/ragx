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
