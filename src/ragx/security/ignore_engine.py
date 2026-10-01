"""IgnoreEngine — reduz ruído, NÃO protege segredo.

Um .env não listado no .gitignore continua sendo bloqueado pelo scanner.
Precedência (o último vence): defaults -> .gitignore (inclusive aninhados)
-> .dockerignore -> .ragignore -> ragx.toml -> flags da CLI.

Ver docs/02-seguranca.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

RULES_DIR = Path(__file__).parent / "rules"
_IGNORE_FILES = (".gitignore", ".dockerignore", ".ragignore")


@dataclass(frozen=True, slots=True)
class IgnoreSource:
    name: str
    spec: GitIgnoreSpec
    scope: str = ""  # prefixo de diretório para .gitignore aninhado


class IgnoreEngine:
    def __init__(
        self,
        root: Path,
        extra_exclude: list[str] | None = None,
        extra_include: list[str] | None = None,
        use_defaults: bool = True,
    ):
        self.root = Path(root).resolve()
        self.sources: list[IgnoreSource] = []
        # (prefixo literal do alvo, veio de --include/config?) de cada negação.
        # É o que decide se uma pasta ignorada pode ser podada (`can_prune`).
        self._negacoes: list[tuple[str, bool]] = []

        self._builtin: list[IgnoreSource] = []
        if use_defaults:
            lines = (RULES_DIR / "default_ignore.txt").read_text(encoding="utf-8").splitlines()
            self._builtin.append(IgnoreSource("builtin", _spec(lines)))

        self._config: list[IgnoreSource] = []
        if extra_exclude:
            self._config.append(IgnoreSource("config/cli:exclude", _spec(extra_exclude)))
        if extra_include:
            # negação: --include reverte exclusões anteriores
            self._config.append(
                IgnoreSource("config/cli:include", _spec([f"!{p}" for p in extra_include]))
            )
            self._negacoes.extend((_prefixo_literal(p, ""), True) for p in extra_include)

        self._arquivos: dict[str, list[tuple[int, IgnoreSource]]] = {n: [] for n in _IGNORE_FILES}
        self._montar()
        self._descobrir()

    def _montar(self) -> None:
        """Precedência: defaults -> .gitignore -> .dockerignore -> .ragignore ->
        config/CLI; dentro de cada tipo, do raso ao fundo."""
        self.sources = list(self._builtin)
        for name in _IGNORE_FILES:
            self.sources.extend(src for _, src in sorted(self._arquivos[name], key=lambda x: x[0]))
        self.sources.extend(self._config)

    def _descobrir(self) -> None:
        """Acha os arquivos de ignore de cima para baixo, como o git.

        Eram três `rglob`, um por nome, pela árvore inteira. No Python 3.12 o
        `rglob` entra em junction e não lembra onde já esteve, e o node_modules
        do pnpm é feito de junctions: num monorepo pnpm com worktrees, isso
        passou de 20 minutos a 100% de CPU antes de indexar um arquivo.

        Agora é uma varredura só. Em cada pasta, os arquivos de ignore dela são
        carregados ANTES de decidir se desce nas subpastas, com as regras dos
        ancestrais já valendo: pasta excluída não é visitada (`can_prune`), e o
        `.gitignore` que mora dentro dela não é lido, que é o que o git faz. Ler
        esse arquivo era pior do que lento: as negações com caminho dele
        (`!.yarn/patches` num worktree em `.claude/worktrees/`) impediam a poda
        da própria pasta excluída. Pasta já visitada (mesmo `st_dev`/`st_ino`)
        é pulada, como o walker do índice; symlink não é seguido.
        """
        visited: set[tuple[int, int]] = set()
        stack = [self.root]
        while stack:
            current = stack.pop()
            try:
                entries = sorted(os.scandir(current), key=lambda e: e.name)
            except OSError:
                continue
            rel = current.relative_to(self.root).as_posix()
            scope = "" if rel == "." else rel

            novos = False
            for entry in entries:
                if entry.name in self._arquivos:
                    try:
                        if entry.is_symlink() or not entry.is_file():
                            continue
                        linhas = Path(entry.path).read_text(encoding="utf-8", errors="replace").splitlines()
                    except OSError:
                        continue
                    nome = f"{scope + '/' if scope else ''}{entry.name}"
                    fonte = IgnoreSource(nome, _spec(linhas), scope)
                    self._arquivos[entry.name].append((scope.count("/") + bool(scope), fonte))
                    self._negacoes.extend(
                        (_prefixo_literal(linha[1:], scope), False)
                        for linha in linhas
                        if linha.startswith("!")
                    )
                    novos = True
            if novos:
                self._montar()

            for entry in entries:
                try:
                    if entry.is_symlink() or not entry.is_dir() or entry.name == ".git":
                        continue
                    filho = f"{scope + '/' if scope else ''}{entry.name}"
                    if self.can_prune(filho):
                        continue
                    # `DirEntry.stat()` zera st_ino no Windows; `os.stat` não.
                    st = os.stat(entry.path)
                    key = (st.st_dev, st.st_ino)
                    if key in visited:
                        continue
                    visited.add(key)
                    stack.append(Path(entry.path))
                except OSError:
                    continue

    def should_ignore(self, rel_path: str) -> tuple[bool, str | None]:
        """Devolve (ignorar, origem_da_decisão). O último source que decide vence."""
        p = rel_path.replace("\\", "/")
        decision: tuple[bool, str | None] = (False, None)
        for src in self.sources:
            target = p
            if src.scope:
                if not p.startswith(src.scope + "/"):
                    continue
                target = p[len(src.scope) + 1 :]
            if src.spec.match_file(target):
                decision = (True, src.name)
            else:
                # negação (!pattern) reverte uma exclusão anterior
                if decision[0] and _negates(src.spec, target):
                    decision = (False, f"{src.name} (negação)")
        return decision

    def can_prune(self, rel_dir: str) -> bool:
        """A pasta está ignorada e nada lá dentro pode voltar: não precisa descer.

        Sem isto, o walker descia em cada `node_modules` e em cada worktree
        ignorado só para pular arquivo por arquivo: num monorepo pnpm, dezenas
        de minutos por commit. Pular a pasta inteira não lê nada que seria lido
        antes, então não afrouxa o Gate; só pode deixar de indexar algo, e as
        regras abaixo garantem que isso só acontece onde o git também não
        indexaria.

        Uma negação com caminho que aponta para dentro da pasta
        (`!build/keep.txt`, `--include node_modules/pkg/**`) impede a poda,
        como sempre funcionou, mas só dessa pasta: do próprio alvo, dos
        ancestrais dele e dos descendentes, nunca dos irmãos (`_prefixo_literal`
        guarda o caminho completo do alvo, não o do pai). Uma negação genérica de arquivo de ignore
        (`!.env.example`, `!**/*.md`) não entra em pasta excluída, que é a
        regra do git ("não é possível reincluir um arquivo se um diretório pai
        está excluído"). Um `--include` genérico, que é pedido explícito,
        continua valendo em qualquer lugar e impede toda poda.
        """
        d = rel_dir.replace("\\", "/").strip("/")
        if not d or not self.should_ignore(d + "/")[0]:
            return False
        for prefixo, explicita in self._negacoes:
            if not prefixo:
                if explicita:
                    return False
                continue
            if prefixo == d or prefixo.startswith(d + "/") or d.startswith(prefixo + "/"):
                return False
        return True

    @property
    def source_names(self) -> list[str]:
        return [s.name for s in self.sources]


def _prefixo_literal(padrao: str, scope: str) -> str:
    """O caminho fixo que um padrão alcança, com o escopo aplicado.

    Sem curinga, é o caminho do próprio alvo: `.vscode/extensions.json` em
    `src/app` -> `src/app/.vscode/extensions.json`; `src/app/build/` ->
    `src/app/build`. Com curinga, é a parte fixa antes dele: `build/**/keep.txt`
    -> `build`; `node_modules/pkg/**` -> `node_modules/pkg`. Padrão de um
    segmento só (`!.env.example`) ou que começa com curinga (`**/x`) vale em
    qualquer profundidade: prefixo vazio.

    `can_prune` lê o resultado como "ancestral do alvo, o próprio alvo ou
    descendente dele". Por isso o último segmento entra quando é literal:
    devolver só o PAI do alvo (`src/app` para `!src/app/build/`) fazia dele
    "ancestral" de tudo sob `src/app`, inclusive `node_modules`, e desligava a
    poda de 19 mil arquivos.
    """
    partes = padrao.strip().lstrip("/").rstrip("/").split("/")
    if len(partes) < 2:
        return ""
    fixas: list[str] = []
    for parte in partes:
        if not parte or any(c in parte for c in "*?["):
            break
        fixas.append(parte)
    if not fixas:
        return ""
    return "/".join([scope, *fixas]) if scope else "/".join(fixas)


def _spec(lines: list[str]) -> GitIgnoreSpec:
    return GitIgnoreSpec.from_lines(lines)


def _negates(spec: GitIgnoreSpec, path: str) -> bool:
    return any(
        p.include is False and p.match_file(path)
        for p in spec.patterns
        if getattr(p, "include", None) is not None
    )
