# Fase 17: Distribuição do painel em Windows, Linux e macOS

6 tarefas, nascidas da análise de distribuição de 2026-09-24. Hoje só o Windows
tem instalador do painel; Linux e macOS têm a CLI (`install.sh`) e a extensão do
VS Code, e o painel não é testado na CI do dia a dia.

O foco atual do produto é o Windows. Por isso a ordem é: primeiro o que protege
e prova o que já existe (0119, 0120), depois o que amplia (0121 a 0123), e a
assinatura de código por último (0124), porque depende de compra de certificado.

| ID | Tarefa | Prio | Est. | Status |
|---|---|---|---|---|
| [RAGX-0119](RAGX-0119-ci-do-painel-em-tres-sistemas.md) | CI do painel (vitest, eslint, tsc) em Windows, Linux e macOS | P1 | 0,5d | `todo` |
| [RAGX-0120](RAGX-0120-release-publica-o-instalador-do-painel.md) | A release publica o instalador do painel de ponta a ponta | P1 | 0,5d | `todo` |
| [RAGX-0121](RAGX-0121-bundle-e-bootstrap-multiplataforma.md) | Bundle (`uv`) e bootstrap da CLI por plataforma | P2 | ~2d | `todo` |
| [RAGX-0122](RAGX-0122-painel-linux.md) | Painel no Linux (AppImage e `.deb`) | P2 | ~2d | `todo` |
| [RAGX-0123](RAGX-0123-painel-macos.md) | Painel no macOS (`.dmg` Intel e Apple Silicon) | P2 | ~3d | `todo` |
| [RAGX-0124](RAGX-0124-assinatura-de-codigo.md) | Assinatura de código (Windows e macOS) | P3 | ~2d + compra | `todo` (adiada) |

```text
0119 ──┐
       ├──> 0121 ──> 0122
0120 ──┘        └──> 0123 ──> 0124 (0124 também depende de 0120)
```

## Diagnóstico que originou a fase (2026-09-24)

| Peça | Windows | Linux | macOS |
|---|---|---|---|
| CLI `ragx` (wheel `py3-none-any`) | testada na CI e na release | testada | testada |
| `install.sh` / `install.ps1` | testados na CI, com idempotência | testado | testado |
| Extensão do VS Code (`.vsix`) | um arquivo só serve os três | igual | igual |
| Painel desktop | gera `.exe` (NSIS) | **não gera** | **não gera** |

Fatos que sustentam as tarefas:

- `electron-builder.yml` só tem a seção `win`; o README do painel diz "Gera o instalador Windows".
- `scripts/prepare-bundle.mjs` só baixa `uv-x86_64-pc-windows-msvc.zip`.
- O PATH do usuário no bootstrap usa `powershell.exe` (`electron/bootstrap/path-user.ts`) e o desinstalador é NSIS.
- `ci.yml` não menciona `src/app`: vitest, eslint e tsc do painel só rodam localmente.
- A release `v1.0.0-beta.3` (17/09) não trouxe o `.exe`: o job `painel-windows` entrou depois. Nenhuma release publicada entregou o instalador do painel.
- O código do painel já tem ramos para os três sistemas em partes (Ollama, `ragx-exe.ts`); o que falta é o empacotamento e o bootstrap em volta.

## Adiado por decisão da pessoa

- **Instalador de um clique com tela de preparação no painel** (estilo AMD Adrenalin): o NSIS passa a copiar e abrir o app, e o painel mostra em tela cheia o progresso da instalação da CLI antes do onboarding. Brainstorming iniciado em 2026-09-24 e pausado sem spec. Pontos levantados: a atualização precisa reinstalar a CLI quando a do pacote é mais nova (hoje o NSIS faz isso a cada instalação); a pasta de instalação deixa de ser escolhida; as duas perguntas do desinstalador continuam iguais. Se retomar, altera a spec do instalador ([ADR-0016](../../docs/adr/ADR-0016-instalador-completo-do-painel.md)) e vira tarefa própria.
- **Assinatura de código**: decisão de 2026-09-24 de seguir sem certificado por enquanto (ver RAGX-0124).
