# 17 — Multiprojeto e federação

> Um agente que trabalha em `order-service` precisa saber que `POST /api/payments`
> é servido por `payment-service`, que vive em outro repositório. Sem isso, ele
> inventa o contrato.

## As três camadas de conhecimento

```text
┌──────────────────────────────────────────────────────────────────────┐
│  HUB          ~/.ragx/hub/hub.db          máquina do dev             │
│               agrega N projetos · derivado · NUNCA versionado        │
│               responde a pergunta que cruza repositórios             │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ ragx hub sync  (lê só artefatos derivados)
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ order-service │   │payment-service│   │  catalog-api  │
├───────────────┤   ├───────────────┤   ├───────────────┤
│ knowledge/    │   │ knowledge/    │   │ knowledge/    │  ← VERSIONADO no repo
│  └ federation/│   │  └ federation/│   │  └ federation/│    (leve, orçado)
│ .ragx/*.db    │   │ .ragx/*.db    │   │ .ragx/*.db    │  ← local, fidelidade total
└───────────────┘   └───────────────┘   └───────────────┘    NÃO versionado
```

| Camada | Onde | Versionado | Fidelidade | Serve para |
|--------|------|-----------|-----------|-----------|
| `.ragx/knowledge.db` | projeto | não | total (float32@768, conteúdo) | busca local rápida |
| `knowledge/` | projeto | **sim** | metadados + int8@256, sem conteúdo | time compartilhar; reidratável |
| `knowledge/federation/` | projeto | **sim** | só a superfície pública | outros projetos consumirem |
| `~/.ragx/hub/hub.db` | máquina | não | referências + fatias públicas | consulta cross-project |

A distinção que faz tudo funcionar: **`knowledge/` é sobre o projeto; `federation/`
é sobre o que o projeto oferece a terceiros.** O primeiro é grande e reidratável;
o segundo é minúsculo e autossuficiente.

## Por que `federation/` precisa ser autossuficiente

O dev tem `order-service` clonado. Pode não ter `payment-service`. Ainda assim o
agente precisa saber o contrato de `POST /api/payments`.

`knowledge/` de `payment-service` não resolve isso — sem o repositório clonado não
há como reidratar o conteúdo. Já `federation/` carrega o contrato **por valor**,
e cabe em poucos KB.

```text
knowledge/federation/
├── service.json        identidade: nome, tipo, dono, remote_hash, versão
├── provides.json       endpoints HTTP, eventos publicados, pacotes, tabelas públicas
├── consumes.json       o que este projeto chama de fora
├── contracts/          OpenAPI · AsyncAPI · protobuf · JSON Schema (quando existirem)
└── glossary.json       termos de domínio, para alinhar vocabulário entre times
```

### `service.json`

```json
{
  "schema_version": 1,
  "project_id": "a91c4f2e",
  "name": "payment-service",
  "kind": "http-service",
  "owner": "squad-billing",
  "remote_hash": "7d2e91c4",
  "languages": ["php"],
  "generated_at": "2026-09-15T14:02:00Z"
}
```

### `provides.json`

```json
{
  "http": [
    {
      "method": "POST", "path": "/api/payments",
      "normalized": "POST /api/payments",
      "handler": "PaymentController.store",
      "request_schema": "contracts/payment-create.schema.json",
      "response_schema": "contracts/payment.schema.json",
      "source": "routes/api.php:42",
      "confidence": 1.0
    }
  ],
  "events": [
    { "name": "payment.captured", "schema": "contracts/payment-captured.json",
      "source": "src/Events/PaymentCaptured.php", "confidence": 1.0 }
  ],
  "packages": [
    { "name": "@acme/payment-sdk", "registry": "npm", "version": "2.4.0" }
  ],
  "tables": [
    { "name": "payments", "public": true, "source": "database/migrations/..." }
  ]
}
```

### `consumes.json`

```json
{
  "http": [
    { "method": "POST", "path": "/api/payments",
      "normalized": "POST /api/payments",
      "call_site": "src/Order/OrderService.php:118",
      "detected_by": "http-client-literal", "confidence": 0.95 }
  ],
  "events": [ { "name": "payment.captured", "handler": "src/Listeners/..." } ],
  "packages": [ { "name": "@acme/payment-sdk", "version": "^2.4" } ]
}
```

`provides`/`consumes` são derivados dos mesmos extratores do grafo (Fase 3),
promovendo a **superfície pública** para um artefato próprio.

## Resolução de vínculos

O hub cruza `consumes` de um projeto com `provides` de todos os outros.

```text
order-service.consumes.http["POST /api/payments"]
        ⟷ normalização ⟷
payment-service.provides.http["POST /api/payments"]
        ↓
relação cross-project:  order-service --consumes--> payment-service  (conf. 1.0)
```

Normalização de rota — sem isso, nada casa entre stacks diferentes:

```text
/api/orders/{id}        Laravel / OpenAPI
/api/orders/:id         Express
/api/orders/<int:id>    Flask
/api/orders/%s          cliente com formatação
        ↓  todos viram
POST /api/orders/{}
```

Confiança do vínculo:

| Evidência | Confiança |
|-----------|-----------|
| Contrato declarado (OpenAPI/AsyncAPI) dos dois lados | 1.0 |
| Método + rota normalizada idênticos | 0.95 |
| Rota idêntica, método divergente | 0.6 (reportado como possível erro) |
| Só nome de evento ou de pacote | 0.8 |
| Só similaridade de nome de serviço | 0.4 — **não** vira aresta, vira sugestão |

Vínculo não resolvido é informação valiosa, não silêncio:

```text
ragx hub link

  Vínculos resolvidos (12)
    order-service    --consumes-->  payment-service   POST /api/payments      1.00
    order-service    --consumes-->  catalog-api       GET  /api/products/{}   0.95
    payment-service  --publishes--> payment.captured                          1.00
    order-service    --subscribes-> payment.captured                          1.00

  Consumos sem provedor conhecido (3)
    order-service → POST /api/shipping/quote
      nenhum projeto registrado provê esta rota
      → registre o repositório correspondente, ou é integração de terceiro

  Divergências (1)
    order-service consome  PUT  /api/payments/{}/refund
    payment-service provê  POST /api/payments/{}/refund
      → método divergente; possível bug de integração
```

Esse último bloco é efeito colateral útil: a federação encontra erro de integração
que nenhum dos dois repositórios consegue ver sozinho.

## Registro de projetos

```bash
ragx project register .                       # registra o projeto atual no hub
ragx project register ../payment-service --name payment
ragx project register --from-federation ./contratos/payment.fed.json   # sem clonar
ragx project list
ragx project unregister payment
```

`~/.ragx/hub/registry.json`:

```json
{
  "schema_version": 1,
  "projects": [
    {
      "id": "a91c4f2e", "name": "order-service",
      "path": "E:/RAGPAG/order-service",
      "remote_hash": "3f9a...", "cloned": true,
      "embedding_model": "ollama:nomic-embed-text", "dim": 768,
      "last_sync": "2026-09-15T14:10:00Z", "chunks": 1832,
      "visibility": "workspace"
    },
    {
      "id": "b72d8e01", "name": "payment-service",
      "path": null, "cloned": false,
      "federation_only": true,
      "source": "hub/federation/payment-service/",
      "last_sync": "2026-09-14T09:00:00Z"
    }
  ]
}
```

Um projeto pode estar no hub em dois estados: **clonado** (busca completa disponível)
ou **só federação** (apenas contratos). O segundo é o caso comum de microsserviços
mantidos por outro time.

## Consulta cross-project

```bash
ragx search "como criar um pagamento" --scope all
ragx search "..." --scope project:payment-service
ragx context "integrar checkout com pagamento" --scope all --tokens 6000
ragx hub graph order-service --depth 2
```

Fluxo:

```text
query --scope all
  │
  ├─► projeto atual              busca híbrida completa
  ├─► projetos clonados          busca híbrida no .ragx/knowledge.db de cada um
  └─► projetos só-federação      busca na fatia pública (contratos, glossário)
        ▼
  fusão RRF, com penalidade 0,85 para projeto externo
        ▼
  todo resultado carrega `project` — obrigatório, sem exceção
```

A penalidade existe porque, empatados, o trecho do projeto em que o dev está
trabalhando é quase sempre o mais útil.

### Modelos de embedding incompatíveis

Projetos podem ter sido indexados com modelos diferentes. Vetores de modelos
distintos **não são comparáveis** — comparar produziria ranking aleatório com
aparência de resultado.

```text
hub sync detecta modelo/dimensão por projeto
        ↓
mesmo modelo   → busca semântica cross-project normal
modelo distinto→ aquele projeto participa só por keyword + federação,
                 com aviso explícito em `ragx hub status`
```

`ragx hub status` sempre mostra qual projeto está degradado e por quê.

## Segurança na federação

Agregar N projetos multiplica a superfície. Regras:

1. **O hub nunca lê o filesystem de projeto nenhum.** Ele lê apenas artefatos
   derivados (`knowledge/`, `federation/`), que já passaram pelo gate do projeto de
   origem. A invariante de [ADR-0008](adr/ADR-0008-security-gate-antes-do-parser.md)
   continua valendo.
2. **Re-scan na entrada do hub.** Artefato de outro projeto é entrada não confiável;
   o ruleset local pode ser mais estrito que o de origem.
3. **`visibility` por projeto**: `workspace` (padrão) ou `private`. Projeto privado
   fica fora de toda consulta cross-project e não gera `federation/`.
4. **Atribuição obrigatória.** Todo resultado, fragmento de contexto e nó de grafo
   carrega `project`. Conhecimento sem origem identificada não é entregue.
5. **Sem caminho absoluto** nos artefatos de federação — nomes de máquina e de
   usuário não atravessam projetos.
6. **Isolamento testado**: a suíte de segurança ganha um cenário com dois projetos,
   em que um contém a fixture de segredos, e nenhuma consulta no outro projeto pode
   retornar nada dela.

## Dicionário de workspace

Assim como cada projeto tem seu `dictionary.json`, o hub gera o mapa do conjunto:

```bash
ragx hub dictionary
```

```json
{
  "workspace": "acme",
  "projects": [
    { "name": "order-service", "kind": "http-service", "languages": ["php"] },
    { "name": "payment-service", "kind": "http-service", "federation_only": true }
  ],
  "integrations": [
    { "from": "order-service", "to": "payment-service", "via": "POST /api/payments", "confidence": 1.0 },
    { "from": "order-service", "to": "payment-service", "via": "event:payment.captured", "confidence": 1.0 }
  ],
  "shared_technologies": ["Redis", "PostgreSQL", "RabbitMQ"],
  "unresolved_consumes": [
    { "from": "order-service", "target": "POST /api/shipping/quote" }
  ],
  "divergences": [
    { "from": "order-service", "to": "payment-service", "issue": "método divergente em /api/payments/{}/refund" }
  ]
}
```

É o primeiro artefato que o agente deve ler quando trabalha em ambiente
multirrepositório: em poucos KB ele descobre quem fala com quem.

## Impacto no MCP

Ferramentas ganham escopo de projeto, e duas novas entram:

| Ferramenta | Mudança |
|------------|---------|
| `search_knowledge`, `search_hybrid`, `search_graph`, `build_context` | parâmetro `scope`: `current` (padrão) · `all` · `project:<nome>` |
| `get_dictionary` | parâmetro `scope`; `all` devolve o dicionário de workspace |
| `list_projects` | **nova** — projetos registrados, estado (clonado/federação) e integrações |
| `get_contract` | **nova** — contrato de um endpoint/evento, com o projeto que o provê |

Toda resposta passa a incluir `project` em cada item. A regra de
[ADR-0006](adr/ADR-0006-mcp-casca-fina.md) continua intacta: o MCP consulta o hub e
os stores, nunca o filesystem.

## Sincronização

```bash
ragx hub sync                  # atualiza o hub a partir de todos os registrados
ragx hub sync --project order-service
ragx hub status
ragx hub link                  # (re)resolve vínculos consumes/provides
ragx federation build          # gera knowledge/federation/ do projeto atual
                              # declarações curadas: knowledge/federation/manual.json
```

`ragx hub sync` é incremental: usa `remote_hash` + `last_sync` + hash do `manifest.json`
de cada projeto para reprocessar só o que mudou. Projeto cujo caminho registrado
deixou de existir é marcado `missing`, não removido — o dev pode ter movido a pasta.

Ordem recomendada no dia a dia:

```bash
git pull && ragx sync          # projeto atual
ragx federation build          # publica a superfície pública atualizada
ragx hub sync && ragx hub link  # workspace enxerga a mudança
```

`sync.auto_federation = true` (padrão) faz os dois primeiros virarem um só.

## Critério de aceite

1. `ragx project register` em 3 repositórios e `ragx hub link` resolve os vínculos
   HTTP e de eventos entre eles.
2. `ragx search "criar pagamento" --scope all` de dentro de `order-service` devolve
   o contrato de `payment-service`, com `project` preenchido.
3. Funciona com `payment-service` **não clonado**, usando só `federation/`.
4. Consumo sem provedor e divergência de método são reportados, não silenciados.
5. Projeto `private` nunca aparece em consulta cross-project.
6. Segredo da fixture em um projeto não retorna em nenhuma consulta feita a partir
   de outro projeto.
7. `federation/` de um projeto real fica abaixo de 1 MB.
8. Modelo de embedding divergente degrada para keyword com aviso, sem ranking falso.
