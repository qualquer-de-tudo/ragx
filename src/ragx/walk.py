"""FileWalker — um dos DOIS únicos pontos autorizados a ler o filesystem do
projeto-alvo (o outro é sync/incremental). Todo byte lido sai daqui já tendo
passado pelo SecurityGate.

Ver docs/04-indexacao.md e ADR-0008.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from ragx.core.models import GateDecision, Verdict
from ragx.security.gate import SecurityGate
from ragx.security.links import is_junction, is_link

_BINARY_PROBE = 8192

#: `rel_path -> (tamanho, mtime_ns, veredito, rule_id)`: o que `file_verdicts` guardou.
Verdicts = dict[str, tuple[int, int, str, str | None]]


@dataclass(frozen=True, slots=True)
class WalkedFile:
    rel_path: str
    size_bytes: int
    mtime_ns: int
    decision: GateDecision
    unchanged: bool = False
    #: o arquivo existe, mas não deu para ler agora (antivírus, editor segurando
    #: o arquivo logo depois do save). NÃO é "arquivo removido": o pipeline
    #: preserva o que já está indexado (RAGX-0133).
    unreadable: bool = False
    #: a decisão veio do veredito guardado (`file_verdicts`), sem abrir o arquivo: o pipeline
    #: não refaz o que o veredito original já gravou (RAGX-0139).
    cached_verdict: bool = False

    @property
    def content(self) -> str | None:
        return self.decision.content


@dataclass(frozen=True, slots=True)
class Candidate:
    """Arquivo que passou nas decisões baratas (ignore, veredito guardado, `unchanged`, tamanho, nome) e
    ainda PRECISA ser lido: leitura, sonda de binário e Gate vêm depois, em `read_candidate` (RAGX-0152).

    Só dados simples (strings e inteiros), para atravessar um processo sem custo.
    """

    path: str  # caminho absoluto no disco
    inner: str  # relativo à raiz, como o Gate o vê
    rel: str  # `inner` com o prefixo do índice (conhecimento base entra como `@base/<fonte>/...`)
    size_bytes: int
    mtime_ns: int


def iter_files(
    root: Path,
    gate: SecurityGate,
    max_bytes: int = 1_048_576,
    follow_symlinks: bool = False,
    only: set[str] | None = None,
    fingerprints: dict[str, tuple[int, int]] | None = None,
    prefix: str = "",
    unreadable_dirs: set[str] | None = None,
    verdicts: Verdicts | None = None,
) -> Iterator[WalkedFile]:
    """Emite candidatos em streaming — nunca carrega o repositório em memória.

    `prefix` namespaceia a árvore no índice (conhecimento base entra como
    `@base/<fonte>/...`). O gate continua vendo o caminho REAL dentro da raiz,
    para que regra de nome e .gitignore funcionem igual; o prefixo só existe
    do lado de fora.

    `unreadable_dirs` recebe (com o `prefix`) as pastas que não puderam ser
    listadas: o que já estava indexado sob elas não pode ser tratado como
    removido.
    """
    for item in iter_candidates(
        root, gate, max_bytes, follow_symlinks, only, fingerprints, prefix, unreadable_dirs, verdicts
    ):
        if isinstance(item, Candidate):
            lido = read_candidate(item, gate)
            if lido is not None:
                yield lido
        else:
            yield item


def iter_candidates(
    root: Path,
    gate: SecurityGate,
    max_bytes: int = 1_048_576,
    follow_symlinks: bool = False,
    only: set[str] | None = None,
    fingerprints: dict[str, tuple[int, int]] | None = None,
    prefix: str = "",
    unreadable_dirs: set[str] | None = None,
    verdicts: Verdicts | None = None,
) -> Iterator[WalkedFile | Candidate]:
    """Primeiro estágio de `iter_files` (RAGX-0152): percorre a árvore e faz só as decisões BARATAS.

    Cada arquivo sai como um `WalkedFile` já decidido (ignorado, veredito guardado, `unchanged`, grande
    demais, nome na deny-list, `stat` com erro) ou como um `Candidate`, que ainda precisa de
    `read_candidate` (leitura + sonda de binário + Gate). A ordem é a da varredura. `iter_files` é a
    composição dos dois estágios; o pipeline paralelo entrega os `Candidate` a processos que o fazem.
    """
    root = Path(root).resolve()
    visited: set[tuple[int, int]] = set()

    def _pasta_ilegivel(pasta: Path) -> None:
        if unreadable_dirs is not None:
            rel_dir = pasta.relative_to(root).as_posix()
            unreadable_dirs.add((prefix + ("" if rel_dir == "." else rel_dir)).rstrip("/"))

    for path in _walk(root, follow_symlinks, visited, gate.ignore.can_prune, _pasta_ilegivel):
        rel = prefix + path.relative_to(root).as_posix()
        if only is not None and rel not in only:
            continue
        decidido = _decidir(path, root, gate, max_bytes, fingerprints, prefix, verdicts)
        if decidido is not None:
            yield decidido


def iter_paths(
    root: Path,
    gate: SecurityGate,
    rels: Iterable[str],
    max_bytes: int = 1_048_576,
    follow_symlinks: bool = False,
    fingerprints: dict[str, tuple[int, int]] | None = None,
    verdicts: Verdicts | None = None,
) -> Iterator[WalkedFile]:
    """Como `iter_files`, mas só para os caminhos pedidos e SEM percorrer a árvore.

    É a base da reindexação por caminho (RAGX-0140): quem acabou de editar um arquivo
    não precisa pagar a varredura do projeto inteiro. O Gate é o MESMO e roda antes de
    qualquer byte sair daqui (`_examinar`); o que muda é como se CHEGA ao arquivo, e por isso
    `iter_paths` repete as recusas que a varredura faria por construção:

    - caminho absoluto, com `..`, vazio ou do conhecimento base (`@base/`): recusado;
    - algum ancestral é link (symlink, ou junction no Windows) e `follow_symlinks` é falso,
      ou o ancestral é uma pasta que a varredura PODA (`IgnoreEngine.can_prune`): a varredura
      nunca chegaria ali, então aqui também não;
    - o caminho resolvido sai da raiz (ameaça A8): recusado;
    - arquivo que não existe: não é emitido (o chamador trata como removido); outro `OSError` vira
      `unreadable`, como na varredura (RAGX-0133).
    """
    root = Path(root).resolve()
    for bruto in rels:
        inner = normalizar_caminho(bruto)
        if inner is None:
            continue
        path = root / inner
        if not _alcancavel(root, inner, gate, follow_symlinks):
            continue
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        yield from _examinar(path, root, gate, max_bytes, fingerprints, "", verdicts)


def normalizar_caminho(bruto: str) -> str | None:
    """Caminho relativo POSIX, ou `None` se não for um caminho que este módulo aceite."""
    texto = bruto.replace("\\", "/").strip()
    while texto.startswith("./"):
        texto = texto[2:]
    if not texto or texto.startswith("/") or (len(texto) > 1 and texto[1] == ":"):
        return None
    partes = texto.split("/")
    if ".." in partes or "" in partes or texto.startswith("@base/"):
        return None
    return "/".join(partes)


def _alcancavel(root: Path, inner: str, gate: SecurityGate, follow_symlinks: bool) -> bool:
    """A varredura chegaria a este arquivo? Mesmas regras de `_walk`, sem varrer."""
    partes = inner.split("/")
    ancestral = root
    for i, parte in enumerate(partes[:-1]):
        ancestral = ancestral / parte
        rel_dir = "/".join(partes[: i + 1])
        try:
            if is_link(ancestral):
                if not follow_symlinks:
                    return False
                if not ancestral.resolve().is_relative_to(root):
                    return False
            if not ancestral.is_dir():
                return False
        except OSError:
            return False
        if gate.ignore.can_prune(rel_dir):
            return False
    try:
        # o próprio arquivo pode ser um symlink para fora, e o caminho final tem de ficar na raiz
        return (root / inner).resolve().is_relative_to(root) and (
            follow_symlinks or not (root / inner).is_symlink()
        )
    except OSError:
        return False


def _examinar(
    path: Path,
    root: Path,
    gate: SecurityGate,
    max_bytes: int,
    fingerprints: dict[str, tuple[int, int]] | None,
    prefix: str,
    verdicts: Verdicts | None = None,
) -> Iterator[WalkedFile]:
    """Decide UM arquivo: ignore, atalho, tamanho, nome, leitura, binário e Gate.

    É a composição de `_decidir` (decisões baratas) e `read_candidate` (leitura + Gate): serve à
    reindexação por caminho e à varredura sequencial. Todo `WalkedFile` entregue leva uma
    `GateDecision`, e o conteúdo só sai depois de `gate.admit`.
    """
    decidido = _decidir(path, root, gate, max_bytes, fingerprints, prefix, verdicts)
    if isinstance(decidido, Candidate):
        decidido = read_candidate(decidido, gate)
    if decidido is not None:
        yield decidido


def _decidir(
    path: Path,
    root: Path,
    gate: SecurityGate,
    max_bytes: int,
    fingerprints: dict[str, tuple[int, int]] | None,
    prefix: str,
    verdicts: Verdicts | None = None,
) -> WalkedFile | Candidate | None:
    """Decisões baratas sobre UM arquivo, SEM abri-lo (RAGX-0152).

    Devolve um `WalkedFile` quando o destino já se sabe (ignorado, veredito guardado, `unchanged`, grande
    demais, nome na deny-list, `stat` com erro), um `Candidate` quando falta ler, ou `None` quando o
    arquivo sumiu.
    """
    inner = path.relative_to(root).as_posix()
    rel = prefix + inner
    try:
        st = path.stat()
    except OSError as exc:
        if _sumiu(exc):
            return None
        decision = _decisao_sem_ler(gate, inner, rel)
        return WalkedFile(rel, 0, 0, decision, unreadable=decision.rule_id == _UNREADABLE)

    # Ignore antes de ler: o arquivo grande ignorado não custa I/O.
    ignored, source = gate.ignore.should_ignore(inner)
    if ignored:
        return WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.SKIP, rel, rule_id=source, reason="ignore"),
        )

    # Veredito guardado (RAGX-0139): arquivo que NÃO entra no índice, decidido antes com este
    # mesmo tamanho e mtime e as mesmas regras (o chamador descarta o cache quando elas mudam).
    # Vem ANTES do atalho de `fingerprints`: se algum dia os dois existirem para o mesmo
    # caminho, vale o mais restritivo. O cache só mantém um arquivo FORA; nunca coloca um dentro.
    if verdicts is not None:
        guardado = verdicts.get(rel)
        if guardado is not None and guardado[:2] == (st.st_size, st.st_mtime_ns):
            return WalkedFile(rel, st.st_size, st.st_mtime_ns, _decisao_guardada(rel, guardado),
                              cached_verdict=True)

    # Atalho: size+mtime idênticos ao registrado -> nem abre o arquivo.
    # É o que faz a reindexação sem mudanças ser barata (docs/04-indexacao.md).
    if fingerprints is not None:
        fp = fingerprints.get(rel)
        if fp is not None and fp == (st.st_size, st.st_mtime_ns):
            return WalkedFile(
                rel, st.st_size, st.st_mtime_ns,
                GateDecision(Verdict.ALLOW, rel, reason="unchanged"),
                unchanged=True,
            )

    if st.st_size > max_bytes:
        return WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.SKIP, rel, rule_id="too_large", reason="too_large"),
        )

    # Deny-list de nome ANTES de abrir o arquivo.
    hit = gate.scanner.scan_filename(inner)
    if hit is not None:
        return WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.BLOCK, rel, rule_id=hit.rule_id, findings=(hit,),
                         reason=hit.rule_id),
        )

    return Candidate(str(path), inner, rel, st.st_size, st.st_mtime_ns)


def read_candidate(candidate: Candidate, gate: SecurityGate) -> WalkedFile | None:
    """Segundo estágio (RAGX-0152): lê o arquivo, sonda binário e passa pelo Gate.

    É o único lugar que lê os bytes de um arquivo do projeto, tanto no processo principal quanto no
    worker do pipeline paralelo (que constrói o PRÓPRIO `SecurityGate` completo). O conteúdo só sai
    depois de `gate.admit`. `None` quando o arquivo sumiu entre a varredura e a leitura; outro
    `OSError` vira `unreadable` (RAGX-0133).
    """
    path, inner, rel = Path(candidate.path), candidate.inner, candidate.rel
    size, mtime = candidate.size_bytes, candidate.mtime_ns
    try:
        raw = path.read_bytes()
    except OSError as exc:
        if _sumiu(exc):
            return None
        return WalkedFile(
            rel, size, mtime,
            GateDecision(Verdict.SKIP, rel, rule_id=_UNREADABLE, reason=_UNREADABLE),
            unreadable=True,
        )

    if b"\x00" in raw[:_BINARY_PROBE]:
        return WalkedFile(
            rel, size, mtime,
            GateDecision(Verdict.SKIP, rel, rule_id="binary", reason="binary"),
        )

    decision = gate.admit(inner, raw)
    if rel != inner:
        decision = replace(decision, path=rel)
    return WalkedFile(rel, size, mtime, decision)


_UNREADABLE = "unreadable"


def _decisao_guardada(rel: str, guardado: tuple[int, int, str, str | None]) -> GateDecision:
    """`GateDecision` equivalente ao veredito guardado. NUNCA é ALLOW: o cache não admite nada."""
    _size, _mtime, veredito, rule_id = guardado
    if veredito == "blocked":
        regra = rule_id or "blocked"
        return GateDecision(Verdict.BLOCK, rel, rule_id=regra, reason=regra)
    return GateDecision(Verdict.SKIP, rel, rule_id=veredito, reason=veredito)


def _sumiu(exc: OSError) -> bool:
    """O arquivo não existe mais. Qualquer outro `OSError` (permissão, violação
    de compartilhamento, antivírus) significa "não sei agora", que é diferente."""
    return isinstance(exc, FileNotFoundError | NotADirectoryError)


def _decisao_sem_ler(gate: SecurityGate, inner: str, rel: str) -> GateDecision:
    """Decisão para um arquivo cujo `stat` falhou, SEM abri-lo.

    O nome continua sendo checado: um arquivo de nome sensível que ficou
    indexado por engano e agora está travado tem de sair do índice do mesmo
    jeito que sairia destravado.
    """
    ignored, source = gate.ignore.should_ignore(inner)
    if ignored:
        return GateDecision(Verdict.SKIP, rel, rule_id=source, reason="ignore")
    hit = gate.scanner.scan_filename(inner)
    if hit is not None:
        return GateDecision(Verdict.BLOCK, rel, rule_id=hit.rule_id, findings=(hit,),
                            reason=hit.rule_id)
    return GateDecision(Verdict.SKIP, rel, rule_id=_UNREADABLE, reason=_UNREADABLE)


def scan_fingerprints(
    root: Path,
    gate: SecurityGate,
    follow_symlinks: bool = False,
    ignored_cache: dict[str, bool] | None = None,
) -> dict[str, tuple[int, int]]:
    """`{caminho: (tamanho, mtime_ns)}` — sem abrir um único arquivo.

    É o que o `ragx watch` compara entre dois instantes. Fica aqui, e não no
    watcher, para que continue valendo que só este módulo enumera o projeto:
    o watcher recebe nomes e números, nunca bytes.

    `ignored_cache` (RAGX-0147) guarda o veredito de `should_ignore` por caminho: o watcher o passa
    de ciclo em ciclo enquanto o gate é o mesmo e o zera quando um arquivo de ignore muda. Caminho
    novo calcula. Só poupa a conta; o veredito de segurança continua sendo `gate.admit` na leitura.
    """
    root = Path(root).resolve()
    visited: set[tuple[int, int]] = set()
    out: dict[str, tuple[int, int]] = {}
    for path in _walk(root, follow_symlinks, visited, gate.ignore.can_prune):
        rel = path.relative_to(root).as_posix()
        if ignored_cache is None:
            ignored, _ = gate.ignore.should_ignore(rel)
        else:
            ignored = ignored_cache.get(rel)  # type: ignore[assignment]
            if ignored is None:
                ignored, _ = gate.ignore.should_ignore(rel)
                ignored_cache[rel] = ignored
        if ignored:
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        out[rel] = (st.st_size, st.st_mtime_ns)
    return out


def _walk(
    root: Path,
    follow_symlinks: bool,
    visited: set[tuple[int, int]],
    can_prune: Callable[[str], bool] | None = None,
    on_unreadable_dir: Callable[[Path], None] | None = None,
) -> Iterator[Path]:
    """`can_prune` pula a pasta ignorada inteira (ver `IgnoreEngine.can_prune`):
    descer num `node_modules` ou num worktree ignorado só para pular arquivo por
    arquivo custava dezenas de minutos por commit num monorepo pnpm."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            # `os.scandir`: tipo (arquivo, pasta, link) vem da enumeração, sem syscall por entrada (RAGX-0147).
            # A ordem é a de `sorted(Path)` de antes (no Windows, sem diferenciar maiúscula).
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: Path(e.path))
        except OSError:
            # Pasta que existe mas não abriu: quem consome precisa saber, para
            # não confundir com "tudo que havia lá foi apagado".
            if on_unreadable_dir is not None and current.exists():
                on_unreadable_dir(current)
            continue
        for entry in entries:
            try:
                # Junction do Windows não é symlink para o Python: sem isto ela
                # passava pela guarda e a pasta de fora era percorrida (A8). Só se
                # pergunta por pasta; em arquivo não há syscall a mais.
                eh_link = entry.is_symlink() or (entry.is_dir() and is_junction(entry.path))
                if eh_link:
                    if not follow_symlinks:
                        continue
                    # Link que escapa da raiz é recusado (ameaça A8).
                    target = Path(entry.path).resolve()
                    if not target.is_relative_to(root):
                        continue
                if entry.is_dir():
                    caminho = Path(entry.path)
                    if can_prune is not None and can_prune(caminho.relative_to(root).as_posix()):
                        continue
                    st = os.stat(entry.path)  # `DirEntry.stat()` zera st_ino no Windows
                    key = (st.st_dev, st.st_ino)
                    if key in visited:  # ciclo
                        continue
                    visited.add(key)
                    stack.append(caminho)
                elif entry.is_file():
                    yield Path(entry.path)
            except OSError:
                if on_unreadable_dir is not None:
                    on_unreadable_dir(Path(entry.path))
                continue
