# RAGX-0205 — Consumo real de tokens e adoção, lidos das sessões do Claude Code

| | |
|---|---|
| **Fase** | 25 — Economia real |
| **Prioridade** | P1 |
| **Estimativa** | 2d |
| **Depende de** | — |
| **Documentação** | [22-vscode-e-desempenho.md](../../docs/22-vscode-e-desempenho.md) · [27-benchmarks.md](../../docs/27-benchmarks.md) |
| **Status** | `review` |

## Objetivo

O painel mostra "tokens economizados" como arquivos inteiros − entregue: um contrafactual que superestima (o agente
quase nunca lê o arquivo inteiro). As sessões do Claude Code já gravam, por turno, os tokens de entrada (lidos do
cache, gravados no cache) e de saída, e cada chamada de ferramenta. O RAGX passa a ler isso (só números, nunca
texto) e mostrar o consumo real por projeto: turnos, tokens, buscas e leituras, e as sessões com e sem RAGX lado a
lado, como observação. A adoção (quantas sessões chamaram o RAGX, e quantas depois do lembrete) passa a vir da
mesma fonte, que não depende de o servidor MCP saber a sessão.

## Entregáveis

- [x] Leitor das sessões (`~/.claude/projects` e as pastas `projects` dos perfis registrados), filtrando por projeto
      pelo `cwd` gravado na sessão (raiz e worktrees); por sessão: início, perfil, turnos, tokens de entrada
      (normal, cache lido, cache gravado), saída, chamadas por tipo (busca, leitura, RAGX, outras) e tamanho dos
      resultados de busca e leitura
- [x] `ragx usage [--days N] [--json]`: por projeto, sessões, medianas com e sem RAGX, buscas e leituras por sessão
- [x] Painel: "Consumo real" no projeto e na Atividade, rotulado como observação; o número antigo vira
      "Economia estimada (contra arquivos inteiros)"; adoção e conversão do lembrete a partir das sessões
- [x] Nunca sai texto de prompt, resposta, comando ou caminho de arquivo das sessões; só contagens

## Fora de escopo

- Sessões de outros clientes (Codex, Gemini): formato próprio, fica para depois
- Afirmar causalidade: com e sem RAGX são grupos diferentes de tarefas

## Critérios de aceite

- [x] Testes com transcrições de exemplo (mensagens repetidas por id contadas uma vez, linhas inválidas ignoradas)
- [x] O painel não abre mais processos por minuto do que hoje (cache do resultado)
