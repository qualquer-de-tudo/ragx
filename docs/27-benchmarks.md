# 27 — Benchmarks

> Gerado de `src/app/src/data/benchmarks.json` por `scripts/gerar_benchmarks.py`; não edite à mão. O painel mostra os mesmos números em
> **Como funciona → Benchmarks**.

Números medidos pelo próprio RAGX, com a data, o método e a máquina. Onde a meta não foi atingida, está dito. Onde o resultado é inconclusivo, também.

**10 de 11 metas atingidas.** Atualizado em 6 de out de 2026. Máquina: Windows 11, Intel i5-13600KF, 31,8 GB de RAM, GPU AMD RX 7700 XT (Ollama).

Quando a linha de base era uma faixa (por exemplo, 3 a 5 s), a tabela usa o **melhor extremo** dela: a melhora mostrada é a menor possível.

## Velocidade

| Métrica | Antes | Agora | Variação | Meta |
|---|---:|---:|---:|---|
| Detecção das conexões dos agentes | indefinido (comando ainda não existia) | **495,3 ms** | — | — |
| Primeira busca de uma sessão | 3.000 ms | **40 ms** | −99% | até 600 ms: atingida |
| Busca com o processo aquecido | 104 ms | **22 ms** | −79% | até 60 ms: atingida |
| Dica de início de sessão | 481 ms | **75 ms** | −84% | até 120 ms: atingida |
| Tempo que o git commit espera pelo hook | 539 ms | **99 ms** | −82% | até 150 ms: atingida |

- **Detecção das conexões dos agentes.** Inclui inicialização do processo CLI; sem comparação de desempenho com versões anteriores e sem chamadas aos agentes.

## Economia de tokens

| Métrica | Antes | Agora | Variação | Meta |
|---|---:|---:|---:|---|
| Contexto entregue por consulta | 7.684 tokens | **2.958 tokens** | −62% | até 3.200 tokens: atingida |
| Custo fixo das ferramentas por sessão | 2.660 tokens | **385 tokens** | −86% | até 600 tokens: atingida |
| Mapa do projeto, nível 0 | 8.660 tokens | **556 tokens** | −94% | até 800 tokens: atingida |


## Frescor

| Métrica | Antes | Agora | Variação | Meta |
|---|---:|---:|---:|---|
| Reindexar depois de editar 1 a 4 arquivos | 26 s | **1,77 s** | −93% | até 3 s: atingida |
| Edição não commitada visível na busca | indefinido (indefinida: só aparecia no próximo commit ou refresh) | **1,4 s** | — | até 5 s: atingida |
| Índice sem mudança, 20 mil arquivos | 7,6 s | **3,7 s** | −51% | até 1,5 s: **não atingida** |

- **Índice sem mudança, 20 mil arquivos.** Meta não atingida: o custo que sobra é por arquivo, em Python (stat, regras de ignore, pathlib), sem atalho seguro. Próximo passo planejado (RAGX-0198): perguntar ao git o que mudou, em vez de varrer; o git leva 0,14 s nos mesmos 20 mil arquivos.

## Painel

| Métrica | Antes | Agora | Variação | Meta |
|---|---:|---:|---:|---|
| Processos que o painel abre por minuto | 290 proc/min | **4,1 proc/min** | −99% | até 20 proc/min: atingida |


### Como cada número foi medido

- **Detecção das conexões dos agentes**: mcp status --json com nove perfis/clientes locais. `PowerShell System.Diagnostics.Stopwatch envolvendo ragx mcp status --json | Out-Null, cinco execuções consecutivas na instalação editável`
- **Contexto entregue por consulta**: build_context com orçamento de 3.000 tokens, medido no fio do MCP. `scripts/medir_fio.py --tool build_context --arg tokens=3000 (tiktoken cl100k, que não é o tokenizador do Claude)`
- **Custo fixo das ferramentas por sessão**: o que as ferramentas do MCP custam em toda sessão, no perfil padrão (slim). `ragx mcp tools --json, régua compacta (chars/4). O perfil full (33 ferramentas) segue em 2.723.`
- **Mapa do projeto, nível 0**: get_dictionary: o primeiro olhar do agente no projeto. `scripts/medir_fio.py --tool get_dictionary --arg level=0 (tiktoken)`
- **Primeira busca de uma sessão**: search_hybrid com o processo recém-aberto. `scripts/medir_mcp_frio.py --espera 5 (5 amostras)`
- **Busca com o processo aquecido**: search_hybrid, mediana de 20. `search(cfg, q, mode="hybrid", limit=10) em laço, depois de uma chamada de aquecimento (sem o transporte MCP)`
- **Dica de início de sessão**: ragx claude hint, no SessionStart do Claude Code. `scripts/medir_hooks.py --n 12 (mediana)`
- **Tempo que o git commit espera pelo hook**: parte síncrona do post-commit. `scripts/medir_hooks.py --n 12 (mediana)`
- **Reindexar depois de editar 1 a 4 arquivos**: refresh incremental, processo já aquecido. `WriteAPI(load_config(), True).refresh() com um arquivo alterado`
- **Edição não commitada visível na busca**: do salvar o arquivo até a busca por palavra-chave achá-lo. `ragx touch real num projeto de 40 arquivos, sondando a busca a cada 50 ms (5 rodadas)`
- **Índice sem mudança, 20 mil arquivos**: projeto sintético de 20.000 arquivos, nenhum alterado. `scripts/medir_indice_inicial.py --arquivos 20000 --provider hashing --jobs 4 --segunda-rodada`
- **Processos que o painel abre por minuto**: 12 projetos, janela visível. `scripts/measure-runtime.mjs (contador de processos filhos, 12 projetos)`

## Contra um agente sem RAGX, no seu projeto

**Inconclusivo em tokens faturáveis; custo e turnos menores.**

Monorepo TypeScript de terceiros, 3.480 arquivos. 18 tarefas geradas do histórico do git (a mensagem do commit é a pergunta, os arquivos alterados são o gabarito), 2 braços, 1 repetição, Sonnet, no máximo 15 turnos: 36 chamadas reais. O braço sem RAGX não recebe nenhum hook do RAGX.

| Medida | Sem RAGX | Com RAGX | Leitura |
|---|---:|---:|---|
| Tokens faturáveis (mediana por tarefa) | 27.569 | 26.040 | economia pareada +0,8%, IC95% de −1,8% a +15,0%, 11 pares: inconclusivo |
| Custo (soma das 18 tarefas) | US$ 3,26 | US$ 2,68 | −18% |
| Turnos (mediana) | 6 | 3 | metade |
| Achou o arquivo certo | 15 de 18 | 14 de 18 | diferença que 18 tarefas não separam do acaso |
| Usou o RAGX | não se aplica | 10 de 18 tarefas | 1 chamada cada, ~900 tokens por resposta |

Quase todo o custo faturável é um piso fixo de ~26 mil tokens (o prompt do próprio projeto), que o RAGX não toca, e as perguntas de "onde está X" um Grep já resolve em poucos turnos. Onde o Grep sofreu (12 e 13 turnos), o RAGX respondeu em 2 e 3. Um projeto, 18 tarefas fáceis, 1 repetição: não mede tarefas de entendimento amplo.

Comando: `RAGX_AB_REAL=1 ragx ab --execute --max-calls 36 --arms without,slim --limit 18 --model sonnet --max-turns 15 --setting-sources project,local --with-hooks`

## Qualidade da busca

Em quantas consultas o arquivo certo aparece entre os 5 primeiros (recall@5, modo híbrido), com intervalo de confiança de 95%, em dois conjuntos independentes neste repositório: 132 consultas escritas à mão e 134 geradas do histórico do git.

| Modelo de embedding | 132 consultas à mão | 134 do histórico do git | Latência da consulta |
|---|---:|---:|---:|
| MiniLM (fastembed, 384d) | **0,62** (0,54 a 0,70) | **0,60** (0,51 a 0,68) | 3,6 ms |
| nomic-embed-text (Ollama, 768d) | **0,71** (0,63 a 0,78) | **0,65** (0,57 a 0,72) | 14,9 ms |

Os intervalos se sobrepõem: é um indício consistente nos dois conjuntos, não uma prova. O nomic custa ~4× a latência de consulta e o dobro do espaço dos vetores.

Método: `ragx bench models (cópia do índice, 9.329 chunks; nada baixado, nada saiu da máquina)`

## Linha do tempo

### 6 de out de 2026 · versão 1.0.3: Conexões por agente e onboarding multicliente

Claude Code, Codex, Gemini e outros clientes ganham controles no painel. A nova detecção local das configurações levou mediana de 495,3 ms em cinco execuções, incluindo abrir o processo da CLI; não mede latência de consulta nem economia de tokens.

- Detecção das conexões dos agentes: sem base → **495,3 ms**

### 2 de out de 2026 · versão 1.0.1: Primeira medição real contra um agente sem RAGX

36 chamadas reais num projeto de terceiros: custo 18% menor e metade dos turnos; tokens faturáveis inconclusivos. O teste também achou um defeito do próprio medidor, que negava toda chamada ao RAGX, corrigido antes de valer.

### 2 de out de 2026 · versão 1.0.0: Benchmark local de modelos de embedding

O nomic-embed-text leva o recall@5 de 0,62 para 0,71 no conjunto manual e de 0,60 para 0,65 no do git, ao custo de ~4× a latência de consulta.

### 2 de out de 2026 · versão 1.0.0: A v1 sai com 12 das 14 metas medidas e atingidas

Contexto 62% menor, perfil slim como padrão (385 tokens fixos), busca em 22 ms, hooks abaixo de 100 ms, painel com 4 processos por minuto em vez de 290. O índice sem mudança em 20 mil arquivos (3,7 s contra 1,5 s) e a economia real de tokens ficaram de fora.

- Contexto entregue por consulta: 7.684 tokens → **2.958 tokens**
- Custo fixo das ferramentas por sessão: 2.660 tokens → **385 tokens**
- Mapa do projeto, nível 0: 8.660 tokens → **556 tokens**
- Busca com o processo aquecido: 104 ms → **22 ms**
- Tempo que o git commit espera pelo hook: 539 ms → **99 ms**
- Processos que o painel abre por minuto: 290 proc/min → **4,1 proc/min**
- Índice sem mudança, 20 mil arquivos: 7,6 s → **3,7 s**

### 30 de set de 2026 · versão 1.0.0-beta.5: A auditoria mede a linha de base

Antes de mexer em qualquer coisa, a v2 mediu onde o RAGX estava: contexto de 7.684 tokens por consulta, 2.660 de custo fixo, refresh de 26 a 91 s, primeira busca de 3 a 5 s.

- Contexto entregue por consulta: 7.684 tokens → **2.958 tokens**
- Custo fixo das ferramentas por sessão: 2.660 tokens → **385 tokens**
- Reindexar depois de editar 1 a 4 arquivos: 26 s → **1,77 s**
- Primeira busca de uma sessão: 3.000 ms → **40 ms**

## Como acrescentar um resultado

1. Meça com o comando do método e confira que o número é **desta** versão (não de memória).
2. Em `src/app/src/data/benchmarks.json`: acrescente um `snapshot` (se for uma versão nova), o ponto em cada métrica medida (ou uma métrica nova) e a entrada em `timeline`. Meta não atingida leva `"met": false` e um `caveat`; resultado inconclusivo diz que é inconclusivo.
3. `uv run python scripts/gerar_benchmarks.py` e commit dos dois arquivos.
