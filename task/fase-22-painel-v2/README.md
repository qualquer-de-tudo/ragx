# Fase 22: Painel v2

25 tarefas, derivadas da [auditoria 24](../../docs/24-auditoria-v2.md) (seção 6, achados U-01 a U-14 e lacunas de produto) e da [spec 25](../../docs/25-spec-v2.md) (seção 5.4, requisitos R-P1 a R-P11). O painel é o lugar onde a pessoa **vê** a v2 acontecer, então a fase tem três frentes: desempenho do próprio painel, fundação de design e UX, e produto.

Desempenho: com 12 projetos o painel dispara ~290 processos `git` por minuto (2 por projeto a cada 5 s, U-02), gasta ~2,7 s de processos filhos a cada 30 s só para checar conexões (U-03), relê o `mcp.jsonl` inteiro a cada 5 s por projeto (U-01) e faz tudo isso também com a janela minimizada (U-04). A auditoria não abriu o Electron real, então não há medição de RAM nem de CPU: a 0177 cria a linha de base antes de qualquer correção. Design: faltam escalas de espaço, tipografia e elevação, há contraste abaixo de AA (`--ink-3` a 3,67:1 em `--surface-3`, U-08), a casca quebra de 480 px e sob zoom (U-07) e falha de ação é silenciosa (U-09). Produto: sem economia em moeda, linha do tempo por sessão, preview de contexto, saúde com tendência, bandeja, auto-update e tema claro. Metas medíveis: S11 e S13 da spec 25; a 0195 fecha a v2 medindo S1 a S14.

## Tarefas

| ID | Tarefa | Prio | Est. | Status |
|---|---|---|---|---|
| [RAGX-0171](RAGX-0171-pausar-pollers-com-a-janela-oculta-instancia-unica.md) | Pausar pollers com a janela oculta; instância única | P0 | 0,5d | `done` |
| [RAGX-0172](RAGX-0172-snapshot-sem-spawn-de-git.md) | Snapshot sem spawn de `git` | P0 | 0,5d | `done` |
| [RAGX-0173](RAGX-0173-checagem-de-conexoes-barata.md) | Checagem de conexões barata | P0 | 0,75d | `done` |
| [RAGX-0174](RAGX-0174-telemetria-incremental-e-rotacao-do-log-da-cli.md) | Telemetria incremental e rotação do log da CLI | P0 | 0,75d | `done` |
| [RAGX-0175](RAGX-0175-so-re-renderiza-o-que-mudou.md) | Só re-renderiza o que mudou | P1 | 0,5d | `done` |
| [RAGX-0176](RAGX-0176-remover-o-fallback-que-le-knowledge-db-inteiro.md) | Remover o fallback que lê `knowledge.db` inteiro | P1 | 0,25d | `done` |
| [RAGX-0177](RAGX-0177-medir-ram-e-cpu-do-electron-em-execucao-linha-de-base.md) | Medir RAM e CPU do Electron em execução (linha de base) | P1 | 0,5d | `done` |
| [RAGX-0178](RAGX-0178-tokens-de-design-completos-e-contraste-aa.md) | Tokens de design completos e contraste AA | P1 | 0,75d | `done` |
| [RAGX-0179](RAGX-0179-primitivos-de-ui-compartilhados.md) | Primitivos de UI compartilhados | P1 | 1d | `done` |
| [RAGX-0180](RAGX-0180-toasts-toda-falha-de-acao-aparece.md) | Toasts: toda falha de ação aparece | P1 | 0,5d | `done` |
| [RAGX-0181](RAGX-0181-responsividade-da-casca-de-480-a-3440-px-e-zoom-200.md) | Responsividade da casca de 480 a 3440 px e zoom 200% | P1 | 1d | `done` |
| [RAGX-0182](RAGX-0182-skeletons-e-primeira-pintura-com-o-ultimo-snapshot.md) | Skeletons e primeira pintura com o último snapshot | P2 | 0,5d | `done` |
| [RAGX-0183](RAGX-0183-paleta-ctrl-k-e-atalhos.md) | Paleta Ctrl+K e atalhos | P2 | 1d | `done` |
| [RAGX-0184](RAGX-0184-detalhe-do-projeto-em-dia-economia-agente-usando.md) | Detalhe do projeto: em dia, economia, agente usando | P2 | 0,5d | `done` |
| [RAGX-0185](RAGX-0185-acessibilidade-grafico-por-teclado-e-setas-nos-grupos.md) | Acessibilidade: gráfico por teclado e setas nos grupos | P2 | 0,5d | `done` |
| [RAGX-0186](RAGX-0186-economia-em-moeda-configuravel.md) | Economia em moeda configurável | P2 | 0,75d | `done` |
| [RAGX-0187](RAGX-0187-preview-do-build-context-no-detalhe-do-projeto.md) | Preview do `build_context` no detalhe do projeto | P2 | 1,25d | `done` |
| [RAGX-0188](RAGX-0188-linha-do-tempo-de-sessoes-na-atividade.md) | Linha do tempo de sessões na Atividade | P2 | 1d | `done` |
| [RAGX-0189](RAGX-0189-saude-do-indice-com-tendencia.md) | Saúde do índice com tendência | P2 | 0,5d | `todo` |
| [RAGX-0190](RAGX-0190-adocao-sessoes-que-chamaram-o-ragx.md) | Adoção: sessões que chamaram o RAGX e as que não | P2 | 0,5d | `todo` |
| [RAGX-0191](RAGX-0191-bandeja-com-estado-e-notificacao-de-defasagem.md) | Bandeja com estado e notificação de defasagem | P3 | 1d | `todo` |
| [RAGX-0192](RAGX-0192-auto-update-com-electron-updater.md) | Auto-update com `electron-updater` | P3 | 1d | `todo` |
| [RAGX-0193](RAGX-0193-tema-claro.md) | Tema claro | P3 | 1d | `todo` |
| [RAGX-0194](RAGX-0194-csp-e-menu-minimo.md) | CSP e menu mínimo | P2 | 0,25d | `done` |
| [RAGX-0195](RAGX-0195-fechar-a-v2.md) | Fechar a v2: medir S1 a S14, publicar o relatório e conferir a documentação | P0 | 1d | `todo` |

## Dependências

```text
0177 ──> 0171, 0172, 0173, 0174, 0175
0171 ──> 0191 (também depende de 0189)
0171 ──> 0192
0178 ──> 0179, 0181
0178 + 0181 ──> 0193
0179 ──> 0180, 0182, 0183, 0184, 0185
0179 + 0154 (fase 20) ──> 0187
0179 + 0156 (fase 20) ──> 0188
0184 ──> 0189 ──> 0191
0156 (fase 20) ──> 0186
0156 (fase 20) + 0188 ──> 0190
independentes: 0176, 0194
0195 depende de todas as P0 e P1 (de todas as fases)
```

## Ordem sugerida

Trechos do [ROTEIRO-V2.md](../ROTEIRO-V2.md). Dentro de cada bloco, a ordem é a da lista. **Nunca inicie uma tarefa com dependência aberta**; se a próxima da lista estiver bloqueada, pule para a seguinte.

**Bloco 5 — painel: desempenho** (≈ 4 d)
0177 · 0172 · 0173 · 0171 · 0174 · 0175 · 0176 · 0194

**Bloco 6 — painel: fundação e UX** (≈ 7 d)
0178 · 0179 · 0180 · 0181 · 0182 · 0183 · 0184 · 0185

**Bloco 7 — painel: produto** (≈ 7 d)
0186 · 0187 · 0188 · 0190 · 0189 · 0191 · 0192 · 0193

**Fecho**: 0195.

A 0192 (auto-update) fica atrás de configuração desligada, porque o `.exe` não é assinado (RAGX-0124, adiada), e termina em `review`; a 0195 mede os números mas uma pessoa decide o que anunciar.
