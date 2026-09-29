"""Gera os ativos de marca do RAGX a partir de uma única geometria.

O símbolo é um "X" de duas barras a 45° cuja cruz tem uma abertura em
losango (o foco: só o contexto relevante passa), com um losango menor no
centro (o trecho recuperado). A geometria é calculada aqui, não desenhada à
mão, para que SVG, PNG e .ico saiam idênticos e simétricos.

Duas versões de desenho:
- "full" (>= 48 px): X, abertura e núcleo.
- "small" (<= 32 px): barras mais grossas, abertura menor e sem núcleo; a
  versão full encolhida fecha a abertura e vira borrão nesses tamanhos.

Uso (só Pillow): python scripts/brand.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
PUBLIC = ROOT / "public"
BUILD = ROOT / "build"

BLUE = "#3b82f6"
INK = "#f2f2f3"
WHITE = "#ffffff"
BLACK = "#000000"

Point = tuple[float, float]

# Proporções em relação à meia-largura S do símbolo (o símbolo ocupa [-S, S]²).
# bar: meia-largura horizontal da barra (k = h·√2); hole/core: distância do
# centro ao vértice do losango.
VARIANTS = {
    "full": {"bar": 0.50, "hole": 0.30, "core": 0.13},
    "small": {"bar": 0.56, "hole": 0.24, "core": 0.0},
}


def x_outline(s: float, k: float) -> list[Point]:
    """Contorno do X: duas barras a 45° (meia-largura horizontal k), recortadas
    pelo quadrado [-s, s]². As pontas ficam retas, alinhadas à caixa."""
    return [
        (0, k), (s - k, s), (s, s), (s, s - k),
        (k, 0), (s, -(s - k)), (s, -s), (s - k, -s),
        (0, -k), (-(s - k), -s), (-s, -s), (-s, -(s - k)),
        (-k, 0), (-s, s - k), (-s, s), (-(s - k), s),
    ]  # fmt: skip


def diamond(d: float) -> list[Point]:
    return [(0, d), (d, 0), (0, -d), (-d, 0)]


def glyph(variant: str, s: float) -> tuple[list[Point], list[Point], list[Point] | None]:
    p = VARIANTS[variant]
    core = diamond(p["core"] * s) if p["core"] else None
    return x_outline(s, p["bar"] * s), diamond(p["hole"] * s), core


# -- SVG -----------------------------------------------------------------


def _path(points: list[Point], cx: float, cy: float, reverse: bool = False) -> str:
    pts = list(reversed(points)) if reverse else points
    # y do SVG cresce para baixo.
    coords = " ".join(f"{cx + x:.2f} {cy - y:.2f}".replace(".00", "") for x, y in pts)
    return f"M{coords}Z"


def svg_glyph(variant: str, size: int, s: float, fg: str, core_fg: str) -> str:
    c = size / 2
    outline, hole, core = glyph(variant, s)
    # Abertura como subcaminho de sentido oposto: com fill-rule nonzero vira furo.
    d = _path(outline, c, c) + _path(hole, c, c, reverse=True)
    out = f'<path fill="{fg}" d="{d}"/>'
    if core:
        out += f'<path fill="{core_fg}" d="{_path(core, c, c)}"/>'
    return out


def svg_doc(size: int, body: str, title: str = "RAGX") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}" role="img" aria-label="{title}">'
        f"<title>{title}</title>{body}</svg>\n"
    )


def svg_lockup(text_fill: str) -> str:
    """Símbolo + "RAGX" lado a lado. O texto usa a fonte de display do painel;
    para uso fora do sistema (impressão, site), converter o texto em curvas."""
    h, w = 320, 1100
    s = 120  # símbolo com 240 de altura, ~1,3x a altura das maiúsculas
    # svg_glyph centra em (h/2, h/2); desloca para x = 40 + s.
    body = (
        f'<g transform="translate({40 + s - h / 2:g} 0)">{svg_glyph("full", h, s, BLUE, INK)}</g>'
    )
    text = (
        f'<text x="{40 + 2 * s + 64}" y="252" fill="{text_fill}" font-size="262" '
        'font-weight="600" letter-spacing="10" '
        "font-family=\"'Segoe UI Variable Display', 'Segoe UI', Inter, system-ui, sans-serif\">"
        "RAGX</text>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
        f'height="{h}" role="img" aria-label="RAGX"><title>RAGX</title>{body}{text}</svg>\n'
    )


def tile_rect(size: int, fill: str) -> str:
    # Squircle aproximado: quadrado com raio de 22,5%.
    r = size * 0.225
    return f'<rect width="{size}" height="{size}" rx="{r:g}" fill="{fill}"/>'


# -- raster --------------------------------------------------------------

SUPER = 8  # supersampling: desenha 8x maior e reduz com LANCZOS


def _poly(draw: ImageDraw.ImageDraw, points: list[Point], c: float, fill: int | str) -> None:
    draw.polygon([(c + x, c - y) for x, y in points], fill=fill)


def raster_glyph(
    variant: str,
    size: int,
    scale: float,
    fg: str,
    core_fg: str,
    tile: str | None = None,
    bg: str | None = None,
) -> Image.Image:
    """scale: fração do canvas ocupada pelo símbolo (2S / size)."""
    n = size * SUPER
    c = n / 2
    s = n * scale / 2
    img = Image.new("RGBA", (n, n), bg or (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if tile:
        draw.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * 0.225, fill=tile)

    outline, hole, core = glyph(variant, s)
    mask = Image.new("L", (n, n), 0)
    mdraw = ImageDraw.Draw(mask)
    _poly(mdraw, outline, c, 255)
    _poly(mdraw, hole, c, 0)
    img.paste(Image.new("RGBA", (n, n), fg), (0, 0), mask)
    if core:
        _poly(draw, core, c, core_fg)
    return img.resize((size, size), Image.LANCZOS)


# Tamanho do símbolo dentro de cada formato.
MARK_SCALE = 0.62  # símbolo sozinho, transparente
TILE_SCALE = 0.50  # dentro do tile do ícone de app


def app_icon(size: int) -> Image.Image:
    variant = "small" if size <= 32 else "full"
    # Em 16 px o tile ocupa tudo e o símbolo precisa de mais área para respirar.
    scale = 0.62 if size <= 16 else 0.56 if size <= 32 else TILE_SCALE
    return raster_glyph(variant, size, scale, WHITE, WHITE, tile=BLUE)


def write_react_paths() -> None:
    """Paths do símbolo (viewBox 0 0 64 64, sem margem) para o componente
    RagxMark do painel: a interface usa a mesma geometria dos ícones."""
    lines = [
        "// Gerado por scripts/brand.py; não editar à mão.",
        "export const MARK_VIEWBOX = '0 0 64 64'",
    ]
    for variant in ("full", "small"):
        outline, hole, core = glyph(variant, 32)
        body = _path(outline, 32, 32) + _path(hole, 32, 32, reverse=True)
        core_d = _path(core, 32, 32) if core else ""
        lines.append(
            f"export const MARK_{variant.upper()} = {{ body: '{body}', core: '{core_d}' }}"
        )
    (ROOT / "src" / "components" / "brand" / "markPaths.ts").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    BRAND.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)

    canvas = 1024
    s_mark = canvas * MARK_SCALE / 2
    s_tile = canvas * TILE_SCALE / 2

    files = {
        # Mestre: azul sobre transparente, núcleo claro. Para fundos escuros.
        "ragx-mark.svg": svg_doc(canvas, svg_glyph("full", canvas, s_mark, BLUE, INK)),
        # Monocromáticos (núcleo na mesma cor).
        "ragx-mark-white.svg": svg_doc(canvas, svg_glyph("full", canvas, s_mark, WHITE, WHITE)),
        "ragx-mark-black.svg": svg_doc(canvas, svg_glyph("full", canvas, s_mark, BLACK, BLACK)),
        # Versão de tamanho pequeno (<= 32 px).
        "ragx-mark-small.svg": svg_doc(
            canvas, svg_glyph("small", canvas, canvas * 0.8 / 2, BLUE, BLUE)
        ),
        # Ícone de app: tile azul, símbolo branco.
        "ragx-app-icon.svg": svg_doc(
            canvas, tile_rect(canvas, BLUE) + svg_glyph("full", canvas, s_tile, WHITE, WHITE)
        ),
        # Símbolo + nome: para fundo escuro e para fundo claro.
        "ragx-lockup.svg": svg_lockup(INK),
        "ragx-lockup-dark-text.svg": svg_lockup(BLACK),
    }
    for name, content in files.items():
        (BRAND / name).write_text(content, encoding="utf-8")

    # Favicon do painel: desenho small, sem margem desperdiçada, sobre transparente
    # (a aba do navegador/Electron pode ser clara ou escura; o azul funciona nas duas).
    (PUBLIC / "favicon.svg").write_text(
        svg_doc(64, svg_glyph("small", 64, 64 * 0.9 / 2, BLUE, BLUE)), encoding="utf-8"
    )

    write_react_paths()

    raster_glyph("full", 1024, MARK_SCALE, BLUE, INK).save(BRAND / "ragx-mark-1024.png")
    big = app_icon(1024)
    big.save(BRAND / "ragx-app-icon-1024.png")
    big.resize((512, 512), Image.LANCZOS).save(BUILD / "icon.png")

    # .ico com cada tamanho rasterizado no próprio tamanho (não reduzido do 256).
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [app_icon(n) for n in sizes]
    frames[-1].save(
        BUILD / "icon.ico", format="ICO", sizes=[(n, n) for n in sizes], append_images=frames[:-1]
    )

    print("ok:", ", ".join(sorted(files)), "+ favicon.svg, icon.ico, icon.png")


if __name__ == "__main__":
    main()
