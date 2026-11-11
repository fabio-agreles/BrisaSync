; BrisaSync NSIS Modern Installer Script
; Arquitetura: x64 (Instalação por usuário, sem necessidade de privilégios de Administrador)

!include "MUI2.nsh"
!include "FileFunc.nsh"

; Definições Gerais
!define PRODUCT_NAME "BrisaSync"
!define PRODUCT_VERSION "0.1.27"
!define PRODUCT_PUBLISHER "Fábio Agreles"
!define PRODUCT_WEB_SITE "https://brisasync.com.br/"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\brisasync.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "..\..\dist\BrisaSync-${PRODUCT_VERSION}-Setup-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\BrisaSync"
InstallDirRegKey HKCU "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show
RequestExecutionLevel user

; Configurações da Interface Modern UI (MUI2)
!define MUI_ABORTWARNING
!define MUI_ICON "brisasync.ico"
!define MUI_UNICON "brisasync.ico"

; Páginas do Instalador
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\brisasync.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Iniciar o BrisaSync agora"
!insertmacro MUI_PAGE_FINISH

; Páginas do Desinstalador
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Idiomas
!insertmacro MUI_LANGUAGE "PortugueseBR"
!insertmacro MUI_LANGUAGE "English"

Section "Principal" SecCore
  SetOutPath "$INSTDIR"
  SetOverwrite ifnewer

  ; Copia os binários e bibliotecas compilados do diretório de build
  File /r "dist_win\*.*"

  ; Cria atalhos
  CreateDirectory "$SMPROGRAMS\BrisaSync"
  CreateShortcut "$SMPROGRAMS\BrisaSync\BrisaSync.lnk" "$INSTDIR\brisasync.exe" "" "$INSTDIR\brisasync.exe" 0
  CreateShortcut "$SMPROGRAMS\BrisaSync\Desinstalar BrisaSync.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
  CreateShortcut "$DESKTOP\BrisaSync.lnk" "$INSTDIR\brisasync.exe" "" "$INSTDIR\brisasync.exe" 0

  ; Cria desinstalador
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Grava entradas no Registro (HKCU)
  WriteRegStr HKCU "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\brisasync.exe"
  WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\brisasync.exe"
  WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr HKCU "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd

Section "Uninstall"
  ; Encerra processos ativos antes de desinstalar
  ExecWait 'taskkill /F /IM brisasync.exe'

  ; Remove atalhos
  Delete "$DESKTOP\BrisaSync.lnk"
  Delete "$SMPROGRAMS\BrisaSync\BrisaSync.lnk"
  Delete "$SMPROGRAMS\BrisaSync\Desinstalar BrisaSync.lnk"
  RMDir "$SMPROGRAMS\BrisaSync"

  ; Remove chave de autoinício se estiver ativa
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "BrisaSync"

  ; Remove arquivos da aplicação instalada
  RMDir /r "$INSTDIR"

  ; Remove registros do instalador
  DeleteRegKey HKCU "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKCU "${PRODUCT_DIR_REGKEY}"

  ; NOTA CRÍTICA DE SEGURANÇA:
  ; O desinstalador PRESERVA ESTRITAMENTE os dados do usuário em %APPDATA%\BrisaSync
  ; e todas as pastas e arquivos sincronizados no disco local.
SectionEnd

