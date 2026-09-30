# RAGX-0126: Tela "Atividade" ao vivo e sinal "em uso agora"

| | |
|---|---|
| **Fase** | 18: Painel — atividade ao vivo, lista de projetos e perfis do Claude |
| **Prioridade** | P1 |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0125 |
| **Status** | `done` |

## Objetivo

Ver, em tempo real, em quais projetos o RAGX está sendo usado, por quem e com
que custo: um item "Atividade" no menu e um sinal no card e no detalhe.

## Entregáveis

- [x] Processo principal acompanha `mcp.jsonl` e `cli.jsonl` de cada projeto
      local pelo deslocamento no arquivo (só o que foi acrescentado), junta as
      indexações em andamento e empurra os eventos ao renderer
- [x] Tela "Atividade": feed dos eventos das últimas 24 h, o mais novo em cima,
      com hora, projeto, o que foi (ferramenta MCP, comando, sessão, indexação),
      quem (perfil do Claude, terminal, hook), tokens e tempo; filtro por
      projeto e por tipo; indicador "ao vivo"
- [x] Card e detalhe mostram "em uso agora" quando houve evento no último minuto
- [x] Clicar num evento abre o projeto

## Fora de escopo

- Mostrar consulta ou conteúdo (o log não os tem, de propósito)
- Histórico além de 24 h na tela (o detalhe já tem economia de 14 dias)

## Critérios de aceite

- [x] Uma chamada MCP aparece na tela em até ~2 s, sem recarregar (leitura a cada 1,5 s; verificado com o painel rodando)
- [x] Arquivo de log grande não é relido inteiro a cada ciclo
- [x] Log com linha quebrada ou truncada não derruba o feed

## Testes

Unit do leitor incremental (deslocamento, arquivo truncado ou recriado, linha
inválida); vitest da tela e do sinal no card.

## Definition of Done

- [x] Critérios verificados
- [x] CHANGELOG na mesma alteração
- [x] src/app/README.md atualizado
