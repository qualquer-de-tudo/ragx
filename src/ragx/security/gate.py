"""SecurityGate — a única porta de entrada de conteúdo no sistema.

Fica ENTRE o leitor de arquivos e o parser. Nenhum componente fora de
ragx.security recebe bytes que não tenham passado por gate.admit().

Ver docs/02-seguranca.md e ADR-0008.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ragx.core.models import Action, GateDecision, SecurityFinding, Severity, Verdict
from ragx.security import redactor
from ragx.security.ignore_engine import IgnoreEngine
from ragx.security.scanner import Ruleset, SecurityScanner, load_ruleset

_BINARY_PROBE = 8192


@dataclass(frozen=True, slots=True)
class GatePolicy:
    """strict: qualquer achado critical/high promove o arquivo inteiro a BLOCK.
    balanced: high isolado vira redact. 'permissive' não existe, deliberadamente."""

    name: str = "strict"

    @property
    def block_threshold(self) -> Severity:
        return Severity.HIGH if self.name == "strict" else Severity.CRITICAL


class SecurityGate:
    def __init__(
        self,
        root: Path,
        policy: str = "strict",
        ruleset: Ruleset | None = None,
        ignore_engine: IgnoreEngine | None = None,
        scan_content: bool = True,
        min_entropy: float = 3.0,
        extra_exclude: list[str] | None = None,
        extra_include: list[str] | None = None,
    ):
        self.root = Path(root).resolve()
        self.policy = GatePolicy(policy)
        self.ruleset = ruleset or load_ruleset()
        self.scanner = SecurityScanner(self.ruleset, min_entropy=min_entropy)
        self.ignore = ignore_engine or IgnoreEngine(
            self.root, extra_exclude=extra_exclude, extra_include=extra_include
        )
        self.scan_content = scan_content

    # ── API pública: uma só ──────────────────────────────────────────────
    def admit(self, rel_path: str, raw: bytes | None = None) -> GateDecision:
        """Único ponto por onde conteúdo pode entrar no sistema."""
        ignored, source = self.ignore.should_ignore(rel_path)
        if ignored:
            return GateDecision(Verdict.SKIP, rel_path, rule_id=source, reason="ignore")

        # Fase 1 — nome do arquivo, ANTES de ler qualquer byte.
        hit = self.scanner.scan_filename(rel_path)
        if hit is not None:
            return GateDecision(
                Verdict.BLOCK, rel_path, rule_id=hit.rule_id, findings=(hit,), reason=hit.rule_id
            )

        if raw is None:
            return GateDecision(Verdict.ALLOW, rel_path, content=None, reason="filename-ok")

        text = _decode(raw)
        if text is None:
            return GateDecision(Verdict.SKIP, rel_path, rule_id="undecodable", reason="undecodable")

        if not self.scan_content:
            return GateDecision(Verdict.ALLOW, rel_path, content=text)

        # Fase 2 — conteúdo.
        hits = self.scanner.scan_content(rel_path, text)
        if not hits:
            return GateDecision(Verdict.ALLOW, rel_path, content=text)

        findings = tuple(f for f, _ in hits)
        worst = max(findings, key=lambda f: f.severity.rank)

        blocking = [
            f
            for f in findings
            if f.action == Action.BLOCK or f.severity.rank >= self.policy.block_threshold.rank
        ]
        if blocking:
            return GateDecision(
                Verdict.BLOCK,
                rel_path,
                rule_id=worst.rule_id,
                findings=findings,
                reason=f"{worst.rule_id} (L{worst.line})",
            )

        redacted = redactor.redact_all(
            text, [(v, f.rule_id.split(":")[-1]) for f, v in hits if f.action == Action.REDACT]
        )
        return GateDecision(
            Verdict.ALLOW_REDACTED,
            rel_path,
            rule_id=worst.rule_id,
            findings=findings,
            content=redacted,
            reason=f"{len(findings)} achado(s) redigido(s)",
        )

    def scan_only(self, rel_path: str, raw: bytes) -> tuple[Verdict, tuple[SecurityFinding, ...]]:
        """Para `ragx security scan`: veredito sem devolver conteúdo."""
        d = self.admit(rel_path, raw)
        return d.verdict, d.findings


def _decode(raw: bytes) -> str | None:
    if b"\x00" in raw[:_BINARY_PROBE]:
        return None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None
