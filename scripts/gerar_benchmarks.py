"""Gera `docs/27-benchmarks.md` a partir de `src/app/src/data/benchmarks.json`, a fonte única dos Benchmarks do painel.

    uv run python scripts/gerar_benchmarks.py           # reescreve a página
    uv run python scripts/gerar_benchmarks.py --check   # sai com 1 se a página não bate com o JSON

Para publicar um resultado novo: acrescente o ponto às métricas (ou uma métrica nova), a entrada na linha do tempo e rode isto.
`tests/unit/test_benchmarks_doc.py` falha se a página e o JSON divergirem.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
JSON = RAIZ / "src" / "app" / "src" / "data" / "benchmarks.json"
DOC = RAIZ / "docs" / "27-benchmarks.md"

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def num(v: float) -> str:
    """7684 -> "7.684", 1.77 -> "1,77", 40.0 -> "40" (no máximo 2 casas, como o painel)."""
    texto = f"{round(v, 2):,.2f}".rstrip("0").rstrip(".")
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def valor(v: float | None, unidade: str) -> str:
    return "indefinido" if v is None else f"{num(v)} {unidade}"


def data(iso: str) -> str:
    a, m, d = (int(x) for x in iso.split("-"))
    return f"{d} de {MESES[m - 1]} de {a}"


def variacao(m: dict) -> tuple[float | None, float | None, float | None]:
    antes = m["points"][0]["value"]
    depois = m["points"][-1]["value"]
    if len(m["points"]) < 2 or antes in (None, 0):
        return antes, depois, None
    return antes, depois, (depois - antes) / antes * 100


def pct(p: float | None) -> str:
    if p is None:
        return "—"
    absoluto = abs(p)
    n = round(absoluto) if absoluto >= 10 else round(absoluto, 1)
    return f"{'−' if p < 0 else '+'}{num(n)}%"


def r2(n: float) -> str:
    return f"{n:.2f}".replace(".", ",")


def gerar(d: dict) -> str:
    metricas = d["metrics"]
    com_meta = [m for m in metricas if m.get("goal")]
    atingidas = sum(1 for m in com_meta if m["goal"]["met"])
    linhas: list[str] = [
        "# 27 — Benchmarks",
        "",
        "> Gerado de `src/app/src/data/benchmarks.json` por `scripts/gerar_benchmarks.py`; não edite à mão. O painel mostra os mesmos números em",
        "> **Como funciona → Benchmarks**.",
        "",
        d["intro"],
        "",
        f"**{atingidas} de {len(com_meta)} metas atingidas.** Atualizado em {data(d['updated'])}. Máquina: {d['environment']}.",
        "",
        "Quando a linha de base era uma faixa (por exemplo, 3 a 5 s), a tabela usa o **melhor extremo** dela: a melhora mostrada é a menor possível.",
        "",
    ]
    grupos: dict[str, list[dict]] = {}
    for m in metricas:
        grupos.setdefault(m["group"], []).append(m)
    for nome, ms in grupos.items():
        linhas += [f"## {nome}", "", "| Métrica | Antes | Agora | Variação | Meta |", "|---|---:|---:|---:|---|"]
        for m in ms:
            antes, depois, p = variacao(m)
            u = m["unit"]
            meta = "—"
            if m.get("goal"):
                sinal = "até" if m["lowerIsBetter"] else "de"
                meta = f"{sinal} {valor(m['goal']['value'], u)}: {'atingida' if m['goal']['met'] else '**não atingida**'}"
            antes_txt = valor(antes, u) if antes is not None else f"indefinido ({m['points'][0].get('note', 'sem medição')})"
            linhas.append(f"| {m['name']} | {antes_txt} | **{valor(depois, u)}** | {pct(p)} | {meta} |")
        linhas.append("")
        for m in ms:
            if m.get("caveat"):
                linhas.append(f"- **{m['name']}.** {m['caveat']}")
        linhas.append("")
    linhas += ["### Como cada número foi medido", ""]
    for m in metricas:
        linhas.append(f"- **{m['name']}**: {m['detail']}. `{m['method']}`")
    ab = d["ab"]
    linhas += ["", f"## {ab['title']}", "", f"**{ab['verdict']}**", "", ab["setup"], "",
          "| Medida | Sem RAGX | Com RAGX | Leitura |", "|---|---:|---:|---|"]
    for r in ab["rows"]:
        linhas.append(f"| {r['label']} | {r['without']} | {r['with']} | {r['note']} |")
    linhas += ["", ab["reading"], "", f"Comando: `{ab['method']}`", ""]
    r = d["retrieval"]
    linhas += [f"## {r['title']}", "", r["intro"], "",
          "| Modelo de embedding | 132 consultas à mão | 134 do histórico do git | Latência da consulta |", "|---|---:|---:|---:|"]
    for row in r["rows"]:
        linhas.append(
            f"| {row['model']} | **{r2(row['manual'])}** ({r2(row['manualCi'][0])} a {r2(row['manualCi'][1])}) "
            f"| **{r2(row['git'])}** ({r2(row['gitCi'][0])} a {r2(row['gitCi'][1])}) | {num(row['queryMs'])} ms |"
        )
    linhas += ["", r["note"], "", f"Método: `{r['method']}`", "", "## Linha do tempo", ""]
    por_id = {m["id"]: m for m in metricas}
    for e in reversed(d["timeline"]):
        linhas += [f"### {data(e['date'])} · versão {e['version']}: {e['title']}", "", e["text"], ""]
        for mid in e["metrics"]:
            m = por_id.get(mid)
            if m:
                antes, depois, _ = variacao(m)
                a = "sem base" if antes is None else valor(antes, m["unit"])
                linhas.append(f"- {m['name']}: {a} → **{valor(depois, m['unit'])}**")
        if e["metrics"]:
            linhas.append("")
    linhas += [
        "## Como acrescentar um resultado",
        "",
        "1. Meça com o comando do método e confira que o número é **desta** versão (não de memória).",
        "2. Em `src/app/src/data/benchmarks.json`: acrescente um `snapshot` (se for uma versão nova), o ponto em cada métrica medida (ou uma métrica nova) e a entrada em `timeline`. "
        "Meta não atingida leva `\"met\": false` e um `caveat`; resultado inconclusivo diz que é inconclusivo.",
        "3. `uv run python scripts/gerar_benchmarks.py` e commit dos dois arquivos.",
        "",
    ]
    return "\n".join(linhas)


def main() -> int:
    texto = gerar(json.loads(JSON.read_text(encoding="utf-8")))
    if "--check" in sys.argv:
        atual = DOC.read_text(encoding="utf-8") if DOC.is_file() else ""
        if atual != texto:
            print("docs/27-benchmarks.md está diferente do JSON: rode `uv run python scripts/gerar_benchmarks.py`.")
            return 1
        return 0
    DOC.write_text(texto, encoding="utf-8", newline="\n")
    print(f"escrito {DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
