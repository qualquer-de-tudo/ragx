"""Quanto do tempo de uma sessão do Claude Code vai para o RAGX.

O servidor MCP responde em milissegundos; o que pesa é o que acontece em volta:
cada ferramenta chamada é uma volta a mais do modelo. Por isso a medição parte
dos transcripts do Claude Code (`~/.claude/projects/*/*.jsonl`), que carimbam
cada mensagem, e não só do tempo que o servidor diz ter gasto.

O tempo de uma sessão é dividido em três, sempre pela diferença entre carimbos
consecutivos:

- **humano** — a pessoa lendo e digitando. Não entra em nada;
- **modelo** — o intervalo até uma mensagem do assistente. Vira "do RAGX" quando
  aquele turno emitiu uma chamada a `mcp__ragx__*`;
- **ferramenta** — o intervalo até o resultado. Vira "do RAGX" quando todas as
  ferramentas daquele resultado são do RAGX.

É uma estimativa, e as regras abaixo escolhem errar para menos: chamadas em
paralelo com ferramenta de fora não são atribuídas ao RAGX, e pausas longas
(máquina dormindo) contam como ociosidade.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

RAGX_PREFIX = "mcp__ragx__"

#: Intervalo acima disto é ociosidade (sono da máquina, sessão largada), não trabalho.
IDLE_GAP_MS = 15 * 60 * 1000


@dataclass(slots=True)
class SessionPerf:
    session_id: str
    project: str
    started: datetime | None = None
    calls: int = 0
    tool_ms: int = 0
    model_ms: int = 0
    active_ms: int = 0
    per_tool: dict[str, list[int]] = field(default_factory=dict)

    @property
    def overhead_ms(self) -> int:
        return self.tool_ms + self.model_ms

    @property
    def share(self) -> float:
        return self.overhead_ms / self.active_ms if self.active_ms else 0.0


@dataclass(frozen=True, slots=True)
class ToolStats:
    n: int
    p50: float
    p95: float


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _blocks(record: dict[str, Any]) -> list[dict[str, Any]]:
    content = (record.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict)]


def _read(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("type") in ("user", "assistant"):
                records.append(rec)
    return records


def _ms(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() * 1000)


def analyze_session(path: Path, project: str | None = None) -> SessionPerf:
    perf = SessionPerf(session_id=path.stem, project=project or path.parent.name)
    ragx_ids: dict[str, tuple[str, datetime]] = {}
    other_ids: set[str] = set()
    prev: datetime | None = None
    last_msg: str | None = None  # id da mensagem do turno em curso
    turn_ragx = False
    turn_gap = 0

    def close_turn() -> None:
        nonlocal turn_ragx, turn_gap
        if turn_gap:
            perf.active_ms += turn_gap
            if turn_ragx:
                perf.model_ms += turn_gap
        turn_ragx, turn_gap = False, 0

    for rec in _read(path):
        ts = _parse_ts(rec.get("timestamp"))
        if ts is None:
            continue
        if perf.started is None:
            perf.started = ts
        gap = _ms(prev, ts) if prev else 0
        idle = gap > IDLE_GAP_MS or gap < 0
        blocks = _blocks(rec)

        if rec["type"] == "assistant":
            msg_id = (rec.get("message") or {}).get("id")
            if msg_id is not None and msg_id == last_msg:
                # Mais um bloco da mesma mensagem: o turno só cresce.
                turn_gap += 0 if idle else max(gap, 0)
            else:
                close_turn()
                last_msg = msg_id
                turn_gap = 0 if idle else max(gap, 0)
                turn_ragx = False
            for b in blocks:
                if b.get("type") != "tool_use":
                    continue
                name = str(b.get("name", ""))
                if name.startswith(RAGX_PREFIX):
                    turn_ragx = True
                    perf.calls += 1
                    ragx_ids[str(b.get("id"))] = (name, ts)
                else:
                    other_ids.add(str(b.get("id")))
        else:
            close_turn()
            last_msg = None
            results = [b for b in blocks if b.get("type") == "tool_result"]
            if not results:
                prev = ts  # prompt humano: o intervalo até aqui não é de trabalho
                continue
            if not idle:
                perf.active_ms += max(gap, 0)
                ids = [str(b.get("tool_use_id")) for b in results]
                if all(i in ragx_ids for i in ids):
                    perf.tool_ms += max(gap, 0)
            for i in (str(b.get("tool_use_id")) for b in results):
                if i in ragx_ids:
                    name, used_at = ragx_ids.pop(i)
                    wall = _ms(used_at, ts)
                    if 0 <= wall <= IDLE_GAP_MS:
                        perf.per_tool.setdefault(name, []).append(wall)
        prev = ts

    close_turn()
    return perf


def load_sessions(
    root: Path, since: datetime | None = None, project: str | None = None
) -> list[SessionPerf]:
    """Analisa toda sessão sob `root` (a pasta `projects` do Claude Code)."""
    sessions: list[SessionPerf] = []
    if not root.is_dir():
        return sessions
    for path in sorted(root.glob("*/*.jsonl")):
        if project and project.lower() not in path.parent.name.lower():
            continue
        perf = analyze_session(path)
        if perf.started is None:
            continue
        if since is not None and perf.started < since:
            continue
        sessions.append(perf)
    return sessions


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def server_stats(path: Path) -> dict[str, ToolStats]:
    """Tempo que o SERVIDOR diz ter gasto, por ferramenta (`.ragx/logs/mcp.jsonl`)."""
    if not path.is_file():
        return {}
    by_tool: dict[str, list[float]] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
                by_tool.setdefault(str(e["tool"]), []).append(float(e["ms"]))
            except (ValueError, KeyError, TypeError):
                continue
    return {
        t: ToolStats(len(v), statistics.median(v), _percentile(v, 0.95))
        for t, v in by_tool.items()
    }


def tool_wall_stats(sessions: list[SessionPerf]) -> dict[str, ToolStats]:
    merged: dict[str, list[float]] = {}
    for s in sessions:
        for tool, values in s.per_tool.items():
            merged.setdefault(tool, []).extend(values)
    return {
        t: ToolStats(len(v), statistics.median(v), _percentile(v, 0.95)) for t, v in merged.items()
    }
