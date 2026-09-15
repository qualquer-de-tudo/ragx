# Module Context Reader Agent

Este agente define o **comportamento obrigatório de leitura e análise do código existente** antes de qualquer implementação, modificação ou revisão em um módulo. O objetivo é garantir que o agente nunca aja às cegas — ele deve entender o contexto real do módulo antes de propor ou executar qualquer mudança.

**Quando invocar este agente:** automaticamente, como primeiro passo de qualquer tarefa que envolva código de um módulo existente.

---

## Por que isso é obrigatório

Agir sem ler o código do módulo causa:
- Geração de código inconsistente com os padrões já estabelecidos no módulo
- Duplicação de lógica que já existe
- Quebra de contratos internos (interfaces, tipos, eventos)
- Conflito com decisões técnicas já tomadas pela equipe
- Planos de execução incorretos por desconhecimento das dependências reais

---

## Quando este agente é ativado

Este agente deve ser executado **antes** de qualquer uma destas ações:

- Criar uma nova classe, arquivo ou feature dentro de um módulo existente
- Modificar ou refatorar código de um módulo
- Conduzir code review de um módulo
- Gerar documentação de um módulo
- Registrar um débito técnico de um módulo
- Criar um plano de execução que afeta um módulo existente

**Exceção:** projetos novos sem nenhum código — usar `ai/new-project.md` em vez deste agente.

---

## O que o agente deve ler e analisar

### Nível 1 — Estrutura do módulo (sempre obrigatório)

```
1. Listar todos os arquivos do módulo e suas responsabilidades
2. Identificar as camadas presentes (Controller, Action, Service, Repository, DTO, etc.)
3. Mapear as dependências internas (quais classes chamam quais)
4. Identificar as dependências externas (serviços, integrações, eventos)
```

### Nível 2 — Padrões em uso no módulo (sempre obrigatório)

```
5. Qual é o padrão de nomenclatura efetivamente usado no módulo?
   (pode diferir de core/standards.md — registrar divergência se houver)
6. Como estão estruturados os métodos públicos das classes principais?
7. Há injeção de dependência? Como está sendo feita?
8. Como erros e exceções estão sendo tratados?
9. Há testes escritos? Qual é a cobertura atual e o padrão dos testes?
```

### Nível 3 — Contexto de negócio (quando relevante para a tarefa)

```
10. Quais regras de negócio estão implementadas neste módulo?
11. Quais são os contratos de entrada e saída (DTOs, requests, responses)?
12. Há eventos disparados ou consumidos por este módulo?
13. Quais endpoints/comandos este módulo expõe?
```

---

## Perguntas que o agente deve fazer ao programador

Após analisar o código, o agente deve confirmar o entendimento com o programador:

```
Analisei o módulo {nome}. Antes de prosseguir, preciso confirmar:

1. Há alguma mudança recente no módulo que ainda não está commitada
   e que eu deva considerar?

2. Há alguma decisão técnica tomada sobre este módulo que não está
   refletida no código ainda? (ex: refatoração planejada, mudança de padrão)

3. Há dependências de outros módulos ou de outros programadores
   que eu deva saber antes de começar?
```

Se qualquer resposta revelar contexto novo, o agente deve reanalisar antes de prosseguir.

---

## Saída obrigatória da análise

Antes de iniciar qualquer ação, o agente deve produzir e exibir um **resumo de contexto** do módulo. Esse resumo serve como base para o plano de execução.

### Estrutura do resumo de contexto

```markdown
## Contexto do Módulo: {nome-do-modulo}

**Analisado em:** {YYYY-MM-DD HH:MM}
**Tarefa associada:** {descrição breve da tarefa}

### Arquivos identificados
| Arquivo | Responsabilidade | Observações |
|---|---|---|
| `path/Arquivo.php` | {responsabilidade} | {observação ou "ok"} |

### Padrões em uso no módulo
- Nomenclatura: {observação}
- Injeção de dependência: {como está sendo feita}
- Tratamento de erros: {padrão identificado}
- Testes: {cobertura estimada e padrão}

### Dependências mapeadas
- Internas: {lista de classes/módulos internos}
- Externas: {serviços, eventos, integrações}

### Contratos de entrada/saída
- Entrada: {DTOs, requests}
- Saída: {responses, eventos}

### Divergências com os padrões do projeto
| Divergência | Arquivo | Impacto | Ação recomendada |
|---|---|---|---|
| {divergência} | `path/Arquivo.php` | baixo/médio/alto | corrigir / aceitar / registrar débito |

### Riscos identificados para a tarefa atual
- {risco 1}
- {risco 2}

### O agente está pronto para: {descrição da próxima ação}
```

---

## Regras deste agente

1. **Nunca pular a análise** — mesmo que o programador diga que "conhece bem o módulo", o agente ainda deve gerar o resumo de contexto
2. **Registrar divergências** — qualquer padrão diferente do definido em `core/` deve ser apontado; o programador decide se é débito ou exceção aceita
3. **Não modificar código durante a análise** — esta fase é exclusivamente de leitura e compreensão
4. **Atualizar o contexto se o código mudar** — se durante a execução da tarefa o módulo for alterado de forma que o contexto inicial fique desatualizado, o agente deve reanalisar os arquivos afetados
5. **Escalar lacunas** — se o agente não conseguir entender a lógica de um trecho de código, deve perguntar ao programador antes de assumir qualquer coisa

---

## Integração com outros agentes

| Quando acionar após a análise | Agente |
|---|---|
| Iniciar implementação nova | `core/plans.md` — gerar plano com contexto do módulo |
| Revisar código | `quality/code-review.md` — iniciar checklist |
| Gerar documentação | `ai/module-doc-generator.md` |
| Identificar vulnerabilidade | `ai/security-blue-team.md` |
| Identificar código problemático | `quality/tech-debt.md` — registrar débito |
