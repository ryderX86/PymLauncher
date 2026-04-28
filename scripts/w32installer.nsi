!addplugindir .\nsis-plugins\x86-ansi
!addplugindir .\nsis-plugins\x86-unicode
!include MUI2.nsh
!include "LogicLib.nsh"

!define NAME "Minecraft Launcher (Python)"
!define APPFILE "launcher.exe"
!define VERSION "1.0.0"
!define SLUG "${NAME} v${VERSION}"
!define AUMID "ryderX86.minecraftlauncher-python"
!define PUBLISHER "ryderX86"

!define MUI_FINISHPAGE_NOAUTOCLOSE ; no value
!define MUI_UNFINISHPAGE_NOAUTOCLOSE ; no value

Name "${NAME}"
OutFile "${NAME}_install.exe"
InstallDir "$PROGRAMFILES64\${NAME}"

!define MUI_ICON "..\resources\dist\icon.ico"
!define MUI_WELCOMEPAGE_TITLE "${SLUG} Installation"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
Function makeDesktopShortcut
	CreateShortcut "$DESKTOP\${NAME}.lnk" "$INSTDIR\${APPFILE}"
	ApplicationID::Set "$DESKTOP\${NAME}.lnk" "${AUMID}"
    ; check applicationid output:
    Pop $0
    ${If} $0 == -1
        MessageBox MB_OK "Failed to set desktop shortcut's AUMID"
    ${Else}
        ; succeeded
    ${EndIf}
FunctionEnd
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Create Desktop Shortcut"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION makeDesktopShortcut
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Section "App"
	SectionIn RO
	SetOutPath "$INSTDIR"
	File /r "..\dist\minecraftlauncher.dist\*.*"
	WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "DisplayName" "${NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "QuietUninstallString" "$\"$INSTDIR\uninstall.exe$\" /S"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "InstallLocation" "$\"$INSTDIR$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "Publisher" "${PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "DisplayVersion" "N/A"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "NoModify" 1
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}" "NoRepair" 1
SectionEnd

Section "Start Menu Shortcut"
	CreateShortcut "$SMPROGRAMS\${NAME}.lnk" "$INSTDIR\${APPFILE}"
	ApplicationID::Set "$SMPROGRAMS\${NAME}.lnk" "${AUMID}"
    Pop $0
    ${If} $0 == -1
        MessageBox MB_OK "Failed to set start menu shortcut's AUMID"
    ${Else}
        ; succeeded
    ${EndIf}
SectionEnd

Function un.RMDirUP
	!define RMDirUP "!insertmacro RMDirUPCall"
	
	!macro RMDirUPCall _PATH
		push '${_PATH}'
		Call un.RMDirUP
	!macroend
	
	ClearErrors
	
	Exch $0
	RMDir "$0\.."
	
	IfErrors Skip
	${RMDirUP} "$0\.."
	Skip:
	
	Pop $0
	
FunctionEnd

Section "Uninstall"
    IfFileExists "$DESKTOP\${NAME}.lnk" 0 +1
	Delete "$DESKTOP\${NAME}.lnk"
	Delete "$SMPROGRAMS\${NAME}.lnk"
	Delete "$INSTDIR\Uninstall.exe"
	RMDir /r "$INSTDIR"
	${RMDirUP} "$INSTDIR"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AUMID}"
SectionEnd