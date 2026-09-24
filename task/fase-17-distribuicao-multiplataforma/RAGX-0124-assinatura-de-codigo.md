# RAGX-0124: Assinatura de código (Windows e macOS)

| | |
|---|---|
| **Fase** | 17: Distribuição do painel em Windows, Linux e macOS |
| **Prioridade** | P3: baixa (adiada por decisão da pessoa em 2026-09-24) |
| **Estimativa** | ~2d de trabalho, mais compra e validação dos certificados |
| **Depende de** | RAGX-0120 (Windows); RAGX-0123 (macOS) |
| **Documentação** | [electron-builder: code signing](https://www.electron.build/docs/features/code-signing/code-signing-win/) |
| **Status** | `todo` (adiada; precisa de compra de certificado antes) |

## Objetivo

Tirar o "Editor desconhecido" e o aviso do SmartScreen no Windows, e viabilizar a
distribuição no macOS, onde app não assinado e não notarizado é bloqueado.

## Levantamento (2026-09-24)

- **Azure Artifact Signing** (antigo Trusted Signing) não atende o Brasil: organizações só em EUA, Canadá, UE, Reino Unido, Austrália, Nova Zelândia, Japão, Coreia do Sul, Singapura, Suíça, Noruega e Israel; pessoa física só EUA e Canadá.
- Caminho no Windows: certificado **OV** em nome da Aivon Labs (CNPJ), com chave em HSM na nuvem (SSL.com eSigner, Certum SimplySign ou DigiCert KeyLocker), porque a chave não pode mais ser arquivo `.pfx` e um token USB não roda na CI. Custo na ordem de US$ 200 a 500 por ano; conferir com a revenda.
- **EV não zera o SmartScreen** desde 2024; a diferença do OV para o EV não justifica o preço só por isso. Com qualquer um, o aviso some aos poucos com a reputação de downloads e passa a mostrar o nome da empresa.
- macOS: conta Apple Developer (US$ 99 por ano), certificado Developer ID, assinatura e notarização.

## Entregáveis

- [ ] Decisão de compra do certificado (Windows) e da conta Apple (macOS), tomada pela pessoa
- [ ] Windows: assinar o `RAGX Painel.exe` no hook `scripts/after-pack.cjs` **depois** do `rcedit` (com `signAndEditExecutable: false` o electron-builder não assina o exe do app), e o instalador e o desinstalador pelo hook de assinatura do electron-builder, sempre com timestamp
- [ ] macOS: assinatura e notarização no `electron-builder`
- [ ] Segredos no GitHub Actions; o build local sem segredos continua funcionando sem assinar
- [ ] Verificação na CI: `signtool verify /pa` no Windows e `spctl` e `stapler validate` no macOS
- [ ] README e notas da release deixam de citar o aviso do SmartScreen e do Gatekeeper

## Fora de escopo

- Auto-update
- Assinar a CLI Python ou o `.vsix`

## Critérios de aceite

- [ ] `Get-AuthenticodeSignature` no `.exe` do app, no instalador e no desinstalador mostra status válido, com timestamp
- [ ] O instalador baixado da release abre no macOS sem liberação manual
- [ ] Nenhum segredo aparece em log da CI

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] CHANGELOG atualizado na MESMA alteração
