"""Prepara uma versão nova do RAGX: número, CHANGELOG e tag, num comando.

    uv run python scripts/versao.py 1.0.0-beta.4          # só edita os arquivos
    uv run python scripts/versao.py 1.0.0-beta.4 --tag    # edita, commita e cria a tag

Depois, o push da tag dispara o `release.yml` no GitHub, que testa, gera o
wheel, a extensão e o instalador do painel (`RAGX-Painel-Setup-<versão>.exe`) e
publica a release:

    git push origin main v1.0.0-beta.4

A versão mora em cinco arquivos, e a release confere que a tag bate com eles.
Editar à mão é como o painel ficou em `0.0.0` enquanto o produto já estava na
beta 3 — e o instalador sairia com o número errado no nome.

Commit comum não dispara nada além do CI: só a tag gera instalador.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        with contextlib.suppress(ValueError, OSError):
            _fluxo.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent

#: SemVer: o npm (painel e extensão) recusa qualquer outra coisa.
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?$")

NAO_LANCADO = "## [Não lançado]"


class RecusaError(Exception):
    """Algo impede a versão; nada foi gravado."""


def pep440(versao: str) -> str:
    """`1.0.0-beta.4` como o `uv.lock` grava (`1.0.0b4`)."""
    try:
        from packaging.version import Version

        return str(Version(versao))
    except ImportError:  # pragma: no cover - packaging vem com o ambiente de dev
        m = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.?(\d+))?", versao)
        if not m:
            raise RecusaError(f"não sei normalizar {versao} para PEP 440") from None
        base, pre, n = m.groups()
        return base + ({"alpha": "a", "beta": "b", "rc": "rc"}[pre] + n if pre else "")


def changelog(texto: str, versao: str, dia: date) -> str:
    """Abre a seção da versão com o que estava em `[Não lançado]`."""
    if f"## [{versao}]" in texto:
        raise RecusaError(f"o CHANGELOG já tem a seção [{versao}]")
    inicio = texto.find(NAO_LANCADO)
    if inicio < 0:
        raise RecusaError(f"o CHANGELOG não tem a seção {NAO_LANCADO!r}")
    corpo_ini = inicio + len(NAO_LANCADO)
    proxima = re.search(r"^## \[", texto[corpo_ini:], re.M)
    corpo_fim = corpo_ini + proxima.start() if proxima else len(texto)
    corpo = texto[corpo_ini:corpo_fim].strip("\n")
    # Só cabeçalhos (### Adicionado) sem item embaixo não é mudança nenhuma.
    if not re.search(r"^\s*[-*] ", corpo, re.M):
        raise RecusaError("a seção [Não lançado] está vazia: não há o que lançar")
    novo = f"{NAO_LANCADO}\n\n## [{versao}] — {dia.isoformat()}\n\n{corpo}\n\n"
    return texto[:inicio] + novo + texto[corpo_fim:]


def pyproject(texto: str, versao: str) -> str:
    novo, n = re.subn(r'^version = "[^"]*"', f'version = "{versao}"', texto, count=1, flags=re.M)
    if n != 1:
        raise RecusaError("não achei `version = ...` no pyproject.toml")
    return novo


def uv_lock(texto: str, versao: str) -> str:
    novo, n = re.subn(
        r'(^name = "ragx"\nversion = )"[^"]*"', rf'\g<1>"{pep440(versao)}"', texto, count=1, flags=re.M
    )
    if n != 1:
        raise RecusaError("não achei o pacote `ragx` no uv.lock")
    return novo


def package_json(texto: str, versao: str) -> str:
    """Troca só a linha da versão, sem reserializar o arquivo.

    A primeira versão deste script regravava o JSON inteiro, e o
    `vscode-plugin/package.json`, com outra formatação, saía com 175 linhas
    mudadas para uma versão nova. Aqui a troca é textual, e o resultado é
    conferido: tem de ser o JSON original com só as versões diferentes.
    """
    esperado = json.loads(texto)
    esperado["version"] = versao
    # package-lock.json repete a versão do próprio pacote em `packages[""]`,
    # que é sempre a segunda ocorrência de "version" no arquivo.
    raiz = (esperado.get("packages") or {}).get("")
    trocas = 1
    if isinstance(raiz, dict) and "version" in raiz:
        raiz["version"] = versao
        trocas = 2
    novo, n = re.subn(r'("version"\s*:\s*)"[^"]*"', rf'\g<1>"{versao}"', texto, count=trocas)
    if n != trocas or json.loads(novo) != esperado:
        raise RecusaError("não consegui trocar só a versão no package.json; edite à mão")
    return novo


ARQUIVOS = {
    "pyproject.toml": pyproject,
    "uv.lock": uv_lock,
    "src/app/package.json": package_json,
    "src/app/package-lock.json": package_json,
    "vscode-plugin/package.json": package_json,
    "vscode-plugin/package-lock.json": package_json,
}


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RecusaError(f"git {' '.join(args)} falhou: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("versao", help="SemVer sem o v, ex.: 1.0.0-beta.4")
    ap.add_argument("--tag", action="store_true", help="commita as mudanças e cria a tag v<versão>")
    args = ap.parse_args(argv)
    versao = args.versao.removeprefix("v")

    try:
        if not SEMVER.match(versao):
            raise RecusaError(f"{versao!r} não é SemVer (ex.: 1.0.0, 1.0.0-beta.4)")
        tag = f"v{versao}"
        if args.tag:
            if _git("status", "--porcelain").strip():
                raise RecusaError("há mudanças não commitadas; commite ou guarde antes de lançar")
            if _git("tag", "--list", tag).strip():
                raise RecusaError(f"a tag {tag} já existe")

        # Calcula tudo antes de gravar qualquer coisa: uma recusa no meio não
        # pode deixar metade dos arquivos na versão nova.
        novos: dict[Path, str] = {}
        cl = RAIZ / "CHANGELOG.md"
        novos[cl] = changelog(cl.read_text(encoding="utf-8"), versao, date.today())
        for rel, ajustar in ARQUIVOS.items():
            caminho = RAIZ / rel
            novos[caminho] = ajustar(caminho.read_text(encoding="utf-8"), versao)
    except RecusaError as exc:
        print(f"[X] {exc}", file=sys.stderr)
        return 1

    for caminho, texto in novos.items():
        caminho.write_text(texto, encoding="utf-8", newline="\n")
        print(f"  {caminho.relative_to(RAIZ).as_posix()}")

    if not args.tag:
        print(f"\nVersão {versao} aplicada. Revise e rode de novo com --tag, ou commite e crie a tag {tag} à mão.")
        return 0

    try:
        _git("add", *(str(p.relative_to(RAIZ)) for p in novos))
        _git("commit", "-m", f"chore(release): {tag}")
        _git("tag", "-a", tag, "-m", f"RAGX {versao}")
        ramo = _git("branch", "--show-current").strip() or "main"
    except RecusaError as exc:
        print(f"[X] {exc}", file=sys.stderr)
        return 1
    print(f"\nCommit e tag {tag} criados. Para gerar o instalador e publicar a release:\n")
    print(f"  git push origin {ramo} {tag}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
