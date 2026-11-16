# Marca do RAGX

Identidade Grafo ([ADR-0017](../../../docs/adr/ADR-0017-identidade-visual-grafo.md), guia em
[docs/28-identidade-visual.md](../../../docs/28-identidade-visual.md)). Arquivos gerados por `scripts/brand.py`.
Não edite à mão: mude a geometria no script e rode de novo (`uv run python src/app/scripts/brand.py`, só precisa
de Pillow). O script também regrava `public/favicon.svg`, `build/icon.ico`, `build/icon.png` e
`src/components/brand/markPaths.ts`.

| Arquivo | Uso |
|---|---|
| `ragx-mark.svg` / `-1024.png` | Símbolo mestre: nós ciano `#22d3ee`, anel violeta `#a78bfa`. Fundos escuros. |
| `ragx-mark-light-bg.svg` | Para fundos claros: nós `#0e7490`, anel `#6d4fd8`. |
| `ragx-mark-white.svg` / `ragx-mark-black.svg` | Uma cor só (impressão, fundos de foto, carimbos). |
| `ragx-mark-small.svg` | Desenho para ~32 px: nós, arestas e anel mais grossos. |
| `ragx-mark-tiny.svg` | Desenho para 16 px: duas diagonais e o anel como ponto cheio. |
| `ragx-app-icon.svg` / `-1024.png` | Ícone de app padrão: tile preto, símbolo colorido. |
| `ragx-app-icon-cyan.svg` / `-light.svg` | Variantes: tile ciano (loja, site) e tile claro (documentação). |
| `ragx-lockup.svg` | Símbolo + `ragx`, texto claro (fundo escuro). |
| `ragx-lockup-dark-text.svg` | O mesmo com texto preto e as cores de fundo claro. |

O texto dos lockups pede Space Grotesk 700. Para uso fora do painel (site, impressão), converta o texto em curvas
num editor vetorial.

## Regras de uso

- Respiro mínimo em volta da assinatura: o diâmetro de um nó.
- Abaixo de 40 px use o desenho small; abaixo de 20 px, o tiny.
- Cor só no símbolo: os nós e o anel nunca trocam de cor entre si. Sem gradiente, sombra, contorno ou rotação.
