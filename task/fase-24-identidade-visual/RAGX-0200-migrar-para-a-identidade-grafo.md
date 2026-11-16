# RAGX-0200 — Migrar painel, ícones e extensão para a identidade Grafo

| | |
|---|---|
| **Fase** | 24 — Identidade visual |
| **Prioridade** | P1 |
| **Estimativa** | 3d |
| **Depende de** | — |
| **Documentação** | [ADR-0017](../../docs/adr/ADR-0017-identidade-visual-grafo.md) · [28-identidade-visual.md](../../docs/28-identidade-visual.md) |
| **Status** | `review` |

## Objetivo

Trocar a marca e a linguagem visual do painel pela identidade Grafo aprovada em 16/11/2026: símbolo de nós e anel,
interface em preto e branco, cor só no símbolo e nos estados, componentes próprios em vez de pílulas genéricas.

## Entregáveis

- [x] `scripts/brand.py` gera o símbolo novo: `brand/*.svg`, PNGs, `build/icon.ico`, `build/icon.png`,
      `public/favicon.svg` e `markPaths.ts`, com desenhos para 32 e 16 px
- [x] `RagxMark` desenha nós, arestas e anel com as cores da marca (`--brand-node`, `--brand-ring`)
- [x] Tokens: acento branco no escuro e quase preto no claro, `--brand-*`, `--critical-ink`; Space Grotesk e
      JetBrains Mono empacotadas (sem rede)
- [x] Componentes: botão Nó, Porta, Relação e Corte; estado pela forma do nó; tags em cadeia; interruptor
      Conexão; abas Trilha; progresso Aresta; cartão com porta e o caminho do dado (barra lateral sem trilha de nós: a pedido, 16/11)
- [x] Extensão do VS Code com o símbolo novo
- [x] Design system registrado (artefato) com tokens, componentes e o guia
- [x] CHANGELOG em `[Não lançado]`

## Fora de escopo

- Mudar o nome do binário ou os textos que escrevem RAGX (a assinatura gráfica é `ragx`, o resto não muda)
- Site, loja e materiais de divulgação
- Redesenhar telas: a migração troca a pele dos componentes, não o fluxo nem o conteúdo

## Critérios de aceite

- [x] `npm run check` verde, com `contrast.test.ts` cobrindo os tokens novos nos dois temas
- [x] Nenhum azul `#3b82f6`/`#2563eb` sobra na interface fora do gráfico de séries
- [x] Captura do painel real nos dois temas conferida
