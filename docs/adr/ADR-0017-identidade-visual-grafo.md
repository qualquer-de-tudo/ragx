# ADR-0017 — Identidade visual Grafo: cor só no símbolo, interface em preto e branco

- **Status:** aceito
- **Data:** 2026-11-16
- **Contexto:** Fase 24 — Identidade visual
- **Relacionado:** [28 — Identidade visual](../28-identidade-visual.md), [RAGX-0200](../../task/fase-24-identidade-visual/RAGX-0200-migrar-para-a-identidade-grafo.md)

## Contexto

O símbolo anterior (um X azul `#3b82f6` com abertura em losango) não dizia nada do que o RAGX faz, e a interface
seguia o padrão de qualquer painel: pílula colorida para estado, botão azul preenchido, selo com ponto `●`. Cinco
direções foram desenhadas (Portal, Grafo, Terminal, Cofre, Destilação); a Grafo foi escolhida e evoluída numa
segunda rodada. Uma versão com interface azul-noite foi rejeitada: o preto e branco do painel atual fica.

## Decisão

1. **Símbolo Grafo.** Quatro nós nos cantos ligados por arestas a um anel central, sobre grade de 8 unidades
   (nó r 6,5, anel r 8 com traço 4, aresta 3,5 a 45° que para no anel). Os nós são o que o RAGX lê; o anel é o
   índice. Desenho próprio para 32 px e para 16 px (o anel vira ponto cheio).
2. **Cor só no símbolo e nos estados.** Nós ciano `#22d3ee` e anel violeta `#a78bfa` no escuro; `#0e7490` e
   `#6d4fd8` no claro. A interface é preto e branco: o acento de ação e seleção é o branco (escuro) ou o quase
   preto (claro). Verde, âmbar e vermelho continuam só para estado, sempre com a forma do nó junto.
3. **Assinatura em minúsculas**, `ragx`, Space Grotesk 700 com tracking −0,045 em. O binário e os textos de
   interface continuam escrevendo RAGX ([ADR-0007](ADR-0007-nome-do-binario.md)); só a assinatura gráfica muda.
4. **Tipografia:** Space Grotesk para interface e títulos, JetBrains Mono para caminhos, números e código.
   Empacotadas com o painel (`font-src 'self'`); nada vem da rede.
5. **Componentes na linguagem do símbolo:** botão Nó (porta + aresta), botão Porta (nó preso à borda), botão
   Relação (texto que puxa uma aresta), estado pela forma do nó (cheio, meio, cortado, em órbita, vazio), tags em
   cadeia, interruptor Conexão, abas em trilha, progresso em aresta, cartão com portas nos cantos e o caminho do
   dado (gate → índice → vetores → agente).

## Consequências

- `scripts/brand.py` passa a gerar o símbolo novo (SVG, PNG, `.ico`, `favicon.svg`, `markPaths.ts`); o ícone do
  `.exe` e do instalador muda junto.
- Os tokens de `index.css` trocam o azul pelo branco como acento; `contrast.test.ts` ganha `--critical-ink`
  (texto sobre o vermelho) porque o texto do botão primário passa a ser preto.
- A extensão do VS Code usa o mesmo símbolo.
- O guia vive em [docs/28-identidade-visual.md](../28-identidade-visual.md); as pranchas de referência, num
  artefato de design.
