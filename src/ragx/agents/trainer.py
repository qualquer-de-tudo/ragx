"""`ragx agent train` — compila conhecimento num perfil utilizável.

Duas garantias que valem mais que o resto:

  1. Regra escrita à mão NUNCA é sobrescrita. O gerado vai para
     `rules/*.generated.md`; o curado vence.
  2. `rules/security.md` é OBRIGATÓRIO. Perfil sem ele não compila.

Ver docs/10-agent-training.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from pathspec import GitIgnoreSpec

from ragx.agents.profile import (
    GENERATED_SUFFIX,
    Manifest,
    ProfilePaths,
    load,
)
from ragx.config import Config
from ragx.core.errors import RagxError
from ragx.dictionary import builder as dict_builder
from ragx.security.gate import SecurityGate
from ragx.storage.db import open_db, utcnow
from ragx.tokens import count_tokens


@dataclass
class TrainReport:
    name: str = ""
    tokens: int = 0
    rules: int = 0
    generated_rules: int = 0
    preserved: list[str] = field(default_factory=list)
    skills: int = 0
    proposed_examples: int = 0
    dictionary_items: int = 0
    warnings: list[str] = field(default_factory=list)


def train(
    cfg: Config, name: str, budget: int = 6000, with_examples: bool = False
) -> TrainReport:
    manifest, paths = load(cfg, name)
    report = TrainReport(name=name)

    if not (paths.rules / "security.md").is_file():
        raise RagxError(
            f"perfil {name} não tem `rules/security.md`.\n"
            "  → esse arquivo é obrigatório; recrie o perfil ou restaure-o"
        )

    _validate_scope(cfg, manifest)

    data, _ = dict_builder.build(cfg)
    recorte = _scoped_dictionary(data, manifest)
    report.dictionary_items = sum(
        len(v) for v in recorte.values() if isinstance(v, list | dict)
    )
    _write(paths.dictionary, json.dumps(recorte, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    convencoes = recorte.get("conventions", [])
    gerado = _generated_rules(recorte, convencoes)
    if gerado:
        _write(paths.rules / f"conventions{GENERATED_SUFFIX}", gerado)
        report.generated_rules = 1

    curadas = [
        p.name for p in sorted(paths.rules.glob("*.md"))
        if not p.name.endswith(GENERATED_SUFFIX)
    ]
    report.preserved = curadas
    report.rules = len(curadas) + report.generated_rules

    skills = sorted(p for p in paths.skills.glob("*.md"))
    report.skills = len(skills)

    if with_examples:
        report.proposed_examples = _propose_examples(cfg, paths, report)

    body = _instructions(cfg, manifest, recorte, curadas, skills, budget)
    report.tokens = count_tokens(body)
    if report.tokens > budget:
        report.warnings.append(
            f"instructions.md com {report.tokens} tokens excede o orçamento de {budget}"
        )
    _write(paths.instructions, body)

    with open_db(cfg.db_path, read_only=True) as conn:
        run = conn.execute("SELECT MAX(id) AS v FROM index_runs").fetchone()
        chunks = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        entities = int(conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])

    manifest.knowledge.index_run = int(run["v"] or 0) if run else 0
    manifest.knowledge.dictionary_hash = dict_builder.stable_digest(data)
    manifest.knowledge.chunks = chunks
    manifest.knowledge.entities = entities
    manifest.version = str(int(manifest.version) + 1)
    manifest.generated_at = utcnow()
    _write(paths.manifest, manifest.model_dump_json(indent=2) + "\n")

    _check_secrets(cfg, paths, report)
    return report


def _validate_scope(cfg: Config, manifest: Manifest) -> None:
    for p in [*manifest.scope.include_paths, *manifest.scope.exclude_paths]:
        norm = p.replace("\\", "/")
        if norm.startswith("/") or ".." in PurePosixPath(norm).parts:
            raise RagxError(f"escopo fora da raiz do projeto: {p!r}")
        if len(norm) > 1 and norm[1] == ":":
            raise RagxError(f"escopo com caminho absoluto: {p!r}")


def _scoped_dictionary(data: dict[str, Any], manifest: Manifest) -> dict[str, Any]:
    include = GitIgnoreSpec.from_lines(manifest.scope.include_paths or ["**"])
    exclude = (
        GitIgnoreSpec.from_lines(manifest.scope.exclude_paths)
        if manifest.scope.exclude_paths
        else None
    )
    langs = set(manifest.scope.languages)

    def keep(path: str | None) -> bool:
        if not path:
            return True
        if exclude is not None and exclude.match_file(path):
            return False
        return include.match_file(path)

    out: dict[str, Any] = {"project": data.get("project", {})}
    out["technologies"] = data.get("technologies", [])
    out["services"] = [s for s in data.get("services", []) if keep(s.get("path"))]
    out["modules"] = [m for m in data.get("modules", []) if keep(m.get("name"))]
    out["entrypoints"] = [e for e in data.get("entrypoints", []) if keep(e.get("source"))]
    out["data_stores"] = [d for d in data.get("data_stores", []) if keep(d.get("defined_in"))]
    out["conventions"] = data.get("conventions", [])
    out["docs"] = [d for d in data.get("docs", []) if keep(d.get("path"))]
    out["concepts"] = data.get("concepts", {})
    if langs:
        out["languages"] = sorted(langs)
    return out


def _generated_rules(recorte: dict[str, Any], convencoes: list[dict]) -> str:
    if not convencoes:
        return ""
    linhas = [
        "# Convenções detectadas",
        "",
        "> Arquivo **gerado** por `ragx agent train`. Não edite: suas mudanças serão",
        "> perdidas. Para uma regra curada, crie um `.md` sem o sufixo `.generated`.",
        "",
    ]
    for c in convencoes:
        linhas.append(f"- {c['rule']}  _({c['occurrences']}x, confiança {c['confidence']})_")
        for ev in c.get("evidence", [])[:2]:
            linhas.append(f"    - `{ev}`")
    return "\n".join(linhas) + "\n"


def _instructions(
    cfg: Config, manifest: Manifest, recorte: dict[str, Any],
    curadas: list[str], skills: list[Any], budget: int,
) -> str:
    from ragx.agents.profile import _INSTRUCTIONS

    tech = ", ".join(t["name"] for t in recorte.get("technologies", [])[:12]) or "—"
    escopo = "\n".join(f"- `{p}`" for p in manifest.scope.include_paths)
    if manifest.scope.exclude_paths:
        escopo += "\n" + "\n".join(f"- excluído: `{p}`" for p in manifest.scope.exclude_paths)

    regras = "\n".join(f"- `rules/{n}`" for n in curadas) or "- (nenhuma)"
    if (ProfilePaths(cfg.root).root / "x").name:  # no-op para manter import claro
        pass
    lista_skills = "\n".join(
        f"- `{s.name}` — {_skill_summary(s)}" for s in skills
    ) or "- (nenhuma)"

    multi = ""
    if manifest.scope.projects:
        multi = (
            "\nEm ambiente multirrepositório, comece por `list_projects` e use\n"
            "`get_contract` para o contrato exato de uma integração.\n"
        )

    servicos = recorte.get("services", [])[:10]
    if servicos:
        multi += "\n### Serviços neste escopo\n\n" + "\n".join(
            f"- **{s['name']}** — `{s['path']}`" + (f" · {s['summary']}" if s.get("summary") else "")
            for s in servicos
        ) + "\n"

    return _INSTRUCTIONS.format(
        name=manifest.name,
        description=manifest.description,
        multi=multi,
        scope=escopo,
        rules=regras,
        skills=lista_skills,
        tech=tech,
    )


def _skill_summary(path: Any) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.stem


def _propose_examples(cfg: Config, paths: ProfilePaths, report: TrainReport) -> int:
    """Exemplos do histórico Git entram em `_proposed/` e precisam de promoção.

    Exemplo ruim ensina padrão ruim — por isso nada entra automaticamente.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "log", "--format=%H%x00%s", "-n", "40"],
            cwd=cfg.root, capture_output=True, text=True, check=True, timeout=15,
        )
    except Exception:
        report.warnings.append("histórico Git indisponível: nenhum exemplo proposto")
        return 0

    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    n = 0
    for line in out.stdout.splitlines():
        if "\x00" not in line:
            continue
        sha, subject = line.split("\x00", 1)
        try:
            diff = subprocess.run(
                ["git", "show", "--stat", "--format=%B", sha],
                cwd=cfg.root, capture_output=True, text=True, check=True, timeout=15,
            ).stdout
        except Exception:
            continue
        # Commit antigo com segredo no diff NÃO vira exemplo.
        if gate.scanner.scan_content(f"commit:{sha[:8]}", diff):
            continue
        _write(
            paths.proposed / f"{sha[:8]}.md",
            f"# {subject}\n\n_commit `{sha[:8]}` — proposta; promova com "
            f"`ragx agent promote-example {sha[:8]}`_\n\n```\n{diff[:3000]}\n```\n",
        )
        n += 1
        if n >= 10:
            break
    return n


def promote_example(cfg: Config, name: str, example_id: str) -> str:
    _manifest, paths = load(cfg, name)
    src = paths.proposed / f"{example_id}.md"
    if not src.is_file():
        raise RagxError(f"proposta não encontrada: {example_id}")
    dst = paths.examples / f"{example_id}.md"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    src.unlink()
    return str(dst)


def _check_secrets(cfg: Config, paths: ProfilePaths, report: TrainReport) -> None:
    """O perfil é artefato compartilhado: nada de segredo em `agents/**`."""
    gate = SecurityGate(cfg.root, policy=cfg.security.policy)
    for p in paths.root.rglob("*"):
        if not p.is_file():
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if gate.scanner.scan_content(p.name, body):
            report.warnings.append(f"achado de segurança em {p.name} — revise antes de commitar")


def _write(path: Any, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
