# RAGX-0123: Painel no macOS (`.dmg` Intel e Apple Silicon)

| | |
|---|---|
| **Fase** | 17: Distribuição do painel em Windows, Linux e macOS |
| **Prioridade** | P2 |
| **Estimativa** | ~3d |
| **Depende de** | RAGX-0121 |
| **Documentação** | [src/app/README.md](../../src/app/README.md#empacotando) |
| **Status** | `todo` |

## Objetivo

Boa parte dos desenvolvedores usa Mac. Gerar o instalador do painel para macOS,
nas duas arquiteturas.

## Entregáveis

- [ ] Seção `mac` no `electron-builder.yml` (`dmg` e `zip`, `x64` e `arm64`), com `icon.icns` gerado a partir do ícone de marca (estender `scripts/brand.py`)
- [ ] Job `painel-macos` na release, em `macos-latest` (Apple Silicon) e num runner Intel, ou build universal
- [ ] Bundle com o `uv` de cada arquitetura (RAGX-0121)
- [ ] `.dmg` anexados à release e ao `SHA256SUMS.txt`
- [ ] README do painel: instalar arrastando para Aplicativos e o que fazer com o aviso do Gatekeeper enquanto não houver assinatura
- [ ] Ollama no macOS segue local (o Docker não usa a GPU); conferir os ramos existentes

## Fora de escopo

- Assinatura e notarização (RAGX-0124): sem elas o Gatekeeper bloqueia o app, e essa limitação precisa estar escrita no README
- Mac App Store
- Auto-update

## Critérios de aceite

- [ ] O `.dmg` abre em macOS limpo (Intel e Apple Silicon) depois da liberação manual no Gatekeeper; "RAGX CLI" fica verde
- [ ] O smoke roda na CI e é bloqueante
- [ ] Ícone correto no Dock e no Launchpad

## Testes

Smoke de empacotamento e de `--bootstrap` em `macos-latest`.

## Notas

Sem certificado de desenvolvedor Apple, o app baixado da internet não abre por
duplo clique. Distribuir de forma decente depende da RAGX-0124. Testar em
hardware real (Intel e Apple Silicon) é parte de aceitar a tarefa; o runner não
substitui.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Verificado num Mac de verdade
