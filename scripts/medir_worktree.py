"""Mede o custo do índice em worktree e em troca de branch (RAGX-0170), num clone local TEMPORARIO.

    uv run python scripts/medir_worktree.py [--recuar 5] [--sem-hook]

Nunca toca o repositório real: `git clone --local` do diretório atual para uma pasta temporária, com HOME
redirecionado (nada vai para o hub nem para `~/.ragx` de verdade) e o cache de modelos do fastembed apontado para
o do repositório (só leitura: sem download).

Mede, com `ragx index --json` em cada raiz:
1. o índice a frio do clone;
2. o primeiro índice de um `git worktree add` novo (sem semente, sem cache compartilhado);
3. a troca de branch no mesmo worktree (ida e volta);
4. se o `post-checkout` disparado por `git worktree add` indexa a raiz PRINCIPAL em vez da do worktree novo.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def sh(*args: str, cwd: Path, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=check
    )


def indexar(raiz: Path, env: dict[str, str], rotulo: str) -> dict:
    t0 = time.perf_counter()
    r = sh(sys.executable, "-m", "ragx.cli.main", "index", "--json", cwd=raiz, env=env, check=False)
    decorrido = time.perf_counter() - t0
    try:
        dados = json.loads(r.stdout[r.stdout.index("{") :])
    except (ValueError, json.JSONDecodeError):
        print(f"{rotulo}: falhou: {r.stdout[-300:]} {r.stderr[-300:]}")
        return {}
    print(
        f"{rotulo}: {decorrido:6.1f} s | documentos indexados {dados.get('documents_indexed')}, chunks {dados.get('chunks')}, "
        f"embutidos {dados.get('embedded')}, unchanged {dados.get('unchanged')}, jobs {dados.get('parallel_jobs')}"
    )
    dados["_segundos"] = decorrido
    return dados


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recuar", type=int, default=5, help="o worktree novo nasce em HEAD~N")
    ap.add_argument("--sem-hook", action="store_true")
    args = ap.parse_args()
    origem = Path.cwd()
    modelos = origem / ".ragx" / "cache" / "models"

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        casa = base / "home"
        casa.mkdir()
        env = dict(os.environ)
        env.update(
            HOME=str(casa), USERPROFILE=str(casa), RAGX_HOME=str(casa),
            RAGX_EMBEDDING_MODEL_CACHE_DIR=str(modelos),
        )
        r = base / "r"
        sh("git", "clone", "--local", "-q", str(origem), str(r), cwd=base)
        sh("git", "config", "user.email", "t@t", cwd=r)
        sh("git", "config", "user.name", "t", cwd=r)
        print(f"clone em {r}; HEAD {sh('git', 'rev-parse', '--short', 'HEAD', cwd=r).stdout.strip()}")

        frio = indexar(r, env, "1. índice a frio do clone               ")

        w1 = base / "w1"
        sh("git", "worktree", "add", "-q", str(w1), f"HEAD~{args.recuar}", cwd=r)
        w = indexar(w1, env, f"2. 1º índice do worktree novo (HEAD~{args.recuar})   ")
        indexar(w1, env, "   rodada seguinte no worktree, sem mudança")
        if frio and w:
            print(f"   worktree novo / índice a frio do clone = {w['_segundos'] / frio['_segundos']:.0%}")

        sh("git", "switch", "-q", "-c", "outra", "HEAD~20", cwd=r)
        indexar(r, env, "3a. troca de branch (HEAD~20) no clone       ")
        sh("git", "switch", "-q", "-", cwd=r)
        indexar(r, env, "3b. volta para a branch original              ")

        if not args.sem_hook:
            sh(sys.executable, "-m", "ragx.cli.main", "hooks", "install", cwd=r, env=env, check=False)
            w2 = base / "w2"
            antes = (r / ".ragx" / "status.json").stat().st_mtime_ns if (r / ".ragx" / "status.json").exists() else 0
            sh("git", "worktree", "add", "-q", str(w2), "HEAD~3", cwd=r, env=env)
            time.sleep(15)  # o hook dispara a indexação destacada
            depois = (r / ".ragx" / "status.json").stat().st_mtime_ns if (r / ".ragx" / "status.json").exists() else 0
            print(
                "4. post-checkout do `git worktree add`: índice do worktree novo criado? "
                f"{(w2 / '.ragx' / 'knowledge.db').exists()}; índice da raiz PRINCIPAL reindexado? {depois != antes}"
            )
        os.chdir(origem)
        shutil.rmtree(base / "w1", ignore_errors=True)


if __name__ == "__main__":
    main()
