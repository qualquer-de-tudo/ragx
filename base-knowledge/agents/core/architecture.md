# Architecture — arquitetura modular

> **Quando carregar:** antes de criar módulo, feature ou qualquer arquivo novo.
> **Precedência:** a arquitetura do projeto ganha desta página. Leia primeiro
> `ai/module-context-reader.md` e confirme o desenho real antes de aplicar.

O objetivo destas regras é um só: **uma mudança de requisito toca um lugar.**
Tudo abaixo é consequência disso.

---

## A regra da dependência

**R-ARC-01 — Dependência aponta para dentro.**

```
  HTTP / CLI / Fila / Job          ← entrada (adapta o mundo)
        ↓
  Action / UseCase                 ← orquestra UM caso de uso
        ↓
  Service / Domain                 ← regra de negócio
        ↓
  Repository (interface)           ← contrato de persistência
        ↓
  Infra (SQL, HTTP, storage)       ← implementa o contrato
```

Cada camada conhece apenas a de baixo. Nunca o contrário. Uma regra de negócio
que importa `Request` está errada — mesmo que funcione.

**R-ARC-02 — A camada de domínio não importa framework.**
Sem `Request`, `Response`, `Eloquent`, `Session`, `Auth::user()`, ORM ou
cliente HTTP dentro de Service ou Domain. Se precisa do usuário logado, ele
chega como parâmetro.

**R-ARC-03 — Módulo não chama o interno de outro módulo.**
Módulos conversam por interface pública: um Service exportado, um evento, um
contrato. `Billing\Internal\TaxCalculator` chamado de `Shipping` é acoplamento
que vai doer.

---

## Papéis

**R-ARC-04 — Controller é tradutor. Sem regra de negócio.**
Recebe, valida o formato (`engineering/validations.md`), chama UMA action,
devolve resposta. Se tem `if` de negócio, ele está no lugar errado.

**R-ARC-05 — Action orquestra um caso de uso e só um.**
Um ponto de entrada público: `execute()` / `handle()`. Se a action precisa de
um segundo método público, são duas actions.

**R-ARC-06 — Service guarda a regra que sobrevive ao framework.**
Cálculo, política, invariante de domínio. É o que continuaria verdadeiro se o
sistema virasse CLI amanhã.

**R-ARC-07 — Repository isola persistência atrás de interface.**
O domínio declara `InvoiceRepository`; a infra implementa
`EloquentInvoiceRepository`. É o que torna o teste de domínio possível sem
banco.

**R-ARC-08 — DTO atravessa fronteira.**
Imutável, tipado, sem comportamento. Nunca passe array associativo entre
camadas: array não tem contrato, e o erro aparece três camadas adiante.

**R-ARC-09 — Model é dado, não orquestrador.**
Model com envio de e-mail, chamada de API e cálculo de imposto é o God Object
clássico. Ver `core/patterns.md`, `R-PAT-01`.

---

## Organização física

**R-ARC-10 — Pasta por MÓDULO, não por tipo de arquivo.**

```
modules/invoicing/
├── Actions/          IssueInvoiceAction.php
├── Services/         TaxCalculator.php
├── DTOs/             InvoiceData.php
├── Models/           Invoice.php
├── Repositories/     InvoiceRepository.php  (interface)
├── Http/             Controllers/, Requests/, Resources/
├── Events/           InvoicePaid.php
├── Listeners/
├── Policies/
├── Tests/
├── plans/            artefatos .plan.md  (core/plans.md)
└── docs/             gerados por ai/module-doc-generator.md
```

`app/Services/` com 200 arquivos de 15 domínios é o anti-padrão que esta regra
existe para evitar.

**R-ARC-11 — Fronteira do módulo é explícita.**
Cada módulo declara em `docs/` o que oferece (endpoints, eventos, services
públicos) e o que consome. É esse arquivo que o RAG usa para responder "quem
depende de quem" sem adivinhar.

---

## Comunicação

**R-ARC-12 — Síncrono quando a resposta é necessária; evento quando não é.**
Emitir nota fiscal precisa de resposta → chamada direta. Notificar o cliente
não precisa → evento.

**R-ARC-13 — Evento é fato consumado, no passado.**
`InvoicePaid`, não `PayInvoice`. Quem emite não sabe nem se importa com quem
escuta. Se o emissor precisa saber o resultado, não era evento.

**R-ARC-14 — Evento carrega ID e o mínimo, não o objeto inteiro.**
O consumidor busca o que precisa. Payload gordo vira contrato implícito que
quebra em silêncio.

**R-ARC-15 — Integração externa fica atrás de interface do projeto.**
`PaymentGateway` é sua; `StripePaymentGateway` implementa. Trocar de
fornecedor passa a ser um arquivo novo, não uma busca global.

---

## Transação e consistência

**R-ARC-16 — A transação começa e termina na Action.**
Service não abre transação: ele não sabe se é parte de uma maior.

**R-ARC-17 — Nada de I/O externo dentro de transação aberta.**
E-mail, webhook e chamada HTTP dentro de `BEGIN` prendem conexão e, se a
transação falhar, já aconteceram. Dispare depois do commit.

**R-ARC-18 — Operação que pode repetir precisa ser idempotente.**
Webhook, job de fila e retry chegam duas vezes — é quando, não se. Chave de
idempotência ou verificação de estado antes de aplicar.

---

## Configuração

**R-ARC-19 — Zero segredo no código.**
Credencial vem de variável de ambiente. `.env` nunca é commitado. O RAGX
bloqueia esses arquivos antes do parser; o repositório também deve.

**R-ARC-20 — Zero valor de ambiente hardcoded.**
URL, timeout, limite e feature flag saem de config. `if ($env === 'prod')`
espalhado pelo código é dívida garantida.

---

## Referências

- Padrões e anti-patterns: `core/patterns.md`
- Planejamento antes de codar: `core/plans.md`
- Leitura do módulo existente: `ai/module-context-reader.md`
- Banco e modelagem: `ai/dba.md`
- Registro de decisão arquitetural: `quality/decision-log.md`
