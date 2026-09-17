"""SecurityScanner — duas fases.

Fase 1: nome do arquivo (deny-list), antes de qualquer leitura de conteúdo.
Fase 2: conteúdo (regras de padrão + atribuição/entropia + contexto de arquivo).

Ver docs/02-seguranca.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pathspec import GitIgnoreSpec

from ragx.core.models import Action, SecurityFinding, Severity
from ragx.security import redactor
from ragx.security.entropy import looks_random, shannon

RULES_DIR = Path(__file__).parent / "rules"


@dataclass(frozen=True, slots=True)
class ContentRule:
    id: str
    severity: Severity
    action: Action
    regex: re.Pattern[str]
    capture_group: int = 0
    min_entropy: float = 0.0
    min_length: int = 0
    high_precision: bool = False


@dataclass(frozen=True, slots=True)
class FilenameRule:
    id: str
    severity: Severity
    spec: GitIgnoreSpec
    reason: str
    #: `True` quando a regra adivinha pelo NOME (`tokens`, `secrets`,
    #: `password`). Nesses casos um arquivo de código-fonte é liberado da fase
    #: 1 e julgado pelo conteúdo, na fase 2. Regras que descrevem FORMATO
    #: (`*.pem`) ou LOCAL (`.ssh/**`) ficam absolutas.
    content_decides: bool = False


class Ruleset:
    """Regras carregadas de YAML. Regex compilado uma única vez."""

    def __init__(self, rules_dir: Path = RULES_DIR, disabled: frozenset[str] = frozenset()):
        self.disabled = disabled
        fn = yaml.safe_load((rules_dir / "filenames.yaml").read_text(encoding="utf-8"))
        pt = yaml.safe_load((rules_dir / "patterns.yaml").read_text(encoding="utf-8"))

        self.allow_spec = _spec(fn.get("allow", []))
        self.code_extensions = frozenset(
            str(e).lower() for e in fn.get("code_extensions", [])
        )
        self.filename_rules: list[FilenameRule] = [
            FilenameRule(
                r["id"],
                Severity(r["severity"]),
                _spec(r["patterns"]),
                r.get("reason", ""),
                bool(r.get("content_decides", False)),
            )
            for r in fn.get("deny", [])
            if r["id"] not in disabled
        ]

        self.content_rules: list[ContentRule] = [
            ContentRule(
                id=r["id"],
                severity=Severity(r["severity"]),
                action=Action(r["action"]),
                regex=re.compile(r["pattern"]),
                capture_group=int(r.get("capture_group", 0)),
                min_entropy=float(r.get("min_entropy", 0.0)),
                min_length=int(r.get("min_length", 0)),
                high_precision=bool(r.get("high_precision", False)),
            )
            for r in pt.get("rules", [])
            if r["id"] not in disabled
        ]

        self.placeholders = {p.lower() for p in pt.get("placeholders", [])}
        self.placeholder_res = [re.compile(p) for p in pt.get("placeholder_patterns", [])]
        ctx = pt.get("context", {})
        self._raise_spec = _spec(ctx.get("raise", {}).get("patterns", []))
        self._raise_delta = int(ctx.get("raise", {}).get("delta", 0))
        self._lower_spec = _spec(ctx.get("lower", {}).get("patterns", []))
        self._lower_delta = int(ctx.get("lower", {}).get("delta", 0))
        self._lower_floor = Severity(ctx.get("lower", {}).get("floor", "medium"))

    @property
    def count(self) -> int:
        return len(self.filename_rules) + len(self.content_rules)

    def is_placeholder(self, value: str) -> bool:
        v = value.strip().strip("\"'")
        if v.lower() in self.placeholders:
            return True
        if any(p in v.lower() for p in ("changeme", "your_", "your-", "placeholder", "redacted")):
            return True
        return any(r.match(v) for r in self.placeholder_res)

    def adjust(self, severity: Severity, rel_path: str, high_precision: bool) -> Severity:
        """Contexto ajusta severidade — mas NUNCA rebaixa regra de alta precisão."""
        order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        idx = order.index(severity)
        if self._raise_spec.match_file(rel_path):
            idx = min(idx + self._raise_delta, len(order) - 1)
        elif self._lower_spec.match_file(rel_path) and not high_precision:
            idx = max(idx + self._lower_delta, order.index(self._lower_floor))
        return order[idx]


def _spec(patterns: list[str]) -> GitIgnoreSpec:
    return GitIgnoreSpec.from_lines(patterns)


@lru_cache(maxsize=4)
def load_ruleset(disabled: frozenset[str] = frozenset()) -> Ruleset:
    return Ruleset(disabled=disabled)


class SecurityScanner:
    def __init__(self, ruleset: Ruleset | None = None, min_entropy: float = 3.0):
        self.rules = ruleset or load_ruleset()
        self.min_entropy = min_entropy

    # ── Fase 1: nome do arquivo ──────────────────────────────────────────
    def scan_filename(self, rel_path: str) -> SecurityFinding | None:
        """Decide só pelo caminho. Verificável sem tocar no disco."""
        p = rel_path.replace("\\", "/")
        if self.rules.allow_spec.match_file(p):
            return None
        # Código-fonte não é recipiente de segredo: `tokens.py` conta tokens,
        # `tokens.ts` são design tokens, `docs/tokens.md` é documentação. Eles
        # seguem para a fase 2, que ainda lê o conteúdo inteiro — o que muda é
        # que o NOME deixa de ser condenação. Ver docs/02-seguranca.md.
        e_codigo = Path(p).suffix.lower() in self.rules.code_extensions
        for rule in self.rules.filename_rules:
            if rule.content_decides and e_codigo:
                continue
            if rule.spec.match_file(p):
                return SecurityFinding(
                    rule_id=f"filename-deny:{rule.id}",
                    severity=rule.severity,
                    action=Action.BLOCK,
                    path=rel_path,
                    line=0,
                    detected_by="filename",
                )
        return None

    # ── Fase 2: conteúdo ─────────────────────────────────────────────────
    def scan_content(self, rel_path: str, content: str) -> list[tuple[SecurityFinding, str]]:
        """Devolve [(finding, valor_bruto)]. O valor bruto só circula em memória,
        para permitir a redação — nunca é persistido."""
        out: list[tuple[SecurityFinding, str]] = []
        seen: set[tuple[str, str]] = set()

        for lineno, line in enumerate(content.splitlines(), start=1):
            if len(line) > 4096:  # minificado/base64 gigante: não vale o custo
                continue
            for rule in self.rules.content_rules:
                for m in rule.regex.finditer(line):
                    value = m.group(rule.capture_group) if rule.capture_group else m.group(0)
                    if not value:
                        continue
                    value = value.strip().strip("\"'")
                    if len(value) < rule.min_length:
                        continue
                    if self.rules.is_placeholder(value):
                        continue
                    if rule.min_entropy and not looks_random(
                        value, max(rule.min_entropy, 0.0), rule.min_length or 8
                    ):
                        continue
                    key = (rule.id, redactor.digest(value))
                    if key in seen:
                        continue
                    seen.add(key)
                    sev = self.rules.adjust(rule.severity, rel_path, rule.high_precision)
                    out.append(
                        (
                            SecurityFinding(
                                rule_id=f"content:{rule.id}",
                                severity=sev,
                                action=rule.action,
                                path=rel_path,
                                line=lineno,
                                column=m.start() + 1,
                                digest=redactor.digest(value),
                                preview=redactor.preview(value),
                                detected_by="entropy" if rule.min_entropy else "pattern",
                            ),
                            value,
                        )
                    )
        return out

    def entropy_of(self, value: str) -> float:
        return shannon(value)


def rules_summary(ruleset: Ruleset | None = None) -> dict[str, Any]:
    rs = ruleset or load_ruleset()
    return {
        "filename_rules": [r.id for r in rs.filename_rules],
        "content_rules": [r.id for r in rs.content_rules],
        "disabled": sorted(rs.disabled),
        "count": rs.count,
    }
