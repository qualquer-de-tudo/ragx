# 28 — Identidade visual

A identidade **Grafo** ([ADR-0017](adr/ADR-0017-identidade-visual-grafo.md)): o conhecimento como rede, a
interface em preto e branco, a cor só no símbolo e nos estados.

## Símbolo

Quatro nós nos cantos, ligados por arestas a um anel central. Os nós são o que o RAGX lê (código, documentação,
contratos, histórico); o anel é o índice que os liga. As arestas param no anel: nada chega ao núcleo sem passar
pelo gate.

| Medida (grade 64) | Valor |
|---|---|
| Nós | centros em (12, 12), (52, 12), (12, 52), (52, 52); raio 6,5 |
| Arestas | traço 3,5, pontas redondas, a 45°, do nó até a borda do anel |
| Anel | centro (32, 32), raio 8, traço 4, sem preenchimento |

Desenhos por tamanho (gerados por `src/app/scripts/brand.py`, nunca à mão):

- **≥ 48 px:** o desenho completo.
- **32 px:** nós r 8, arestas 5, anel com traço 6.
- **≤ 16 px:** duas diagonais de ponta a ponta, traço 10, e o anel vira um ponto cheio.

Respiro mínimo: o diâmetro de um nó em volta da assinatura. Nunca girar, nunca trocar a cor dos nós pela do anel.

### Cores do símbolo

| Uso | Nós | Anel |
|---|---|---|
| Fundo escuro (padrão) | `#22D3EE` | `#A78BFA` |
| Fundo claro | `#0E7490` | `#6D4FD8` |
| Uma cor | branco `#F2F2F3` ou preto `#000000` nos dois | |

### Assinatura

`ragx` em minúsculas, Space Grotesk 700, tracking −0,045 em, ao lado do símbolo (altura do símbolo ≈ altura da
caixa-alta). Alternativa para peças grandes: o símbolo no lugar do `x` (`rag✕`). Textos corridos e o binário
continuam escrevendo RAGX ([ADR-0007](adr/ADR-0007-nome-do-binario.md)).

### Ícone de app

Tile preto `#000` com o símbolo colorido (padrão: instalador, barra de tarefas, extensão). Variantes: tile ciano
com símbolo preto e anel `#5B3FC4` (loja, site) e tile claro `#F4F4F5` com as cores de fundo claro (documentação).

## Interface

Preto e branco, como o painel já era. Os tokens vivem em `src/app/src/index.css` e são conferidos por
`contrast.test.ts` nos dois temas.

| Token | Escuro | Claro | Papel |
|---|---|---|---|
| `--bg` | `#000000` | `#F4F4F7` | fundo |
| `--surface` · `-2` · `-3` | `#0C0C0E` · `#141417` · `#1C1C20` | `#FFFFFF` · `#F0F0F4` · `#E6E6EC` | camadas |
| `--line` · `--line-strong` | `#242428` · `#34343A` | `#DCDCE3` · `#C4C4CD` | separação |
| `--ink` · `-2` · `-3` | `#F2F2F3` · `#A3A3AB` · `#8A8A93` | `#16161A` · `#4A4A54` · `#5F5F6A` | texto |
| `--accent` / `--accent-solid` | `#F2F2F3` | `#16161A` | ação e seleção |
| `--accent-ink` | `#000000` | `#FFFFFF` | texto sobre o acento |
| `--brand-node` · `--brand-ring` | `#22D3EE` · `#A78BFA` | `#0E7490` · `#6D4FD8` | só o símbolo |
| `--good` · `--warning` · `--critical` | verde · âmbar · vermelho | | só estado, sempre com forma |

**Tipografia:** Space Grotesk (interface e títulos), JetBrains Mono (caminhos, números, código, rótulos de estado
em caixa-alta). As duas vão no pacote do painel; nada é baixado.

## Componentes

Cada componente herda uma peça do símbolo.

| Componente | Forma | Estados |
|---|---|---|
| Botão **Nó** (primário) | pílula no acento; à esquerda uma porta escura com um anel, ligada ao rótulo por uma aresta | hover: aresta cresce, anel enche, halo; pressionado: aresta encolhe; ocupado: anel tracejado |
| Botão **Porta** (secundário) | borda de 1,5 px, raio 12, com um nó preso na borda esquerda | hover: borda e nó no acento |
| Botão **Relação** (fantasma) | só texto, seguido de uma aresta com seta | hover: texto no acento |
| Botão **Corte** (destrutivo) | borda vermelha, aresta partida antes do rótulo | |
| **Estado** | glifo do nó + aresta curta + rótulo em mono caixa-alta | cheio com anel (atualizado), meio (defasado), cortado com aresta tracejada (com problema), anel tracejado (indexando), vazio (sem uso) |
| **Tag** | caixa mono com marcador por tipo (● linguagem, ■ dado, ◆ serviço); várias se ligam por arestas | relação: duas entidades e o verbo na aresta |
| Interruptor **Conexão** | dois nós (o agente e o RAGX) e a aresta entre eles | desligado: aresta tracejada e nó vazio; ligado: aresta cheia |
| Abas **Trilha** | paradas de um caminho: nó por aba sobre uma linha | ativa: nó cheio com halo |
| Progresso **Aresta** | nó de partida, aresta que enche, nó de chegada | o nó de chegada só enche no fim |
| **Cartão** | borda de 1 px, raio 18, uma porta no canto superior esquerdo | o caminho do dado: gate → índice → vetores → agente, cada parada com o seu estado |

As pranchas de referência (marca, componentes e painel aplicado) estão no artefato de design da identidade; o
design system registrado é a fonte para quem desenhar telas novas.
