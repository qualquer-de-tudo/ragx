"""Gera todos os artefatos instaláveis, num comando.

    python scripts/release.py

Produz em `release/`:

    ragx-<versão>-py3-none-any.whl      pacote Python (Windows, Linux, macOS)
    ragx-<versão>.tar.gz                fonte
    ragx-knowledge-explorer-<v>.vsix    extensão do VS Code
    install.sh / install.ps1            instaladores, copiados
    SHA256SUMS.txt                      para conferir o download

Por que Python e não Makefile: o RAGX já exige Python, e um Makefile não roda
no Windows sem mais uma dependência. Este script funciona nos três sistemas
com o que já está instalado.
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

# O console do Windows ainda usa cp1252 por padrão, e qualquer caractere fora
# dele derruba o script com UnicodeEncodeError — no meio de um build que deu
# certo. O RAGX faz o mesmo em `ragx.cli.__init__`.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        with contextlib.suppress(ValueError, OSError):
            _fluxo.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "release"
PLUGIN = RAIZ / "vscode-plugin"


def resolver(programa: str) -> str:
    """Caminho absoluto do executável.

    No Windows, `subprocess` não procura `.cmd`/`.exe` sozinho quando
    `shell=False` — `npm` e `npx` são `.cmd`, e `uv` pode estar num diretório
    que só o shell conhece. Sem isto, o erro é um `FileNotFoundError` cru que
    não diz qual programa faltou.
    """
    caminho = shutil.which(programa)
    if caminho:
        return caminho
    if sys.platform == "win32":
        for sufixo in (".cmd", ".exe", ".bat"):
            caminho = shutil.which(programa + sufixo)
            if caminho:
                return caminho
    print(f"\n[X] `{programa}` nao encontrado no PATH.", file=sys.stderr)
    raise SystemExit(1)


def executar(comando: list[str], cwd: Path, nome: str) -> None:
    print(f"  -> {nome}")
    comando = [resolver(comando[0]), *comando[1:]]
    r = subprocess.run(
        comando, cwd=cwd, capture_output=True, text=True, shell=False,
        encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        # A saída inteira, não um resumo: quem está publicando precisa do erro
        # real, não de "falhou".
        print(f"\n[X] {nome} falhou (código {r.returncode})\n", file=sys.stderr)
        print((r.stderr or r.stdout)[-3000:], file=sys.stderr)
        raise SystemExit(1)


def versao_ragx() -> str:
    dados = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    return str(dados["project"]["version"])


def versao_plugin() -> str:
    import json

    dados = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    return str(dados["version"])


def main() -> int:
    v_ragx = versao_ragx()
    v_plugin = versao_plugin()
    print(f"\nRAGX {v_ragx} · plugin {v_plugin}\n")

    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)

    # ── pacote Python ───────────────────────────────────────────────────
    print("pacote Python")
    dist = RAIZ / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    executar(["uv", "build"], RAIZ, "uv build")
    for arquivo in sorted(dist.glob(f"ragx-{v_ragx}*")):
        shutil.copy2(arquivo, DESTINO / arquivo.name)
        print(f"     {arquivo.name}")

    # ── extensão ────────────────────────────────────────────────────────
    print("\nextensão do VS Code")
    if not (PLUGIN / "node_modules").is_dir():
        executar(["npm", "install", "--no-audit", "--no-fund"], PLUGIN, "npm install")
    executar(["npm", "run", "build"], PLUGIN, "build")
    executar(["npm", "test"], PLUGIN, "testes")
    executar(
        ["npx", "vsce", "package", "--no-dependencies", "--allow-missing-repository"],
        PLUGIN,
        "vsce package",
    )
    for arquivo in sorted(PLUGIN.glob("*.vsix")):
        shutil.copy2(arquivo, DESTINO / arquivo.name)
        print(f"     {arquivo.name}")

    # ── instaladores ────────────────────────────────────────────────────
    print("\ninstaladores")
    for nome in ("install.sh", "install.ps1"):
        origem = RAIZ / "install" / nome
        # Cópia byte a byte: o `.ps1` tem BOM e o `.sh` precisa de LF. Reescrever
        # texto aqui desfaria as duas coisas em silêncio.
        shutil.copy2(origem, DESTINO / nome)
        print(f"     {nome}")

    # ── somas ───────────────────────────────────────────────────────────
    linhas = []
    for arquivo in sorted(DESTINO.iterdir()):
        if arquivo.name == "SHA256SUMS.txt" or not arquivo.is_file():
            continue
        h = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        linhas.append(f"{h}  {arquivo.name}")
    (DESTINO / "SHA256SUMS.txt").write_text(
        "\n".join(linhas) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"\n{len(linhas)} artefato(s) em {DESTINO}\n")
    for linha in linhas:
        print(f"  {linha.split('  ')[1]}")

    print(
        f"""
Para publicar como release no GitHub:

  gh release create v{v_ragx} release/* \\
     --title "RAGX {v_ragx}" \\
     --notes-file CHANGELOG.md

Para instalar localmente agora:

  uv tool install --python 3.12 release/ragx-{v_ragx}-py3-none-any.whl
  code --install-extension release/ragx-knowledge-explorer-{v_plugin}.vsix
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
