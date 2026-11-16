# Fase 25: Economia real

Derivada da análise de 16/11/2026 sobre 57 sessões reais do Claude Code no Juriflux: o agente busca pelo Bash
(12.962 buscas via `grep`/`rg`/`find` contra 1.599 pelo Grep), quase nunca chama o RAGX, e uma busca do RAGX
devolve ~2.200 tokens contra ~400 de um grep. A economia que importa vem de **menos turnos** e **resultados
menores**, porque cada resultado fica no contexto e é relido do cache a cada turno. O número de economia do
painel (arquivos inteiros − entregue) superestima; a medição real (A/B de 02/10) deu custo −18% e turnos 6 → 3.

Objetivo da fase: quem baixar o RAGX economiza token sem fazer nada além de conectar o agente, e consegue ver
quanto economizou com número medido, não estimado.

## Tarefas

| ID | Tarefa | Prio | Est. | Status |
|---|---|---|---|---|
| [RAGX-0201](RAGX-0201-lembrete-nas-buscas-via-bash.md) | Lembrete também nas buscas via Bash | P1 | 0,5d | `review` |
| [RAGX-0202](RAGX-0202-instrucoes-para-clientes-sem-hook.md) | Instruções para Codex e Gemini CLI (Cursor e Windsurf não têm arquivo de instruções do usuário) | P1 | 0,5d | `review` |
| [RAGX-0203](RAGX-0203-busca-enxuta-e-mapa-de-arquivo.md) | Busca enxuta por padrão e mapa de arquivo no perfil slim | P1 | 1d | `review` |
| [RAGX-0204](RAGX-0204-embedding-escolhido-ao-criar-o-indice.md) | Embedding escolhido ao criar o índice | P2 | 0,5d | `review` |
| [RAGX-0205](RAGX-0205-consumo-real-de-tokens.md) | Consumo real de tokens e adoção, lidos das sessões do Claude Code | P1 | 2d | `review` |
| [RAGX-0198](../fase-23-pos-lancamento/RAGX-0198-indice-sem-mudanca-perguntando-ao-git-o-que-mudou.md) | Índice sem mudança: perguntar ao git | P2 | 1d | `review` |
| [RAGX-0206](RAGX-0206-scan-de-seguranca-que-cabe-no-painel.md) | Scan de segurança que cabe no painel | P1 | 1d | `review` |

## Fora de escopo da fase

- Federação, orquestração de tarefas e qualquer funcionalidade nova que não reduza token ou não meça a redução
- Trocar o modelo de embedding padrão por um maior (a qualidade da busca não é o gargalo; a adoção é)
- Botão de A/B no painel: o `ragx ab` faz chamadas reais e pagas; fica para quando o consumo real estiver na tela
