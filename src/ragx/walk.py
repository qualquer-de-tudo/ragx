"""FileWalker — um dos DOIS únicos pontos autorizados a ler o filesystem do
projeto-alvo (o outro é sync/incremental). Todo byte lido sai daqui já tendo
passado pelo SecurityGate.

Ver docs/04-indexacao.md e ADR-0008.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from ragx.core.models import GateDecision, Verdict
from ragx.security.gate import SecurityGate
from ragx.security.links import is_junction, is_link

_BINARY_PROBE = 8192


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

    @property
    def content(self) -> str | None:
        return self.decision.content


def iter_files(
    root: Path,
    gate: SecurityGate,
    max_bytes: int = 1_048_576,
    follow_symlinks: bool = False,
    only: set[str] | None = None,
    fingerprints: dict[str, tuple[int, int]] | None = None,
    prefix: str = "",
    unreadable_dirs: set[str] | None = None,
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
        yield from _examinar(path, root, gate, max_bytes, fingerprints, prefix)


def iter_paths(
    root: Path,
    gate: SecurityGate,
    rels: Iterable[str],
    max_bytes: int = 1_048_576,
    follow_symlinks: bool = False,
    fingerprints: dict[str, tuple[int, int]] | None = None,
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
        yield from _examinar(path, root, gate, max_bytes, fingerprints, "")


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
) -> Iterator[WalkedFile]:
    """Decide UM arquivo: ignore, atalho, tamanho, nome, leitura, binário e Gate.

    É o único lugar onde bytes de arquivo do projeto são lidos e entregues, para a
    varredura e para a reindexação por caminho. Todo `yield` constrói um `WalkedFile`
    com uma `GateDecision`, e o conteúdo só sai depois de `gate.admit`.
    """
    inner = path.relative_to(root).as_posix()
    rel = prefix + inner
    try:
        st = path.stat()
    except OSError as exc:
        if _sumiu(exc):
            return
        decision = _decisao_sem_ler(gate, inner, rel)
        yield WalkedFile(rel, 0, 0, decision, unreadable=decision.rule_id == _UNREADABLE)
        return

    # Ignore antes de ler: o arquivo grande ignorado não custa I/O.
    ignored, source = gate.ignore.should_ignore(inner)
    if ignored:
        yield WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.SKIP, rel, rule_id=source, reason="ignore"),
        )
        return

    # Atalho: size+mtime idênticos ao registrado -> nem abre o arquivo.
    # É o que faz a reindexação sem mudanças ser barata (docs/04-indexacao.md).
    if fingerprints is not None:
        fp = fingerprints.get(rel)
        if fp is not None and fp == (st.st_size, st.st_mtime_ns):
            yield WalkedFile(
                rel, st.st_size, st.st_mtime_ns,
                GateDecision(Verdict.ALLOW, rel, reason="unchanged"),
                unchanged=True,
            )
            return

    if st.st_size > max_bytes:
        yield WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.SKIP, rel, rule_id="too_large", reason="too_large"),
        )
        return

    # Deny-list de nome ANTES de abrir o arquivo.
    hit = gate.scanner.scan_filename(inner)
    if hit is not None:
        yield WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.BLOCK, rel, rule_id=hit.rule_id, findings=(hit,),
                         reason=hit.rule_id),
        )
        return

    try:
        raw = path.read_bytes()
    except OSError as exc:
        if _sumiu(exc):
            return
        yield WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.SKIP, rel, rule_id=_UNREADABLE, reason=_UNREADABLE),
            unreadable=True,
        )
        return

    if b"\x00" in raw[:_BINARY_PROBE]:
        yield WalkedFile(
            rel, st.st_size, st.st_mtime_ns,
            GateDecision(Verdict.SKIP, rel, rule_id="binary", reason="binary"),
        )
        return

    decision = gate.admit(inner, raw)
    if prefix:
        decision = replace(decision, path=rel)
    yield WalkedFile(rel, st.st_size, st.st_mtime_ns, decision)


_UNREADABLE = "unreadable"


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
    root: Path, gate: SecurityGate, follow_symlinks: bool = False
) -> dict[str, tuple[int, int]]:
    """`{caminho: (tamanho, mtime_ns)}` — sem abrir um único arquivo.

    É o que o `ragx watch` compara entre dois instantes. Fica aqui, e não no
    watcher, para que continue valendo que só este módulo enumera o projeto:
    o watcher recebe nomes e números, nunca bytes.
    """
    root = Path(root).resolve()
    visited: set[tuple[int, int]] = set()
    out: dict[str, tuple[int, int]] = {}
    for path in _walk(root, follow_symlinks, visited, gate.ignore.can_prune):
        rel = path.relative_to(root).as_posix()
        ignored, _ = gate.ignore.should_ignore(rel)
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
            entries = list(current.iterdir())
        except OSError:
            # Pasta que existe mas não abriu: quem consome precisa saber, para
            # não confundir com "tudo que havia lá foi apagado".
            if on_unreadable_dir is not None and current.exists():
                on_unreadable_dir(current)
            continue
        for entry in sorted(entries):
            try:
                # Junction do Windows não é symlink para o Python: sem isto ela
                # passava pela guarda e a pasta de fora era percorrida (A8). Só se
                # pergunta por pasta; em arquivo não há syscall a mais.
                eh_link = entry.is_symlink() or (entry.is_dir() and is_junction(entry))
                if eh_link:
                    if not follow_symlinks:
                        continue
                    # Link que escapa da raiz é recusado (ameaça A8).
                    target = entry.resolve()
                    if not target.is_relative_to(root):
                        continue
                if entry.is_dir():
                    if can_prune is not None and can_prune(entry.relative_to(root).as_posix()):
                        continue
                    st = entry.stat()
                    key = (st.st_dev, st.st_ino)
                    if key in visited:  # ciclo
                        continue
                    visited.add(key)
                    stack.append(entry)
                elif entry.is_file():
                    yield entry
            except OSError:
                if on_unreadable_dir is not None:
                    on_unreadable_dir(entry)
                continue
