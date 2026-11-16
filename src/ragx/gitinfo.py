"""Metadados do git de uma raiz de projeto.

Só metadados: branch, commit, estado do working tree, pasta de hooks. Nada
aqui lê conteúdo de arquivo do projeto; quem lê conteúdo é o pipeline, depois
do Security Gate (docs/02-seguranca.md).

Nenhuma função lança: sem git instalado, fora de repositório ou com timeout,
a resposta é `None`. Um índice que não sabe a branch continua funcionando.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ragx.procs import run_quiet

_TIMEOUT_S = 5


@dataclass(frozen=True)
class GitState:
    branch: str | None  # None com HEAD destacado
    commit: str
    dirty: bool


def git(root: Path, *args: str, timeout: float = _TIMEOUT_S) -> str | None:
    try:
        out = run_quiet(
            # `--no-optional-locks`: `git status` por padrão refresca e grava
            # `.git/index`. Rodado em background (hook, watcher) ao mesmo
            # tempo que um `git rebase`/`checkout`/`commit` do usuário, essa
            # escrita pode colidir com a dele — exatamente o cenário que
            # dispara os hooks que chamam esta função. Todos os subcomandos
            # usados aqui (rev-parse, symbolic-ref, status, rev-list) se
            # comportam identicamente com a flag; sem ela, nenhum precisa da
            # trava opcional.
            ["git", "--no-optional-locks", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.rstrip("\n")


def read_state(root: Path) -> GitState | None:
    """Commit, branch e se o working tree está sujo, numa chamada só.

    `git status --porcelain=v2 --branch` traz tudo: `# branch.oid` (o commit, ou
    `(initial)` num repositório sem commit), `# branch.head` (a branch, ou
    `(detached)`) e, depois dos cabeçalhos, uma linha por arquivo alterado. Eram
    três processos (`rev-parse`, `symbolic-ref`, `status`) a cada indexação.
    """
    out = git(root, "status", "--porcelain=v2", "--branch", "--untracked-files=normal", "--", ".")
    if out is None:
        return None
    commit = ""
    branch: str | None = None
    dirty = False
    for linha in out.splitlines():
        if linha.startswith("# branch.oid "):
            commit = linha[len("# branch.oid "):]
        elif linha.startswith("# branch.head "):
            nome = linha[len("# branch.head "):]
            branch = None if nome == "(detached)" else nome
        elif linha and not linha.startswith("#"):
            dirty = True
    if not commit or commit == "(initial)":
        return None
    return GitState(branch=branch, commit=commit, dirty=dirty)


_HOOKS_DIR: dict[str, Path] = {}


def hooks_dir(root: Path) -> Path | None:
    """Pasta de hooks do repositório, respeitando `core.hooksPath`.

    Memoizado por processo e por raiz: `write_status` pergunta duas vezes por
    indexação. `None` nunca é guardado, para que um `git init` na mesma sessão
    seja visto; `hooks_dir_cache_clear` é chamado quando os hooks mudam.
    """
    chave = str(root)
    achado = _HOOKS_DIR.get(chave)
    if achado is not None:
        return achado
    out = git(root, "rev-parse", "--git-path", "hooks")
    if not out:
        return None
    p = Path(out)
    resolvido = p if p.is_absolute() else (root / p).resolve()
    _HOOKS_DIR[chave] = resolvido
    return resolvido


def hooks_dir_cache_clear() -> None:
    _HOOKS_DIR.clear()


@dataclass(frozen=True)
class Commit:
    """Um commit para o conjunto-ouro (RAGX-0167): só hash, assunto e caminhos. Autor, e-mail e corpo NUNCA saem do git."""

    short: str
    subject: str
    files: tuple[str, ...]
    date: int = 0  # `%ct`, só para ordenar de forma estável


def log_commits(root: Path, limit: int | None = None, since: str | None = None, timeout: float = 60.0) -> list[Commit] | None:
    """Commits sem merge com os arquivos alterados (`git log --no-merges --name-status -M`), mais recentes primeiro.

    `None` fora de git ou em erro/timeout. Renomeação segue pelo caminho NOVO; apagado fica de fora (não existe mais).
    """
    args = ["-c", "core.quotepath=off", "log", "--no-merges", "--name-status", "-M", "--format=@@%h%x09%ct%x09%s"]
    if limit:
        args += ["-n", str(limit)]
    if since:
        args += [f"--since={since}"]
    out = git(root, *args, timeout=timeout)
    if out is None:
        return None
    commits: list[Commit] = []
    atual: tuple[str, int, str] | None = None
    arquivos: list[str] = []

    def fecha() -> None:
        if atual is not None:
            commits.append(Commit(atual[0], atual[2], tuple(dict.fromkeys(arquivos)), atual[1]))

    for linha in out.splitlines():
        if linha.startswith("@@"):
            fecha()
            arquivos = []
            h, _, resto = linha[2:].partition("\t")
            data, _, assunto = resto.partition("\t")
            atual = (h, int(data) if data.isdigit() else 0, assunto)
        elif linha.strip() and atual is not None:
            partes = linha.split("\t")
            status = partes[0][:1]
            if status in ("A", "M", "T") and len(partes) >= 2:
                arquivos.append(partes[1])
            elif status in ("R", "C") and len(partes) >= 3:
                arquivos.append(partes[2])
    fecha()
    return commits


_COMMON_DIR: dict[str, Path] = {}


def common_dir(root: Path) -> Path | None:
    """A pasta `.git` COMPARTILHADA por todos os worktrees do repositório (RAGX-0170), ou `None` fora de git.

    `.git` num worktree é um ARQUIVO (`gitdir: ...`), nunca uma pasta: por isso a resposta vem de
    `git rev-parse --git-common-dir`, que devolve a mesma pasta no repositório principal e em qualquer worktree
    (relativa à raiz no principal, absoluta nos outros). Memoizado por processo e raiz; `None` não é guardado.
    """
    chave = str(root)
    achado = _COMMON_DIR.get(chave)
    if achado is not None:
        return achado
    out = git(root, "rev-parse", "--git-common-dir")
    if not out:
        return None
    p = Path(out)
    resolvido = (p if p.is_absolute() else Path(root) / p).resolve()
    _COMMON_DIR[chave] = resolvido
    return resolvido


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str | None = None  # commit; `None` num worktree sem commit
    branch: str | None = None  # `None` com HEAD destacado ou bare
    bare: bool = False
    detached: bool = False


def worktrees(root: Path) -> list[Worktree]:
    """Os worktrees do repositório (`git worktree list --porcelain`), o principal primeiro; vazio fora de git."""
    out = git(root, "worktree", "list", "--porcelain")
    if not out:
        return []
    achados: list[Worktree] = []
    for bloco in out.split("\n\n"):
        caminho: Path | None = None
        head: str | None = None
        branch: str | None = None
        bare = detached = False
        for linha in bloco.splitlines():
            if linha.startswith("worktree "):
                caminho = Path(linha[len("worktree "):])
            elif linha.startswith("HEAD "):
                head = linha[len("HEAD "):]
            elif linha.startswith("branch "):
                branch = linha[len("branch "):].removeprefix("refs/heads/")
            elif linha == "bare":
                bare = True
            elif linha == "detached":
                detached = True
        if caminho is not None:
            achados.append(Worktree(caminho, head, branch, bare, detached))
    return achados


def commits_between(root: Path, old: str, new: str) -> int | None:
    out = git(root, "rev-list", "--count", f"{old}..{new}")
    try:
        return int(out) if out is not None else None
    except ValueError:
        return None


#: Limite de cada chamada do git no caminho rápido do índice (RAGX-0198). Passou disso, a rodada
#: volta para a varredura completa, que não depende do git.
TIMEOUT_INDICE_S = 10.0

#: Modos de entrada que o git não trata como arquivo comum: link simbólico e submódulo.
_MODO_LINK = "120000"
_MODO_SUBMODULO = "160000"
#: Hash de commit completo, SHA-1 (40) ou SHA-256 (64): o único formato aceito como `desde` em `mudancas`.
_COMMIT_HEX = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


@dataclass(frozen=True)
class Mudancas:
    """O que o git diz da árvore, para o índice decidir QUAIS arquivos olhar (RAGX-0198).

    Só caminhos, relativos à raiz do projeto (que pode ser uma subpasta do repositório). Nada aqui lê
    conteúdo: quem lê é o walker, depois do Security Gate. `motivo` preenchido quer dizer "não use esta
    lista agora, varra tudo". `completo` quer dizer que status e ignorados vieram inteiros: mesmo com
    `motivo` (commit sumido, submódulo), dá para registrar o commit para a PRÓXIMA rodada.
    """

    head: str = ""
    branch: str | None = None
    #: arquivos alterados, novos ou apagados agora (status) — o que estiver sujo no fim da rodada
    sujos: frozenset[str] = frozenset()
    #: arquivos diferentes entre o commit do índice e o HEAD (`git diff`)
    entre_commits: frozenset[str] = frozenset()
    #: pastas que o git dá inteiras: repositório aninhado não rastreado (`? pasta/`)
    pastas_sujas: frozenset[str] = frozenset()
    #: o que o git ignora sob a raiz: arquivos e pastas inteiras (com `/` no fim)
    ignorados: tuple[str, ...] = ()
    motivo: str | None = None
    completo: bool = False

    @property
    def estado(self) -> GitState | None:
        """Branch, commit e sujeira, como `read_state` (sem outro processo)."""
        if not self.head:
            return None
        return GitState(branch=self.branch, commit=self.head, dirty=bool(self.sujos or self.pastas_sujas))


def _git_indice(root: Path, *args: str) -> tuple[str | None, str | None]:
    """Como `git`, mas diz POR QUE falhou: `(saída, None)` ou `(None, motivo)`."""
    try:
        out = run_quiet(
            ["git", "--no-optional-locks", *args],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TIMEOUT_INDICE_S,
        )
    except subprocess.TimeoutExpired:
        return None, "git_demorou"
    except (OSError, subprocess.SubprocessError):
        return None, "sem_git"
    if out.returncode != 0:
        return None, "git_falhou"
    return out.stdout, None


def _relativo(caminho: str, prefixo: str) -> str | None:
    if prefixo and not caminho.startswith(prefixo):
        return None
    return caminho[len(prefixo):]


def mudancas(root: Path, desde: str | None = None) -> Mudancas:
    """Status, diferença desde `desde` e ignorados, em até quatro processos curtos.

    - `git status --porcelain=v2 -z --branch --no-renames --untracked-files=all`: commit, branch e cada
      arquivo alterado, novo, apagado ou em conflito. `--no-renames` faz a renomeação aparecer como
      apagado + novo, que é o que o índice precisa (o caminho velho sai, o novo entra).
    - `git diff --raw -z --no-renames <desde> <HEAD>`: só quando o commit mudou. Falha quando `desde`
      não existe mais (rebase seguido de `gc`): recuo, sem adivinhar.
    - `git ls-files -o -i --exclude-standard --directory`: o que o git ignora. Pasta ignorada inteira sai
      como `pasta/`, sem descer nela. É por aqui que o RAGX acha arquivo que ELE indexa e o git ignora
      (negação no `.ragignore`, `include` da config, regra global de exclusão do git).
    - `git rev-parse --show-prefix`: só quando a raiz não tem `.git`, isto é, é subpasta do repositório.

    `-z` em todos: caminho com espaço, acento ou aspas sai cru, sem o escape de `core.quotepath`.
    Link simbólico na lista, commit do índice que sumiu, submódulo e nome que não é UTF-8 viram
    `motivo`: o caminho rápido não tenta tratar esses casos, devolve a decisão para a varredura. Com
    submódulo (ou `.gitmodules`), nem o registro para a próxima rodada vale: o `status` do repositório de
    cima pode esconder o que muda dentro dele (`ignore = all`).
    """
    saida, motivo = _git_indice(
        root, "status", "--porcelain=v2", "-z", "--branch", "--no-renames", "--untracked-files=all", "--", ".",
    )
    if saida is None:
        # `status` só falha, na prática, fora de repositório (o git responde 128)
        return Mudancas(motivo="nao_e_repositorio_git" if motivo == "git_falhou" else motivo)
    head = ""
    branch: str | None = None
    brutos: list[str] = []
    pastas: list[str] = []
    recuo: str | None = None
    completo = True
    campos = saida.split("\0")
    i = 0
    while i < len(campos):
        linha = campos[i]
        i += 1
        if not linha:
            continue
        if linha.startswith("# branch.oid "):
            head = linha[len("# branch.oid "):]
        elif linha.startswith("# branch.head "):
            nome = linha[len("# branch.head "):]
            branch = None if nome == "(detached)" else nome
        elif linha.startswith("#"):
            continue
        elif linha.startswith("? ") or linha.startswith("! "):
            caminho = linha[2:]
            (pastas if caminho.endswith("/") else brutos).append(caminho.rstrip("/"))
        elif linha[:2] in ("1 ", "2 ", "u "):
            partes = linha.split(" ")
            # 1 XY sub mH mI mW hH hI caminho | 2 ... Xscore caminho \0 origem | u XY sub m1 m2 m3 mW h1 h2 h3 caminho
            n_modos = 4 if linha[0] == "u" else 3
            n_antes = {"1": 8, "2": 9, "u": 10}[linha[0]]
            if len(partes) <= n_antes:
                return Mudancas(motivo="git_saida_inesperada")
            modos = partes[3:3 + n_modos]
            if not partes[2].startswith("N") or _MODO_SUBMODULO in modos:
                recuo, completo = recuo or "submodulo", False
            elif _MODO_LINK in modos:
                recuo = recuo or "link_simbolico"
            brutos.append(" ".join(partes[n_antes:]))
            if linha[0] == "2" and i < len(campos):
                brutos.append(campos[i])  # o caminho de origem vem no campo seguinte
                i += 1
        else:
            return Mudancas(motivo="git_saida_inesperada")
    if not head or head == "(initial)":
        return Mudancas(motivo="sem_commit")

    prefixo = ""
    topo = root
    if not (root / ".git").exists():
        out, motivo = _git_indice(root, "rev-parse", "--show-prefix")
        if out is None:
            return Mudancas(head=head, branch=branch, motivo=motivo)
        prefixo = out.strip()
        for _ in prefixo.strip("/").split("/") if prefixo else ():
            topo = topo.parent
    if (topo / ".gitmodules").exists():
        recuo, completo = recuo or "submodulo", False

    entre: list[str] = []
    if desde is not None and not _COMMIT_HEX.fullmatch(desde):
        # `desde` vem do banco (`meta.git_snapshot`): um `.ragx/` adulterado poderia trazer `--output=...` ou outra
        # opção no lugar do commit, e o git a leria como opção. Só hash de commit (SHA-1 ou SHA-256) passa; o resto
        # volta para a varredura completa, sem chamar o git com esse valor.
        recuo = recuo or "commit_do_indice_invalido"
    elif recuo is None and desde and desde != head:
        out, motivo = _git_indice(root, "diff", "--raw", "-z", "--no-renames", desde, head, "--", ".")
        if out is None:
            recuo = "commit_do_indice_sumiu" if motivo == "git_falhou" else motivo
        else:
            campos = out.split("\0")
            for j in range(0, len(campos) - 1, 2):
                cabecalho, caminho = campos[j], campos[j + 1]
                if not cabecalho.startswith(":"):
                    return Mudancas(head=head, branch=branch, motivo="git_saida_inesperada")
                modos = cabecalho[1:].split(" ")[:2]
                if _MODO_SUBMODULO in modos:
                    recuo, completo = recuo or "submodulo", False
                elif _MODO_LINK in modos:
                    recuo = recuo or "link_simbolico"
                entre.append(caminho)

    sujos = [r for r in (_relativo(c, prefixo) for c in brutos) if r]
    pastas_sujas = [r for r in (_relativo(c, prefixo) for c in pastas) if r]
    entre_rel = [r for r in (_relativo(c, prefixo) for c in entre) if r]
    out, motivo = _git_indice(root, "ls-files", "-z", "-o", "-i", "--exclude-standard", "--directory")
    if out is None:
        return Mudancas(head=head, branch=branch, sujos=frozenset(sujos), pastas_sujas=frozenset(pastas_sujas),
                        motivo=recuo or motivo)
    ignorados = tuple(c for c in out.split("\0") if c)  # já relativos à raiz (cwd)
    if any("�" in c for c in (*sujos, *pastas_sujas, *entre_rel, *ignorados)):
        recuo, completo = recuo or "nome_nao_utf8", False
    return Mudancas(
        head=head, branch=branch, sujos=frozenset(sujos), entre_commits=frozenset(entre_rel),
        pastas_sujas=frozenset(pastas_sujas), ignorados=ignorados, motivo=recuo, completo=completo,
    )


def changed_paths(root: Path) -> list[str] | None:
    """Caminhos alterados, novos ou apagados sob a raiz, relativos a ela."""
    prefix = git(root, "rev-parse", "--show-prefix")
    raw = git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", ".")
    if prefix is None or raw is None:
        return None
    entries = raw.split("\0")
    out: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            i += 1  # o próximo item é o nome antigo
        if prefix and not path.startswith(prefix):
            continue
        out.append(path[len(prefix):])
    return out
