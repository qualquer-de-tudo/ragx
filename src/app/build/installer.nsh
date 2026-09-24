; Ganchos NSIS do RAGX Painel (spec: docs/superpowers/specs/2026-09-23-instalador-completo-design.md).
; Sem lógica própria: tudo o que instala/remove a CLI vive em TypeScript
; (electron/bootstrap/*) e o .exe só é chamado com --bootstrap / --uninstall-cli.

; Instalação: customInstall roda em installSection.nsh DEPOIS de copiar os
; arquivos e gravar o registro. Falha do bootstrap nunca falha a instalação:
; o painel refaz na primeira abertura ("Reparar"). Em /S nada é exibido.
!macro customInstall
  DetailPrint "Instalando a CLI ragx (uv + Python 3.12 + wheel)..."
  ClearErrors
  ExecWait '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" --bootstrap' $0
  ${If} $0 != 0
  ${AndIfNot} ${Silent}
    MessageBox MB_OK|MB_ICONINFORMATION "A instalação da CLI ragx não terminou (código $0).$\r$\n$\r$\nO RAGX Painel tenta de novo na primeira abertura, em 'RAGX CLI > Instalar / Tentar de novo'. O log está em %APPDATA%\app\bootstrap.log."
  ${EndIf}
!macroend

; Desinstalação: customUnInstall roda em uninstaller.nsh DEPOIS de
; `RMDir /r $INSTDIR` (o .exe do painel já não existe), então não serve.
; customRemoveFiles roda ANTES da remoção e a substitui — por isso o bloco
; padrão do template (app-builder-lib 25.x, uninstaller.nsh) é repetido no fim.
; Em atualização (--updated) a CLI e os dados não são tocados.
!macro customRemoveFiles
  ${IfNot} ${isUpdated}
    StrCpy $R8 "0" ; remover a CLI?
    StrCpy $R9 "" ; argumentos extras do --uninstall-cli
    ${If} ${Silent}
      ${GetParameters} $R0
      ClearErrors
      ${GetOptions} $R0 "--remove-cli" $R1
      ${IfNot} ${Errors}
        StrCpy $R8 "1"
      ${EndIf}
      ClearErrors
      ${GetOptions} $R0 "--remove-data" $R1
      ${IfNot} ${Errors}
        StrCpy $R8 "1"
        StrCpy $R9 " --remove-data"
      ${EndIf}
    ${Else}
      MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON1 "Remover também a CLI ragx e o registro no Claude Code?" IDNO ragxSemCli
      StrCpy $R8 "1"
      MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "Remover também os dados do hub (~\.ragx)?" IDNO ragxSemDados
      StrCpy $R9 " --remove-data"
      ragxSemDados:
      ragxSemCli:
    ${EndIf}
    ${If} $R8 == "1"
      ExecWait '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" --uninstall-cli$R9' $R0
    ${EndIf}
  ${EndIf}

  ; --- bloco padrão do template, inalterado ---
  ${if} ${isUpdated}
    CreateDirectory "$PLUGINSDIR\old-install"

    Push ""
    Call un.atomicRMDir
    Pop $R0

    ${if} $R0 != 0
      DetailPrint "File is busy, aborting: $R0"

      Push ""
      Call un.restoreFiles
      Pop $R0

      Abort `Can't rename "$INSTDIR" to "$PLUGINSDIR\old-install".`
    ${endif}
  ${endif}

  RMDir /r $INSTDIR
!macroend
