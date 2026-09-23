# RAGX-0116: Ollama no Docker ou local, com configuração automática

| | |
|---|---|
| **Fase** | 15: Painel desktop |
| **Prioridade** | P1: alta |
| **Estimativa** | ~3d (inicial; confirmar no brainstorming) |
| **Depende de** | nenhuma |
| **Documentação** | [src/app/README.md](../../src/app/README.md) · [docs/15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `review` (código e testes prontos; falta a verificação visual no app Electron de verdade) |

## Objetivo

O RAGX precisa de um Ollama para gerar embeddings, e hoje isso pressupõe um container Docker chamado `ollama`. O painel deve perguntar à pessoa se prefere **Docker** ou **local (instalação nativa)**, descobrir o que a máquina suporta e fazer a configuração por baixo dos panos, pela fila de tarefas.

## O que motivou (medido em 2026-09-23)

- A máquina da pessoa tem uma **AMD Radeon RX 7700 XT (12 GB)**. O Docker Desktop no Windows só repassa GPU **NVIDIA** para containers; dentro do container `ollama` não aparece nenhum dispositivo de GPU (`/dev/dxg`, `/dev/kfd`, `/dev/dri`).
- Resultado: embeddings 100% em CPU. Medido nos logs do Ollama: **8,8 chunks/s**, lotes de 32, ~3,7 s por lote, container a ~990% de CPU.
- O Ollama nativo para Windows tem suporte a placas Radeon RX 7000 (incluindo a 7700 XT). Ganho esperado com GPU: bem acima de 8,8 chunks/s, **ainda não medido**.
- O card de Ollama do painel só considera "Conectado" se existir um container `ollama`. Com instalação nativa ele mostraria "Não conectado" mesmo funcionando.
- O RAGX fala com `http://localhost:11434` (`/api/embed`, `/api/tags`) tanto no container quanto no nativo, então **não há mudança de configuração do RAGX** entre os modos.

## Entregáveis

- [x] Detecção: Docker instalado e rodando; fabricante da GPU (NVIDIA, AMD, Intel, nenhuma); Ollama nativo no PATH ou respondendo na 11434; quem está ocupando a porta 11434
- [x] Recomendação automática: NVIDIA com Docker, container com `--gpus all`; AMD, Intel, sem Docker, ou macOS, instalação nativa; a pessoa sempre pode escolher outro
- [x] Tarefas na fila para cada passo: instalar o Ollama nativo (winget no Windows), criar/iniciar/parar o container, baixar o modelo, liberar a porta 11434 quando os dois modos existem
- [x] Verificação de que a GPU está em uso (`ollama ps`, coluna do processador) e velocidade medida em chunks/s mostrada no card
- [x] Card de Ollama mostra o modo (Docker ou local), o processador (GPU ou CPU) e a velocidade; "Conectado" passa a significar API respondendo e modelo baixado, não "container existe"
- [x] Controles de iniciar e parar (container: `docker start/stop`; nativo: iniciar o app e encerrar o processo) e explicação de que o modelo sai da VRAM sozinho depois de ociosidade
- [ ] `ragx doctor` informa o modo e o processador (informa só o processador; o modo fica no card do painel)

## Fora de escopo

- LM Studio: ele expõe `/v1/embeddings` no estilo OpenAI e o RAGX só tem os providers `ollama`, `fastembed` e `hashing`. Suportá-lo é outra tarefa (novo provider)
- Trocar o modelo de embedding, Ollama remoto, ROCm dentro do Docker no Windows (não suportado pelo Docker Desktop)

## Critérios de aceite

- [x] Em máquina com Docker e sem GPU compatível, a recomendação é o Ollama nativo e o fluxo termina com embeddings funcionando
- [x] Nunca há dois Ollama disputando a 11434 depois do fluxo
- [ ] **Com o Claude Code trabalhando**, o caminho do agente embeda certo: com o Ollama de pé, `refresh` (MCP) e os hooks de git geram os embeddings dos arquivos alterados; com o Ollama parado, a indexação continua (ADR-0004), `pending_embeddings` sobe, o card mostra "Embeddings faltando" e "Gerar embeddings" recupera
- [x] Nenhum travessão em texto visível

## Testes

- [x] Detecção com `exec` simulado: Docker ausente, Docker parado, NVIDIA, AMD, nativo já instalado, porta ocupada
- [x] Recomendação para cada combinação
- [x] Fluxo completo com a fila simulada, incluindo falha no meio
- [x] Card de Ollama para cada estado

## Notas

Passa pelo brainstorming e por spec própria antes de virar plano. A pessoa autorizou fazer a troca na máquina dela (Docker para nativo) depois que terminar o lote de embeddings em andamento.

## Verificado na máquina

Em 2026-09-23, nesta máquina (AMD Radeon RX 7700 XT), o Ollama nativo 0.34.3, instalado via winget, detectou a placa por ROCm (gfx1101, 12 GiB). O benchmark foi de 12,1 chunks/s no container Docker (CPU) para 85,2 e 114,3 chunks/s na instalação nativa (GPU, 308 MB de VRAM), com o mesmo digest do modelo.

Ainda sem verificar e por isso desmarcados: o critério de aceite "com o Claude Code trabalhando, o caminho do agente embeda certo" (`refresh` do MCP e hooks de git com o Ollama de pé e parado) e a verificação visual do card e do fluxo de troca no app Electron de verdade. O `ragx doctor` informa o processador (GPU ou CPU), mas não o modo, então esse entregável fica só pela metade. O critério "nunca há dois Ollama" tem o aviso de conflito e a troca que para o outro modo cobertos por teste, sem verificação do fluxo real completo em máquina com os dois de pé.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] `npm test`, `npm run lint`, `tsc` (app e electron) e `uv run pytest -m "not slow"` limpos
- [x] CHANGELOG atualizado na MESMA alteração
- [ ] Verificado no app Electron de verdade
