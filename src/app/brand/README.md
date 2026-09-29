# Marca do RAGX

Arquivos gerados por `scripts/brand.py`. Não edite à mão: mude a geometria no
script e rode de novo (`uv run python src/app/scripts/brand.py`, só precisa de
Pillow). O script também regrava `public/favicon.svg`, `build/icon.ico`,
`build/icon.png` e `src/components/brand/markPaths.ts`.

| Arquivo | Uso |
|---|---|
| `ragx-mark.svg` | Símbolo mestre: azul `#3b82f6`, núcleo `#f2f2f3`. Fundos escuros. |
| `ragx-mark-white.svg` / `ragx-mark-black.svg` | Uma cor só (impressão, fundos de foto, carimbos). |
| `ragx-mark-small.svg` | Desenho para 32 px ou menos: barras mais grossas, sem núcleo. |
| `ragx-app-icon.svg` / `-1024.png` | Ícone de app: tile azul, símbolo branco. |
| `ragx-lockup.svg` | Símbolo + "RAGX", texto claro (fundo escuro). |
| `ragx-lockup-dark-text.svg` | O mesmo com texto preto (fundo claro). |

O texto dos lockups usa a fonte do sistema (Segoe UI Variable Display). Para
uso fora do Windows (site, impressão), converta o texto em curvas num editor
vetorial.

## Regras de uso

- Respiro mínimo ao redor do símbolo: a largura de uma barra.
- Abaixo de 32 px, use sempre o desenho small; o núcleo e a abertura do
  desenho full fecham e viram borrão.
- Só duas cores: azul `#3b82f6` e branco/`#f2f2f3` (ou preto na versão
  monocromática). Sem gradiente, sombra, contorno ou rotação.
