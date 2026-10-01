# Medição de consumo do painel

Seções acrescentadas por `node scripts/measure-runtime.mjs` (RAGX-0177). Os JSONL brutos ficam em %TEMP% e não são versionados.

## baseline-1.0.0-beta.5

- Data: 2026-10-01T12:09:43.611Z
- Máquina: Windows_NT 10.0.26200 (win32 x64), 20 núcleos lógicos, 13th Gen Intel(R) Core(TM) i5-13600KF, 31.8 GB de RAM
- Painel 1.0.0-beta.5, Electron 33.4.11 (não empacotado: `electron dist-electron/main.js`, casca de produção)
- Projetos no hub: 12 (fixture: 12 repositórios `git init` em pasta temporária)
- Plano: `visible:5,minimized:5,hidden:5` (15 min); amostra a cada 5 s; a 1ª amostra de cada execução é descartada (`warmup`)
- Amostras: 179 (JSONL em %TEMP%, não versionado)
- Convenção de CPU: `percentCPUUsage` do `app.getAppMetrics()`, medido desde a chamada anterior; **por núcleo** (pode passar de 100), somado entre os processos do painel

| Estado | Amostras | RAM working set (média / pico MB) | RAM privada (média / pico MB) | CPU soma (média / p95) | `git`/min | filhos (ms/min) | snapshot (ms) |
|---|---|---|---|---|---|---|---|
| visible | 59 | 333 / 337 | 213.3 / 219.4 | 0.1 / 0.3 | 290.8 | 16775 | 141.9 |
| minimized | 59 | 339.3 / 341.1 | 217.8 / 219.3 | 0.2 / 0.4 | 284.3 | 19256 | 174.9 |
| hidden | 60 | 341.3 / 341.9 | 219 / 219.5 | 0.1 / 0.3 | 287.3 | 19618 | 161 |

- **visible** (59 amostras, 296 s): filhos/min: git 290.8, ragx 2.2, docker 6.1, tasklist 2, powershell 0.2; ms de filhos/min: git 13873, ragx 949, docker 1549, tasklist 324, powershell 80; CPU média/p95 por tipo: Browser 0.1/0.3, GPU 0/0, Utility 0/0, Tab 0/0; custo médio do amostrador: 0.44 ms
- **minimized** (59 amostras, 299 s): filhos/min: git 284.3, ragx 2, docker 6, tasklist 2; ms de filhos/min: git 16444, ragx 851, docker 1627, tasklist 334; CPU média/p95 por tipo: Browser 0.2/0.4, GPU 0/0, Utility 0/0, Tab 0/0; custo médio do amostrador: 0.66 ms
- **hidden** (60 amostras, 300 s): filhos/min: git 287.3, ragx 2, docker 6, tasklist 2; ms de filhos/min: git 16363, ragx 876, docker 1930, tasklist 449; CPU média/p95 por tipo: Browser 0.1/0.3, GPU 0/0, Utility 0/0, Tab 0/0; custo médio do amostrador: 0.48 ms

**Leitura (RAGX-0177).** A auditoria acertou: **≈ 288 processos `git` por minuto** com 12 projetos (290,8 visível, 284,3 minimizada, 287,3 oculta; a auditoria estimava ≈ 290, desvio < 2%), e o número **não cai com a janela minimizada nem oculta**: o polling não sabe que ninguém está olhando (RAGX-0171). O que o painel gasta não é CPU dele: o conjunto Electron fica em ~0,1 a 0,2% de um núcleo, com ~335 MB de working set (~215 MB privados) em qualquer estado. O custo está nos filhos: **~17 a 20 s de processos filhos por minuto** (~28 a 33% de um núcleo ocupado por `git`, `docker`, `ragx` e `tasklist`), dos quais o `git` é 83 a 86%. O restante da checagem de conexões (`ragx` 2/min, `docker` 6/min, `tasklist` 2/min = ~10 filhos/min, ~2,8 s/min) bate com a estimativa da auditoria (~2,7 s por ciclo de 30 s = ~5,4 s/min; medido ~2,8 s/min aqui). O amostrador custa 0,4 a 0,7 ms por amostra (meta < 5 ms).

Ressalvas: fixture (12 repositórios `git init` em pasta temporária, projetos pequenos); Electron não empacotado (a diferença para o `.exe` não foi medida); fila de tarefas vazia; a máquina tem 20 núcleos lógicos, então percentuais de CPU "por núcleo" são pequenos em valor absoluto.
## depois-0172-git-por-arquivos

- Data: 2026-10-01T12:14:58.176Z
- Máquina: Windows_NT 10.0.26200 (win32 x64), 20 núcleos lógicos, 13th Gen Intel(R) Core(TM) i5-13600KF, 31.8 GB de RAM
- Painel 1.0.0-beta.5, Electron 33.4.11 (não empacotado: `electron dist-electron/main.js`, casca de produção)
- Projetos no hub: 12 (fixture: 12 repositórios `git init` em pasta temporária)
- Plano: `visible:3` (3 min); amostra a cada 5 s; a 1ª amostra de cada execução é descartada (`warmup`)
- Amostras: 36 (JSONL em %TEMP%, não versionado)
- Convenção de CPU: `percentCPUUsage` do `app.getAppMetrics()`, medido desde a chamada anterior; **por núcleo** (pode passar de 100), somado entre os processos do painel

| Estado | Amostras | RAM working set (média / pico MB) | RAM privada (média / pico MB) | CPU soma (média / p95) | `git`/min | filhos (ms/min) | snapshot (ms) |
|---|---|---|---|---|---|---|---|
| visible | 35 | 331.1 / 337.9 | 214.8 / 223.6 | 0.1 / 0.2 | 0 | 6542 | 2.9 |

- **visible** (35 amostras, 175 s): filhos/min: docker 6.2, tasklist 2.1, powershell 0.3, ragx 2.4; ms de filhos/min: docker 2606, tasklist 870, powershell 1599, ragx 1467; CPU média/p95 por tipo: Browser 0.1/0.2, GPU 0/0, Utility 0/0, Tab 0/0; custo médio do amostrador: 1.66 ms

## depois-0173-conexoes-leves

- Data: 2026-10-01T12:23:15.235Z
- Máquina: Windows_NT 10.0.26200 (win32 x64), 20 núcleos lógicos, 13th Gen Intel(R) Core(TM) i5-13600KF, 31.8 GB de RAM
- Painel 1.0.0-beta.5, Electron 33.4.11 (não empacotado: `electron dist-electron/main.js`, casca de produção)
- Projetos no hub: 12 (fixture: 12 repositórios `git init` em pasta temporária)
- Plano: `visible:4` (4 min); amostra a cada 5 s; a 1ª amostra de cada execução é descartada (`warmup`)
- Amostras: 48 (JSONL em %TEMP%, não versionado)
- Convenção de CPU: `percentCPUUsage` do `app.getAppMetrics()`, medido desde a chamada anterior; **por núcleo** (pode passar de 100), somado entre os processos do painel

| Estado | Amostras | RAM working set (média / pico MB) | RAM privada (média / pico MB) | CPU soma (média / p95) | `git`/min | filhos (ms/min) | snapshot (ms) |
|---|---|---|---|---|---|---|---|
| visible | 47 | 330.4 / 336.7 | 212.1 / 220 | 0 / 0.1 | 0 | 1353 | 3 |

- **visible** (47 amostras, 235 s): filhos/min: docker 2, tasklist 0.3, powershell 0.3, ragx 0.5; ms de filhos/min: docker 263, tasklist 43, powershell 810, ragx 237; CPU média/p95 por tipo: Browser 0/0.1, GPU 0/0, Utility 0/0, Tab 0/0; custo médio do amostrador: 0.68 ms

