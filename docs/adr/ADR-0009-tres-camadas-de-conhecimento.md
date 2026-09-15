# ADR-0009 — Três camadas de conhecimento (local, repo, hub)

**Status:** aceito · 2026-09-15

## Contexto

Dois requisitos que a arquitetura original ([ADR-0002](ADR-0002-sqlite-como-store-unico.md))
não atendia:

1. O conhecimento precisa existir **no repositório do projeto** (para o time) e
   **na máquina do dev** agregando vários projetos (para perguntas que cruzam
   repositórios — APIs e microsserviços distribuídos).
2. O que vai para o Git nunca pode estourar os limites do Git.

Um único SQLite não resolve: ele é binário (não versionável), tem fidelidade total
(grande demais) e é por projeto (não cruza repositórios).

## Decisão

Três camadas, com papéis distintos e conversão explícita entre elas.

```text
┌───────────────────────────────────────────────────────────────┐
│ HUB      ~/.ragx/hub/hub.db      máquina · derivado · N proj.  │
└──────────────────────────┬────────────────────────────────────┘
                           │ lê só artefatos derivados
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  knowledge/         knowledge/         knowledge/     ← repo · versionado · leve
  .ragx/*.db         .ragx/*.db         .ragx/*.db     ← local · completo · descartável
```

| Camada | Fidelidade | Versionado | Reconstruível a partir de |
|--------|-----------|-----------|---------------------------|
| `.ragx/knowledge.db` | total: conteúdo + float32@768 | não | `knowledge/` + working tree |
| `knowledge/` | metadados + int8@256, **sem conteúdo** | sim | working tree (reindexação) |
| `knowledge/federation/` | só a superfície pública, **por valor** | sim | `knowledge/` + grafo |
| `~/.ragx/hub/hub.db` | referências + fatias públicas | não | projetos registrados |

Regras que decorrem:

1. **Toda camada acima é descartável.** `rm -rf .ragx/` e `ragx sync` reconstrói.
   Apagar o hub e `ragx hub sync` reconstrói.
2. **A direção do fluxo é única:** working tree → `.ragx/` → `knowledge/` →
   `federation/` → hub. Nada volta.
3. **O hub nunca lê o filesystem dos projetos**, apenas artefatos derivados que já
   passaram pelo gate do projeto de origem. A invariante de
   [ADR-0008](ADR-0008-security-gate-antes-do-parser.md) se mantém.
4. **`federation/` é autossuficiente**; `knowledge/` não. O primeiro funciona sem o
   repositório de origem clonado; o segundo precisa dele para reidratar.

## Consequências

Positivas:
- Cada camada é dimensionada para o seu meio: Git recebe texto pequeno e estável,
  o disco local recebe o índice grande e rápido, o hub recebe só o suficiente para
  cruzar projetos.
- Onboarding vira `git clone && ragx sync` — sem reindexar do zero, sem baixar binário.
- Cross-project funciona mesmo com a maioria dos repositórios não clonados.
- Merge no Git continua viável, porque a camada versionada é texto e shardada.

Negativas:
- Três representações do mesmo conhecimento é mais superfície para divergir.
  Mitigação: o fluxo é unidirecional e cada conversão tem teste de round-trip.
- Reidratação depende do working tree estar coerente com `knowledge/`. Mitigação:
  conferência de `content_hash` em toda reidratação, com divergência reportada.
- O hub pode ficar obsoleto se o dev não rodar `ragx hub sync`. Mitigação:
  `ragx hub status` mostra a idade de cada projeto e `post-merge` sincroniza.

## Alternativas rejeitadas

- **Um SQLite versionado no Git** — binário, sem merge, cresce o histórico a cada
  indexação. É exatamente o que o requisito de tamanho proíbe.
- **Git LFS para o `.db`** — resolve o tamanho do repositório e não resolve merge,
  nem diff, nem revisão em PR. Além disso exige LFS configurado em todo clone.
- **Servidor central de conhecimento** — resolveria multiprojeto elegantemente e
  quebraria o requisito local-first: passa a exigir infraestrutura, autenticação e
  disponibilidade.
- **Só o hub, sem camada no repo** — o conhecimento deixaria de ser compartilhável
  pelo time via Git, que é o requisito da Fase 9.
