"""PageRank sobre o grafo de referências, no nível do arquivo, e o repo map compacto (RAGX-0168).

O agente que chega num repositório não sabe quais arquivos importam. O mapa do Aider (PageRank sobre quem referencia quem)
dá essa ordem em ~1k tokens. Aqui o insumo é o grafo que o RAGX já tem: as relações de CÓDIGO (`calls`, `imports`, `extends`,
`implements`) projetadas para o nível do arquivo. Prosa (`documented_by`, `mentions`) NÃO pesa: documentação que cita um nome
não torna o arquivo central.

A armadilha: o extrator referencial casa uma chamada pelo NOME com qualquer entidade homônima (confiança 0,75). Sem um filtro,
`get`, `status` e `cfg` viram hubs falsos e o PageRank premia nomes genéricos, não arquivos centrais. Por isso a aresta cujo
destino tem um nome AMBÍGUO (mais de `AMBIGUOUS_NAME` entidades com o mesmo nome) é descartada, só aqui, no ranking.

Determinístico (o resultado entra em `knowledge/` versionado): rank arredondado a 6 casas, desempate pelo caminho, nenhum
timestamp. Sem dependência nova: iteração de potência em NumPy.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from ragx.config import Config
from ragx.storage.db import open_db
from ragx.tiers import Tier, classify
from ragx.tokens import count_tokens

#: tipos de relação que são CÓDIGO; o resto é prosa ou estrutura
CODE_RELATIONS = ("calls", "imports", "extends", "implements")
#: um nome com mais entidades que isto é genérico demais para dizer qual arquivo foi chamado (a tarefa propunha 5; medido neste repositório, com 3 `config_cmd.py` e `embeddings/base.py` deixam de ser hubs falsos de `get`/`set` e a cobertura sobe de 24 para 27 dos 114)
AMBIGUOUS_NAME = 3
_NAMED_TYPES = ("class", "function", "method", "file")


def file_rank(
    conn: sqlite3.Connection, damping: float = 0.85, iters: int = 50, reverse: float = 0.0
) -> dict[str, float]:
    """PageRank dos DOCUMENTOS (`document_id` -> rank), com rank arredondado a 6 casas. Vazio se não há arestas de código."""
    entidades = {
        r["id"]: (r["document_id"], r["name"].lower())
        for r in conn.execute("SELECT id, document_id, name FROM entities WHERE document_id IS NOT NULL")
    }
    homonimos = Counter(
        r["name"].lower()
        for r in conn.execute(
            f"SELECT name FROM entities WHERE type IN ({','.join('?' * len(_NAMED_TYPES))})", _NAMED_TYPES
        )
    )
    ph = ",".join("?" * len(CODE_RELATIONS))
    pares: dict[tuple[str, str], float] = defaultdict(float)
    for r in conn.execute(
        f"SELECT src_id, dst_id, weight, confidence FROM relations WHERE type IN ({ph})", CODE_RELATIONS
    ):
        origem, destino = entidades.get(r["src_id"]), entidades.get(r["dst_id"])
        if origem is None or destino is None or origem[0] == destino[0]:
            continue
        if homonimos[destino[1]] > AMBIGUOUS_NAME:
            continue  # nome genérico: a aresta é um palpite, não uma referência
        w = float(r["weight"]) * float(r["confidence"])
        pares[(origem[0], destino[0])] += w
        if reverse:  # quem ORQUESTRA (chama muito) também importa: a aresta volta com peso menor
            pares[(destino[0], origem[0])] += w * reverse
    if not pares:
        return {}

    docs = sorted({d for par in pares for d in par})
    idx = {d: i for i, d in enumerate(docs)}
    n = len(docs)
    src = np.array([idx[a] for a, _ in pares], dtype=np.int64)
    dst = np.array([idx[b] for _, b in pares], dtype=np.int64)
    peso = np.array(list(pares.values()), dtype=np.float64)
    saida = np.bincount(src, weights=peso, minlength=n)
    # o mesmo vetor `pares` tem ordem de inserção determinística (a consulta não tem ORDER BY, então ordenamos por índice)
    ordem = np.lexsort((dst, src))
    src, dst, peso = src[ordem], dst[ordem], peso[ordem]
    norm = np.where(saida[src] > 0, peso / np.where(saida[src] > 0, saida[src], 1.0), 0.0)
    sem_saida = saida == 0

    rank = np.full(n, 1.0 / n)
    for _ in range(iters):
        massa_solta = rank[sem_saida].sum()  # nó sem saída redistribui a massa para todos
        entra = np.bincount(dst, weights=rank[src] * norm, minlength=n)
        novo = (1.0 - damping) / n + damping * (entra + massa_solta / n)
        if np.abs(novo - rank).sum() < 1e-10:
            rank = novo
            break
        rank = novo
    return {d: round(float(rank[i]), 6) for d, i in idx.items()}


@dataclass(frozen=True)
class MapEntry:
    path: str
    rank: float
    symbols: tuple[str, ...]


def ranked_files(conn: sqlite3.Connection, reverse: float = 0.0) -> list[MapEntry]:
    """Os arquivos de CÓDIGO da camada `knowledge` por rank decrescente, com até 3 símbolos de maior grau de entrada."""
    ranks = file_rank(conn, reverse=reverse)
    if not ranks:
        return []
    docs = {r["id"]: r["rel_path"] for r in conn.execute("SELECT id, rel_path FROM documents WHERE doc_kind = 'code'")}
    entrada: Counter[str] = Counter()
    for r in conn.execute(
        "SELECT dst_id, COUNT(*) AS n FROM relations WHERE type IN ('calls','imports','extends','implements') GROUP BY dst_id"
    ):
        entrada[r["dst_id"]] = int(r["n"])
    simbolos: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in conn.execute(
        "SELECT id, document_id, name FROM entities WHERE type IN ('class','function') AND document_id IS NOT NULL"
    ):
        if not r["name"].startswith("_"):
            simbolos[r["document_id"]].append((entrada[r["id"]], r["name"]))
    out: list[MapEntry] = []
    for doc_id, rank in ranks.items():
        path = docs.get(doc_id)
        if path is None or classify(path) is not Tier.KNOWLEDGE or path.startswith(("knowledge/", "vscode-plugin/node_modules/")):
            continue
        melhores = sorted(simbolos.get(doc_id, []), key=lambda t: (-t[0], t[1]))[:3]
        out.append(MapEntry(path, rank, tuple(nome for _, nome in melhores)))
    return sorted(out, key=lambda e: (-e.rank, e.path))


def repo_map(cfg: Config, tokens: int = 600, files: int | None = None) -> list[dict[str, object]]:
    """O mapa: os N melhores arquivos de código, cada um `{path, rank, symbols}`, cortado pelo orçamento de tokens.

    O custo de cada linha é o de `caminho: Simbolo1, Simbolo2` (o formato de leitura); o corte é pelo `count_tokens` do conjunto.
    Grafo vazio devolve lista vazia.
    """
    with open_db(cfg.db_path, read_only=True) as conn:
        entradas = ranked_files(conn)
    return to_dicts(select_by_budget(entradas, tokens, files))


def select_by_budget(entradas: list[MapEntry], tokens: int, files: int | None = None) -> list[MapEntry]:
    """Os primeiros `entradas` que cabem em `tokens` (e em `files`, se dado), contando a linha de leitura de cada um."""
    escolhidos: list[MapEntry] = []
    gasto = 0
    for e in entradas:
        if files is not None and len(escolhidos) >= files:
            break
        custo = count_tokens(format_line(e)) + 1  # +1: a quebra de linha
        if gasto + custo > tokens:
            break
        escolhidos.append(e)
        gasto += custo
    return escolhidos


def to_dicts(entradas: list[MapEntry]) -> list[dict[str, object]]:
    return [{"path": e.path, "rank": e.rank, "symbols": list(e.symbols)} for e in entradas]


def format_line(e: MapEntry) -> str:
    return f"{e.path}: {', '.join(e.symbols)}" if e.symbols else e.path
