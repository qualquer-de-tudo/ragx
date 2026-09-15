"""IgnoreEngine — reduz ruído, NÃO protege segredo.

Um .env não listado no .gitignore continua sendo bloqueado pelo scanner.
Precedência (o último vence): defaults -> .gitignore (inclusive aninhados)
-> .dockerignore -> .ragignore -> ragx.toml -> flags da CLI.

Ver docs/02-seguranca.md.
"""

from __future__ import annotations

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

        if use_defaults:
            lines = (RULES_DIR / "default_ignore.txt").read_text(encoding="utf-8").splitlines()
            self.sources.append(IgnoreSource("builtin", _spec(lines)))

        for name in _IGNORE_FILES:
            for path in self._find_ignore_files(name):
                scope = path.parent.relative_to(self.root).as_posix()
                scope = "" if scope == "." else scope
                self.sources.append(
                    IgnoreSource(
                        f"{scope + '/' if scope else ''}{name}",
                        _spec(path.read_text(encoding="utf-8", errors="replace").splitlines()),
                        scope,
                    )
                )

        if extra_exclude:
            self.sources.append(IgnoreSource("config/cli:exclude", _spec(extra_exclude)))
        if extra_include:
            # negação: --include reverte exclusões anteriores
            self.sources.append(
                IgnoreSource("config/cli:include", _spec([f"!{p}" for p in extra_include]))
            )

    def _find_ignore_files(self, name: str) -> list[Path]:
        """.gitignore aninhado afeta apenas sua subárvore; ordena do raso ao fundo."""
        found = [p for p in self.root.rglob(name) if ".git" not in p.parts]
        return sorted(found, key=lambda p: len(p.parts))

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

    @property
    def source_names(self) -> list[str]:
        return [s.name for s in self.sources]


def _spec(lines: list[str]) -> GitIgnoreSpec:
    return GitIgnoreSpec.from_lines(lines)


def _negates(spec: GitIgnoreSpec, path: str) -> bool:
    return any(
        p.include is False and p.match_file(path)
        for p in spec.patterns
        if getattr(p, "include", None) is not None
    )
