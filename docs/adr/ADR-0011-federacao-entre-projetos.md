# ADR-0011 — Federação por fatia pública, não por índice compartilhado

**Status:** aceito · 2026-09-15

## Contexto

Um agente trabalhando em `order-service` precisa do contrato de `POST /api/payments`,
servido por `payment-service` — outro repositório, outro time, provavelmente **não
clonado** na máquina do dev.

Três formas de resolver:

1. **Indexar todos os repositórios no hub.** Exige ter todos clonados, custa tempo e
   disco proporcionais ao número de projetos, e reindexa código de que o agente só
   precisa da superfície.
2. **Servidor central de conhecimento.** Resolve bem e quebra o requisito local-first:
   passa a exigir infraestrutura, autenticação e disponibilidade.
3. **Cada projeto publica sua superfície pública; o hub cruza as superfícies.**

## Decisão

Opção 3. Cada projeto gera, versionado no próprio repositório, uma **fatia de
federação** minúscula e autossuficiente:

```text
knowledge/federation/
├── service.json      identidade
├── provides.json     endpoints, eventos, pacotes, tabelas públicas
├── consumes.json     o que chama de fora
├── contracts/        OpenAPI · AsyncAPI · protobuf · JSON Schema
└── glossary.json     termos de domínio
```

Ao contrário de `knowledge/`, a fatia guarda conteúdo **por valor** — é o que permite
funcionar sem o repositório de origem. Ela cabe em poucos KB porque contém só a
superfície, nunca a implementação.

O hub cruza `consumes` de cada projeto com `provides` de todos os outros, normalizando
rotas entre stacks:

```text
/api/orders/{id}  ·  /api/orders/:id  ·  /api/orders/<int:id>   →   /api/orders/{}
```

Confiança por tipo de evidência (contrato declarado 1.0 · método+rota 0.95 ·
rota com método divergente 0.6 · só nome 0.8 · só similaridade de nome 0.4, que vira
sugestão e não aresta).

Um projeto entra no hub em um de dois estados: **clonado** (busca completa) ou
**só federação** (apenas contratos). O segundo é o caso comum.

## Consequências

Positivas:
- Cross-project funciona com a maioria dos repositórios não clonados.
- Custo por projeto federado é de KB, não de MB — o hub escala para dezenas de repos.
- A fatia é versionada junto com o código que a origina, então não envelhece em
  separado: quem muda a rota atualiza o contrato no mesmo PR.
- Efeito colateral valioso: consumo sem provedor e divergência de método viram
  relatório. A federação encontra erro de integração que nenhum dos dois
  repositórios enxerga sozinho.
- Fatia pode ser compartilhada isoladamente (um arquivo), sem dar acesso ao repositório.

Negativas:
- A fatia é derivada por heurística: chamada HTTP montada dinamicamente pode não ser
  detectada. Mitigação: `confidence` explícito, relatório de não resolvidos, e
  possibilidade de declarar manualmente em `federation/manual.json` (curado, vence
  o derivado).
- Exige um passo a mais (`ragx federation build`). Mitigação: `sync.auto_federation`
  ligado por padrão.
- Projeto que nunca publica a fatia é invisível para os outros. Mitigação:
  `ragx hub status` lista projetos registrados sem fatia.

## Segurança

- A fatia passa pelo gate como qualquer outro artefato compartilhado, com re-scan
  antes de gravar.
- `visibility = "private"` desliga a geração da fatia e exclui o projeto de toda
  consulta cross-project.
- O hub re-escaneia artefatos de outros projetos na entrada — ruleset local pode ser
  mais estrito que o de origem.
- Nenhum caminho absoluto atravessa projetos.
- Todo item cross-project carrega `project`; conhecimento sem origem não é entregue.

## Alternativas rejeitadas

- **Indexar tudo no hub** — exige todos os repositórios clonados; custo linear no
  número de projetos; indexa implementação onde só a superfície interessa.
- **Servidor central** — quebra local-first.
- **Descoberta por service registry / Kubernetes** — funcionaria em runtime, mas o
  agente trabalha em tempo de desenvolvimento, sobre código, frequentemente sem
  acesso ao cluster.
- **Só OpenAPI** — cobre HTTP e ignora eventos, pacotes compartilhados e tabelas;
  além disso muitos projetos não mantêm spec atualizada. OpenAPI entra como a
  evidência de maior confiança quando existe, não como a única.
