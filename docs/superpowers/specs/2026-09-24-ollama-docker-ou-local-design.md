# Ollama no Docker ou local, com configuração automática

Tarefas do backlog: [RAGX-0116](../../../task/fase-15-painel-desktop/RAGX-0116-ollama-docker-ou-local-com-configuracao-automatica.md)
e [RAGX-0115](../../../task/fase-15-painel-desktop/RAGX-0115-feedback-de-fila-nas-acoes-do-card.md).

## O problema

O RAGX gera embeddings pelo Ollama, e o painel só sabe lidar com um container Docker
chamado `ollama`. Numa máquina com GPU AMD no Windows (caso real: Radeon RX 7700 XT
com 12 GB), o Docker Desktop não repassa a GPU e os embeddings rodam em CPU a
8,8 chunks/s. A pessoa também não tem como saber, pelo painel, se o Ollama usa GPU ou
CPU, nem como parar ou trocar de modo. E quem instalar o Ollama nativo vê "Não
conectado" no card, porque a checagem procura o container.

## Decisões

1. **O RAGX não muda de configuração entre os modos.** Container e instalação nativa
   respondem na mesma porta (`http://localhost:11434`, `/api/embed`, `/api/tags`), e o
   `embedding.base_url` já aponta para ela. Toda a novidade fica no painel.
2. **"Conectado" passa a significar API respondendo e modelos baixados**, não "container
   existe". Docker vira um detalhe do modo.
3. **Modo é um fato detectado**, nunca uma preferência guardada: `docker` (container
   `ollama` rodando), `native` (Ollama nativo respondendo), `none` (nada responde) ou
   `conflict` (os dois de pé, disputando a 11434).
4. **Processador é medido, não presumido.** Um benchmark curto (`/api/embed` com 64
   textos, depois `/api/ps`) devolve chunks/s e diz se o modelo está na VRAM
   (`size_vram > 0` é GPU). Só roda quando a pessoa pede.
5. **Recomendação automática**, sempre substituível:

   | Situação | Recomendado | Motivo mostrado |
   |---|---|---|
   | macOS | local | no macOS o Docker não usa a GPU |
   | GPU NVIDIA e Docker instalado | Docker | container com acesso à GPU NVIDIA (`--gpus all`) |
   | GPU NVIDIA sem Docker | local | |
   | GPU AMD (qualquer sistema) | local | o Docker não repassa GPU AMD |
   | GPU Intel, nenhuma ou desconhecida | Docker se instalado, senão local | |

6. **Trocar de modo é uma tarefa da fila** (serial, com log e cancelamento), composta de
   passos condicionais avaliados na hora de rodar: parar o outro modo, instalar/criar/
   iniciar o escolhido, esperar a API, baixar os modelos que os projetos usam.
7. **Instalação automática do Ollama nativo só no Windows** (`winget install -e --id
   Ollama.Ollama --silent`, por usuário, sem elevação). Em macOS e Linux o painel mostra
   o link de download em vez de tentar instalar.
8. **Parar e iniciar** ganham botões no card. Parar não apaga nada (o container e o
   volume dos modelos ficam; a instalação nativa fica). O modelo sai da VRAM sozinho
   depois de ociosidade, então não há "descarregar modelo" no painel.
9. **Segurança de IPC inalterada:** o renderer pede tipo de tarefa (e modelo, validado
   por `MODEL_PATTERN`); nenhum comando, caminho ou argumento livre. Os executáveis são
   resolvidos no processo principal.

## Componentes

- `electron/ollama/environment.ts`: `detectOllama(deps)` devolve `OllamaEnvironment`
  (plataforma, GPU, Docker, container, nativo, API, modelos, modo, recomendação).
  Todas as dependências injetadas (`exec`, HTTP, plataforma, arquivos).
- `electron/ollama/benchmark.ts`: `runOllamaBenchmark(deps)`.
- `electron/jobs/catalog.ts` e `queue.ts`: novos tipos `ollama-use-native`,
  `ollama-use-docker`, `ollama-stop`; `ollama-start` e `ollama-pull` passam a seguir o
  modo. Passos ganham condição (`when`), execução destacada e espera pela API.
- `electron/connections/checks.ts`: `checkOllama` reescrito sobre o ambiente.
- IPC: `getOllamaEnvironment` e `runOllamaBenchmark`; o painel guarda o último
  benchmark em memória e o mostra no card.
- Renderer: card de Ollama com modo, processador, velocidade e ações (trocar, parar,
  medir); o mesmo card aparece no passo 2 do onboarding.
- Card de projeto (RAGX-0115): botão desabilitado com o estado da tarefa ativa do mesmo
  tipo e aviso de "adicionado à fila".
- Núcleo Python: `ragx doctor` informa o processador do Ollama quando há modelo carregado.

## Fora de escopo

LM Studio (outro protocolo, outro provider), Ollama remoto, trocar o modelo de
embedding, ROCm dentro do Docker no Windows.

## Testes

Detecção com `exec` simulado para cada combinação (Docker ausente, parado, container
existente ou não, NVIDIA, AMD, nativo instalado, porta ocupada); recomendação para cada
linha da tabela; catálogo (cada tarefa nova, recusas); fila (condições, passo destacado,
espera pela API, código de saída aceito); `checkOllama` para cada estado; card e página.
Nada nos testes toca Docker, winget ou a rede de verdade. A verificação real (trocar o
Ollama desta máquina para o nativo e medir) é feita pelo controlador depois.

## Ordem

1. Detecção e recomendação. 2. Benchmark. 3. Catálogo. 4. Fila. 5. IPC e ligação no
`main.ts`. 6. `checkOllama`. 7. Interface. 8. Feedback do card. 9. `ragx doctor`,
documentação e backlog.
