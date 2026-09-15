# Decision Log

Este arquivo define **como registrar decisões técnicas** no projeto. Cada decisão é salva em arquivo separado por programador ou por contexto, evitando conflitos entre múltiplos desenvolvedores trabalhando simultaneamente.

---

## Responsabilidade deste arquivo

`quality/decision-log.md` orienta o **comportamento do agente ao registrar decisões**. Os arquivos de decisão gerados **não ficam aqui** — são salvos em local definido pelo projeto.

---

## Onde salvar os arquivos de decisão gerados

### Configuração preferencial (definida pelo Tech Lead)

O Tech Lead deve definir o caminho base e registrá-lo aqui neste arquivo, na seção abaixo.

Caminhos sugeridos:
```
docs/decisions/
src/app/modules/{modulo}/decisions/
.decisions/
```

### Definição atual do projeto

```
# Preencher pelo Tech Lead:
CAMINHO_DECISION_LOG: (não definido)
```

> Enquanto `(não definido)`, o agente deve perguntar ao programador antes de salvar:
>
> "Ainda não há um caminho padrão para o decision log neste projeto. Onde deseja salvar?
> Sugestões: `docs/decisions/` | `src/app/modules/{modulo}/decisions/` | outro caminho
>
> Após definir, avise o Tech Lead para registrar aqui em `quality/decision-log.md`."

### Convenção de nome do arquivo

```
{YYYY-MM-DD}_{slug-da-decisao}.decision.md
```

Exemplos:
```
2026-04-24_escolha-padrao-planos.decision.md
2026-04-24_remover-cache-redis.decision.md
```

---

## Quando registrar uma decisão

O agente deve criar um arquivo de decisão sempre que:

- Uma escolha técnica com alternativas foi feita (ex: qual biblioteca usar, qual padrão adotar)
- Um caminho padrão de arquivos foi definido (planos, revisões, débitos)
- Uma regra de `core/` ou `engineering/` foi adicionada, alterada ou removida
- Uma exceção consciente a um padrão existente foi aceita
- Uma decisão de arquitetura afeta múltiplos módulos

**Não** é necessário registrar decisões triviais ou de implementação rotineira.

---

## Estrutura obrigatória do arquivo de decisão gerado

```markdown
# Decisão: {título da decisão}

**Data:** {YYYY-MM-DD}
**Autor:** {nome ou @username}
**Status:** PROPOSTA | ACEITA | SUBSTITUÍDA | REVOGADA

---

## Contexto
{descrever o problema ou situação que motivou a decisão}

## Alternativas consideradas
| Opção | Prós | Contras |
|---|---|---|
| {opção 1} | {prós} | {contras} |
| {opção 2} | {prós} | {contras} |

## Decisão tomada
{descrever claramente o que foi decidido e por quê}

## Consequências
- **Positivas:** {o que melhora}
- **Negativas / trade-offs:** {o que piora ou exige atenção}

## Impacto em arquivos de contexto
- {ex: `core/standards.md` atualizado para refletir esta decisão}

---

**Revisado por:** {nome} em {data}
**Substitui:** {caminho para decisão anterior, se houver}
```

---

## Regras do agente ao registrar decisões

1. Nunca sobrescrever um arquivo de decisão existente — criar um novo com status `SUBSTITUÍDA` referenciando o anterior
2. Decisões que alteram arquivos de contexto (`core/`, `engineering/`, `ai/`) devem registrar quais arquivos foram impactados
3. O agente deve propor o registro de decisão sempre que perceber que uma escolha técnica relevante foi feita sem documentação
