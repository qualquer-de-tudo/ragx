"""Gera os ativos de marca do RAGX a partir de uma única geometria (identidade Grafo, ADR-0017).

O símbolo são quatro nós nos cantos ligados por arestas a um anel central, numa grade de 64 unidades: os nós
são o que o RAGX lê, o anel é o índice que os liga, e as arestas param no anel. A geometria é calculada aqui,
não desenhada à mão, para que SVG, PNG, .ico e o componente React saiam idênticos.

Três desenhos, por tamanho (docs/28-identidade-visual.md):
- "full" (>= 48 px): nós r 6,5, arestas 3,5, anel r 8 com traço 4.
- "small" (~32 px): nós, arestas e anel mais grossos.
- "tiny" (<= 16 px): duas diagonais de ponta a ponta e o anel vira um ponto cheio.

Uso (só Pillow): python scripts/brand.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
PUBLIC = ROOT / "public"
BUILD = ROOT / "build"

# Cores do símbolo. A interface é preto e branco; cor só aqui e nos estados.
NODE = "#22d3ee"
RING = "#a78bfa"
NODE_LIGHT = "#0e7490"
RING_LIGHT = "#6d4fd8"
RING_ON_CYAN = "#5b3fc4"
INK = "#f2f2f3"
WHITE = "#ffffff"
BLACK = "#000000"
PAPER = "#f4f4f5"

GRID = 64
CENTER = 32.0
CORNERS = ((12.0, 12.0), (52.0, 12.0), (12.0, 52.0), (52.0, 52.0))

VARIANTS = {
    "full": {"node": 6.5, "edge": 3.5, "ring": 8.0, "ring_w": 4.0, "dot": 0.0},
    "small": {"node": 8.0, "edge": 5.0, "ring": 8.0, "ring_w": 6.0, "dot": 0.0},
    "tiny": {"node": 0.0, "edge": 10.0, "ring": 0.0, "ring_w": 0.0, "dot": 11.0},
}


def edges(variant: str) -> list[tuple[float, float, float, float]]:
    """Arestas (x1, y1, x2, y2). Full e small param na linha do anel; tiny cruza de canto a canto."""
    if variant == "tiny":
        return [(12, 12, 52, 52), (52, 12, 12, 52)]
    r = VARIANTS[variant]["ring"]
    out = []
    for x, y in CORNERS:
        d = math.hypot(CENTER - x, CENTER - y)
        k = (d - r) / d
        out.append((x, y, round(x + (CENTER - x) * k, 2), round(y + (CENTER - y) * k, 2)))
    return out


# -- SVG -----------------------------------------------------------------


def svg_glyph(variant: str, node: str, ring: str) -> str:
    """O símbolo em unidades da grade (0..64). Quem usa posiciona com um `<g transform>`."""
    v = VARIANTS[variant]
    parts = [
        f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{node}" '
        f'stroke-width="{v["edge"]:g}" stroke-linecap="round"/>'
        for x1, y1, x2, y2 in edges(variant)
    ]
    if v["node"]:
        parts += [f'<circle cx="{x:g}" cy="{y:g}" r="{v["node"]:g}" fill="{node}"/>' for x, y in CORNERS]
    if v["ring"]:
        parts.append(
            f'<circle cx="32" cy="32" r="{v["ring"]:g}" fill="none" stroke="{ring}" stroke-width="{v["ring_w"]:g}"/>'
        )
    if v["dot"]:
        parts.append(f'<circle cx="32" cy="32" r="{v["dot"]:g}" fill="{ring}"/>')
    return "".join(parts)


def placed(variant: str, node: str, ring: str, size: float, box: float, x: float = 0, y: float = 0) -> str:
    """Símbolo de lado `box` centrado num quadrado de lado `size` a partir de (x, y)."""
    k = box / GRID
    off_x = x + (size - box) / 2
    off_y = y + (size - box) / 2
    return f'<g transform="translate({off_x:g} {off_y:g}) scale({k:g})">{svg_glyph(variant, node, ring)}</g>'


def svg_doc(w: int, h: int, body: str, title: str = "RAGX") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" role="img" aria-label="{title}">'
        f"<title>{title}</title>{body}</svg>\n"
    )


def svg_lockup(text_fill: str, node: str, ring: str) -> str:
    """Símbolo + "ragx". O texto pede Space Grotesk 700; fora do painel (impressão, site), converter em curvas."""
    h, w = 320, 1000
    mark = placed("full", node, ring, h, 240, 0, 0)
    text = (
        f'<text x="300" y="232" fill="{text_fill}" font-size="250" font-weight="700" letter-spacing="-11" '
        "font-family=\"'Space Grotesk', 'Segoe UI', system-ui, sans-serif\">ragx</text>"
    )
    return svg_doc(w, h, mark + text)


def tile_rect(size: int, fill: str) -> str:
    return f'<rect width="{size}" height="{size}" rx="{size * TILE_RADIUS:g}" fill="{fill}"/>'


# -- raster --------------------------------------------------------------

SUPER = 8  # supersampling: desenha 8x maior e reduz com LANCZOS
TILE_RADIUS = 0.25


def raster_glyph(
    variant: str, size: int, box_frac: float, node: str, ring: str, tile: str | None = None
) -> Image.Image:
    """`box_frac`: fração do lado ocupada pela grade de 64 do símbolo."""
    n = size * SUPER
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if tile:
        draw.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * TILE_RADIUS, fill=tile)
    k = n * box_frac / GRID
    o = (n - GRID * k) / 2

    def pt(x: float, y: float) -> tuple[float, float]:
        return (o + x * k, o + y * k)

    def disc(x: float, y: float, r: float, fill: str) -> None:
        cx, cy = pt(x, y)
        draw.ellipse((cx - r * k, cy - r * k, cx + r * k, cy + r * k), fill=fill)

    v = VARIANTS[variant]
    for x1, y1, x2, y2 in edges(variant):
        draw.line([pt(x1, y1), pt(x2, y2)], fill=node, width=max(1, round(v["edge"] * k)))
        disc(x1, y1, v["edge"] / 2, node)  # pontas redondas
        disc(x2, y2, v["edge"] / 2, node)
    if v["node"]:
        for x, y in CORNERS:
            disc(x, y, v["node"], node)
    if v["ring"]:
        cx, cy = pt(CENTER, CENTER)
        outer = (v["ring"] + v["ring_w"] / 2) * k
        draw.ellipse((cx - outer, cy - outer, cx + outer, cy + outer), outline=ring, width=round(v["ring_w"] * k))
    if v["dot"]:
        disc(CENTER, CENTER, v["dot"], ring)
    return img.resize((size, size), Image.LANCZOS)


def variant_for(size: int) -> str:
    return "tiny" if size <= 20 else "small" if size <= 40 else "full"


def app_icon(size: int) -> Image.Image:
    """Tile preto com o símbolo colorido. Nos tamanhos pequenos o símbolo ocupa mais do tile."""
    frac = 0.86 if size <= 20 else 0.78 if size <= 40 else 0.68
    return raster_glyph(variant_for(size), size, frac, NODE, RING, tile=BLACK)


def write_react_geometry() -> None:
    """Geometria do símbolo para o componente RagxMark: a interface desenha o mesmo que os ícones."""
    lines = ["// Gerado por scripts/brand.py; não editar à mão.", "export const MARK_VIEWBOX = '0 0 64 64'"]
    for variant, v in VARIANTS.items():
        arestas = ", ".join(f"[{x1:g}, {y1:g}, {x2:g}, {y2:g}]" for x1, y1, x2, y2 in edges(variant))
        nos = ", ".join(f"[{x:g}, {y:g}]" for x, y in CORNERS) if v["node"] else ""
        lines.append(
            f"export const MARK_{variant.upper()} = {{ edges: [{arestas}], edge: {v['edge']:g}, "
            f"nodes: [{nos}], node: {v['node']:g}, ring: {v['ring']:g}, ringWidth: {v['ring_w']:g}, dot: {v['dot']:g} }}"
        )
    (ROOT / "src" / "components" / "brand" / "markPaths.ts").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    BRAND.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    c = 1024
    files = {
        # Mestre: para fundos escuros.
        "ragx-mark.svg": svg_doc(c, c, placed("full", NODE, RING, c, c * 0.8)),
        # Para fundos claros.
        "ragx-mark-light-bg.svg": svg_doc(c, c, placed("full", NODE_LIGHT, RING_LIGHT, c, c * 0.8)),
        # Uma cor.
        "ragx-mark-white.svg": svg_doc(c, c, placed("full", INK, INK, c, c * 0.8)),
        "ragx-mark-black.svg": svg_doc(c, c, placed("full", BLACK, BLACK, c, c * 0.8)),
        # Desenhos de tamanho pequeno.
        "ragx-mark-small.svg": svg_doc(c, c, placed("small", NODE, RING, c, c * 0.9)),
        "ragx-mark-tiny.svg": svg_doc(c, c, placed("tiny", NODE, RING, c, c * 0.9)),
        # Ícones de app: preto (padrão), ciano (loja, site) e claro (documentação).
        "ragx-app-icon.svg": svg_doc(c, c, tile_rect(c, BLACK) + placed("full", NODE, RING, c, c * 0.68)),
        "ragx-app-icon-cyan.svg": svg_doc(
            c, c, tile_rect(c, NODE) + placed("full", BLACK, RING_ON_CYAN, c, c * 0.68)
        ),
        "ragx-app-icon-light.svg": svg_doc(
            c, c, tile_rect(c, PAPER) + placed("full", NODE_LIGHT, RING_LIGHT, c, c * 0.68)
        ),
        # Símbolo + assinatura: fundo escuro e fundo claro.
        "ragx-lockup.svg": svg_lockup(INK, NODE, RING),
        "ragx-lockup-dark-text.svg": svg_lockup(BLACK, NODE_LIGHT, RING_LIGHT),
    }
    for name, content in files.items():
        (BRAND / name).write_text(content, encoding="utf-8")

    # Favicon: tile preto com o desenho small. A aba pode ser clara ou escura; o tile resolve as duas.
    (PUBLIC / "favicon.svg").write_text(
        svg_doc(64, 64, tile_rect(64, BLACK) + placed("small", NODE, RING, 64, 64 * 0.78)), encoding="utf-8"
    )

    write_react_geometry()

    raster_glyph("full", 1024, 0.8, NODE, RING).save(BRAND / "ragx-mark-1024.png")
    big = app_icon(1024)
    big.save(BRAND / "ragx-app-icon-1024.png")
    big.resize((512, 512), Image.LANCZOS).save(BUILD / "icon.png")

    # .ico com cada tamanho rasterizado no próprio tamanho (não reduzido do 256).
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [app_icon(n) for n in sizes]
    frames[-1].save(BUILD / "icon.ico", format="ICO", sizes=[(n, n) for n in sizes], append_images=frames[:-1])

    print("ok:", ", ".join(sorted(files)), "+ favicon.svg, icon.ico, icon.png, markPaths.ts")


if __name__ == "__main__":
    main()
