"""O índice está em dia com o working tree? Só contagens, nunca caminhos."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ragx import gitinfo
from ragx.config import Config


def _epoch(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()


def _uncommitted(cfg: Config, conn: Any, finished_at: str) -> int | None:
    paths = gitinfo.changed_paths(cfg.root)
    if paths is None:
        return None
    # finished_at tem resolução de segundo (truncado). Sem a folga de 1 s, um
    # arquivo salvo no mesmo segundo do fim da indexação, e JÁ indexado,
    # contaria como alterado depois dela.
    limit = _epoch(finished_at) + 1.0
    count = 0
    for rel in paths:
        full = cfg.root / rel
        try:
            if full.stat().st_mtime > limit:
                count += 1
        except FileNotFoundError:
            known = conn.execute(
                "SELECT 1 FROM documents WHERE rel_path = ?", (rel,)
            ).fetchone()
            if known:
                count += 1
    return count


def compute(cfg: Config, conn: Any, last_run: dict[str, Any] | None) -> dict[str, Any]:
    state = gitinfo.read_state(cfg.root)
    current = None if state is None else {
        "branch": state.branch, "commit": state.commit, "dirty": state.dirty,
    }
    if last_run is None or not last_run.get("finished_at"):
        return {"state": "unknown", "current": current, "reasons": []}

    reasons: list[dict[str, Any]] = []
    if state is not None:
        old_branch = last_run.get("git_branch")
        if old_branch and state.branch and old_branch != state.branch:
            reasons.append(
                {"kind": "branch_changed", "indexed": old_branch, "current": state.branch}
            )
        old_commit = last_run.get("git_commit")
        if old_commit and old_commit != state.commit:
            reasons.append({
                "kind": "commits_since_index",
                "count": gitinfo.commits_between(cfg.root, old_commit, state.commit),
            })
        changed = _uncommitted(cfg, conn, last_run["finished_at"])
        if changed:
            reasons.append({"kind": "uncommitted_changes", "count": changed})

    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    embedded = conn.execute("SELECT COUNT(DISTINCT chunk_id) FROM embeddings").fetchone()[0]
    if chunks > embedded:
        reasons.append({"kind": "pending_embeddings", "count": chunks - embedded})

    verdict = "stale" if reasons else "fresh" if state is not None else "unknown"
    return {"state": verdict, "current": current, "reasons": reasons}
