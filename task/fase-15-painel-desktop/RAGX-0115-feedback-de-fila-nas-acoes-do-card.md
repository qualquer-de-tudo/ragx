# RAGX-0115: Feedback de fila nas ações do card (Instalar hooks e outras)

| | |
|---|---|
| **Fase** | 15: Painel desktop |
| **Prioridade** | P1: alta (defeito visível no uso diário) |
| **Estimativa** | 0,5d |
| **Depende de** | nenhuma |
| **Documentação** | [src/app/README.md](../../src/app/README.md) |
| **Status** | `review` (código e testes prontos; falta a verificação visual no app Electron de verdade) |

## Objetivo

Ao clicar em **Instalar hooks** no card de um projeto (tela Projetos), nada indica que o pedido entrou na fila: o botão continua igual e habilitado. A pessoa não sabe se o clique valeu, clica de novo e não vê o resultado. O mesmo vale para qualquer ação do card que não seja de indexação.

## Relato

> "Quando eu clico em instalar hooks não fala que foi pra fila, o botão fica disponível ali em projetos."

## Causa provável (confirmar antes de mexer)

O selo e o botão do card vêm de `deriveProjectState(project, busyProjectIds(jobs))`. Depois da revisão final da Task 9 do plano do painel v2, `busyProjectIds` (`src/app/src/state.ts`) só conta tarefas de indexação (`add-project`, `update`, `embed`, `reindex-full`), para o selo "Indexando…" não aparecer durante um `sync` ou um `graph`. Efeito colateral: uma tarefa `hooks-install` na fila não muda nada no card. A página de detalhe não sofre disso, porque os botões dela usam `activeJobFor` e mostram "Na fila" e "Rodando".

## Entregáveis

- [x] O botão principal do card fica desabilitado enquanto existe tarefa **do mesmo tipo** ativa para o projeto, com texto que diz o que está acontecendo ("Na fila" e "Instalando hooks…", "Gerando embeddings…" etc., no mesmo vocabulário do detalhe)
- [x] Confirmação leve no momento do clique: aviso "Adicionado à fila: Instalar hooks em {projeto}" com atalho para abrir a fila
- [x] Quando a tarefa termina com erro, o card mostra o motivo (hoje só a fila mostra)
- [ ] Quando termina bem, o estado do card muda sem esperar o próximo ciclo de 5 s (já existe reconstrução do snapshot ao fim de tarefa; conferir que cobre `hooks-install`)

## Fora de escopo

- Voltar a marcar "Indexando…" para tarefas que não indexam (foi decisão consciente)
- Reorganizar a fila ou o popover da fila

## Critérios de aceite

- [x] Clicar em "Instalar hooks" desabilita o botão no mesmo instante e o texto muda
- [x] Clique duplo não enfileira duas tarefas (a fila já deduplica; o botão deixa de convidar ao segundo clique)
- [x] Falha (por exemplo, pasta que não é repositório git) aparece no card com o motivo
- [x] Nenhum travessão em texto visível

## Testes

- [x] Teste do card: com uma tarefa `hooks-install` `queued` para o projeto, o botão está desabilitado com o texto esperado
- [x] Teste do card: tarefa `failed` mostra o erro
- [x] Teste de que uma tarefa de outro projeto não afeta o card

## Notas de verificação

O botão do card usa "Na fila" e "Rodando" (o mesmo vocabulário do detalhe), não "Instalando hooks…". Continua sem marcar: o entregável "o estado do card muda sem esperar o ciclo de 5 s" para `hooks-install` (não há teste específico) e a verificação no app Electron de verdade, que é visual e precisa ser feita à mão.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [x] `npm test`, `npm run lint` e `tsc` (app e electron) limpos
- [x] CHANGELOG atualizado na MESMA alteração
- [ ] Verificado no app Electron de verdade, não só nos testes
