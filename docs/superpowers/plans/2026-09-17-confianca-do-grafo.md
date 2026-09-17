# Confiança do grafo (EXTRACTED/INFERRED) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the confidence/provenance data the graph already computes (`Entity.confidence`, `Entity.source`, `Relation.confidence`, `Relation.source` — see `src/ragx/graph/store.py:39-67`) actually visible end-to-end: a plain-language tier in the MCP `get_entity` response, in the docs, and in the VS Code extension (which currently drops `confidence` entirely when mapping the MCP response).

**Architecture:** No new extraction logic and no schema change — `confidence: float` and `source: str` already exist on both `Entity` and `Relation`, populated by `structural.py` (source="structural", confidence=1.0 implicit default) and `reference.py` (source="reference", confidence 0.6–0.8). The gap is purely in what gets *surfaced*: `mcp/server.py:get_entity` already returns `confidence` (a bare float) but not `source`, and the VS Code extension's `McpClient.ts`/`CliClient.ts` mapping functions silently drop `confidence` when building their typed `GraphNode`/`GraphEdge`/`EntityDetail` objects. This plan adds one small pure function — `confidence_tier(confidence: float) -> str` mapping `>= 0.95` to `"extracted"` and anything lower to `"inferred"` — and threads it through the MCP response, the CLI, the docs, and the two VS Code client adapters (plus their existing test suite).

**Tech Stack:** Python (`src/ragx/graph`, `src/ragx/mcp`), TypeScript (`vscode-plugin/src/rag`), `pytest`, `vitest` (already the plugin's test runner — see `vscode-plugin/tests/unit/mcp-limits.test.ts`).

**Spec:** This plan's Architecture section. Ground truth for current behavior: `src/ragx/graph/store.py:39-67` (data model), `src/ragx/graph/extractors/structural.py` (confidence=1.0 default, source="structural"), `src/ragx/graph/extractors/reference.py:110` (confidence=0.75/0.6, source="reference"), `src/ragx/mcp/server.py:302-337` (`get_entity`, currently exposes `confidence` but not `source`), `vscode-plugin/src/rag/types.ts:154-189` (`GraphNode`/`GraphEdge`/`EntityDetail` — no `confidence` field today), `vscode-plugin/src/rag/McpClient.ts:335-364` (`entity()` — drops `rel.confidence` from the API response when mapping).

## Global Constraints

- No new dependency, no schema migration — `confidence`/`source` columns already exist in the `entities`/`relations` tables (`graph/store.py`'s `upsert_entities`/`upsert_relations` already write them).
- The tier boundary (`>= 0.95`) must be a single named constant/function, not a magic number repeated in three languages — Python owns the source of truth; the TypeScript side receives the already-computed `tier` string from the server, it does not recompute the threshold.
- Keep the existing raw `confidence` float in every response that has it today — the tier is additive, not a replacement (some caller might already depend on the float, e.g. `graph_cmd.py:60`).

---

### Task 1: `confidence_tier()` and wire it into `get_entity`

**Files:**
- Modify: `src/ragx/graph/store.py` (add the function near the `Entity`/`Relation` dataclasses)
- Modify: `src/ragx/mcp/server.py:302-337` (`get_entity`)
- Test: `tests/unit/test_graph_confidence.py`

**Interfaces:**
- Consumes: nothing new — reads the existing `Entity.confidence`/`.source` and `Relation.confidence`/`.source` fields, and the `neighborhood()` result shape from `src/ragx/graph/traversal.py` (each edge dict already has `confidence` per `store.py:neighbors()`'s SQL `r.*` select, which includes the `source` column too since `relations` table has it — confirm by reading the row, it is a `sqlite3.Row` from `SELECT r.*, ...`).
- Produces: `confidence_tier(confidence: float) -> str` (module-level function in `ragx.graph.store`, returns `"extracted"` or `"inferred"`), used by Task 2 (CLI) and referenced by Task 3 (docs). `get_entity`'s response gains `"source"` and `"tier"` keys on the entity dict and on every item in `relations`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_graph_confidence.py`:

```python
from __future__ import annotations

import pytest

from ragx.graph.store import confidence_tier

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "confidence,expected",
    [
        (1.0, "extracted"),
        (0.95, "extracted"),
        (0.94, "inferred"),
        (0.75, "inferred"),
        (0.6, "inferred"),
        (0.0, "inferred"),
    ],
)
def test_confidence_tier_boundary(confidence: float, expected: str) -> None:
    assert confidence_tier(confidence) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_graph_confidence.py -v`
Expected: FAIL with `ImportError: cannot import name 'confidence_tier'`

- [ ] **Step 3: Write minimal implementation**

In `src/ragx/graph/store.py`, add right after the `Relation` dataclass (after line 67, before `@dataclass class GraphStats`):

```python
# Fronteira entre "lido direto da fonte" e "resolvido por heurística/inferência" —
# mesma distinção que o Graphify chama de EXTRACTED/INFERRED. `structural.py`
# grava confidence=1.0 (hierarquia já está no chunk, sem ambiguidade);
# `reference.py` grava 0.6-0.8 (regex/heurística pode errar). 0.95 separa os
# dois sem depender de o valor exato ser 1.0 (float de ponto flutuante).
_EXTRACTED_THRESHOLD = 0.95


def confidence_tier(confidence: float) -> str:
    return "extracted" if confidence >= _EXTRACTED_THRESHOLD else "inferred"
```

In `src/ragx/mcp/server.py`, modify `get_entity` (currently lines 302-337):

```python
    def get_entity(self, name: str, depth: int = 1) -> dict[str, Any]:
        blocked = self._guard()
        if blocked:
            return blocked
        from ragx.graph.store import GraphStore, confidence_tier
        from ragx.graph.traversal import neighborhood
        from ragx.storage.db import open_db

        with open_db(self.cfg.db_path, read_only=True) as conn:
            store = GraphStore(conn)
            found = store.find(name)
            if not found:
                return err("not_found", f"entidade não encontrada: {safe_echo(name)}")
            target = found[0]
            edges = neighborhood(store, target["id"], depth=min(max(depth, 1), 2))
        return cap(
            ok(
                {
                    "project": self.project,
                    "entity": {
                        "id": target["id"], "type": target["type"], "name": target["name"],
                        "qualified_name": target["qualified_name"],
                        "confidence": target["confidence"],
                        "source": target["source"],
                        "tier": confidence_tier(target["confidence"]),
                    },
                    "relations": [
                        {
                            "direction": e["direction"], "type": e["type"],
                            "other": e["other_name"], "other_type": e["other_type"],
                            "confidence": e["confidence"],
                            "source": e["source"],
                            "tier": confidence_tier(e["confidence"]),
                        }
                        for e in edges
                    ],
                }
            ),
            self.cfg.mcp.max_response_bytes,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_graph_confidence.py -v`
Expected: 6 passed

- [ ] **Step 5: Verify `get_entity` still works end to end**

Run: `uv run pytest tests/integration -k graph -v` (existing graph integration tests must still pass — this confirms `e["source"]` exists on the `neighborhood()` row and doesn't `KeyError`)
Expected: all pass. If any test fails with `KeyError: 'source'`, check `src/ragx/graph/traversal.py`'s `neighborhood()` — it must select `r.*` (it does, via `GraphStore.neighbors()`'s `SELECT r.*, ...` at `store.py:210-222`), so `source` is already in every edge row; this step should pass without code changes.

- [ ] **Step 6: Commit**

```bash
git add src/ragx/graph/store.py src/ragx/mcp/server.py tests/unit/test_graph_confidence.py
git commit -m "feat(graph): expoe source e tier extracted/inferred no get_entity"
```

---

### Task 2: Mostrar a fonte no `ragx graph show` (CLI)

**Files:**
- Modify: `src/ragx/cli/commands/graph_cmd.py:60` (the existing confidence-dimming line)
- Test: existing CLI graph tests — locate with `grep -rl "graph.*show\|graph_cmd" tests/`

**Interfaces:**
- Consumes: `confidence_tier` from Task 1 (`ragx.graph.store.confidence_tier`).
- Produces: nothing new consumed elsewhere — this is a leaf/display-only task.

- [ ] **Step 1: Read the current line in context**

Open `src/ragx/cli/commands/graph_cmd.py` around line 60 and read 10 lines before/after to see the exact f-string this line feeds into, before editing (the plan does not paste that surrounding context because it must match the file's actual current state exactly, not a guess — read it first).

- [ ] **Step 2: Add the tier next to the existing confidence display**

Change:

```python
conf = "" if r["confidence"] >= 1.0 else f"  [dim]{r['confidence']:.2f}[/]"
```

to:

```python
from ragx.graph.store import confidence_tier  # add to the file's top-level imports, not inline

...

conf = (
    ""
    if r["confidence"] >= 1.0
    else f"  [dim]{r['confidence']:.2f} ({confidence_tier(r['confidence'])})[/]"
)
```

(Keep the import at the top of the file with the other imports — this plan shows it inline only to make the diff obvious; place it correctly per the file's existing import block.)

- [ ] **Step 3: Run the existing graph CLI tests**

Run: `uv run pytest -k graph_cmd -v` (adjust the `-k` filter after Step 1's `grep` confirms the actual test file/function names)
Expected: all pass (this change is additive text, no behavior change to what's asserted structurally — if an existing test asserts exact string output containing the old format, update that assertion to match the new suffix)

- [ ] **Step 4: Commit**

```bash
git add src/ragx/cli/commands/graph_cmd.py
git commit -m "feat(cli): ragx graph show mostra o tier extracted/inferred junto da confianca"
```

---

### Task 3: Documentar o modelo de confiança

**Files:**
- Modify: `docs/06-grafo.md` (add a "Modelo de confiança" section)
- Modify: `docs/09-mcp.md` (note the new `source`/`tier` fields on `get_entity`'s consulta table row)

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing.

- [ ] **Step 1: Add to `docs/06-grafo.md`**

Add a new section (placing it near the existing `source = "semantic"` mentions at lines 91 and 157 — read those two lines' surrounding context first, then insert right after the second one so the section flows from the existing camadas explanation):

```markdown
## Modelo de confiança

Toda entidade e relação carrega `confidence` (float) e `source` (a camada que
a gerou). `confidence_tier()` (`src/ragx/graph/store.py`) resume isso num
rótulo em linguagem natural, a mesma distinção que ferramentas como o
Graphify chamam de `EXTRACTED`/`INFERRED`:

| `source` | `confidence` típico | `tier` |
|---|---|---|
| `structural` (Camada 1 — hierarquia já está no chunk) | 1.0 | `extracted` |
| `reference` (Camada 2 — regex/heurística) | 0.6 – 0.8 | `inferred` |
| `semantic` (Camada 3, custa dinheiro — ver nota acima) | variável | depende |

`get_entity` (MCP) e `ragx graph show` (CLI) expõem os três campos. Um agente
que recebe `tier: "inferred"` sabe que aquela relação foi deduzida, não lida
direto da fonte — trate com a mesma cautela que trataria um `INFERRED` de
qualquer outra ferramenta de grafo.
```

- [ ] **Step 2: Update `docs/09-mcp.md`**

In the "Consulta" table, the `get_entity` row currently reads (approximately) `| \`get_entity\` | \`name\` ou \`id\` | entidade + relações diretas | Fase 3 |` — find the exact current row text and append a footnote-style clause to the "Saída" column: `entidade + relações diretas (com \`confidence\`, \`source\` e \`tier\`)`.

- [ ] **Step 3: Commit**

```bash
git add docs/06-grafo.md docs/09-mcp.md
git commit -m "docs: documenta o modelo de confianca extracted/inferred do grafo"
```

---

### Task 4: Parar de descartar `confidence` na extensão VS Code

**Files:**
- Modify: `vscode-plugin/src/rag/types.ts:154-189` (`GraphNode`, `GraphEdge`, `EntityDetail.relations`)
- Modify: `vscode-plugin/src/rag/McpClient.ts:282-364` (`graph()` and `entity()`)
- Modify: `vscode-plugin/src/rag/CliClient.ts:219-275` (`graph()` and `entity()` — the CLI transport has no `confidence` in its `ragx graph show --json` output today; see Step 4 note below)
- Test: `vscode-plugin/tests/unit/graph-confidence.test.ts`

**Interfaces:**
- Consumes: the MCP `get_entity` response shape from Task 1 (`entity.confidence`, `entity.source`, `entity.tier`, and the same three fields on each item of `relations`).
- Produces: `GraphNode.tier?: 'extracted' | 'inferred'`, `EntityDetail.relations[].tier?: 'extracted' | 'inferred'`, consumed by whatever UI component renders the graph explorer (out of scope for this plan — rendering is a follow-up; this task only stops the data from being thrown away).

- [ ] **Step 1: Write the failing test**

Create `vscode-plugin/tests/unit/graph-confidence.test.ts`, mirroring the mocking pattern from `vscode-plugin/tests/unit/mcp-limits.test.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from 'vitest';

let ultimaResposta: Record<string, unknown> = {};

vi.mock('@modelcontextprotocol/sdk/client/stdio.js', () => ({
  StdioClientTransport: class {
    stderr = undefined;
  },
}));

vi.mock('@modelcontextprotocol/sdk/client/index.js', () => ({
  Client: class {
    async connect(): Promise<void> {}
    async close(): Promise<void> {}
    async listTools(): Promise<{ tools: Array<{ name: string }> }> {
      return { tools: ['get_playbook', 'get_entity'].map((name) => ({ name })) };
    }
    async callTool(req: {
      name: string;
      arguments: Record<string, unknown>;
    }): Promise<{ content: Array<{ type: string; text: string }> }> {
      const corpo = req.name === 'get_playbook' ? { project: 'ragx' } : ultimaResposta;
      return { content: [{ type: 'text', text: JSON.stringify({ ok: true, data: corpo }) }] };
    }
  },
}));

const { McpRagClient } = await import('../../src/rag/McpClient');

describe('confidence e tier na entidade e nas relacoes', () => {
  it('nao descarta confidence/source/tier vindos do MCP', async () => {
    ultimaResposta = {
      entity: {
        id: 'e1', name: 'AuthService', type: 'class', qualified_name: 'auth.py::AuthService',
        confidence: 1.0, source: 'structural', tier: 'extracted',
      },
      relations: [
        {
          type: 'uses', direction: 'out', target: 'Redis', target_id: 'e2',
          confidence: 0.75, source: 'reference', tier: 'inferred',
        },
      ],
      sources: [],
    };
    const client = new McpRagClient({ command: 'ragx', args: ['mcp'], cwd: '/proj' });
    await client.connect();
    const r = await client.entity('AuthService');
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.data.entity.tier).toBe('extracted');
    expect(r.data.relations[0].tier).toBe('inferred');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `vscode-plugin/`): `npm test -- graph-confidence`
Expected: FAIL — `r.data.entity.tier` is `undefined` (the type doesn't have `tier` and the mapping code doesn't read it)

- [ ] **Step 3: Add the fields to `types.ts`**

In `vscode-plugin/src/rag/types.ts`, modify `GraphNode` (lines 154-164):

```typescript
export interface GraphNode {
  id: string;
  name: string;
  type: string;
  qualifiedName?: string | null;
  documentPath?: string | null;
  summary?: string | null;
  /** Quantos vizinhos existem além dos já carregados. Move a expansão progressiva. */
  degree?: number;
  expanded?: boolean;
  /** `undefined` quando a fonte não tem o dado (ex.: transporte CLI antigo). */
  confidence?: number;
  source?: string;
  tier?: 'extracted' | 'inferred';
}
```

Modify `GraphEdge` (lines 166-171):

```typescript
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
  confidence?: number;
  tier?: 'extracted' | 'inferred';
}
```

Modify `EntityDetail` (lines 180-189):

```typescript
export interface EntityDetail {
  entity: GraphNode;
  relations: Array<{
    type: string;
    direction: 'out' | 'in';
    target: string;
    targetId?: string;
    confidence?: number;
    source?: string;
    tier?: 'extracted' | 'inferred';
  }>;
  sources: Array<{ path: string; line?: number }>;
}
```

- [ ] **Step 4: Stop dropping the fields in `McpClient.ts`**

Modify `entity()` (currently `vscode-plugin/src/rag/McpClient.ts:335-364`) — the `relacoes` mapping and the `entity:` object both need the new fields:

```typescript
  async entity(name: string): Promise<RagResult<EntityDetail>> {
    const r = await this.call<Json>('get_entity', { name, depth: 1 });
    if (!r.ok) return propagate<EntityDetail>(r);
    const e = (r.data?.entity as Json) ?? {};
    const relacoes = ((r.data?.relations as Json[]) ?? []).map((rel) => ({
      type: str(rel.type) || 'related',
      direction: (str(rel.direction) === 'in' ? 'in' : 'out') as 'in' | 'out',
      target: str(rel.target) || str(rel.name) || '?',
      targetId: str(rel.target_id) || undefined,
      confidence: typeof rel.confidence === 'number' ? rel.confidence : undefined,
      source: str(rel.source) || undefined,
      tier: (rel.tier === 'extracted' || rel.tier === 'inferred') ? rel.tier : undefined,
    }));
    const fontes: Array<{ path: string; line?: number }> = [];
    const doc = str(e.document_path);
    if (doc) fontes.push({ path: doc, line: num(e.line) || undefined });
    for (const s of (r.data?.sources as Json[]) ?? []) {
      const p = str(s.path) || str(s.document_path);
      if (p) fontes.push({ path: p, line: num(s.line) || undefined });
    }
    return done({
      entity: {
        id: str(e.id) || name,
        name: str(e.name) || name,
        type: str(e.type) || 'entity',
        qualifiedName: str(e.qualified_name) || null,
        documentPath: doc || null,
        summary: str(e.summary) || null,
        confidence: typeof e.confidence === 'number' ? e.confidence : undefined,
        source: str(e.source) || undefined,
        tier: (e.tier === 'extracted' || e.tier === 'inferred') ? e.tier : undefined,
      },
      relations: relacoes,
      sources: fontes,
    });
  }
```

Also replace the `graph()` method (currently `vscode-plugin/src/rag/McpClient.ts:282-333`) in full:

```typescript
  async graph(
    entity: string,
    depth: number,
    maxNodes: number,
  ): Promise<RagResult<GraphSlice>> {
    const r = await this.call<Json>('get_entity', { name: entity, depth });
    if (!r.ok) return propagate<GraphSlice>(r);

    const centro = (r.data?.entity as Json) ?? {};
    const relacoes = (r.data?.relations as Json[]) ?? [];

    const nodes = new Map<string, GraphNode>();
    const centroId = str(centro.id) || str(centro.name) || entity;
    nodes.set(centroId, {
      id: centroId,
      name: str(centro.name) || entity,
      type: str(centro.type) || 'entity',
      qualifiedName: str(centro.qualified_name) || null,
      documentPath: str(centro.document_path) || null,
      summary: str(centro.summary) || null,
      expanded: true,
      confidence: typeof centro.confidence === 'number' ? centro.confidence : undefined,
      source: str(centro.source) || undefined,
      tier: (centro.tier === 'extracted' || centro.tier === 'inferred') ? centro.tier : undefined,
    });

    const edges: GraphEdge[] = [];
    for (const rel of relacoes) {
      if (nodes.size >= maxNodes) break;
      const alvo = str(rel.target) || str(rel.dst) || str(rel.name);
      if (!alvo) continue;
      const alvoId = str(rel.target_id) || alvo;
      if (!nodes.has(alvoId)) {
        nodes.set(alvoId, {
          id: alvoId,
          name: alvo,
          type: str(rel.target_type) || 'entity',
          expanded: false,
        });
      }
      const saida = str(rel.direction) !== 'in';
      edges.push({
        source: saida ? centroId : alvoId,
        target: saida ? alvoId : centroId,
        type: str(rel.type) || 'related',
        weight: typeof rel.weight === 'number' ? rel.weight : undefined,
        confidence: typeof rel.confidence === 'number' ? rel.confidence : undefined,
        tier: (rel.tier === 'extracted' || rel.tier === 'inferred') ? rel.tier : undefined,
      });
    }

    return done({
      nodes: [...nodes.values()],
      edges,
      truncated: relacoes.length > 0 && nodes.size >= maxNodes,
    });
  }
```

Note: `rel` (an edge in `get_entity`'s response) does not carry the *neighbor entity's own* confidence — only the edge's. The neighbor `GraphNode` built inside the loop (`nodes.set(alvoId, {...})`) intentionally has no `confidence`/`tier` here; it stays `undefined` until that neighbor is itself expanded as a center (a future `get_entity` call on it). Do not invent a value for it.

- [ ] **Step 5: Run test to verify it passes**

Run (from `vscode-plugin/`): `npm test -- graph-confidence`
Expected: 1 passed

- [ ] **Step 6: `CliClient.ts` — confirm no regression, no new capability**

`ragx graph show --json` (the command `CliClient.ts:219-244`'s `graph()` calls) does not emit `confidence` in its JSON output today — that's a CLI output-format gap, not something this plan's Task 1/2 changed (Task 2 only changed the human-readable Rich table, not `--json`). Do **not** invent fields the CLI doesn't send. Run the plugin's existing CLI-transport graph test (if any — `grep -rl "CliClient" vscode-plugin/tests/unit/`) to confirm it still passes unchanged; if none exists, this step is a no-op and the CLI transport simply falls back to `tier: undefined`, which the optional `?` fields from Step 3 already handle safely.

- [ ] **Step 7: Full plugin suite + typecheck**

Run (from `vscode-plugin/`): `npm run typecheck && npm test`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add vscode-plugin/src/rag/types.ts vscode-plugin/src/rag/McpClient.ts vscode-plugin/tests/unit/graph-confidence.test.ts
git commit -m "fix(vscode): para de descartar confidence/source/tier do get_entity"
```
