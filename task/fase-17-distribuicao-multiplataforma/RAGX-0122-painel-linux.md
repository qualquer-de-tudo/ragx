# RAGX-0122: Painel no Linux (AppImage e `.deb`)

| | |
|---|---|
| **Fase** | 17: Distribuição do painel em Windows, Linux e macOS |
| **Prioridade** | P2 |
| **Estimativa** | ~2d |
| **Depende de** | RAGX-0121 |
| **Documentação** | [src/app/README.md](../../src/app/README.md#empacotando) |
| **Status** | `todo` |

## Objetivo

Quem usa Linux e quer o painel hoje só tem a CLI. Gerar o instalador do painel para Linux.

## Entregáveis

- [ ] Seção `linux` no `electron-builder.yml` (AppImage e `deb`), com o ícone gerado por `scripts/brand.py` (PNGs em vários tamanhos)
- [ ] Job `painel-linux` na release: empacotar, instalar em `ubuntu-latest` e verificar `ragx --version` depois do bootstrap
- [ ] AppImage e `.deb` anexados à release e ao `SHA256SUMS.txt`
- [ ] README do painel: como baixar, tornar executável e desinstalar; dependências do Electron no Linux (libfuse2 para o AppImage)
- [ ] Verificar o comportamento do painel sem Docker e com Ollama local (ramos de `pkill -x ollama`)

## Fora de escopo

- `.rpm`, Flatpak, Snap
- Arquitetura ARM (`aarch64`), salvo se o `uv` e o Electron entrarem sem custo
- Auto-update

## Critérios de aceite

- [ ] O `.deb` instala e o AppImage abre numa VM limpa de Ubuntu LTS; "RAGX CLI" fica verde
- [ ] O smoke roda na CI e é bloqueante
- [ ] Ícone e nome corretos no menu de aplicativos

## Testes

Smoke em `ubuntu-latest` (empacota, instala o `.deb`, roda `--bootstrap`, confere a CLI).

## Notas

Sem NSIS: a instalação da CLI é feita na primeira abertura (RAGX-0121). A
desinstalação da CLI e dos dados precisa de um caminho pelo próprio app, porque o
gerenciador de pacotes não pergunta nada. Decidir e registrar aqui.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Verificado numa máquina Linux de verdade
