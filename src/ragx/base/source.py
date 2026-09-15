"""Conhecimento base — fontes externas que valem para TODOS os projetos.

Regras de arquitetura, guardrails, padrões de código: coisas que não pertencem
a um repositório específico, mas que o agente precisa conhecer em qualquer um.

Ficam em `~/.ragx/base/<nome>/`, baixadas **uma vez por máquina**, e são
indexadas em cada projeto sob o prefixo `@base/<nome>/` — nunca colidem com
arquivo do projeto e aparecem marcadas em toda busca.

Conteúdo de terceiro é ENTRADA NÃO CONFIÁVEL: passa pelo mesmo Security Gate
que o código do projeto.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ragx.config import Config
from ragx.core.errors import RagxError, UsageError
from ragx.storage.db import utcnow

PREFIX = "@base"
REGISTRY = "sources.json"


@dataclass
class BaseSource:
    name: str
    origin: str  # url do git ou caminho local
    kind: str = "git"  # git | path
    ref: str | None = None
    commit: str | None = None
    added_at: str = ""
    updated_at: str = ""
    files: int = 0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "origin": self.origin, "kind": self.kind,
            "ref": self.ref, "commit": self.commit, "added_at": self.added_at,
            "updated_at": self.updated_at, "files": self.files, "enabled": self.enabled,
        }


@dataclass
class BaseReport:
    name: str = ""
    path: str = ""
    files: int = 0
    commit: str | None = None
    updated: bool = False
    warnings: list[str] = field(default_factory=list)


def base_dir(cfg: Config) -> Path:
    return cfg.hub_dir.parent / "base"


def registry_path(cfg: Config) -> Path:
    return base_dir(cfg) / REGISTRY


def load_registry(cfg: Config) -> list[BaseSource]:
    path = registry_path(cfg)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [BaseSource(**s) for s in data.get("sources", [])]


def save_registry(cfg: Config, sources: list[BaseSource]) -> None:
    path = registry_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": 1, "sources": [s.to_dict() for s in sources]},
            ensure_ascii=False, indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8", newline="\n",
    )


def source_path(cfg: Config, name: str) -> Path:
    return base_dir(cfg) / name


def _norm(origin: str) -> str:
    """Mesma origem escrita de formas diferentes é a mesma origem.

    `C:\\x\\regras` num registro e `C:/x/regras` num ragx.toml (TOML trata `\\`
    como escape, então todo mundo escreve com `/`) precisam casar.
    """
    return origin.replace("\\", "/").rstrip("/")


def _slug(origin: str) -> str:
    tail = _norm(origin).split("/")[-1]
    return tail.removesuffix(".git") or "base"


def _git(cwd: Path, *args: str, timeout: int = 180) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if out.returncode != 0:
        raise RagxError(f"git {' '.join(args)} falhou: {out.stderr.strip()[:200]}")
    return out.stdout.strip()


def add(
    cfg: Config, origin: str, name: str | None = None, ref: str | None = None
) -> BaseReport:
    sources = load_registry(cfg)
    slug = name or _slug(origin)
    if any(s.name == slug for s in sources):
        raise UsageError(f"fonte já registrada: {slug} (use `ragx base update {slug}`)")

    target = source_path(cfg, slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    report = BaseReport(name=slug, path=str(target))

    local = Path(origin).expanduser()
    if local.is_dir():
        shutil.copytree(local, target, dirs_exist_ok=True)
        kind, commit = "path", None
    else:
        if target.exists():
            shutil.rmtree(target)
        args = ["clone", "--depth", "1"]
        if ref:
            args += ["--branch", ref]
        _git(target.parent, *args, origin, str(target))
        kind = "git"
        commit = _git(target, "rev-parse", "HEAD")
        # O histórico não interessa e só ocupa espaço.
        shutil.rmtree(target / ".git", ignore_errors=True)

    report.files = _count(target)
    report.commit = commit
    sources.append(
        BaseSource(
            name=slug, origin=origin, kind=kind, ref=ref, commit=commit,
            added_at=utcnow(), updated_at=utcnow(), files=report.files,
        )
    )
    save_registry(cfg, sources)
    return report


def update(cfg: Config, name: str | None = None) -> list[BaseReport]:
    sources = load_registry(cfg)
    if not sources:
        raise UsageError("nenhuma fonte base registrada — use `ragx base add <url>`")
    alvos = [s for s in sources if name is None or s.name == name]
    if name and not alvos:
        raise UsageError(f"fonte não encontrada: {name}")

    out: list[BaseReport] = []
    for s in alvos:
        target = source_path(cfg, s.name)
        r = BaseReport(name=s.name, path=str(target))
        try:
            if s.kind == "path":
                local = Path(s.origin).expanduser()
                if not local.is_dir():
                    r.warnings.append(f"origem local sumiu: {s.origin}")
                    out.append(r)
                    continue
                shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(local, target)
            else:
                shutil.rmtree(target, ignore_errors=True)
                args = ["clone", "--depth", "1"]
                if s.ref:
                    args += ["--branch", s.ref]
                _git(target.parent, *args, s.origin, str(target))
                novo = _git(target, "rev-parse", "HEAD")
                r.updated = novo != s.commit
                r.commit = s.commit = novo
                shutil.rmtree(target / ".git", ignore_errors=True)
        except RagxError as exc:
            r.warnings.append(str(exc))
            out.append(r)
            continue
        r.files = s.files = _count(target)
        s.updated_at = utcnow()
        out.append(r)

    save_registry(cfg, sources)
    return out


def declared_for(cfg: Config, manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """O que ESTE projeto exige: `ragx.toml` + `knowledge/base.json`.

    A leitura do manifesto mora aqui, e não em quem chama, porque `ragx.mcp`
    não pode tocar em arquivo — a regra do ADR-0006 vale também para o caminho
    de escrita novo.
    """
    out: list[dict[str, Any]] = [{"origin": o} for o in cfg.base.sources if o]
    path = manifest_path or (cfg.knowledge_dir / "base.json")
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return out
        # O manifesto carrega o commit exato de cada fonte: reproduz a base,
        # não só a origem.
        out += [s for s in data.get("sources", []) if s.get("origin")]
        out += [{"origin": o} for o in data.get("required", []) if o]
    return out


def sync_declared(cfg: Config, declared: list[dict[str, Any]]) -> list[BaseReport]:
    """Instala as fontes que o projeto exige e ainda não existem nesta máquina.

    É o que fecha o ciclo do multi-máquina: `knowledge/base.json` viaja no Git,
    o colega roda `ragx base sync` e fica com a mesma base — sem que um único
    byte do conteúdo de terceiro tenha entrado no repositório.
    """
    existentes = {s.name for s in load_registry(cfg)}
    out: list[BaseReport] = []
    for d in declared:
        origin = d.get("origin") or ""
        if not origin:
            continue
        nome = d.get("name") or _slug(origin)
        if nome in existentes:
            continue
        try:
            out.append(add(cfg, origin, name=nome, ref=d.get("ref")))
        except (RagxError, UsageError) as exc:
            r = BaseReport(name=nome)
            r.warnings.append(str(exc))
            out.append(r)
    return out


def remove(cfg: Config, name: str) -> bool:
    sources = load_registry(cfg)
    restantes = [s for s in sources if s.name != name]
    if len(restantes) == len(sources):
        return False
    shutil.rmtree(source_path(cfg, name), ignore_errors=True)
    save_registry(cfg, restantes)
    return True


def set_enabled(cfg: Config, name: str, enabled: bool) -> bool:
    sources = load_registry(cfg)
    achou = False
    for s in sources:
        if s.name == name:
            s.enabled = enabled
            achou = True
    if achou:
        save_registry(cfg, sources)
    return achou


def active_roots(cfg: Config) -> list[tuple[str, Path]]:
    """(nome, caminho) das fontes que ESTE projeto declara e estão instaladas.

    Instalar não basta: o projeto precisa declarar. A alternativa — indexar
    tudo que existe em `~/.ragx/base/` — faz `ragx base add` num projeto mudar
    em silêncio o índice de todos os outros da máquina, e ninguém descobre até
    a busca começar a devolver regra de outro contexto.

    Declarar em `ragx.toml` também é o que viaja no Git: o colega não precisa
    saber o que estava instalado na sua máquina.
    """
    declarados: set[str] = set()
    for d in declared_for(cfg):
        origem = str(d.get("origin") or "")
        if nome := d.get("name"):
            declarados.add(str(nome))
        if origem:
            declarados.add(_norm(origem))
            declarados.add(_slug(origem))
    if not declarados:
        return []

    out = []
    for s in load_registry(cfg):
        if not s.enabled or not (
            s.name in declarados
            or _norm(s.origin) in declarados
            or _slug(s.origin) in declarados
        ):
            continue
        p = source_path(cfg, s.name)
        if p.is_dir():
            out.append((s.name, p))
    return out


def is_base_path(rel_path: str) -> bool:
    return rel_path.startswith(f"{PREFIX}/")


def split_base_path(rel_path: str) -> tuple[str, str] | None:
    """`@base/agents/ai/guardrails.md` -> ('agents', 'ai/guardrails.md')."""
    if not is_base_path(rel_path):
        return None
    resto = rel_path[len(PREFIX) + 1 :]
    if "/" not in resto:
        return resto, ""
    nome, caminho = resto.split("/", 1)
    return nome, caminho


def _count(root: Path) -> int:
    return sum(1 for p in root.rglob("*") if p.is_file())
