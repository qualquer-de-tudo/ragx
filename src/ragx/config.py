"""Configuração com cascata completa.

Precedência: flags CLI > RAGX_* > ragx.toml do projeto > config do usuário > defaults.
Ver docs/15-configuracao.md.

Nenhuma chave de API é lida do TOML — credencial vem só de variável de ambiente.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CONFIG_NAME = "ragx.toml"
STATE_DIR = ".ragx"
KNOWLEDGE_DIR = "knowledge"


class ProjectCfg(BaseModel):
    name: str = "projeto"
    id: str = ""
    kind: str = "other"
    visibility: str = "workspace"  # workspace | private


class IndexCfg(BaseModel):
    include_unknown: bool = False
    max_file_bytes: int = 1_048_576
    follow_symlinks: bool = False
    jobs: int = 0
    batch_size: int = 200
    exclude: list[str] = Field(default_factory=list)
    include: list[str] = Field(default_factory=list)


class ChunkCfg(BaseModel):
    max_tokens: int = 512
    min_tokens: int = 24
    overlap: int = 0


class SecurityCfg(BaseModel):
    policy: str = "strict"  # strict | balanced
    min_entropy: float = 3.0
    allow_remote_llm: bool = False
    scan_content: bool = True
    disabled_rules: list[str] = Field(default_factory=list)


class EmbeddingCfg(BaseModel):
    provider: str = "ollama"  # ollama | fastembed | hashing
    model: str = "nomic-embed-text"
    dim: int = 768
    base_url: str = "http://localhost:11434"
    batch: int = 32
    timeout_s: int = 60
    cache: bool = True
    normalize: bool = True
    versioned_dim: int = 256
    versioned_quant: str = "int8"
    rescore: bool = True


class SearchCfg(BaseModel):
    default_mode: str = "hybrid"
    limit: int = 10
    rrf_k: int = 60
    weight_semantic: float = 1.0
    weight_keyword: float = 0.8
    candidate_factor: int = 3
    max_per_document: int = 3


class GraphCfg(BaseModel):
    enabled: bool = True
    max_depth: int = 2
    max_nodes: int = 200
    max_fanout: int = 25
    decay: float = 0.6
    semantic: bool = False


class ContextCfg(BaseModel):
    default_tokens: int = 3000
    dedup_threshold: float = 0.93
    mmr_lambda: float = 0.7
    compress: bool = True
    reserve_ratio: float = 0.05
    min_sources: int = 3


class SizeCfg(BaseModel):
    max_artifact_bytes: int = 20_971_520
    warn_total_bytes: int = 104_857_600
    fail_total_bytes: int = 262_144_000
    max_chunks: int = 500_000
    shards: int = 16


class FederationCfg(BaseModel):
    enabled: bool = True
    auto_build: bool = True
    min_confidence: float = 0.6


class HubCfg(BaseModel):
    path: str = "~/.ragx/hub"
    auto_sync: bool = False
    external_penalty: float = 0.85
    max_projects: int = 50


class BaseCfg(BaseModel):
    """Conhecimento base — fontes externas válidas para todos os projetos."""

    enabled: bool = True
    # Origens que ESTE projeto exige. Versionado no ragx.toml: quem clona o
    # repositório roda `ragx base sync` e obtém a mesma base.
    sources: list[str] = Field(default_factory=list)
    max_file_bytes: int = 262_144


class McpCfg(BaseModel):
    read_only: bool = True
    allow_index: bool = False
    log_queries: bool = False
    rate_per_min: int = 60
    max_response_bytes: int = 1_048_576
    # Escrita no ÍNDICE (reindexar, sincronizar, reconstruir grafo). Nunca dá
    # ao agente acesso ao filesystem nem afrouxa o Security Gate. Ver ADR-0012.
    allow_write: bool = False
    write_timeout_s: int = 900


class TasksCfg(BaseModel):
    """Orquestracao. Ver docs/21-orquestracao-de-tarefas.md."""

    enabled: bool = True
    # Generoso: o agente pode levar minutos numa tarefa real. Lease curto demais
    # faz a tarefa voltar para a fila enquanto alguem ainda trabalha nela.
    lease_seconds: int = 900
    max_retries: int = 3
    backoff: list[int] = Field(default_factory=lambda: [30, 60, 300, 900, 1800])
    max_concurrency: int = 1
    context_tokens: int = 4000
    worker_id: str = ""


class WatchCfg(BaseModel):
    enabled: bool = False
    interval_s: float = 2.0
    debounce_s: float = 1.5
    full_sync_every: int = 50  # ciclos de mudança até um `sync` completo
    max_batch: int = 500


class SyncCfg(BaseModel):
    auto_dictionary: bool = True
    auto_federation: bool = True
    rehydrate_strict: bool = False
    git_hooks: bool = False


class LogCfg(BaseModel):
    level: str = "info"
    dir: str = ".ragx/logs"
    retain_days: int = 14


class Config(BaseModel):
    project: ProjectCfg = Field(default_factory=ProjectCfg)
    index: IndexCfg = Field(default_factory=IndexCfg)
    chunk: ChunkCfg = Field(default_factory=ChunkCfg)
    security: SecurityCfg = Field(default_factory=SecurityCfg)
    embedding: EmbeddingCfg = Field(default_factory=EmbeddingCfg)
    search: SearchCfg = Field(default_factory=SearchCfg)
    graph: GraphCfg = Field(default_factory=GraphCfg)
    context: ContextCfg = Field(default_factory=ContextCfg)
    size: SizeCfg = Field(default_factory=SizeCfg)
    federation: FederationCfg = Field(default_factory=FederationCfg)
    hub: HubCfg = Field(default_factory=HubCfg)
    mcp: McpCfg = Field(default_factory=McpCfg)
    sync: SyncCfg = Field(default_factory=SyncCfg)
    base: BaseCfg = Field(default_factory=BaseCfg)
    tasks: TasksCfg = Field(default_factory=TasksCfg)
    watch: WatchCfg = Field(default_factory=WatchCfg)
    log: LogCfg = Field(default_factory=LogCfg)

    # não serializado; preenchido na carga
    root: Path = Field(default_factory=Path, exclude=True)
    has_config_file: bool = Field(default=False, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR

    @property
    def db_path(self) -> Path:
        return self.state_dir / "knowledge.db"

    @property
    def knowledge_dir(self) -> Path:
        return self.root / KNOWLEDGE_DIR

    @property
    def hub_dir(self) -> Path:
        return Path(os.path.expanduser(self.hub.path))


def find_root(start: Path | None = None) -> tuple[Path, bool]:
    """Sobe do cwd até achar ragx.toml. Sem ele, usa o cwd."""
    cur = Path(start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / CONFIG_NAME).is_file():
            return candidate, True
    return cur, False


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _from_env() -> dict[str, Any]:
    """RAGX_<SECAO>_<CHAVE>. Chaves compostas usam o nome do campo com _."""
    sections = set(Config.model_fields) - {"root", "has_config_file"}
    out: dict[str, Any] = {}
    for raw_key, raw_val in os.environ.items():
        if not raw_key.startswith("RAGX_"):
            continue
        rest = raw_key[5:].lower()
        for sec in sections:
            prefix = sec + "_"
            if rest.startswith(prefix):
                field = rest[len(prefix) :]
                model = Config.model_fields[sec].annotation
                if field in getattr(model, "model_fields", {}):
                    out.setdefault(sec, {})[field] = _coerce(model, field, raw_val)
                break
    if "OLLAMA_HOST" in os.environ:
        out.setdefault("embedding", {}).setdefault("base_url", os.environ["OLLAMA_HOST"])
    return out


def _coerce(model: Any, field: str, value: str) -> Any:
    ann = model.model_fields[field].annotation
    if ann is bool:
        return value.strip().lower() in ("1", "true", "yes", "on")
    if ann is int:
        return int(value)
    if ann is float:
        return float(value)
    if ann is list[str]:
        return [v for v in value.split(",") if v]
    return value


def load_config(
    start: Path | None = None, overrides: dict[str, Any] | None = None
) -> Config:
    root, found = find_root(start)
    data: dict[str, Any] = {}

    user_cfg = Path(os.path.expanduser("~/.config/ragx/config.toml"))
    if user_cfg.is_file():
        data = _deep_merge(data, tomllib.loads(user_cfg.read_text(encoding="utf-8")))

    if found:
        data = _deep_merge(data, tomllib.loads((root / CONFIG_NAME).read_bytes().decode("utf-8")))

    data = _deep_merge(data, _from_env())
    if overrides:
        data = _deep_merge(data, overrides)

    cfg = Config(**data)
    cfg.root = root
    cfg.has_config_file = found
    return cfg
