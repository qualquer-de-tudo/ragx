# RAGX-0126: Tela "Atividade" ao vivo e sinal "em uso agora"

| | |
|---|---|
| **Fase** | 18: Painel — atividade ao vivo, lista de projetos e perfis do Claude |
| **Prioridade** | P1 |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0125 |
| **Status** | `todo` |

## Objetivo

Ver, em tempo real, em quais projetos o RAGX está sendo usado, por quem e com
que custo: um item "Atividade" no menu e um sinal no card e no detalhe.

## Entregáveis

- [ ] Processo principal acompanha `mcp.jsonl` e `cli.jsonl` de cada projeto
      local pelo deslocamento no arquivo (só o que foi acrescentado), junta as
      indexações em andamento e empurra os eventos ao renderer
- [ ] Tela "Atividade": feed dos eventos das últimas 24 h, o mais novo em cima,
      com hora, projeto, o que foi (ferramenta MCP, comando, sessão, indexação),
      quem (perfil do Claude, terminal, hook), tokens e tempo; filtro por
      projeto e por tipo; indicador "ao vivo"
- [ ] Card e detalhe mostram "em uso agora" quando houve evento no último minuto
- [ ] Clicar num evento abre o projeto

## Fora de escopo

- Mostrar consulta ou conteúdo (o log não os tem, de propósito)
- Histórico além de 24 h na tela (o detalhe já tem economia de 14 dias)

## Critérios de aceite

- [ ] Uma chamada MCP aparece na tela em até ~2 s, sem recarregar
- [ ] Arquivo de log grande não é relido inteiro a cada ciclo
- [ ] Log com linha quebrada ou truncada não derruba o feed

## Testes

Unit do leitor incremental (deslocamento, arquivo truncado ou recriado, linha
inválida); vitest da tela e do sinal no card.

## Definition of Done

- [ ] Critérios verificados
- [ ] CHANGELOG na mesma alteração
- [ ] src/app/README.md atualizado
