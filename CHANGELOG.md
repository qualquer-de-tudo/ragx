# Changelog

Formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
versionamento [SemVer](https://semver.org/lang/pt-BR/).

> **Regra deste arquivo:** toda alteração relevante atualiza o CHANGELOG na
> MESMA alteração que a produz. Deixar para depois é como uma correção some do
> histórico — quem a escreveu lembra do porquê; a próxima pessoa, não.

## [Não lançado]

### Adicionado

- **`ragx watch` com ciclo ocioso mais barato.** A cada 2 s o watcher reconstruía o `SecurityGate` e o `IgnoreEngine` e
  fazia 5 syscalls por arquivo. Agora o gate é construído uma vez (refeito só quando um `.gitignore`, `.dockerignore`
  ou `.ragignore` muda), o veredito de ignore fica em cache, a enumeração usa `os.scandir` e o lote vai por
  `index_paths`. Medido num projeto sintético: 643 arquivos 126 para 48 ms, 2.000 arquivos 282 para 97 ms por ciclo;
  segredo criado depois de 50 ciclos continua bloqueado (RAGX-0147).
- **Cache de embedding em SQLite, em lote, com checkpoint.** O cache guardava um arquivo por chunk e o `embed_pending`
  fazia dois `SELECT` por chunk e só gravava no fim. Agora é um SQLite por modelo lido e escrito em lote, um único
  `SELECT` busca o que falta, e a cada 10 lotes o que já foi embutido é gravado: um `ragx index` morto no meio
  retoma de onde parou. Num projeto sintético de 4.001 chunks, a parte de cache e prefixo foi de 3,8 s para 0,37 s e o
  primeiro índice de 7,5 s para 3,7 s; o cache antigo é lido de passagem (RAGX-0146).
- **Tema claro no painel, como preferência.** O painel era só escuro. Agora Preferências tem "Tema": Escuro (o
  padrão, intocado), Claro e Seguir o sistema, com troca na hora e sem reiniciar. Todos os tokens de cor foram
  redefinidos para o claro, com contraste AA conferido por teste nos dois temas, e a janela e o `nativeTheme` do
  Electron acompanham o tema salvo (RAGX-0193).
- **Atualização do painel pelo GitHub Releases, desligada por padrão.** Atualizar era baixar o instalador novo e rodá-lo
  por cima, sem aviso de que existe uma versão nova. Agora Preferências tem "Verificar atualizações do painel"
  (`electron-updater`): desligado não faz nenhuma chamada de rede, ligado confere ao abrir e quando você pede, e só
  baixa e instala quando você manda. A release passa a anexar `latest.yml` e o `.exe.blockmap`. O `.exe` não é
  assinado: o Windows pode alertar, e a tela diz isso. Falta testar uma atualização real entre duas versões
  (RAGX-0192, em revisão).
- **Bandeja com estado e notificação de defasagem no painel (desligadas por padrão).** O painel só avisava que um
  índice ficou defasado a quem estivesse olhando. Agora a página Preferências (nova) liga um ícone na bandeja com o
  estado geral em texto e uma notificação do sistema quando um projeto continua defasado por mais de 2 minutos, uma vez
  por episódio (depois de um commit com hook o índice fica defasado por alguns segundos e isso não avisa); o clique
  abre o detalhe do projeto. Com a notificação ligada e a janela fora da vista, o painel confere os projetos no máximo
  uma vez por minuto, sem abrir processos (RAGX-0191).
- **Saúde do índice com tendência no detalhe do projeto.** O painel dizia só se o índice está em dia agora. Agora a
  Visão geral tem "Saúde do índice": nível em texto, poucas checagens (embeddings pendentes, última indexação com
  erro, falhas seguidas, hooks ausentes) com a ação que resolve, e a tendência das últimas indexações (mediana de
  duração com e sem mudança, falhas e se está mais lenta, estável ou mais rápida), com gráfico e tabela. Com menos de
  6 indexações diz "poucos dados" (RAGX-0189).
- **Adoção pelos agentes no painel.** A adoção só se media à mão, lendo transcripts. Agora a Atividade mostra "x de y
  sessões chamaram o RAGX (z%)" desde o evento mais antigo lido (até 14 dias), por projeto e no total, e o detalhe
  do projeto mostra as sessões dele; linha sem sessão e chamada sem início registrado ficam fora da razão e são
  contadas à parte. Só contagens: nada de consulta (RAGX-0190).
- **Visão "Sessões" na Atividade do painel.** O feed era plano e misturava as chamadas de conversas diferentes. Agora
  dá para alternar para uma linha por sessão (quem, projeto, intervalo, chamadas, tokens entregues, se usou o RAGX,
  inícios de contexto de subagentes e falhas, com "sem dado" quando o log não tem `ok`), que abre os eventos em
  ordem. Eventos sem sessão ficam em "Sem sessão identificada" e o mesmo id em dois projetos nunca funde
  (RAGX-0188).
- **Preview do `build_context` no painel e `ragx context --query-stdin`.** O dono não tinha como ver o que o agente
  receberia para uma pergunta. Agora a aba Economia tem "Pré-visualizar o contexto": trechos, arquivos e linhas,
  tokens do orçamento e descartes, sem mostrar código. A pergunta vai só por stdin (nova opção `--query-stdin`, que
  também força o cache desligado), nunca no argv, em log, em mensagem de erro nem no cache em disco; o processo
  principal descarta `query` e `content` da resposta. Em JSON, pacote vazio agora sai 0 com `fragments: []`. Corrigido:
  `ragx context "x"` sem `--tokens` saía com erro de uso (RAGX-0187).
- **Economia em dinheiro, com o preço que você informa.** O painel só mostrava tokens e percentual. Agora "Configurar
  preço" (moeda e preço por milhão de tokens de entrada, guardados no `settings.json` do painel) faz o card de
  Economia, o resumo de Projetos e Atividade mostrarem o valor, sempre como estimativa. O RAGX não embute tabela de
  preços nem câmbio e não usa rede; sem preço, nenhuma tela mostra dinheiro (RAGX-0186).
- **Gráfico de economia por teclado e alvos de clique de 24 px no painel.** O gráfico só respondia ao mouse (quem usa
  teclado ou leitor de tela só chegava aos números pela tabela) e 180 alvos medidos ficavam abaixo de 24x24 px (o
  interruptor, os nomes de projeto nas listas e nos cartões). Agora cada dia é focável com nome acessível, setas,
  Home e End percorrem os 14 dias e o balão acompanha o foco; os alvos passaram a ter 24 px (0 abaixo disso nas telas
  medidas) e um teste com axe-core (0 violações `serious` e `critical`) e o harness visual vigiam a volta
  (RAGX-0185).
- **Detalhe do projeto responde as três perguntas no topo.** "O índice está em dia?" era a segunda coisa da página, a
  economia ficava noutra aba e o uso pelo agente vinha embaixo. Agora uma faixa antes das abas, em todas elas, diz em
  texto se está em dia (com o primeiro motivo e o botão da ação), quanto economizou nos últimos 14 dias (com "Ver
  gráfico") e se o agente está usando (em uso agora, a última chamada ou nenhuma chamada). Medido a 900 x 600 px: as
  três respostas aparecem sem rolar (RAGX-0184).
- **Paleta de comandos (Ctrl K) e atalhos no painel.** Ir de um projeto a outro ou disparar "Atualizar" exigia vários
  cliques. Agora `Ctrl K` abre uma paleta (sem acento nem maiúscula) que navega e enfileira só `update` e `embed`,
  `/` foca a busca, `?` mostra a ajuda e `Ctrl 1` a `Ctrl 4` trocam de tela. Nada destrutivo passa pela paleta, e
  nenhum atalho usa Alt (RAGX-0183).
- **Primeira pintura do painel sem esperar o snapshot, com cache e erro.** O painel abria numa tela cheia de
  "Carregando…" até o primeiro snapshot (um `git` por projeto) e, se `getSnapshot()` falhasse, ela nunca saía. Agora a
  casca aparece com skeletons em 115 ms, o último snapshot (guardado em `localStorage`, sem o estado de conexões) é
  pintado em 186 ms com a faixa "Dados de HH:mm, atualizando…" e trocado pelo vivo sem remontar, e a falha mostra o
  motivo com "Tentar de novo". Conexões e "Está em dia?" também usam skeleton (RAGX-0182).
- **O painel passa a caber de 450 a 3440 px.** Com zoom de 150% a 200% (600 e 450 px de CSS) a barra superior e o
  conteúdo estouravam a janela (818 px a 480 px) e, a 3440 px, a barra e o conteúdo tinham bordas diferentes (1084 px
  de diferença). Agora a barra superior fica compacta até 900 px e em duas linhas até 640 px, o conteúdo e a barra
  compartilham as mesmas bordas e uma largura máxima que cresce em tela larga, os breakpoints são só 640, 900 e
  1200, e a economia, o feed e o cartão de projeto reagem ao espaço que têm (`@container`). Um harness
  (`node scripts/visual-check.mjs`, Edge pelo `playwright-core`) mede 10 telas em 6 larguras: de 96 estouros para 0
  (RAGX-0181).
- **Toda falha de ação do painel aparece num aviso.** Enfileirar uma tarefa, cancelar, copiar o texto de ajuda,
  escolher pasta e salvar o fim do assistente só escreviam no console: a pessoa clicava e nada acontecia. Agora um
  aviso (`role="alert"` para erro, `role="status"` para sucesso, no máximo 3, erro some em 8 s e sucesso em 4 s,
  com o prazo pausado em hover e foco) mostra "Não foi possível ...: <motivo>" sem o prefixo do Electron, e uma
  tarefa que falha em andamento também avisa (RAGX-0180).
- **Primitivos de UI compartilhados no painel.** O controle segmentado, o interruptor, o modal com foco preso, os
  ícones em SVG e as telas vazias estavam copiados à mão em vários arquivos (2 dos 3 segmentados não tinham setas), e
  10 atributos `title` levavam informação que teclado e toque não alcançam. Agora vivem em `src/components/ui/`
  (`Segmented`, `Switch`, `Modal`, `Icon`, `IconButton`, `EmptyState`, `Tooltip`), os usos foram migrados, os 3 grupos
  segmentados respondem a seta, Home e End, a dica abre no foco e no mouse, e um teste impede a volta (RAGX-0179).
- **Tokens de design completos e contraste AA no painel.** O `index.css` só tinha cor, raio e fonte, e 8 pares de
  cor ficavam abaixo de 4,5:1 (texto de apoio, botão primário e perigo, selos azul e vermelho). Agora há tokens de
  espaço, tipografia, camadas, movimento e estado semântico completo, o contraste passa AA (calculado por teste, por
  tema), `App.css` não tem mais cor literal (15 → 0) e os tamanhos de fonte caíram de 16 para 8 da escala (mais o
  10 px da logo). O hover dos botões ficou 6% mais claro em vez de 12%, para continuar AA. Travas: `contrast`,
  `no-hardcoded-color` e `css-ratchet` (RAGX-0178).
- **CSP restritiva, menu mínimo e DevTools desligadas no painel de produção.** O renderer não tinha
  Content-Security-Policy e o Electron usava o menu padrão (Alt abria Recarregar e Ferramentas do desenvolvedor).
  Agora o build de produção injeta uma política `default-src 'none'` (sem `unsafe-eval`, sem `unsafe-inline` em script
  nem estilo, sem host remoto), o menu fica em Edição, Exibir (zoom) e Sair, e as DevTools só abrem em
  desenvolvimento ou com `RAGX_DEVTOOLS=1`. Percorridas as telas do build de produção: 0 violações (RAGX-0194).
- **O painel não lê mais o `knowledge.db` e perdeu o `sql.js`.** Sem `.ragx/status.json`, o painel carregava o banco
  inteiro na memória a cada 5 s só para três `COUNT(*)`. Agora o projeto sem `status.json` aparece como "Defasado",
  com o motivo e o botão "Atualizar agora" (que gera o arquivo), e a dependência saiu: `app.asar` de **30,3 para
  9,0 MB**, uma dependência de runtime a menos (RAGX-0176). O estado "Com problema" fica só para `last_error`.
- **O painel só re-renderiza o que mudou.** Com os dados parados, o renderer refazia tudo a cada 5 s (o snapshot
  chega com `generatedAt` novo e objetos novos, o relógio do `App` e nenhum `memo`). Agora o snapshot, a fila e as
  conexões mantêm a referência quando o conteúdo é o mesmo, o processo principal não manda `ragx:snapshot` repetido,
  o relógio é um só e o "há N min" é uma folha própria. Com 12 projetos parados por 60 s: **300 → 12** renders de
  card e **24 → 0** do `App`; mudando um projeto, só o card dele renderiza (RAGX-0175).
- **Telemetria incremental no painel e rotação dos logs.** O painel relia o `mcp.jsonl` inteiro de cada
  projeto a cada snapshot (5 s) e o servidor nunca rotacionava `mcp.jsonl` nem `cli.jsonl`: o custo era latente
  e crescia sem limite (`[log] retain_days` nem tinha leitor). Agora o painel lê só o que foi acrescentado
  (um `stat` e o mesmo objeto de volta quando nada mudou), o resumo é idêntico ao da leitura completa, e os dois
  logs rotacionam aos **5 MiB** para `<nome>.1` (`retain_days` apaga o `.1` velho). Medido com 12 projetos: log de
  10 MB **777 → 0,9 ms** por ciclo, de 50 MB **7.227 → 1,96 ms** (RAGX-0174).
- **O painel para de trabalhar quando ninguém o está vendo, e abre uma só vez.** Os três pollers (snapshot
  a cada 5 s, conexões a cada 30 s, atividade a cada 1,5 s) rodavam também com a janela minimizada, oculta,
  com a tela bloqueada ou o computador suspendendo (~290 processos `git` por minuto, medido na RAGX-0177).
  Agora pausam nesses estados e retomam na volta (um snapshot na hora se algo mudou ou já passou o
  intervalo); uma tarefa que termina com a janela fora da vista só marca o snapshot como sujo, e a fila não
  pausa. Medido com 12 projetos: janela minimizada de **~284 para 0,5 filho por minuto** (e 0 `git`), oculta
  **0**. O painel agora é de **instância única** (abrir de novo foca a janela existente; os modos do
  instalador `--bootstrap` e `--uninstall-cli` não pegam a trava, e `RAGX_PANEL_ALLOW_MULTI=1` a desliga) e o
  `win.on('closed')` passou a zerar também o poller de atividade (RAGX-0171).
- **Checagem de conexões barata no tick de 30 s.** A cada 30 s o painel rodava `ragx --version`, `docker
  --version`, `docker info`, `docker ps -a` e `tasklist` (~2,8 s de processos filhos por minuto). Agora a
  versão do `ragx` fica em cache pela assinatura do executável, o Docker é consultado por UM `docker ps`, e o
  tick de fundo usa uma detecção **leve** (API do Ollama primeiro; `docker ps` só se o Docker estava de pé,
  senão a cada 5 min; `tasklist` só com suspeita de conflito; "Ollama local rodando" inferido com a API no
  ar e sem container). Início do app, fim de tarefa, "Verificar agora" e as condições da fila seguem com a
  detecção completa. Medido: de ~300 para **~3 processos filhos por minuto** (com a RAGX-0172) e de ~17 s
  para **1,35 s por minuto** de tempo de filhos. `localhost` e `127.0.0.1` não diferem no Electron e não
  foram trocados (RAGX-0173).
- **O painel lê branch e commit dos arquivos do git, sem criar processo.** O snapshot rodava `git
  rev-parse HEAD` e `git symbolic-ref` por projeto a cada 5 s: **~290 processos `git` por minuto** com 12
  projetos, mesmo com a janela minimizada. Agora lê `.git/HEAD`, a ref solta ou `.git/packed-refs` (e
  `commondir` em worktree e submódulo; só metadado, até 64 KB por arquivo, nenhum conteúdo de código), com
  cache por assinatura de `mtime` e tamanho que devolve o mesmo objeto enquanto nada muda. O `git` só roda
  como último recurso (`reftable`, formato desconhecido). Medido com o amostrador da RAGX-0177: **`git` de
  290,8 para 0 por minuto**, `buildSnapshot` de **141,9 para 2,9 ms**, e o tempo de processos filhos de
  16,8 para 6,5 s por minuto (RAGX-0172).
- **O painel mede o próprio consumo (opt-in).** A auditoria só tinha comandos isolados: "o Electron real não
  foi aberto". Com `RAGX_PANEL_METRICS=<arquivo.jsonl>` o painel amostra, a cada 5 s, RAM e CPU de cada
  processo (`app.getAppMetrics()`) e os processos filhos que ele cria por executável (`git`, `ragx`,
  `docker`...), e `node scripts/measure-runtime.mjs --plan visible:5,minimized:5,hidden:5` leva a janela a
  cada estado e acrescenta o resumo a `src/app/docs/medicao-runtime.md`. Sem a variável nada é criado, e
  nenhum canal IPC foi acrescentado. **Linha de base (12 projetos, 15 min):** ~288 `git` por minuto nos três
  estados (a auditoria estimava ≈290), o mesmo com a janela minimizada ou oculta; ~335 MB de RAM; CPU do
  painel ~0,1 a 0,2% de um núcleo, mas **17 a 20 s por minuto de processos filhos** (RAGX-0177).
- **`ragx ab`: harness de A/B de economia.** "O RAGX economiza X%" não era afirmável (o baseline do painel
  e do `trial` é o arquivo inteiro). `ragx ab` planeja as mesmas tarefas por `claude -p` em três braços
  (`without`, `full`, `slim`), com o mesmo modelo e ferramentas, ordem girando por tarefa, e compara o
  `usage` real (tokens faturáveis, custo, turnos) **só onde os dois braços acharam o arquivo certo**,
  com quartis, intervalo por bootstrap e o rótulo "inconclusivo" (menos de 10 tarefas ou intervalo que
  cruza zero). Por padrão só imprime o plano (nada é executado); `--simulate` roda com números sintéticos
  marcados `simulated`; `--execute` roda de verdade e exige `RAGX_AB_REAL=1` e `--max-calls N` (gasta cota
  da conta). Não grava o texto das respostas. **Nenhuma chamada real foi feita**: a economia segue
  desconhecida até uma pessoa executá-lo (RAGX-0162).
- **Subagente `ragx-explorer` instalável (opt-in).** `ragx claude agent install` (ou `ragx claude on
  --agent`) grava `<perfil>/agents/ragx-explorer.md`: um explorador só de leitura (RAGX, `Read`, `Grep`,
  `Glob`) que usa o RAGX primeiro e **responde curto**, para a exploração não encher o contexto do
  agente principal. Desligado por padrão (aparece na lista da pessoa), com marcador de versão: só o
  arquivo com o marcador é atualizado ou removido, e um arquivo da pessoa com o mesmo nome nunca é
  sobrescrito. A `description` (que entra no contexto principal) tem ~44 tokens. `agent remove|status` e
  `agent` em `claude status --json`. O efeito em tokens só se mede no A/B da RAGX-0162 (RAGX-0161).
- **Lembrete do índice no primeiro `Grep`/`Glob` da sessão.** Quase ninguém chamava o RAGX (3 de 38
  sessões em projetos indexados): o hint de `SessionStart` é lido uma vez e esquecido, e o modelo vai no
  que já está carregado. `ragx claude on` instala agora um hook `PreToolUse` (`Grep|Glob`) que roda
  `ragx claude nudge`: na primeira busca da sessão devolve `additionalContext` (~50 tokens) lembrando do
  `build_context`. Sugere, **nunca bloqueia**, cala fora de projeto indexado e nas repetições (marcador
  `O_EXCL` por `session_id`, apagado depois de 7 dias), não ecoa o `tool_input`, sai com 0 em qualquer
  erro e roda pela entrada leve (**~105 ms** imprimindo, **~83 ms** calado; meta 120). `--no-nudge`
  desliga. Os marcadores da dica de `SessionStart` passam a ser podados do mesmo jeito (RAGX-0160).
- **Dica de início de sessão enxuta e uma vez por sessão.** `ragx claude hint` custava ~349 tokens
  (tiktoken) e repetia em cada subagente, inflando também a contagem de sessões do painel. O texto agora
  tem **~140 tokens** (a regra, as três ferramentas e a linha de ToolSearch; sai o resumo de documentos,
  data e branch do índice, que `stale_paths` substitui onde importa) e sai **uma vez por sessão**: o
  hook lê `session_id` e `source` do stdin, marca a entrega em `.ragx/cache/hint/<session_id>` e, na
  repetição, cala e não grava o `session_start`. `source` igual a `clear` ou `compact` reentrega. Sem
  `session_id` (uso manual, stdin vazio ou inválido) a dica sai sempre (RAGX-0164).
- **Dedupe de sessão no `build_context` do MCP (desligado por padrão).** Com `[context] session_dedupe =
  true`, o chunk que a sessão já recebeu volta como referência (`caminho:linhas [id]`, reabrível com
  `get_chunk`) em vez do conteúdo inteiro, e `get_chunk` continua devolvendo o conteúdo íntegro. O
  livro-razão guarda só metadado (nunca conteúdo), com TTL (45 min) e teto de entradas, e a resposta e a
  telemetria trazem `dedupe_refs` e `dedupe_saved_tokens`. Medido em 3 consultas sobrepostas neste
  repositório: **−4,2%** (8.110 → 7.767 tokens). Por isso e pelo risco (o servidor não sabe quando o
  cliente compacta o contexto, nem distingue subagente) o padrão é **desligado**; a RAGX-0162 decide
  (RAGX-0159).
- **Descrições das ferramentas MCP para Tool Search, `instructions` com teto e lista estável.** As 33
  descrições foram reescritas: começam por um verbo, dizem o que a ferramenta faz com os termos de quem
  procura ("localiza", "onde", "quem chama", "reindexa") e têm no máximo 200 caracteres (a maior: 141).
  As `instructions` passam a ser montadas por perfil em `playbook.py` (o `slim` não cita `get_playbook`
  nem `sync`), com teto de 2.048 bytes (hoje 531 no `full`, 356 no `slim`) e sem depender de estado da
  sessão. Dois arquivos-ouro (`tests/fixtures/mcp_tools_full.json` e `mcp_tools_slim.json`) travam a lista:
  mudar uma descrição ou um schema por acaso agora falha o teste, e regravar é deliberado. Custo fixo: o
  `full` foi de 2.575 para 2.680 tokens (as descrições ficaram mais informativas, +4%) e o `slim` de 355
  para 370 (RAGX-0158).
- **Perfil `slim` do servidor MCP: 6 ferramentas.** O servidor expõe 33 ferramentas e só 5 aparecem
  nos logs de uso real; as outras 28 custam tokens em todo turno (2.773 tokens de nome, descrição e
  schema, na régua de antes). `[mcp] profile = "slim"` (ou `RAGX_MCP_PROFILE=slim`, ou
  `ragx mcp serve --profile slim`) expõe só `get_dictionary`, `search_hybrid`, `build_context`,
  `get_chunk`, `get_entity` e `refresh`, com descrições curtas e schemas sem `title`/`default`/`anyOf`:
  **~380 tokens, −86%**. O padrão continua `full` (33, nada renomeado): trocar para `slim` é decisão de
  quem usa. `ragx perf` e `ragx mcp tools` liam `inputSchema` e o campo do SDK é `input_schema`: a
  régua contava ~1.000 tokens em vez de ~2.800 e `ragx mcp tools --json` imprimia `input_schema: null`.
  As mensagens de "outra operação em andamento" deixaram de mandar usar uma ferramenta (`get_status`)
  que não existe (RAGX-0157).
- **Clone novo usa os embeddings versionados.** O projeto versiona os vetores int8 em `knowledge/embeddings/`
  para que um clone não recalcule nada, mas `serialize.read_embeddings` não tinha chamador: num clone
  `ragx sync` falhava com "banco não encontrado" e o primeiro `ragx index` reembedava todos os chunks.
  Agora `ragx sync` funciona sem banco prévio, importa o int8 versionado dos chunks que continuam iguais
  (só do mesmo modelo, só chunk que existe, só vetor válido, nunca sobrescreve um float32) e embute apenas
  o que falta; os importados ficam só grosseiros e a busca avisa em `partial` até `ragx index
  --embed-only` completar o float32. Num clone sem alterações locais, **0 textos** vão ao embedder (antes,
  todos). Sem banco mas com `knowledge/`, os comandos de consulta mandam rodar `ragx sync`. Hooks, `watch`
  e `touch` não completam o float32 em segundo plano (RAGX-0144).
- **Expansão do grafo: semeadura pelo topo, filtros honrados e grau só dos visitados.** A expansão
  semeava todas as entidades dos documentos dos 100 melhores chunks (90 a 304 sementes nas 26 consultas
  do repositório; truncada em 26 de 26, sem andar), ignorava `path_glob`/`lang`/`kind` (130 de 650
  resultados fora do filtro) e calculava o grau de todas as entidades a cada expansão. Agora as sementes
  são as entidades dos `[graph] seed_top_k` (10) primeiros chunks (6 a 10 sementes, **0 de 26 truncadas**),
  o teto `max_nodes` conta só os nós expandidos, o desempate é determinístico, o filtro vale para o que o
  grafo traz (**0 de 650 fora do filtro**) e o grau vem de uma consulta agrupada só dos vizinhos.
  `--explain` e `pack.stats` ganham `graph_expanded`, `graph_truncated` e `graph_only`. **Atenção:** com a
  expansão funcionando, o MRR do grafo nessas consultas cai de 0,593 para 0,381 (recall@5 igual, 0,731):
  os vizinhos passam à frente do arquivo certo; a decisão sobre o peso do grafo na fusão ficou em aberto.
  O cache do contexto foi invalidado (`CACHE_FORMAT` 3), porque o conteúdo muda (RAGX-0145).
- **Entrada leve para os hooks.** `ragx claude hint` (roda em toda sessão do Claude Code, até em
  subagente) levava 493 ms e o `hook-run post-commit` bloqueava o commit por 509 ms, porque o ponto de
  entrada importava typer, rich, pydantic e 25 módulos de comando antes de olhar o primeiro argumento.
  `ragx` e `rag` agora apontam para `ragx.entry:main`, que despacha `claude hint`, `touch --stdin-json`
  e `hook-run` para `ragx.hooklight` (só stdlib): **hint 493 → 86 ms, commit 509 → 114 ms** (mediana
  de 12; metas S7 120 ms e S8 150 ms). A dica sai idêntica byte a byte; o resto vai para a CLI
  completa. O `post-checkout` ganhou uma guarda no shell do hook (`[ "$3" = "1" ]`): `git checkout --
  arquivo` não sobe Python nenhum. **Hooks já instalados:** rode `ragx hooks install` de novo para
  ganhar a guarda (`ragx hooks status` avisa); instalações editáveis precisam de `uv tool install
  --editable --force --python 3.12 ".[all]"` para enxergar o novo ponto de entrada (RAGX-0143).
- **Aquecimento do servidor MCP.** A primeira `search_hybrid` de cada sessão pagava o carregamento do
  modelo de embedding e do `tiktoken` (1.447 ms medidos neste repositório, 3 a 5 s nos logs reais). O
  servidor agora os carrega numa thread em segundo plano ao subir (`[mcp] warmup`, padrão ligado, só em
  pasta com índice): a primeira busca depois de 5 s ociosos leva **42 ms**, e o `initialize` não
  piora (910 → 922 ms). `build_embedder` e `count_tokens` passaram a ser seguros entre threads (trava
  por configuração): busca e aquecimento simultâneos constroem o modelo uma vez só. Falha no
  aquecimento vai para `errors.log` e não derruba o servidor. Script de medição:
  `scripts/medir_mcp_frio.py` (RAGX-0142).
- **Veredito guardado de arquivo fora do índice (`file_verdicts`).** Arquivo `unsupported`, binário,
  indecodável ou bloqueado nunca entrava em `documents`, então o atalho de tamanho+mtime não valia
  para ele: era relido inteiro e passava de novo pelo Security Gate a cada rodada (e os bloqueados
  refaziam `DELETE`+`INSERT` em `security_events`). Com 800 `.csv` o `index` sem mudança lia **800
  arquivos, agora 0**, e caiu de 629 para 344 ms (p50, processo quente; o resto é a varredura).
  Novo `0008_file_verdicts.sql` (`SCHEMA_VERSION` 8). O cache só mantém um arquivo FORA do índice
  (nunca admite), vale só com o mesmo tamanho, `mtime` e o mesmo contexto (hash das regras de
  segurança, `[security]`, `[index]`, versões), e `--full` o refaz. Trocar a política de `strict` para
  `balanced` reavalia e o arquivo entra redigido (RAGX-0139).
- **Aviso de edição: hook `PostToolUse`, `ragx touch` e `stale_paths` na busca.** Uma edição não
  commitada só entrava no índice pelo `refresh` (26 a 91 s) ou no próximo commit. `ragx claude on`
  instala agora um hook assíncrono (`Edit|Write|MultiEdit`) que roda `ragx touch --stdin-json`: o
  caminho editado vai para `.ragx/touch.queue` (um `write` atômico, a raiz vem do próprio arquivo) e
  uma drenagem destacada reindexa só ele (`index_paths`); várias edições em 400 ms viram uma
  reindexação. O servidor MCP drena a fila antes de buscar e, se algo não puder ser reindexado, a
  resposta traz `stale_paths` e `stale_count`. `--no-touch` desliga, `off` remove só o nosso hook, e
  o texto da dica e do playbook deixou de mandar chamar `refresh` a cada edição (RAGX-0141).
- **Reindexação por caminho: `index_paths` e `ragx index --only`.** Reindexar um arquivo editado
  pagava a varredura do projeto, o git e a leitura dos hooks (703 ms mesmo depois da poda e do
  embedder preguiçoso). `index_paths` reindexa só os arquivos pedidos, com o mesmo Security
  Gate (a leitura de bytes vive num só lugar, `_examinar`, que a varredura e `iter_paths`
  compartilham): **703 ms → 107 ms** (p50, processo quente, 1 arquivo alterado, 15 chunks mantidos
  e 1 trocado). Recusa caminho absoluto, `..`, `@base/`, pasta podada e link para fora da raiz,
  respeita a trava e o arquivo ilegível, e equivale a `index_project` em 12 rodadas sorteadas
  (`.gitignore`, pasta ignorada, arquivo grande, binário, `.env`). Grava uma run `mode='paths'` que não
  vira "a última indexação" do veredito de frescor. Cai no incremental completo com mais de
  `watch.max_batch` caminhos ou com um arquivo de regra. É a base do hook de edição (RAGX-0141)
  (RAGX-0140).

- **Guia de uso do RAGX** (`docs/GUIA-DE-USO.md`): do instalador ao agente
  consultando o índice — instalação e SmartScreen, configuração inicial, telas
  do painel, as três conexões, MCP, comandos do terminal, problemas comuns e
  desinstalação. Vai anexado à release.

### Alterado

- **Teto do `build_context` e `response_format` `concise`/`detailed`.** O agente podia pedir até 32.000
  tokens de contexto e a busca devolvia o conteúdo inteiro de cada hit mesmo quando só queria
  localizar. Agora `[mcp] max_context_tokens` (5.000) limita o pedido e a resposta diz
  (`tokens_capped`), sem cortar em silêncio (uso real: máx. 3.239 tokens, nenhum acima de 5.000), e
  `response_format` (padrão `concise`) faz a busca devolver um `snippet` de 140 caracteres no lugar de
  `content`: `search_hybrid` com 10 hits **2.915 → 1.108 tokens (−62%)**; com `snippet_chars` 200 seriam
  −56,8%, abaixo da meta de −60%, então o padrão é 140. `detailed` devolve o conteúdo como antes
  e, no `build_context`, acrescenta `intent`, `fragments_meta`, `dropped` e `stats`. **Muda o
  comportamento:** quem lia `content` na busca passa a ver `snippet` (abra o trecho com `get_chunk`);
  `[mcp] response_format = "detailed"` reverte sem código. O plugin do VS Code pede `detailed`
  (RAGX-0165).

- **A economia do `ragx trial` e do painel fica honesta: dois baselines, a conservadora e nada de
  "real".** O "sem RAGX" era o arquivo inteiro (`size_bytes // 4` no log, `read_text` no trial), em
  unidade diferente do entregue, e a economia logada (92,7%) passava da entrega real (~82%). Agora o
  `trial` compara o markdown entregue com o **oráculo** (os arquivos certos, inteiros) e com um **Grep
  simulado** (`--grep-files K`, padrão 1) e mostra a economia **conservadora**, contra o menor dos
  dois: neste repositório (26 consultas, `--budget 3000`) **27,2% pelo oráculo e 24,2% pela
  conservadora com K=1**, 8 e 15 consultas negativas, cobertura de fonte 58%. O `baseline_tokens` do
  log do servidor passa a ser a soma de `chunks.token_count` dos documentos-fonte, na mesma unidade do
  entregue (antes `bytes/4`, que em markdown erra por ~30%), e a conta saiu de `ragx.mcp` para
  `ragx.context.baseline`. O painel diz "Arquivos inteiros (limite superior)" e "Economia estimada" e
  mostra a conservadora e os dois baselines quando o CLI os traz (o `ragx trial` antigo continua
  legível). Logs antigos seguem em bytes/4 (RAGX-0163).

- **A telemetria do MCP diz se a chamada deu certo e quanto saiu.** A linha de `mcp.jsonl` não
  tinha `ok`, `err_code` nem tamanho: uma chamada que devolvia `ok: false` (`not_found`,
  `rate_limited`) era gravada como sucesso, as que falhavam por argumento inválido ou erro
  interno saíam sem resultado, e a taxa de erro não era calculável (55 linhas no log deste
  repositório, 19 sem `session` nem nenhum agrupador). Agora toda linha leva `v: 2`, `ok`,
  `resp_chars` e `resp_tokens` (o texto exato que o cliente recebe; contar tokens de 30 KB custa
  ~1,2 ms), `proc` (8 hex por servidor, que agrupa quando não há `session`) e, com `ok: false`,
  `err_code` (nunca a mensagem nem a consulta). `ragx perf` mostra `n` e a taxa de erro por
  ferramenta, tratando linha antiga como "desconhecida", e o parser do painel lê os campos novos
  (a tela é da 0188/0190). Aditivo: o log já gravado segue legível (RAGX-0156).

- **Respostas MCP compactas: sem indentação, sem duplicar em `structuredContent`, sem
  `outputSchema`, sem repetição.** Toda resposta saía com `indent=2` (o SDK reindentava o
  `dict`), era repetida em `structuredContent` (o JSON ia duas vezes no fio) e cada uma das 33
  ferramentas anunciava um `outputSchema` que não serve ao modelo. Agora o servidor devolve
  JSON compacto (`dump`) uma vez só, as chaves nulas somem (`compact`; ausência = `null`), `project`
  vai uma vez em `data.project` (o federado mantém por hit), `score` tem 4 casas, `chunk_id` vai com
  12 hex e `get_chunk` aceita prefixo de 8+. Medido (tiktoken, texto da resposta, antes → depois):
  `search_hybrid` com 10 hits **3.547 → 2.915 tokens** (−18,4% em chars) e a mesma quantidade a
  menos em `structuredContent`; `get_dictionary` **9.548 → 6.225** (−41,4% em chars);
  `get_document` **808 → 492**; `get_entity` **8.079 → 6.207**; `build_context(3000)` **2.947**;
  `tools/list` **4.141 → 3.310** (-831, sem `outputSchema`). **Muda o formato:** quem lia `project`
  em cada hit deve usar `data.project`; cliente que validava `outputSchema` deixa de ter o que
  validar. O plugin do VS Code já herda a origem do envelope. O piso do pacote `mcp` subiu de
  `>=1.2` para `>=2.0`: o código importa `mcp.server.mcpserver`, que só existe a partir da 2.0.0
  (verificado nos wheels; na 1.x o módulo é `fastmcp`), então um `ragx mcp serve` com `mcp` 1.x
  falhava com `ModuleNotFoundError` depois de uma instalação "bem-sucedida" (RAGX-0155).

- **`build_context` entrega uma só representação do conteúdo, e `estimated_tokens` conta
  o que sai.** A resposta MCP trazia o mesmo texto em `fragments` e em `markdown`
  (e o SDK ainda o repete em `structuredContent`), e `estimated_tokens` somava só o
  conteúdo, ignorando ~33 tokens de cabeçalho por fragmento (o orçamento assumia 12).
  Medido com `scripts/medir_fio.py` (novo; tiktoken, este repositório): um pedido de
  3.000 tokens chegava como **7.983 tokens** no texto da resposta (declarado: 2.471);
  agora **3.004** (S1 pedia ≤ 3.200), e `estimated_tokens` é exatamente o que o
  agente recebe. `format: "markdown"` (padrão) devolve só `markdown`, sem título (o
  agente já sabe a consulta); `format: "json"` devolve só `fragments`, agora com
  `chunk_id` e `tokens`. **Muda o formato:** quem lia `fragments` com o formato
  padrão deve pedir `format: "json"`; o plugin do VS Code já pede. O orçamento
  (`allocate`) conta o cabeçalho real de cada candidato e reserva o rodapé; o alvo de
  compressão desconta esse custo (RAGX-0154).

- **`refresh` do MCP é incremental de verdade.** A descrição, o playbook e o hint diziam
  "barato quando nada mudou", mas ele rodava `sync` completo: reidratava o projeto
  inteiro só para um relatório descartado, refazia grafo, dicionário e federação e
  regravava todo `knowledge/` (medir `refresh` chegou a sujar 577 arquivos a 779). Agora
  só reindexa: **22,1 s → 0,56 s** sem mudança e **34 s → 1,23 s** com 4 arquivos
  mudados, com o `knowledge/` byte a byte intacto. No `sync`, a reidratação virou
  opt-in (`ragx sync --rehydrate`; `--report` a implica), o grafo é refeito **antes** de
  `knowledge/` ser regravado (antes `entities` e `relations` saíam um `sync` atrás) e
  a regravação é pulada quando nada mudou desde o último `sync` completo. `ragx sync`
  sem mudança: ~4-7 s, contra 28 s com a reidratação (RAGX-0131).

- **`load_index` vetorizado e cacheado por geração: `search_hybrid` quente de 100 ms
  para 18 ms.** A matriz de vetores era reconstruída a cada busca, linha a linha em
  laço Python, e a documentação prometia um cache que não existia. Agora é uma
  operação de matriz (7.285 vetores: **53,5 ms → 17,4 ms** frio) e fica em cache por
  processo, invalidado pela geração `meta('vec_gen')`, que gatilhos em `embeddings`
  incrementam em qualquer INSERT, UPDATE ou DELETE (inclusive em cascata): **0,013 ms**
  com o cache quente. `search_hybrid` quente, p50 de 10 consultas: **100,1 ms →
  17,9 ms**. Nova migração `0007_vec_gen.sql` (`SCHEMA_VERSION` 7). O resultado é o
  mesmo (diferença máxima ~6e-8 na matriz grosseira, igual byte a byte na float32);
  o `VectorIndex` compartilhado é somente leitura (RAGX-0134).

- **Indexação sem mudança não carrega o modelo de embedding nem chama o `git` 7
  vezes.** `embed_pending` construía o embedder (e sondava o Ollama) antes de saber
  se havia chunk pendente; agora o nome e a dimensão do modelo vêm da configuração
  (`embedder_id`) e o embedder só é construído com pendência. O estado do git
  (`read_state`) passou de 3 processos para 1 (`status --porcelain=v2 --branch`), e
  `hooks_dir` é memoizado por processo. Neste repositório, `ragx index .` sem
  mudança: **~3,5 s → 302–308 ms** (inclui o efeito da RAGX-0129) e **7 → 2**
  chamadas ao `git`. Com o Ollama fora do ar e nada pendente, a indexação deixa de
  reportar erro de embedder (RAGX-0130).

- **A poda de pasta ignorada voltou a funcionar com negação em `.gitignore`
  aninhado.** `!src/app/build/` na raiz fazia o `IgnoreEngine` guardar o pai do
  alvo (`src/app`), e a regra "ancestral do alvo não se poda" passava a valer
  para tudo sob `src/app`, inclusive `node_modules`, `dist` e `out`: o walker
  descia em todos. Agora guarda o caminho completo do alvo, e a negação só
  protege o alvo, os ancestrais e os descendentes dele. Neste repositório,
  `ragx index . --dry-run`: arquivos vistos **19.195 → 743**, `duration_ms`
  **3.775 → 328**; varredura do watcher (`snapshot`) **3,49 s → 0,13–0,16 s**;
  `IgnoreEngine.__init__` **0,35 s → 0,02 s**; o walker inteiro, **17,0 s → 2,5 s**.
  O conjunto de arquivos admitidos e bloqueados é idêntico com e sem poda
  (754 arquivos, verificado no repositório inteiro e por teste em
  `tests/security/test_poda_e_gate.py`) (RAGX-0129).

- **Ollama em `127.0.0.1`: fim dos ~2 s por requisição no Windows.** `localhost`
  resolve para `::1` antes de `127.0.0.1` e o Ollama escuta só em IPv4, então
  cada chamada esperava o tempo de falha do IPv6. Medido nesta máquina:
  `GET /api/tags` **2.040–2.110 ms → 3–17 ms**; embedding de 1 texto por
  chamada **2.085 ms → 10–21 ms** (batch 1) e **7 ms** (batch 32).
  O padrão passa a `http://127.0.0.1:11434` e `localhost` é convertido onde quer
  que apareça (`ragx.toml`, `RAGX_EMBEDDING_BASE_URL`, `OLLAMA_HOST`, `ragx
  doctor`); outro host, inclusive `http://[::1]:11434`, continua valendo
  (RAGX-0132).

- **A release publica só o instalador e o guia.** Antes, a página trazia o
  `.exe`, o wheel, o sdist, o `.vsix`, `install.sh`, `install.ps1` e o
  `SHA256SUMS.txt`, e quem procurava o instalador encontrava um monte de
  arquivo de código. Agora são dois: `RAGX-Painel-Setup-<versão>.exe` e
  `GUIA-DE-USO.md`; o SHA-256 do `.exe` está nas notas. Wheel e extensão do VS
  Code continuam sendo construídos e testados na release, mas ficam como
  artefatos do workflow (30 dias), não na página. O "Source code (zip/tar.gz)"
  que o GitHub acrescenta a toda release não tem como ser desligado.

### Corrigido

- **Editar um arquivo não derruba mais os vetores nem as pontes do grafo dos chunks que não
  mudaram.** `ChunkRepo.replace_for_document` apagava todos os chunks do documento e
  reinseria; como `embeddings.chunk_id` é `ON DELETE CASCADE` e `entities.chunk_id` /
  `relations.evidence_chunk_id` são `ON DELETE SET NULL`, uma linha editada levava embora o vetor
  e a ponte de TODOS os chunks do arquivo (medido: 19 embeddings viravam 0 e as pontes 18 viravam 0,
  até o próximo `sync`). Como o `chunk.id` já é hash do conteúdo, o id é o diff: quem tem o mesmo
  id sobrevive. Reinserir os mesmos 19 chunks: **0 escritas**, 19 vetores e 19 pontes intactos;
  editar um chunk: só ele sai e entra, os 18 outros mantêm `created_at`, vetor e ponte, e só o novo vai
  ao embedder. Equivale a apagar-e-reinserir em 200 sequências sorteadas (estado de `chunks` idêntico,
  FTS com `integrity-check` ok). `ragx index --json` mostra `chunks_kept` e `chunks_removed` (RAGX-0138).
- **O `scope` do MCP deixou de ser ignorado em silêncio.** `search_hybrid`,
  `search_knowledge` e `build_context` aceitavam `scope` e o descartavam:
  `scope="all"` consultava só o projeto atual e o agente acreditava ter consultado o
  conjunto. Agora `all` e `project:<nome>` cruzam projetos (a resposta ganha `scope` e
  `projects`, e `path_glob` é respeitado), `build_context(scope="project:<nome>")` monta o
  pack com o índice e a configuração do outro projeto, e `build_context(scope="all")` é
  recusado com `scope_unsupported` e o motivo. Projeto privado ou inexistente continuam
  indistinguíveis (`not_found` igual), e o privado segue invisível em qualquer escopo.
  Corrigidos também `docs/09-mcp.md` e `docs/17-multiprojeto-e-federacao.md`, que
  prometiam `scope` em `search_graph`, `get_dictionary` e `ragx context --scope all`
  (RAGX-0137).
- **A busca usa o modelo de embedding configurado, e avisa quando o índice vetorial é
  parcial.** `load_index` escolhia o modelo mais recente do banco: com outra dimensão a
  busca estourava `ValueError: matmul`, e com a mesma dimensão devolvia resultado
  aleatório em silêncio. Agora usa `embedder_id(cfg)`; sem vetores desse modelo, a
  busca segue só com keyword e `degraded` cita o modelo do banco e o configurado, com o
  comando que resolve. Vetor parcial (o embedder caiu no meio) vem em `partial`
  (`vetores parciais: N de M chunks`) na CLI, no MCP (só quando existe) e em
  `stats.partial_vectors` do contexto. A deduplicação do `build_context` também lê os
  vetores do modelo configurado, e `_resolve_model` desempata por `rowid` (RAGX-0136).
- **O cache do `build_context` não devolve mais o pack de outra consulta.** A chave
  não tinha os filtros, os pesos de busca e do grafo, `reserve_ratio`, `min_sources` nem
  `work_paths`, e a versão do índice já contava uma indexação em andamento: `lang=markdown`
  e depois `lang=python`, mesma consulta, devolviam o mesmo pack com `cached=True`
  (demonstrado), e o pack parcial de uma indexação rodando entrava no cache sob o id
  final. Agora a chave leva tudo que altera o resultado, a versão do índice é
  `vec_gen` + a última run terminada e sem erro, nada é gravado com indexação em curso, a
  gravação é atômica (`os.replace`), entrada com `format`/`key` errados vira miss e o
  diretório despeja os mais antigos acima de 200 arquivos ou 32 MB. Num teste de
  propriedade com 200 combinações (semente fixa) de consulta, orçamento, filtros, grafo e
  configuração, **0 acertos incorretos**. Acerto de cache: **p50 6,0 ms** (máx. 7,9),
  sem regressão no miss (65-88 ms quente) (RAGX-0135).
- **Junction do Windows não escapa mais da raiz do projeto.** `mklink /J` (o que o
  pnpm cria, e que não exige privilégio) não é symlink para o Python, então passava
  pela guarda anti-escape do walker e a pasta de **fora** do projeto era percorrida e
  indexada (reproduzido: `linkout/notes.md` entrava). Agora junction conta como link:
  não é seguida por padrão e, com `index.follow_symlinks = true`, só se resolver para
  dentro da raiz; o `IgnoreEngine` também não lê `.gitignore` de dentro dela. **Muda o
  comportamento:** junctions *dentro* do projeto deixam de ser indexadas pelo padrão,
  como os symlinks. `ragx sync` também recusa `rel_path` absoluto, com `..` ou que
  resolva para fora ao reidratar o conteúdo (reproduzido: `../fora.txt` era lido)
  (RAGX-0149).
- **Arquivo travado no momento do save não some mais do índice.** No Windows, o
  antivírus ou o editor seguram o arquivo logo depois do save, que é quando o hook
  dispara; um `OSError` ao abri-lo fazia o walker simplesmente não entregá-lo e o
  pipeline o apagava como "removido" (medido: documentos 1 e chunks 20 viravam 0 e 0
  até a rodada seguinte). Agora o arquivo é `unreadable`: nada é regravado, a rodada
  mostra `unreadable` no `--json` e no resumo, e uma pasta que não abriu protege o que
  estava sob ela. Só "não existe" significa removido; o nome sensível continua sendo
  bloqueado sem abrir o arquivo (RAGX-0133).

## [1.0.0-beta.5] — 2026-09-30

### Adicionado

- **O log de atividade diz quem chamou e o que a CLI fez.** Cada linha de
  `.ragx/logs/mcp.jsonl` chamada pelo Claude Code passa a trazer `client`,
  `profile` (o perfil, pelo `CLAUDE_CONFIG_DIR`: `padrão`, `empresa`...) e
  `session`. Os comandos de consulta rodados à mão (`search`, `context`,
  `graph-search`, `chunk`, `trial`) e o início de uma sessão do Claude Code num
  projeto indexado vão para `.ragx/logs/cli.jsonl`, sem a consulta nem os
  argumentos. O que o próprio painel roda não entra (`RAGX_CALLER=painel`).
  Base da tela de atividade (RAGX-0126).
- **Tela "Atividade" no painel, ao vivo.** Um item novo no menu mostra o que
  os agentes e a CLI estão fazendo nos projetos: resumo das últimas 24 h
  (chamadas MCP, sessões do Claude, comandos no terminal, tokens economizados,
  projetos em uso), as indexações em andamento e o feed dos eventos com hora,
  projeto, ferramenta ou comando, quem chamou (perfil do Claude ou terminal),
  tokens com a economia e o tempo, com filtro por tipo e por projeto. Um
  evento aparece em até ~1,5 s: o painel lê só o que foi acrescentado aos
  logs. O card e o detalhe do projeto mostram "em uso agora", e o item do menu
  acende, quando houve atividade no último minuto.
- **Vários Claude Code no mesmo computador, cada um com o seu interruptor.** Em
  Conexões, o card "Perfis do Claude Code" lista cada conta (o padrão, os
  `~/.claude-*` detectados e as pastas que você adicionar, em qualquer lugar),
  com a pasta, se foi detectada ou adicionada e um interruptor por perfil.
  "Adicionar perfil" pede a pasta e já liga o RAGX nela; "Remover" desliga antes
  de tirar da lista. O interruptor do topo continua ligando e desligando todos.
  Na CLI: `ragx claude profiles list|add|remove` (as pastas ficam em
  `~/.ragx/claude-profiles.json`) e `ragx claude on|off --profile <nome>`.
- **Lista de projetos com resumo, números, ordenação e visão em lista.** No
  topo, o resumo do hub: projetos, chamadas MCP nas últimas 24 h, tokens
  economizados em 14 dias e quantos pedem atenção. Cada card mostra a economia,
  as chamadas em 24 h e os documentos. Dá para ordenar por nome, uso recente ou
  estado (o que pede atenção primeiro), e alternar entre a grade de cards e uma
  lista compacta em tabela, com a mesma ação do card; a escolha fica lembrada
  enquanto o painel estiver aberto.

### Alterado

- **Tela Conexões redesenhada.** Os três cards estreitos, esticados até a altura
  do maior, viraram uma faixa por peça na largura toda: ícone, nome, selo e
  resumo à esquerda, as ações na mesma linha à direita, os fatos em blocos
  compactos embaixo. O topo resume "3 de 3 conectadas" (ou quantas pedem
  atenção), e os perfis do Claude Code ficam dentro da faixa do Claude, em vez de
  num card à parte. Sem medição, o processador do Ollama diz `GPU ou CPU? Use
  "Medir velocidade"` em vez de "ainda não medido".
- **Detalhe do projeto em abas.** Os onze blocos empilhados numa página só viraram
  quatro abas: **Visão geral** (índice, "Está em dia?" e uso pelos agentes nas
  últimas 24 h), **Economia de tokens** (gráfico, tabela e simulação),
  **Histórico** (linha do tempo na largura toda) e **Manutenção** (ações, hooks,
  segurança, conhecimento no git e "Remover do hub"). A aba escolhida vale para o
  próximo projeto aberto, e trocar de aba não perde a página carregada da linha
  do tempo nem a simulação. Navegável pelo teclado (setas, Home, End).

## [1.0.0-beta.4] — 2026-09-29

### Adicionado

- **O agente passa a saber que o projeto tem RAGX, e o perfil da empresa também tem o RAGX.**
  Em 14 dias de uso real, com o servidor registrado, o Claude Code abriu cerca de 50
  sessões e chamou o RAGX 4 vezes, todas no próprio repositório do RAGX: as
  ferramentas chegam como *deferred* e Grep/Read já estão à mão. Por isso os cards
  "Economia de tokens" e "Uso pelos agentes" do painel ficavam vazios. Agora
  `ragx claude on` instala um hook `SessionStart` que roda `ragx claude hint`. Num
  projeto indexado, ele diz ao agente que há índice (documentos, data, branch),
  quando usar `search_hybrid`/`build_context` e como carregá-las. Numa pasta acima
  de projetos indexados (monorepo com front e back separados), lista o
  `scope="project:<nome>"` de cada um. Fora de projeto RAGX, fica calado.
  `--no-hint` liga só o MCP; `off` tira o hook e preserva os seus.
- **Perfis do Claude Code com `CLAUDE_CONFIG_DIR`** (ex.: `~/.claude-empresa`).
  `ragx claude on|off|status` e `ragx mcp install --client claude-code` tratam cada
  perfil como um Claude Code: o padrão, cada `~/.claude-*` com `.claude.json` e o
  diretório de `CLAUDE_CONFIG_DIR`. Antes só `~/.claude.json` era lido, e o painel
  dizia "ligado" com o perfil da empresa sem a ferramenta. `status --json` traz
  `profiles`, e `enabled` só é verdadeiro com todos ligados.
- **`scripts/versao.py`: versão, CHANGELOG e tag num comando.** Sobe a versão no
  `pyproject.toml`, `uv.lock`, painel e extensão, abre a seção da versão com o que
  estava em `[Não lançado]` e, com `--tag`, commita e cria a tag `v<versão>`. O
  push da tag dispara a release, que agora publica o instalador do painel.
- **Logo do RAGX no executável, no instalador e no painel.** O símbolo é um X
  com uma abertura em losango no cruzamento (o foco: só o contexto relevante
  passa) e um núcleo no centro (o trecho recuperado), no azul do painel. O
  `RAGX Painel.exe` e o instalador/desinstalador passam a usar o ícone (tile
  azul com o símbolo branco) em vez do ícone padrão do Electron, e o .exe ganha
  ProductName/FileDescription. No painel, o símbolo aparece no topo da barra
  lateral, no cabeçalho da configuração inicial e no favicon. Tudo sai de uma
  única geometria em `src/app/scripts/brand.py` (SVGs em `src/app/brand/`,
  `build/icon.ico` e os paths do componente `RagxMark`), com um desenho mais
  grosso e sem núcleo para 32 px ou menos.

- **Gráfico de economia de tokens no detalhe do projeto, com uso real.** O
  servidor MCP passa a gravar em `.ragx/logs/mcp.jsonl`, a cada `build_context`,
  o `baseline_tokens`: o tamanho em tokens dos arquivos inteiros de onde o
  contexto saiu (lido do índice, `documents.size_bytes / 4`, sem abrir arquivo).
  O painel soma por dia e mostra, nos últimos 14 dias, "sem RAGX" contra "com
  RAGX": economia em %, totais, barras por dia com tooltip e a mesma série em
  tabela. Conta só a partir desta versão; linhas antigas, sem o baseline, ficam
  de fora. A simulação (`ragx trial`) virou parte do mesmo card.
- **`ragx trial` funciona em qualquer projeto.** Sem `tests/eval/queries.yaml`,
  gera 8 consultas do próprio índice (símbolos mais conectados do grafo ou,
  sem grafo, nomes de arquivos de código) e marca `auto_generated` no JSON. O
  painel espera até 4 minutos por ele.
- **`ragx runs --limit --offset`** e **"Carregar mais" na linha do tempo**: o
  histórico de indexações deixa de parar nas 10 últimas.
- **Detalhe do projeto reorganizado:** índice e "Está em dia?" no topo, a
  economia de tokens em destaque, linha do tempo ao lado de manutenção e hooks,
  e "Knowledge versionado" virou "Conhecimento no git", explicando para que
  serve a pasta `knowledge/` e o que cada ação faz e quando usar.
- **Barra de rolagem no tema do painel**, fina, sem setas, e uma só: a janela
  não rola mais junto com o conteúdo.

- **`ragx perf`: quanto tempo o RAGX ocupa nas sessões do Claude Code.** Lê os
  transcripts do Claude Code e separa, do tempo ativo da sessão, o que foi volta
  do modelo e espera de ferramenta do RAGX, com espera por ferramenta (p50/p95)
  ao lado do tempo que o servidor registra em `.ragx/logs/mcp.jsonl` e o custo
  fixo em tokens do schema das ferramentas.
- **`ragx claude on|off|status`: interruptor global do RAGX no Claude Code.**
  Retira ou devolve só a entrada `ragx` de `~/.claude.json` (backup datado,
  idempotente), para alternar entre "só o Claude" e "Claude com RAGX" sem editar
  arquivo à mão. Vale a partir da próxima sessão.
- **Interruptor "RAGX no Claude" no header do painel.** Um switch ao lado da fila
  liga e desliga o RAGX no Claude Code para todos os projetos, pelo mesmo
  `ragx claude on|off` (que ganhou `--json`). O estado é lido da CLI, o botão só
  muda quando ela confirma, dois cliques seguidos rodam um por vez e uma falha
  mostra o motivo sem trocar o estado. Depois de trocar, o header lembra que
  vale na próxima sessão do Claude Code.

- **Instalador completo do RAGX Painel (Windows).** O `.exe` do painel agora
  instala tudo sozinho, numa máquina limpa e com internet: o NSIS chama o
  próprio painel com `--bootstrap`, que instala a CLI `ragx` (com o `uv`
  embutido em `resources/ragx-bundle`, Python 3.12 e o wheel, com SHA256
  conferido contra `bundle.json`), garante `~\.local\bin` no PATH do usuário e
  registra o MCP no Claude Code quando ele existe. Se o bootstrap falhar, a
  instalação não falha: o card "RAGX CLI" ganha "Instalar / Tentar de novo".
  O desinstalador pergunta duas coisas (remover a CLI e o registro no Claude
  Code, padrão Sim; remover os dados do hub `~\.ragx`, padrão Não) e, em modo
  silencioso, aceita `--remove-cli` e `--remove-data`. Ollama e os `.ragx/` dos
  projetos nunca são tocados. `npm run package` agora roda `npm run bundle`
  (`scripts/prepare-bundle.mjs`, `uv` 0.12.18 fixo com SHA256 conferido), e a
  release ganha o job `painel-windows`, que instala, confere `ragx --version`
  e `ragx mcp serve --help`, desinstala e confere que o `ragx.exe` sumiu, e
  anexa o instalador aos arquivos da release. Ver
  [ADR-0016](docs/adr/ADR-0016-instalador-completo-do-painel.md).

- **`ragx mcp uninstall`** remove o RAGX da configuração dos clientes MCP
  (`--client`, `--dry-run`, `--json`). Retira só a entrada `ragx` (ou a tabela
  `[mcp_servers.ragx]` no Codex), com backup datado, idempotente e sem tocar
  em configuração ilegível.

- **`ragx doctor` informa se o Ollama usa GPU ou CPU.** Quando o Ollama
  responde e o modelo do projeto está baixado, o diagnóstico ganha a linha
  `Ollama`, lida de `GET /api/ps`: "GPU (N MB de VRAM)", "CPU" ou
  "processador ainda não medido (nenhum modelo carregado)". Se a consulta
  falhar, a linha diz "não foi possível consultar o processador". É só
  informação: a linha nunca falha o `doctor` nem muda o código de saída.

- **Telemetria de chamadas MCP gravada em `.ragx/logs/mcp.jsonl`** — cada
  ferramenta MCP registra um JSON line com `ts`, `tool`, `ms` (latência),
  `project` e (para `build_context` apenas) `tokens_delivered`. Queries e
  argumentos nunca são gravados, evitando que a telemetria vire um log do que
  o time está perguntando sobre o próprio código.

- **Registro automático no hub durante `ragx init`** — o projeto é registrado
  best-effort; falhas (projeto privado, colisão de nome) nunca fazem `init`
  falhar. Projetos que predatam essa mudança, ou marcados `private` que o
  usuário depois quer registrar com visibilidade diferente, continuam usando
  `ragx project register`.

- **Painel desktop (Electron)**: aplicativo local, sem login, tema sempre
  escuro (fundo preto, sem seguir o tema do Windows), título de janela
  "RAGX Painel". Fechar o painel com alguma tarefa em andamento pergunta
  antes de cancelar todas elas.

  A tela Projetos é uma grade de cards, um por projeto registrado no hub.
  Cada card mostra onde o projeto mora (dois projetos chamados `src`
  deixam de ser indistinguíveis), o selo de estado ("Atualizado",
  "Defasado", "Embeddings faltando", "Sem hooks", "Com problema", "Pasta
  ausente" ou "Indexando…"), a branch atual (com aviso quando o índice é
  de outra branch), há quanto tempo foi indexado, a cobertura de
  embeddings e um botão que faz o que o estado pede ("Atualizar agora",
  "Gerar embeddings", "Instalar hooks", "Abrir"). O estado vem de
  `.ragx/status.json` e da branch/commit atuais do git, não só de
  "ok"/"degradado". Um filtro segmentado separa "Todos", "Defasados" e
  "Com problema"; a busca ignora maiúsculas e acentos. "Adicionar
  projeto" pede uma pasta e lista os projetos do RAGX encontrados dentro
  dela (marcados; os já registrados aparecem desmarcados) e também os
  repositórios git sem `ragx.toml`, com a marca "novo" e desmarcados. Cada
  nova pasta escolhida soma à lista em vez de trocá-la, e cada item pode
  sair dela; a própria pasta como projeto novo só é oferecida quando a busca
  nela não acha nada. Os hooks de git são instalados por padrão, e pulados
  com um aviso quando a pasta não é um repositório git. Um projeto que foi
  indexado mas não entrou no hub (nome já usado por outro projeto, ou
  `visibility = "private"`) termina como falha que explica o motivo, em vez
  de "Concluída" sem card.

  O detalhe do projeto responde "o índice está em dia?" com os motivos
  exatos de `ragx status --json` (troca de branch, commits novos depois da
  última indexação, arquivos alterados, embeddings pendentes) e mostra a
  linha do tempo das últimas 10 indexações: quando, quem disparou
  (Terminal, Painel, Watcher, Sync, Agente, Troca de branch, Commit, Merge
  ou pull), o modo, a branch, o commit e quantos arquivos mudaram ou o
  erro. Na mesma página: os números do índice com a cobertura de
  embeddings, um interruptor para os hooks de git, "Atualizar agora",
  "Gerar embeddings faltantes", "Reindexar do zero" (pede um segundo
  clique), as ações que alteram `knowledge/` versionado (sincronizar,
  reconstruir grafo, gerar dicionário) com o aviso para revisar o diff, o
  uso pelos agentes nas últimas 24 h, a economia estimada sob demanda (via
  `ragx trial`), os achados de segurança sob demanda (via
  `ragx security scan`, sem exibir o trecho do segredo) e "Remover do hub"
  (também com segundo clique; nada é apagado no disco).

  Uma fila única e serial (o Ollama é compartilhado) roda as tarefas de
  cada projeto e mostra progresso, previsão ("Faltam cerca de 2 min") e um
  botão "Cancelar" por tarefa, com pedidos duplicados do mesmo tipo e
  projeto deduplicados em vez de empilhados. Um botão cuja tarefa já está
  na fila ou rodando fica desabilitado e diz "Na fila" ou "Rodando". O
  selo "Indexando…" só aparece para tarefas que indexam (adicionar,
  atualizar, gerar embeddings, reindexar); sincronizar knowledge,
  reconstruir grafo, gerar dicionário e mexer nos hooks não contam.
  "Indexando…" também some quando o processo que segurava a indexação
  morreu (um índice cancelado ou um hook que caiu). Quando outra indexação
  já está rodando, a tarefa diz o que acontece com o pedido de cada tipo
  (atualizar fica agendado; embeddings faltantes saem quando a outra
  terminar; "Reindexar do zero" precisa ser pedido de novo), inclusive nos
  comandos que saem com o código 4. "Gerar embeddings" que não gerou nada
  (Ollama fora do ar, por exemplo) termina como falha com o motivo, não
  como "Concluída". O erro mostrado é a mensagem inteira do CLI, não a
  última linha quebrada em 80 colunas, e um comando que não existe aparece
  como "Comando não encontrado".

  A tela Conexões mostra três cards (RAGX CLI, Claude Code e Ollama), cada um com o selo "Conectado", "Atenção" ou "Não conectado",
  os fatos da checagem (versão e local do ragx, projetos onde o RAGX está
  registrado, última chamada MCP, modelos instalados e projetos que
  dependem deles), a ajuda em bloco de texto que dá para copiar e as
  correções de um clique ("Registrar para todos os projetos", "Iniciar
  container", "Baixar nomic-embed-text"). O painel confere tudo a cada 30
  segundos, na hora com "Verificar agora" e logo depois que uma dessas
  correções termina, sempre por uma checagem só no processo principal.
  Docker ausente aparece como "O Docker não está instalado nesta máquina.",
  não como "não está rodando". Antes da primeira resposta os cards ficam em
  "Verificando…", nunca verdes. RAGX registrado no Claude Code só no
  escopo de um projeto aparece como "Atenção", não como conectado.

  O card de Ollama funciona com o Ollama no Docker ou instalado na máquina.
  "Conectado" passa a significar API respondendo e modelos baixados, não
  "existe um container". O card mostra o modo (Docker ou local), o
  processador (GPU ou CPU) e a velocidade em chunks/s, medida por um
  benchmark curto que só roda quando a pessoa pede ("Medir velocidade"). O
  painel detecta Docker, GPU e Ollama nativo e recomenda um modo (no macOS e
  com GPU AMD, o local; com GPU NVIDIA e Docker, o container com acesso à
  GPU); a recomendação é sempre substituível, e o modo escolhido fica
  guardado. Trocar de modo é uma tarefa da fila (instala ou baixa a imagem
  do escolhido antes de parar o outro, para uma falha no meio nunca deixar a
  máquina sem Ollama; cria ou inicia o escolhido e baixa os modelos que os
  projetos usam), assim como "Parar" e "Iniciar". Trocar para o Docker com o
  Docker Desktop fechado é recusado com "Abra o Docker Desktop e aguarde ele
  iniciar.". O texto do "Iniciar" diz o que a tarefa de fato liga
  (container ou Ollama local), seguindo o modo escolhido, e o card não
  insiste em sugerir o outro modo quando o atual foi o escolhido. Enquanto
  uma troca está na fila ou rodando, as ações do card do Ollama ficam
  desabilitadas. A velocidade medida vale só para o modo em que foi medida
  e some quando o Ollama troca, para ou inicia. No Windows, parar o Ollama
  local encerra só o Ollama da pasta detectada, nunca o `ollama.exe` que
  outro app traz junto. Os dois modos de pé ao mesmo tempo aparecem como
  conflito na porta 11434, com os modelos instalados; no Linux, o processo
  do próprio container não conta mais como Ollama local. No Windows, o
  painel instala o Ollama local sozinho, por usuário e via winget; em
  macOS e Linux ele mostra o link de download. Numa RX 7700 XT, o Ollama
  local passou de 12,1 chunks/s (Docker, CPU) para 85,2 e 114,3 chunks/s
  (GPU).

  O card de projeto confirma que a ação entrou na fila ("Adicionado à
  fila"), desabilita o botão enquanto há tarefa do mesmo tipo ativa para o
  projeto e mostra o motivo quando a tarefa falha, em vez de só a fila
  mostrar.

  Na primeira abertura, ou com o hub vazio, o painel começa pela
  configuração inicial: quatro passos (como o RAGX funciona, conexões,
  escolher os projetos, indexar) com "Voltar", "Continuar" e "Pular
  configuração"; "Começar" enfileira a indexação dos projetos marcados.
  "Como funciona" repete a explicação e permite refazer a configuração.

  Telemetria de chamadas MCP (tokens reais entregues) por projeto vem do
  log em `.ragx/logs/mcp.jsonl`. O painel atualiza por polling a cada 5 s
  e logo depois que uma tarefa termina; instalador `.exe` gerado com
  `electron-builder`.

- **O índice acompanha a branch.** Cada indexação registra branch, commit e quem
  disparou (`cli`, `panel`, `watch`, `sync`, `mcp:*`, `hook:*`). `ragx status --json`
  diz se o índice está defasado e por quê (troca de branch, commits novos,
  arquivos alterados depois da indexação, embeddings pendentes) e traz as
  últimas 10 indexações. `ragx hooks install` (ou `ragx init --git-hooks`) liga
  hooks de `post-checkout`, `post-commit` e `post-merge` que reindexam em
  segundo plano. Só uma indexação roda por vez (`.ragx/index.lock`); pedidos
  que chegam no meio ficam agendados. O estado de cada projeto fica em
  `.ragx/status.json`, e `ragx index --progress` emite progresso em JSON.

  A trava (`.ragx/index.lock`) protege `ragx index` — `mcp:index`/`mcp:sync`
  respondem `busy` estruturado nesse caso, em vez de um falso `internal` — mas
  ainda **não** cobre `ragx sync`, `ragx graph rebuild` nem
  `ragx dictionary generate`. Um pedido de `ragx sync` que chega ocupado
  reagenda só a reindexação incremental; knowledge/, grafo, dicionário e
  federação não são refeitos automaticamente quando ela libera — a CLI avisa
  isso explicitamente em vez de prometer "o pedido ficou agendado" (mensagem
  genérica, certa para `index`, enganosa aqui). Rodar `ragx sync`,
  `ragx graph rebuild` ou `ragx dictionary generate` ao mesmo tempo que uma
  indexação disparada por hook pode, raramente, gerar dois escritores;
  cobertura completa da trava para os três fica para uma tarefa futura.

### Corrigido

- **Indexar um monorepo pnpm travava por mais de 20 minutos a cada commit.** A
  busca pelos arquivos de ignore fazia três `rglob` pela árvore inteira, e o do
  Python 3.12 entra nas junctions do `node_modules` do pnpm sem lembrar onde já
  esteve: só o `node_modules` do projeto de referência levava 119 s, contra 4 s
  visitando cada pasta uma vez. Com worktrees em `.claude/worktrees/`, o `ragx
  index` passava de 20 minutos a 100% de CPU antes de ler um arquivo, e os hooks de
  commit empilhavam pedidos. Agora é uma varredura só, sem revisitar pasta, e o
  walker **poda pasta ignorada** em vez de pular os arquivos dela um a um: a
  varredura completa desse projeto caiu para 55 s. Nos repositórios de referência,
  os arquivos admitidos ficaram idênticos com e sem poda. Uma mudança de
  semântica, igual ao git: negação genérica (`!.env.example`) não reinclui mais
  arquivo **dentro** de pasta excluída, e arquivo de ignore de dentro de pasta
  excluída não é lido; negação com caminho (`!build/keep.txt`) e `--include`
  continuam valendo. Contra o código anterior, em cinco repositórios reais,
  quatro deram exatamente os mesmos arquivos admitidos, de 2,5x a 6x mais
  rápido; no quinto, um `!README.md` no `.gitignore` trazia 659 `README.md` de
  pacotes do `node_modules` para o índice, e agora não traz mais. Ver
  `docs/02-seguranca.md`.
- **"Este Python foi compilado sem FTS5" aparecia com o banco apenas ocupado.**
  A sonda de FTS5 criava uma tabela no próprio banco a cada conexão de escrita; com
  outro processo escrevendo (o painel indexando, um hook de commit) por mais que o
  `busy_timeout`, o "database is locked" virava esse erro falso. A sonda agora roda
  num banco em memória, uma vez por processo.
- **A release publica o instalador do painel com a versão certa.** O
  `package.json` do painel estava em `0.0.0`, e o instalador sairia como
  `RAGX-Painel-Setup-0.0.0.exe`; agora acompanha o produto, e a release recusa a
  tag se `pyproject.toml`, painel e extensão divergirem. No disparo manual, a
  release usava o nome do ramo (`main`) como tag. As notas saem da seção da versão
  no CHANGELOG (as da beta 3 ainda anunciavam a beta 1) e explicam como instalar o
  `.exe` e passar pelo aviso do SmartScreen.
- A suíte de testes não herda mais `CLAUDE_CONFIG_DIR`: rodada de dentro de um
  perfil separado, ela gravaria na configuração real dele.

- **Reinstalar o painel não deixa mais o `ragx` quebrado.** O `ragx-install` trocava o
  ambiente da CLI no lugar (`uv tool install --force`); com um `python.exe` dele em
  uso (indexação disparada por hook, servidor MCP de um Claude Code aberto) a troca
  falhava no meio e o `ragx.exe` ficava sem o pacote (`ModuleNotFoundError: No
  module named 'ragx'`, card "RAGX CLI" em "Não conectado"). No Windows, um passo
  novo encerra, antes da troca, só os processos do ambiente do `ragx` no `uv` e os
  `ragx.exe`/`rag.exe` da pasta de executáveis (com os filhos), e a tarefa avisa
  para reconectar o Claude Code (`/mcp`).

- **Commit não abre mais janela de terminal no Windows.** A indexação que o hook
  de git dispara rodava com `DETACHED_PROCESS`, sem console, e cada `git` que ela
  chamava ganhava uma janela nova. Agora usa `CREATE_NO_WINDOW` (console oculto,
  herdado pelos filhos), e todo `subprocess.run` do pacote passa por
  `ragx.procs.run_quiet`, com teste que barra chamada direta nova.

- `ragx mcp install` voltou a funcionar. O pacote `ragx.clients` tinha se perdido
  num merge e o comando (e os instaladores, que o chamam) quebrava com
  `ModuleNotFoundError`.

- `ragx mcp install` não afrouxa mais as permissões do arquivo de configuração
  do cliente. A escrita atômica criava o temporário com o umask padrão (0644
  no Linux e no macOS) e trocava um `~/.claude.json` 0600, que pode guardar
  tokens de outros servidores MCP, por um legível por todos. Agora o arquivo
  mantém o modo que já tinha, e um arquivo novo nasce 0600.

- `freshness.state` não diz mais "fresh" para um projeto git cujo último run
  útil é anterior à migração 0006 (sem `git_commit` gravado). Sem proveniência
  para comparar, o estado agora fica "unknown" a menos que outro motivo, como
  `pending_embeddings`, indique "stale".

## [1.0.0-beta.3] — 2026-09-17

### Corrigido

- **A métrica `nDCG@10` estava errada e podia passar de 1,0** (`RAGX-0098`).
  Ela contava caminhos duplicados como acertos separados, com o denominador
  ideal contado em arquivos: `_ndcg(['a','a','a'], ('a',))` devolvia **2,131**
  numa métrica cuja definição tem teto 1,0.

  O erro tinha direção, e é isso que o tornava caro: **premiava devolver o
  mesmo arquivo picado em vários chunks** — o oposto de um contexto bom. Quem
  otimizasse contra ela estaria otimizando para fragmentar o resultado.

  O ganho passa a ser contado uma vez por documento, na posição em que ele
  aparece pela primeira vez. **Os valores mudam**: nDCG cai de 0,76 para 0,48
  (keyword), 0,66 para 0,44 (semantic) e 0,76 para 0,49 (hybrid). A série
  histórica quebra porque os valores antigos estavam inflados.

### Adicionado

- **Camada do documento: conhecimento, registro de trabalho ou teste**
  (`RAGX-0102`). Um repositório não guarda só conhecimento — guarda também o
  registro de como ele foi construído. Medido aqui: `task/` é **22% dos
  chunks**, mais que toda a documentação, e vencia o código na busca. Para
  *"como o security gate decide bloquear um arquivo"*, o primeiro fragmento era
  o enunciado da TAREFA que pediu para construir o gate.

  `ragx.tiers` classifica por caminho, configurável em `ragx.toml`:

  ```toml
  [index]
  work_paths = ["task/", "adr-drafts/"]
  test_paths = ["tests/"]

  [search]
  weight_tier_work = 0.45
  weight_tier_test = 0.7
  ```

  **Pesa, não exclui** — às vezes a resposta está mesmo na tarefa, e há teste
  fixando que ela continua encontrável. A classificação acontece na LEITURA, e
  não numa coluna do banco: mudar `work_paths` passa a valer sem reindexar.

  Efeito no conjunto de 26 consultas:

  | modo | recall@5 | MRR |
  |---|---|---|
  | keyword | 0,77 → **0,81** | 0,47 → **0,62** |
  | semantic | 0,54 → **0,69** | 0,44 → **0,51** |
  | hybrid | 0,62 → **0,77** | 0,51 → **0,59** |

  > Os `relevant_paths` do conjunto nunca apontam para `task/` ou `tests/`, então
  > rebaixar essas camadas melhora a métrica **em parte por construção**. O ganho
  > é real no sentido de que o conjunto encoda julgamento humano sobre onde a
  > resposta mora — e precisa ser confirmado com casos cuja resposta esteja numa
  > tarefa, o que entra na `RAGX-0099`.

### Adicionado

- **`ragx eval` passa a reportar o intervalo de confiança** (`RAGX-0100`):

  ```text
  Modo          Recall@5          IC 95%      MRR   nDCG@10
  keyword           0.77     [0.58–0.89]     0.47      0.48
  semantic          0.54     [0.35–0.71]     0.44      0.44
  hybrid            0.62     [0.43–0.78]     0.51      0.49

  ! O intervalo de confiança chega a 0.36 de largura com n=26.
    Acima de 0.20 o conjunto não distingue os modos.
  ```

  Wilson, não o intervalo normal: com n pequeno e proporção perto de 0 ou 1, o
  normal escapa de [0,1] e mente sobre a precisão. O aviso vem **antes** do
  veredito ✓/✗, e o veredito sai marcado como inconclusivo enquanto o conjunto
  não distinguir os modos — foi lendo o número sozinho que "0,62 contra 0,77"
  virou a afirmação publicada de que a busca híbrida falhou o critério.

### Desempenho

- **O embedder passa a ser construído uma vez por processo** (`RAGX-0097`).
  `build_embedder()` era chamado a CADA busca semântica — e mais uma vez dentro
  do `build_context`. Construir o modelo ONNX custa 2537–3638 ms; embutir a
  consulta com ele pronto custa 6–27 ms. Ou seja: ~99% da latência da busca
  semântica era carregar o modelo de novo.

  | | antes | depois |
  |---|---:|---:|
  | `search --mode hybrid` (2ª chamada no mesmo processo) | 2677 ms | **58 ms** |
  | `build_context` (sem cache) | 5327 ms | **287 ms** |

  Nenhum resultado muda — há teste de contrato fixando que os `chunk_id`
  devolvidos são os mesmos, nos três modos. O ganho aparece em processo que
  vive: o servidor MCP, o `ragx watch` e a indexação. A diferença de 150× que
  havia entre `search keyword` (18 ms) e `search hybrid` não era propriedade de
  busca vetorial — era este defeito.

## [1.0.0-beta.2] — 2026-09-17

### Corrigido

- Regra de segurança `filename-deny:tokens` bloqueava `src/ragx/tokens.py` e um
  doc de tarefa da própria indexação do projeto — o padrão `**/tokens.*` casava
  com qualquer extensão. Restringido a extensões plausíveis de dump de segredo
  e a separador explícito antes de `token(s)`.

  A lista precisa resolve o caso de DADOS (`tokens.json`, `api_token.txt`
  continuam bloqueados), mas sozinha ainda derrubava `auth_token.py` e
  `refresh-token.go`, que casam em `**/*_token.*`. Junto dela entra
  `content_decides`: as regras que ADIVINHAM pelo nome (`tokens`, `secrets`,
  `credentials`, `password`) deixam de bloquear arquivos de código-fonte, que
  seguem para a fase 2 e têm o conteúdo lido por inteiro. As regras de FORMATO
  ou LOCAL (`*.pem`, `.ssh/**`, `.env`) continuam absolutas.

  O contrapeso é testado: um segredo real dentro de `tokens.py` continua
  bloqueado, agora pelo conteúdo. Quem afrouxar um lado sem o outro quebra
  `tests/security/test_filename_deny.py`.

- **O grafo aparecia sem nenhuma aresta na extensão do VS Code.** `get_entity`
  descrevia cada relação só como "o nó do outro lado" (`other`, `other_type`),
  sem dizer quem era origem e quem era destino. A extensão procurava
  `target`/`dst`, não encontrava e descartava a relação em silêncio: a tela
  mostrava os nós soltos, sem erro em lugar nenhum.

  `get_entity` passa a devolver também a aresta ORIENTADA (`src`/`dst`, os
  mesmos nomes da tabela `relations`), sem remover `other*` — que continua
  sendo a forma certa para uma lista de vizinhos. Verificado ponta a ponta:
  34 relações viram 34 arestas desenháveis, onde antes eram zero.

  Na `GraphEdge` a procedência viaja como `tier`, e não como `source`: o campo
  `source` da aresta é o nó de ORIGEM, e usar o mesmo nome para as duas coisas
  sobrescreveria a ponta da aresta.

- A lista de relações de uma entidade mostrava `?` em todo destino — o mesmo
  campo trocado, no mesmo lugar.

- `ragx graph show --json` não emitia `nodes`. A extensão filtrava as arestas
  contra um conjunto de nós vazio e descartava todas: o transporte de reserva
  também desenhava um grafo em branco.

- **A extensão podia subir dois processos RAGX.** Ativação, troca de pasta do
  workspace e mudança de configuração disparam conexão, e nada impedia que
  duas corressem juntas — só a última ficava referenciada, e a outra virava um
  processo Python órfão de ~100 MB. `conectar()` agora tem fila, e trocar de
  pasta só reconecta se a RAIZ do projeto mudar.

- **A queda do RAGX passava despercebida.** Crash do Python, pipe fechado ou
  `kill` de fora só apareciam na consulta seguinte, com um erro de transporte,
  enquanto a barra de status ainda dizia `Ready`.

- **A suíte de testes lia o `$HOME` da máquina.** `test_list_projects` esperava
  o projeto `demo` e recebia o primeiro projeto registrado no hub real de quem
  rodava — verde no CI, vermelho na máquina de quem usa o RAGX em mais de um
  projeto. Pior: um teste que lê o hub real também escreve nele.
  `tests/conftest.py` redireciona o HOME da sessão inteira.

### Adicionado

- macOS na matriz de CI (`ragx` e `instalador`) — o `install.sh` sempre se
  descreveu como suporte a Linux e macOS, mas nunca tinha rodado de verdade lá.
- `LICENSE` (MIT), `AGENTS.md` (onboarding de quem contribui no próprio RAGX)
  e `SECURITY.md` (canal de disclosure via GitHub Security Advisories).
- `ragx trial` — mede, no corpus de avaliação, quantos tokens o `build_context`
  economiza contra o baseline de ler o arquivo inteiro.
- Instalador agora também registra o servidor MCP em Cursor, Windsurf, Gemini
  CLI e Codex CLI — antes só Claude Desktop e Claude Code.
- **Reconexão com espera crescente.** Detectada a queda, a extensão reconecta
  sozinha em 1 s, 2 s, 4 s… até 60 s, com seis tentativas. Desligar de
  propósito não conta como queda, e "RAGX: Reconnect" zera o contador. Um RAGX
  não instalado falha em ~50 ms; sem a espera, isso era um laço de `spawn` a
  100% de CPU.
- **Medição de cada etapa da conexão**, numa linha do log. É o que transforma
  "o RAGX está lento" em um número, sem profiler.
- `vscode-plugin/scripts/bench-connect.mjs` — benchmark do caminho real de
  conexão, com mediana de cada etapa.
- A versão que a extensão anuncia ao servidor MCP passa a ser injetada pelo
  esbuild a partir do `package.json`. Era um literal em `McpClient.ts`, e
  mantê-los em dia dependia de lembrar de bumpar dois arquivos no mesmo commit.

### Desempenho

- **Imports pesados saíram do topo dos módulos de comando.** `cli/main.py`
  importa os 21 módulos de comando só para registrá-los, e cada um carregava
  seu subsistema junto: `ragx --version` puxava numpy, o motor de contexto e o
  avaliador de agentes. Medido com `python -X importtime`:

  | | antes | depois |
  |---|---:|---:|
  | `ragx --version` | 882 ms | 523 ms |
  | `ragx documents --limit 5` | 1086 ms | 597 ms |
  | `ragx entities --limit 5` | 938 ms | 537 ms |
  | `import ragx.cli.main` | 899 ms | 484 ms |

  Vale para toda invocação da CLI, inclusive o transporte de reserva da
  extensão, que roda um processo por consulta.

- **Conexão VS Code → RAGX: 1747 ms → 1482 ms** (mediana de 7 rodadas, -15%).

  O ganho é modesto de propósito, e a medição explica por quê: **mais de 98% do
  tempo é boot de processo Python**, e ~1,4 s disso é o import do SDK de MCP,
  que é de terceiros e constrói os modelos de todas as versões do protocolo.
  Transporte, handshake e consultas somam ~15 ms — não há nada a ganhar ali.

  Por isso o trabalho de desempenho foi para **não pagar esse custo duas
  vezes** (fila de conexão, reconexão só quando a raiz muda de verdade) em vez
  de perseguir os milissegundos que já eram baratos.

### Documentado

- `docs/09-mcp.md` agora cobre as 33 ferramentas MCP reais — as 13 de
  orquestração de tarefas (Fase 13) nunca tinham sido documentadas no contrato
  formal. E `tests/unit/test_documentacao_mcp.py` compara as ferramentas
  registradas com as documentadas **nos dois sentidos**, para que a divergência
  quebre a suíte em vez de envelhecer calada.
- `docs/README.md` não trava mais números de "estado atual" (documentos,
  entidades) que ficavam desatualizados sem aviso — aponta para `ragx doctor`.
- `docs/06-grafo.md` documenta o contrato de uma relação: as duas leituras da
  mesma aresta, `confidence`, `tier` e por que os dois formatos convivem.
- `docs/22-vscode-e-desempenho.md` — o caminho completo da conexão, onde o
  tempo vai, prontidão, reconexão, diagnóstico e o que foi deliberadamente
  **não** feito, com o motivo.

## [1.0.0-beta.1] — 2026-09-16

Relançamento. As releases **1.0.0, 1.0.1 e 1.0.2 foram retiradas**: saíram
enquanto o repositório era privado, e todas as instruções de instalação delas
partiam dessa premissa. O repositório agora é público, o caminho de instalação
mudou, e manter releases que ensinam o caminho errado é pior do que não ter
release nenhuma.

Nada foi perdido: esta beta reúne tudo o que as três traziam, com o histórico
de cada correção preservado abaixo. O número volta a `1.0.0-beta.1` porque é o
que a maturidade honesta do projeto comporta — veja as ressalvas no fim.

### Mudado

- **Instalar voltou a ser um comando.** Com o repositório público, o
  `curl | bash` e o `irm | iex` funcionam de novo: o instalador cai no caminho
  `git+`, que até aqui nunca tinha sido exercitado porque o clone anônimo
  falhava por credencial. Verificado de ponta a ponta com `UV_TOOL_DIR`
  isolado — instala e responde com as 33 ferramentas MCP.

  Continua valendo baixar os arquivos da release: é o único caminho que traz a
  **extensão do VS Code** junto, e o único que prega uma versão exata.

### Corrigido

- **O instalador do Linux abortava mudo, com código 2.** `instalar_extensao`
  procura o `.vsix` com `ls -1 "$pasta"/*.vsix | sort -r | head -1`. Sem
  correspondência o `ls` sai com 2, o `pipefail` propaga isso pelo pipe, a
  atribuição herda o status e o `set -e` mata o script — **depois** de já ter
  instalado o RAGX, configurado o PATH e registrado o MCP, e sem imprimir uma
  linha de erro. O job de instalação do CI em Ubuntu vinha caindo assim desde
  que a função foi introduzida.

  `encontrar_wheel` tem o mesmo padrão e escapou por acidente: é chamada dentro
  de um `elif`, onde o `set -e` fica suspenso. As duas passam a terminar em
  `|| true`, porque depender do ponto de chamada é armadilha para quem mexer
  depois.

  A instalação a partir dos arquivos de uma release **não** era afetada: com o
  `.vsix` na pasta, o `ls` encontra algo e não falha. Quem instalava de um
  clone do repositório, sim.

- **O instalador agora diz onde parou.** Uma parada silenciosa foi o que fez o
  bug acima sobreviver a um ciclo de release: no log, três linhas de sucesso e
  então `exit code 2`. O script ganhou `set -E` e um `trap ... ERR` — sem o
  `-E` o trap não vale dentro de função, que é justamente onde a falha
  acontecia. Agora a saída é `✗ o instalador parou na linha N (codigo 2)`.

  O `install.ps1` não tem o problema: usa `Get-ChildItem -ErrorAction
  SilentlyContinue`, que devolve vazio em vez de lançar.

- **A extensão pedia mais resultados do que o RAGX aceita.** O `SearchRequest`
  do servidor limita `limit` a 50 e **recusa** acima disso — não trunca. O
  inventário de documentos pedia 100 quando caía na derivação por busca, e a
  aba inteira respondia `search_hybrid falhou: ValidationError`. O teto do
  servidor agora é uma constante no cliente (`MAX_SEARCH_LIMIT`), aplicada
  dentro do `search()`, de modo que **todo** chamador fica coberto — não só o
  que estourou desta vez.
- **`ValidationError` virava `internal`.** Argumento fora do contrato é erro de
  quem chamou, não falha interna do servidor. Tratá-lo como `internal`
  produzia "`<ferramenta>` falhou: ValidationError. Detalhe em
  `.ragx/logs/errors.log`" — uma mensagem que manda caçar num traceback o que
  ela mesma poderia dizer. Agora o código é `invalid_argument` e a mensagem
  nomeia campo, limite e valor recebido:

  ```text
  search_hybrid: `limit` input should be less than or equal to 50 (recebido: 100)
  ```

- **A extensão não tinha texto para dois códigos de erro.** `invalid_argument`
  e `unsupported` caíam no ramo padrão e apareciam como "Falha ao falar com o
  RAGX", que culpa o transporte por um erro de chamada ou por uma instalação
  velha. Cada um tem agora título próprio; o de `unsupported` traz o comando de
  atualização.

### Notas

- **O wheel da 1.0.0 que chegou a circular foi construído antes de
  `list_documents` existir.** Instalações a partir dele caem na derivação por
  busca, que é o caminho degradado. Como aquela release foi retirada, o
  problema some com ela — mas se você instalou de um wheel `1.0.0` baixado
  antes, reinstale.
- Ferramenta e extensão passam a andar no mesmo número: `1.0.0-beta.1`.
- As notas de release e os dois READMEs foram reescritos para o repositório
  público: comando único primeiro, download da release como o caminho que
  prega a versão e traz a extensão.

### Adicionado

- **GitHub Actions**: `ci.yml` roda testes em Ubuntu e Windows, Python 3.11 e
  3.12, mais o build do plugin e a **instalação de ponta a ponta** nos dois
  sistemas. `release.yml` constrói e publica com a tag.
- **`scripts/release.py`** — gera wheel, sdist, `.vsix`, instaladores e
  `SHA256SUMS.txt` em `release/`, num comando, nos três sistemas.
- **`.gitattributes`** — `.sh` sempre com LF, `.ps1` com CRLF. Sem isto, o
  `core.autocrlf` do Windows grava CRLF no instalador e o Linux responde
  `bad interpreter: No such file or directory`, que não diz nada sobre a causa.

### Registro do MCP: dois bugs de corrupção de configuração

Encontrados registrando o servidor de verdade nesta máquina. Escrever no
arquivo de configuração de outro programa é a operação mais perigosa que o
instalador faz, e as duas falhas eram silenciosas:

- **`Set-Content -Encoding utf8` grava COM BOM** no PowerShell 5.1, e o
  `JSON.parse` do Node — que é quem lê esses arquivos — lança exceção ao ver
  BOM. O `claude_desktop_config.json` ficou com o conteúdo certo e ilegível
  para o cliente. Agora usa `WriteAllText` com `UTF8Encoding($false)`.
- **`ConvertFrom-Json '{}'` devolve `$null`** no PS 5.1. O código chamava
  `.PSObject` nele, estourava, e gravava um arquivo **vazio** — apagando os
  outros servidores MCP da pessoa sem avisar. Agora a conversão passa por uma
  tabela hash que trata nulo, dicionário e objeto.

Verificado em cinco formatos de config: inexistente, vazio, `{}`, com outro
servidor, e com um `ragx` anterior. Em todos, as chaves de topo, os outros
servidores e os dados de projeto foram preservados.

O registro passou a usar o **caminho absoluto** do executável: aplicativo
gráfico não herda o PATH do usuário de forma confiável, e `ragx` sozinho pode
não ser encontrado pelo cliente.

### Pasta sem projeto não é falha interna

Com o servidor MCP registrado globalmente, ele sobe em toda sessão — inclusive
onde não existe projeto RAGX. A busca respondia `internal` e mandava olhar
`.ragx/logs/errors.log`, que não existe ali. O agente concluiria que o RAGX
está quebrado e pararia de consultá-lo.

Agora responde `not_indexed`, dizendo o que fazer: rodar `ragx init` se for o
projeto certo, ou abrir a sessão dentro de um projeto já indexado.

### Instalação a partir dos arquivos baixados

> Escrito quando o repositório ainda seria privado. O comando único voltou a
> funcionar (veja **Mudado**, no topo); o que está abaixo continua valendo como
> o caminho que prega uma versão e traz a extensão do VS Code.

O instalador faz o resto sozinho:

- **encontra o `ragx-*.whl` sozinho**, na pasta do próprio script, na pasta
  atual ou em `~/Downloads`. O wheel vem ANTES do clone na ordem de busca:
  quem baixou os arquivos de uma release quer AQUELA versão, não o que
  estiver no `main` hoje.
- **encontra o `.vsix` e instala a extensão**, se o `code` estiver no PATH.
  Sem ele, imprime o comando em vez de falhar — muita gente usa outro editor.
- `RAGX_ORIGEM` / `-Origem` continua disponível para apontar um caminho.
- `RAGX_INSTALL_VSCODE=0` / `-SemVsCode` pula a extensão.

Corrigido junto: **o instalador saía com código != 0 mesmo dando certo.** O
`ragx doctor` sai diferente de zero enquanto não existe índice — o que é
esperado numa instalação nova — e esse código vazava como resultado do script.
Qualquer automação concluiria que a instalação falhou depois de ela ter dado
certo.

Verificado nos dois sistemas simulando o download de verdade: os cinco assets
numa pasta, terminal aberto ali, um comando. Saída 0 em ambos.

### Corrigido depois de tentar o comando único de verdade

O `irm ... | iex` não instalava. Três camadas de falha, empilhadas:

1. **TLS.** O PowerShell 5.1 negocia TLS 1.0 por padrão e o GitHub recusa. O
   erro é `A conexão foi fechada de modo inesperado`, que não menciona TLS. O
   comando documentado agora traz a linha que ajusta isso — ela não é opcional.
2. **Encoding.** O `Invoke-RestMethod` não recebe charset num asset de release
   (`application/octet-stream`) e decodifica o corpo como Latin-1. Com acentos,
   o script chegava corrompido e o parser cuspia dezenas de "Token inesperado".
   O `install.ps1` passou a ser **ASCII puro, sem BOM** — o oposto da regra
   anterior, que existia para a leitura em disco.
3. **Execução por pipe.** Sem arquivo em disco, `$PSScriptRoot` e
   `${BASH_SOURCE[0]}` vêm vazios. Os dois instaladores morriam ao derivar a
   raiz do repositório. Agora detectam a ausência do arquivo antes de usá-la.

Também: o `install.ps1` deixou de usar `exit` — por `iex` ele roda dentro da
sessão de quem chamou, e `exit` fecharia o terminal da pessoa no meio do
trabalho. Falha virou `throw`, com a mensagem impressa e a sessão intacta.

Novo: `RAGX_ORIGEM` / `-Origem` para instalar de um wheel baixado, sem clone e
sem acesso ao repositório.

Verificado servindo os scripts por HTTP e rodando `irm | iex` neste Windows e
`curl | bash` num container Ubuntu 24.04.

### Corrigido depois da primeira execução do workflow

Os dois jobs de instalação falharam na primeira tentativa. As duas causas eram
do workflow, não do produto:

- **`python` não é garantido no runner.** O passo que conferia se o segredo
  entrou no índice usava `python -c` para contar resultados. A contagem agora
  usa `grep -c '"chunk_id"'`, que não depende de interpretador nenhum.
- **`$HOME/.local/bin` no Windows.** Em bash, `$HOME` vira `/c/Users/...`, e o
  PATH do Windows não entende esse formato — o `ragx` não era encontrado no
  passo seguinte. O diretório agora vem de `uv tool dir --bin`, que devolve o
  caminho nativo de cada sistema.

Os dois passos foram reproduzidos localmente antes de subir: num container
Ubuntu 24.04 sem Python instalado, e neste Windows.

As ações também subiram de versão (`checkout@v5`, `setup-uv@v6`,
`setup-node@v5`, `upload/download-artifact@v5`) — o runner já forçava Node 24 e
avisava a cada execução.

### Verificado na publicação

O workflow de release **não publica antes de testar**. Ele instala a partir do
wheel recém-construído, nos dois sistemas, roda o ciclo completo num projeto
novo e confere que um `.env` com credencial não entra no índice. Se entrar, o
build quebra ali — não na máquina de alguém.

### Ressalva que continua valendo

A busca híbrida ainda não supera a busca por palavra-chave neste corpus
(recall@5 0,65 contra 0,77). O critério documentado `híbrida > semântica >
keyword` não foi atingido, e o diagnóstico com evidência está em
`docs/05-busca.md`. Trate a busca como auxílio à descoberta, não como fonte
única de verdade.

## [0.3.1] — 2026-09-15

Instalação de verdade e interface visual.

### Adicionado

- **Extensão do VS Code** `ragx-knowledge-explorer` 1.0.0-beta.1
  ([vscode-plugin/](vscode-plugin/README.md)) — busca semântica, grafo
  navegável com expansão progressiva, dicionário, Context Builder, monitor e
  status de segurança, dentro do editor. React + Tailwind sobre as variáveis de
  tema do VS Code: Light, Dark e High Contrast saem de graça.
- **Instaladores** para Windows (`install/install.ps1`) e Linux/macOS
  (`install/install.sh`). Colocam o `ragx` no PATH, registram o servidor MCP e
  **verificam** o resultado.
- Extra `all` no pacote: servidor MCP, busca semântica e contagem de tokens.

### Corrigido

Três bugs de instalação achados testando os instaladores de verdade — o do
Windows neste Windows, o do Linux num container Ubuntu 24.04:

- **`uv` escolhia Python 3.10** e o RAGX usa `StrEnum` (3.11+). A falha
  aparecia depois, como `ModuleNotFoundError: pydantic_core._pydantic_core`,
  longe da causa. `--python` agora é explícito.
- **`ragx mcp serve` falhava após instalar com sucesso**: o pacote `mcp` era um
  extra que o instalador não pedia. Servir agentes por MCP é o propósito do
  RAGX, não um acessório — daí o extra `all`.
- **PowerShell 5.1** (padrão do Windows) tratava o stderr do `uv` como exceção
  e lia o `.ps1` sem BOM como ANSI. Corrigido com um helper para chamada nativa
  e BOM no arquivo.

Há testes para os três: `tests/unit/test_documentacao.py` verifica que o extra
`all` carrega `mcp`, que os instaladores fixam o Python e registram o MCP, e
que o `.ps1` tem BOM.

No plugin, dois bugs achados pelos próprios testes:

- `humanize()` ecoava a mensagem crua do RAGX — um traceback de Python chegaria
  à tela, exatamente o que a §39 do pedido proíbe.
- `isBlocked()` só olhava a raiz do objeto; um resultado de busca com marcação
  de bloqueio dentro de `content` passava direto para a UI.

### Segurança

- A webview roda sob CSP restrita: sem `eval`, sem script inline,
  `connect-src 'none'`. Nenhum `dangerouslySetInnerHTML`.
- A lista de arquivos bloqueados **nunca** chega à tela — só a contagem
  agregada por regra. A agregação acontece no cliente, antes da webview.
- Zero rede, zero telemetria, zero CDN: a extensão empacota tudo que usa.

## [0.3.0] — 2026-09-15

Task Analyzer e orquestração. O RAGX deixa de só responder perguntas e passa a
decidir **se vale executar agora ou documentar e decompor antes** — e a manter
a fila de trabalho que sai disso. Fase 13 em
[`task/fase-13-task-analyzer-orquestracao/`](task/fase-13-task-analyzer-orquestracao/).

### Adicionado

- **Task Analyzer** (`ragx task analyze`) — classifica toda solicitação em 7
  dimensões e decide a estratégia. Determinístico e offline: sinais declarados
  em `signals.yaml`, mais duas dimensões **medidas no índice real** (quantos
  módulos já tocam o assunto, e se existe documento cobrindo). Ver
  [docs/20](docs/20-task-analyzer.md).
- **Documentation Planner** — decide QUAIS documentos o trabalho exige, em
  ordem topológica entre 15 tipos, e produz esqueletos já fundamentados no
  conhecimento existente. Lacuna vira `> **Pendente:**` explícito; o RAGX não
  inventa texto.
- **Task Decomposer** — 12 trilhas (análise, documentação, banco, backend,
  frontend, integração, testes, segurança, performance, deploy,
  observabilidade, validação) com DAG, critérios de aceite e escopo de arquivos
  derivado do grafo.
- **Banco de orquestração** `.ragx/ragx.sqlite` — 18 tabelas, máquina de
  estados com 11 estados, lease atômico, retry com backoff. Separado do
  `knowledge.db` ([ADR-0014](docs/adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md)).
- **Dispatcher e validação** — `claim`/`report`/`release` com contexto montado
  por tarefa; validação determinística (escopo, evidência, gate), sem juízo
  sobre qualidade de código.
- **Worker e scheduler** — `ragx worker` para cron; parser de cron de 5 campos
  sem dependência nova; agendamento `once|cron|interval|dependency|event|manual`.
- **13 ferramentas MCP novas** — `analyze_request`, `plan_work`, `claim_task`,
  `report_task_result`, `release_task`, `next_task`, `list_tasks`, `get_task`,
  `task_graph`, `task_status`, `set_task_status`, `add_task_dependency`,
  `run_worker`. Total: 32.
- **Board versionado** — `knowledge/tasks/` viaja no Git; execução não.
  Conflito de `status` resolve por precedência declarada.
- `ragx task` (17 subcomandos), `ragx worker`, `ragx schedule` (5 subcomandos).

### Alterado

- `ragx sync` reidrata o board de tarefas antes de regravá-lo, e **avisa**
  quando o histórico de execução local não voltou.
- `docs/09-mcp.md` e `docs/roadmap.md` atualizados com a fase 13.

### Segurança

- O contexto entregue ao agente vem do índice, que não contém segredo —
  verificado por teste com um `.env` real no projeto de teste.
- `ragx.tasks` entrou na lista de módulos que leem artefatos próprios, com um
  teste novo garantindo que ele **não varre o projeto**: `rglob`, `walk`,
  `scandir` e `read_bytes` são proibidos ali. O teste já pegou um `glob` em
  `docs/adr/` no planner, trocado por consulta ao índice.
- As invariantes do ADR-0006 seguem verificadas e não relaxadas.

### Notas de desenho

- O RAGX **não executa** a tarefa. Ele é a fila e o árbitro; quem executa é o
  agente conectado por MCP
  ([ADR-0015](docs/adr/ADR-0015-quem-executa-a-tarefa.md)). Embutir um cliente
  de LLM traria rede e credencial para dentro de um sistema cujo argumento é
  rodar offline.
- Pedido trivial **não** vira projeto. Metade do valor do analisador está em
  não criar burocracia: typo, renomear variável e ajuste visual continuam
  sendo execução direta.

## [0.2.0] — 2026-09-15

Autonomia do agente e conhecimento compartilhado entre projetos. Fase 12 em
[`task/fase-12-autonomia-e-conhecimento-base/`](task/fase-12-autonomia-e-conhecimento-base/).

### Adicionado

- **Conhecimento base** (`ragx base`) — fontes externas de regras, baixadas uma
  vez por máquina em `~/.ragx/base/`, indexadas sob `@base/<fonte>/` em cada
  projeto que as **declara** em `[base] sources`. Conteúdo de terceiro passa
  pelo mesmo Security Gate; `knowledge/base.json` carrega a receita (origem,
  ref, commit), não os arquivos. Ver
  [ADR-0013](docs/adr/ADR-0013-conhecimento-base-compartilhado.md).
- **`ragx watch`** — o índice acompanha o working tree por polling de
  `size+mtime`, com debounce e duas velocidades (reindexa a cada mudança,
  consolida a cada N). Zero dependência nova.
- **Escrita no índice via MCP** — `refresh`, `reindex`, `sync`,
  `rebuild_graph`, `generate_dictionary`, `base_sync`, `publish_contract`.
  Habilitadas por padrão em `ragx mcp serve`; `--read-only` desliga. Ver
  [ADR-0012](docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md).
- **`get_playbook`** — procedimento operacional que o agente lê uma vez:
  ordem das ferramentas, quando reindexar, e o que o índice deliberadamente
  não faz.
- `list_base_sources` no MCP.
- `ragx.walk.scan_fingerprints` — enumeração sem abrir arquivo, para o watcher.
- Testes de documentação: todo comando da CLI documentado, todo link relativo
  resolvendo.

### Alterado

- **`ragx` é o comando primário**; `rag` continua funcionando como alias
  histórico. 417 ocorrências em documentação, 85 em código.
  [ADR-0007](docs/adr/ADR-0007-nome-do-binario.md) revisado.
- `iter_files` aceita `prefix`, para namespaciar uma árvore no índice sem que o
  gate deixe de ver o caminho real.
- Serialização de `knowledge/` exclui `@base/` de documentos, chunks,
  embeddings, entidades e relações.
- `docs/09-mcp.md` não diz mais que "indexação é operação de CLI, não de
  agente" — a decisão foi revista, com o motivo registrado.

### Corrigido

- `publish_contract` chamava `hub.push`, que não existe (é `hub.sync`), e
  `generate_dictionary` tratava um `DictionaryReport` como dict. Ambos achados
  por um cliente MCP real, não pela suíte — que agora exercita **toda**
  ferramenta de escrita, parametrizada, para que ferramenta nova nasça coberta.
- `docs/06-grafo.md` e `docs/14-cli.md` documentavam `ragx graph <entidade>`;
  o comando real é `ragx graph show <entidade>`.

### Segurança

- Conteúdo de fonte base entra por `iter_files` → `SecurityGate.admit`, igual
  ao código do projeto. Teste garante que `ragx.base` nunca chama `read_bytes`
  nem `open`.
- Fonte instalada mas **não declarada** pelo projeto não é indexada — evita que
  um `ragx base add` mude em silêncio o índice de todos os projetos da máquina.
  A regra nasceu de sete testes que quebraram exatamente assim.
- As invariantes do ADR-0006 seguem verificadas e **não foram relaxadas**: o
  pacote `ragx.mcp` continua sem `open`, sem `pathlib`, sem rede, e abrindo o
  banco só em leitura.

## [0.1.0] — 2026-09-15

Primeira versão. MVP completo das 12 fases planejadas em [`task/`](task/).

### Segurança

- `SecurityGate` entre o leitor de arquivos e o parser: nenhum componente fora de
  `ragx.security` recebe bytes que não tenham passado por `admit()` (ADR-0008).
- 28 regras declarativas em YAML — auditáveis sem ler Python.
- Deny-list por nome de arquivo avaliada **antes** de qualquer leitura.
- Detecção em conteúdo: padrões de provedor, atribuição + entropia de Shannon,
  allowlist de placeholder e ajuste de severidade por contexto.
- `Redactor`: o valor do segredo nunca é persistido, logado ou impresso.
- `safe_echo`: entrada do chamador que pareça segredo volta mascarada — evita que
  uma query com a chave da AWS seja ecoada em mensagem de erro ou cabeçalho.
- Suíte de **8 superfícies** de vazamento (database, embeddings, graph, mcp,
  export, knowledge, federation, hub) — zero `xfail`.
- Testes arquiteturais: MCP sem filesystem/rede, só dois módulos leem o
  projeto-alvo, `core` não importa infraestrutura.

### Indexação

- Chunking estrutural por AST (Python) e por heading (Markdown); JSON, YAML,
  TOML, XML e SQL por estrutura nativa; fallback por parágrafo.
- IDs determinísticos e estáveis entre Windows e Linux.
- Indexação incremental com atalho por `size`+`mtime` e cache de embeddings.
- Transação por lote: `Ctrl+C` deixa o banco consistente.

### Busca e contexto

- Busca semântica em dois estágios (int8@256 grosseira → float32 rescoring),
  keyword FTS5/BM25 com pesos por coluna, fusão RRF.
- Grafo de conhecimento em duas camadas determinísticas, sem LLM.
- Context Engine: dedup literal/quase-duplicata/MMR, compressão extrativa em
  quatro estratégias, orçamento com reserva por fonte e `--explain`.

### Colaboração

- `knowledge/` versionado sem conteúdo de chunk (reidratado e conferido por hash)
  e com embeddings int8 shardados por prefixo de ID (ADR-0010).
- `ragx sync` com delta por Git e fallback por hash.
- Pacote `.rag` com re-scan obrigatório, verificação de integridade, checksums,
  proteção contra zip-slip e matriz de compatibilidade.

### Multiprojeto

- Fatia de federação versionada e autossuficiente: contratos por valor.
- Hub local agregando N projetos, clonados ou só pela fatia.
- Resolução de vínculos `consumes` ⟷ `provides` com normalização de rota entre
  stacks; consumo sem provedor e divergência de método são reportados.
- Busca cross-project com `--scope all` e atribuição obrigatória de `project`.

### Agentes

- Servidor MCP com 10 ferramentas, casca fina sobre a API interna (ADR-0006).
- Perfis de agente versionáveis; regras curadas à mão preservadas no retreino.
- `ragx agent eval` mede recuperação — não geração, e diz isso.

### Conhecido

- A qualidade da busca semântica **não está validada**: sem Ollama na máquina de
  desenvolvimento, os testes usam o provider `hashing`, de qualidade semântica
  nula. Ver `task/fase-02-busca/RAGX-0031-*.md`.
- Camada semântica do grafo (`--semantic`) e enriquecimento do dicionário por LLM
  ainda não implementados — ambos opt-in por design.
