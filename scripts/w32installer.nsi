
!include MUI2.nsh
!include logiclib.nsh

!define NAME "MinecraftLauncher-python"
!define APPFILE "launcher.exe"
!define VERSION "1.0.0"
!define SLUG "${NAME} v${VERSION}"

Name "${NAME}"
OutFile "${NAME}_install.exe"
InstallDir "$PROGRAMFILES64\${NAME}"

!define MUI_ICON "..\resources\_dist\icon.ico"
!define MUI_WELCOMEPAGE_TITLE "${SLUG} Installation"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Section "App"
	SectionIn RO
	SetOutPath "$INSTDIR"
	File /r "..\dist\Launcher.dist\*.*"
	WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Desktop Shortcut" DeskShort
	CreateShortcut "$DESKTOP\${NAME}.lnk" "$INSTDIR\${APPFILE}"
SectionEnd

Section "Start Menu Shortcut"
	CreateDirectory "$SMPROGRAMS\minecraftlauncher-py"
	CreateShortcut "$SMPROGRAMS\minecraftlauncher-py\${NAME}.lnk" "$INSTDIR\${APPFILE}"
	CreateShortcut "$SMPROGRAMS\minecraftlauncher-py\${NAME} Uninstaller.lnk" "$INSTDIR\Uninstall.exe"
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
	Delete "$DESKTOP\${NAME}.lnk"
	Delete "$SMPROGRAMS\minecraftlauncher-py\${NAME}.lnk"
	Delete "$SMPROGRAMS\minecraftlauncher-py\${NAME} Uninstaller.lnk"
	Delete "$INSTDIR\Uninstall.exe"
	RMDir /r "$INSTDIR"
	${RMDirUP} "$INSTDIR"
SectionEnd