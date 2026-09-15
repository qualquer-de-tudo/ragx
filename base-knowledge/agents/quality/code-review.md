# Code Review

Este arquivo define o **checklist obrigatório de revisão de código**. Para cada implementação, o agente gera um arquivo de revisão separado — nunca compartilhado entre programadores — para evitar conflitos e manter rastreabilidade individual.

---

## Responsabilidade deste arquivo

`quality/code-review.md` orienta o **comportamento do agente ao conduzir revisões**. Os arquivos de revisão gerados **não ficam aqui** — cada revisão é salva em arquivo separado no projeto.

---

## Onde salvar os arquivos de revisão gerados

### Configuração preferencial (definida pelo Tech Lead)

O Tech Lead deve definir o caminho base para revisões. Registre em `quality/decision-log.md`.

Caminhos sugeridos:
```
src/app/modules/{modulo}/reviews/
docs/reviews/
.reviews/
```

### Se o caminho ainda não foi definido

O agente deve perguntar ao programador:

> "Ainda não há um caminho padrão para arquivos de revisão neste projeto. Onde deseja salvar?
> Sugestões: `src/app/modules/{modulo}/reviews/` | `docs/reviews/` | outro caminho"

Após a resposta, o agente salva o arquivo **e registra o caminho em `quality/decision-log.md`**.

### Convenção de nome do arquivo

```
{YYYY-MM-DD}_{slug-da-tarefa}_{@programador}.review.md
```

Exemplos:
```
2026-04-24_criar-modulo-agendamento_@joao.review.md
2026-04-24_refatorar-servico-pagamento_@maria.review.md
```

O `@programador` no nome evita conflito quando dois desenvolvedores revisam a mesma área simultaneamente.

---

## Checklist obrigatório de revisão

O agente aplica este checklist a cada implementação e preenche o resultado no arquivo gerado.

### Arquitetura e padrões
- [ ] Segue a arquitetura modular definida em `core/architecture.md`
- [ ] Não viola nenhum anti-pattern listado em `core/patterns.md`
- [ ] Nomenclatura de classes, métodos e variáveis segue `core/standards.md`
- [ ] Responsabilidades estão corretamente separadas (Action / Service / DTO)

### Qualidade de código
- [ ] Sem código duplicado ou lógica copy-paste
- [ ] Métodos com mais de 20 linhas foram justificados ou refatorados
- [ ] Sem comentários de código morto (código comentado)
- [ ] Tipagem estrita aplicada em todos os parâmetros e retornos

### Segurança
- [ ] Inputs validados conforme `engineering/validations.md`
- [ ] Sem dados sensíveis em logs ou respostas de API
- [ ] Autenticação e autorização verificadas nos endpoints afetados
- [ ] Sem queries SQL dinâmicas sem binding de parâmetros

### Testes
- [ ] Testes unitários escritos para a lógica de negócio nova
- [ ] Casos de borda cobertos (null, vazio, limites)
- [ ] Testes de integração criados se há mudança de contrato ou banco
- [ ] Cobertura mínima respeitada conforme `engineering/testing.md`

### Performance
- [ ] Sem queries N+1 introduzidas
- [ ] Uso de cache onde aplicável conforme `engineering/performance.md`
- [ ] Sem operações bloqueantes em fluxos críticos

### Observabilidade
- [ ] Logs estruturados adicionados em pontos relevantes
- [ ] Erros tratados e logados com contexto suficiente
- [ ] Métricas ou rastreamento adicionados se aplicável

### Débito técnico
- [ ] Todos os `TODO`, `FIXME` ou soluções provisórias foram registrados em `quality/tech-debt.md`

---

## Estrutura obrigatória do arquivo de revisão gerado

```markdown
# Code Review: {título da tarefa}

**Data:** {YYYY-MM-DD}
**Programador:** {nome ou @username}
**Revisor:** {agente IA | nome do revisor humano}
**Branch/PR:** {identificador}
**Plano de referência:** {caminho para o .plan.md correspondente}

---

## Resultado geral

**Status:** APROVADO | APROVADO COM RESSALVAS | REPROVADO

---

## Checklist

### Arquitetura e padrões
- [x] Segue arquitetura modular
- [x] Sem anti-patterns
- [ ] **FALHA:** Nomenclatura inconsistente em `UserService` — renomear `getData()` para `getUserData()`

### Qualidade de código
- [x] Sem duplicação
- [x] Tipagem estrita aplicada
...

### Segurança
...

### Testes
...

### Performance
...

### Observabilidade
...

### Débito técnico
...

---

## Itens que bloqueiam aprovação
1. {descrição do item bloqueante com arquivo e linha}

## Itens que são ressalvas (não bloqueiam)
1. {descrição da ressalva}

## Débitos registrados
> Ver: {caminho para o .techdebt.md correspondente}

---

**Decisão final:** {APROVADO | REQUER AJUSTES}
**Aprovado por:** {nome} em {data}
```

---

## Regras do agente ao conduzir a revisão

1. O agente **nunca aprova automaticamente** — o status final deve ser confirmado por humano
2. Qualquer item bloqueante deve ser resolvido antes de avançar para merge
3. Ressalvas sem resolução imediata devem ser registradas em `quality/tech-debt.md`
4. O arquivo de revisão deve referenciar o `.plan.md` correspondente para rastreabilidade
