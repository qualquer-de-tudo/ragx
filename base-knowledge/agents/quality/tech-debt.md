# Tech Debt

Este arquivo define **como identificar e registrar débitos técnicos** no projeto. Cada débito é salvo em arquivo separado por contexto, evitando conflitos entre múltiplos desenvolvedores trabalhando simultaneamente.

---

## Responsabilidade deste arquivo

`quality/tech-debt.md` orienta o **comportamento do agente ao registrar débitos**. Os arquivos de débito gerados **não ficam aqui** — são salvos em local definido pelo projeto.

---

## Onde salvar os arquivos de débito gerados

### Configuração preferencial (definida pelo Tech Lead)

O Tech Lead deve definir o caminho base e registrá-lo aqui neste arquivo, na seção abaixo.

Caminhos sugeridos:
```
docs/tech-debt/
src/app/modules/{modulo}/tech-debt/
.tech-debt/
```

### Definição atual do projeto

```
# Preencher pelo Tech Lead:
CAMINHO_TECH_DEBT: (não definido)
```

> Enquanto `(não definido)`, o agente deve perguntar ao programador antes de salvar:
>
> "Ainda não há um caminho padrão para tech debt neste projeto. Onde deseja salvar?
> Sugestões: `docs/tech-debt/` | `src/app/modules/{modulo}/tech-debt/` | outro caminho
>
> Após definir, avise o Tech Lead para registrar aqui em `quality/tech-debt.md`."

### Convenção de nome do arquivo

```
{YYYY-MM-DD}_{slug-do-debito}.techdebt.md
```

Exemplos:
```
2026-04-24_remover-gambiarra-servico-pagamento.techdebt.md
2026-04-24_adicionar-indice-tabela-agendamentos.techdebt.md
```

---

## Quando registrar um débito técnico

O agente deve criar um arquivo de débito sempre que:

- Uma solução provisória (`TODO`, `FIXME`, `HACK`, `workaround`) for introduzida
- Um item do checklist de code-review não for resolvido imediatamente
- Uma vulnerabilidade de segurança for identificada e não corrigida na mesma tarefa
- Um padrão do projeto for violado conscientemente por restrição de prazo
- Uma otimização de performance necessária for adiada
- Um teste obrigatório for omitido temporariamente

---

## Classificação de débitos

| Tipo | Descrição |
|---|---|
| `code` | Código ruim, duplicação, violação de padrão |
| `security` | Vulnerabilidade identificada e não corrigida |
| `performance` | Otimização necessária adiada |
| `test` | Cobertura de testes insuficiente |
| `architecture` | Violação de arquitetura aceita temporariamente |
| `documentation` | Documentação ausente ou desatualizada |

## Prioridade

| Prioridade | Critério |
|---|---|
| `CRÍTICA` | Impacta segurança ou estabilidade em produção |
| `ALTA` | Impacta qualidade ou manutenibilidade de forma significativa |
| `MÉDIA` | Melhoria importante mas não urgente |
| `BAIXA` | Melhoria cosmética ou de conveniência |

---

## Estrutura obrigatória do arquivo de débito gerado

```markdown
# Tech Debt: {título do débito}

**Data:** {YYYY-MM-DD}
**Registrado por:** {nome ou @username}
**Tipo:** code | security | performance | test | architecture | documentation
**Prioridade:** CRÍTICA | ALTA | MÉDIA | BAIXA
**Status:** ABERTO | EM RESOLUÇÃO | RESOLVIDO

---

## Descrição
{descrever o problema técnico de forma clara}

## Localização
| Arquivo | Linha | Descrição |
|---|---|---|
| `path/arquivo.php` | {linha ou intervalo} | {o que está errado} |

## Causa raiz
{por que este débito foi introduzido — restrição de prazo, falta de informação, etc.}

## Impacto se não resolvido
{descrever consequências: risco de bug, vulnerabilidade, dificuldade de manutenção, etc.}

## Solução proposta
{descrever como deve ser resolvido}

## Esforço estimado
{horas ou dias estimados para resolução}

## Referências
- Plano relacionado: {caminho para .plan.md, se houver}
- Review relacionado: {caminho para .review.md, se houver}
- Decisão relacionada: {caminho para .decision.md, se houver}

---

**Resolvido por:** {nome} em {data}
**PR/commit de resolução:** {referência}
```

---

## Regras do agente ao registrar débitos

1. Débitos de prioridade `CRÍTICA` devem ser comunicados imediatamente ao Tech Lead
2. O agente não pode fechar um débito de segurança sem que a correção tenha passado por `ai/security-blue-team.md`
3. Débitos introduzidos em uma tarefa devem ser referenciados no arquivo de revisão correspondente (`.review.md`)
4. O agente deve propor um plano de resolução para débitos `CRÍTICA` ou `ALTA` na mesma sessão em que os registra
