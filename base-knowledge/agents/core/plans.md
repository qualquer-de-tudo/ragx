# Plans

Este arquivo define **como o agente deve conduzir o processo de planejamento** de qualquer implementação. O objetivo é garantir que nenhum código seja produzido sem um plano revisado e aprovado por humano.

---

## Responsabilidade deste arquivo

`core/plans.md` orienta o **comportamento do agente ao criar planos**. Os arquivos de plano gerados **não ficam aqui** — cada plano é salvo em um arquivo separado no projeto, conforme definido abaixo.

---

## Onde salvar os planos gerados

### Configuração preferencial (definida pelo Tech Lead)

O Tech Lead deve definir o caminho base para armazenamento de planos no projeto. Registre essa decisão em `quality/decision-log.md`.

Caminhos sugeridos:
```
src/app/modules/{modulo}/plans/
docs/plans/
.plans/
```

### Se o caminho ainda não foi definido

O agente deve perguntar ao programador antes de salvar:

> "Ainda não há um caminho padrão definido para planos neste projeto. Onde deseja salvar o plano?
> Sugestões: `src/app/modules/{modulo}/plans/` | `docs/plans/` | outro caminho"

Após a resposta, o agente salva o arquivo **e registra o caminho em `quality/decision-log.md`** para que os próximos programadores usem o mesmo local.

### Convenção de nome do arquivo

```
{YYYY-MM-DD}_{slug-da-tarefa}.plan.md
```

Exemplos:
```
2026-04-24_criar-modulo-agendamento.plan.md
2026-04-24_refatorar-servico-pagamento.plan.md
```

---

## Perguntas obrigatórias antes de montar o plano

O agente deve fazer estas perguntas ao programador antes de gerar qualquer plano. Não pule etapas.

### 1. Escopo
- O que exatamente deve ser implementado?
- Quais módulos/arquivos serão criados ou alterados?
- Há alguma restrição de escopo (o que NÃO deve ser feito nesta tarefa)?

### 2. Contexto técnico
- Existe algum padrão já estabelecido no projeto para este tipo de implementação?
- Há dependências de outras tarefas ou de outros programadores?
- Qual é o prazo ou prioridade desta tarefa?

### 3. Riscos e impactos
- Esta mudança afeta contrato de API, banco de dados ou integrações externas?
- Existe risco de regressão em funcionalidades existentes?
- É necessário plano de rollback?

### 4. Critérios de aceite
- Como saberemos que a implementação está correta?
- Quais testes devem passar?
- Há validações de negócio específicas?

---

## Estrutura obrigatória do arquivo de plano gerado

O agente deve gerar o arquivo de plano com esta estrutura:

```markdown
# Plano: {título da tarefa}

**Data:** {YYYY-MM-DD}
**Programador:** {nome ou @username}
**Status:** DRAFT | APPROVED | EXECUTION | DONE

---

## Objetivo
{descrição clara do que será implementado}

## Escopo
### Incluído
- {item 1}
- {item 2}

### Excluído (fora do escopo)
- {item}

## Arquivos afetados
| Arquivo | Ação | Motivo |
|---|---|---|
| `path/arquivo.php` | criar / alterar / deletar | {motivo} |

## Dependências
- {dependência de outra tarefa ou programador, se houver}

## Riscos identificados
| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| {risco} | baixo/médio/alto | baixo/médio/alto | {ação} |

## Passos de execução
1. {passo 1}
2. {passo 2}
3. {passo N}

## Critérios de aceite
- [ ] {critério 1}
- [ ] {critério 2}

## Plano de rollback
{descrever como desfazer se necessário, ou "N/A"}

---

**Aprovado por:** {nome} em {data}
```

---

## Regras de transição de estado

| De | Para | Condição |
|---|---|---|
| `DRAFT` | `APPROVED` | Aprovação explícita de humano responsável |
| `APPROVED` | `EXECUTION` | Programador inicia a implementação |
| `EXECUTION` | `DONE` | Todos os critérios de aceite marcados como concluídos |
| qualquer | `DRAFT` | Revisão solicitada — agente atualiza e volta ao início |

O agente **não pode avançar para `EXECUTION`** sem que o status esteja `APPROVED`.
