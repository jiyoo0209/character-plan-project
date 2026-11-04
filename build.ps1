# CharacterPlan 빌드 스크립트 (Windows PowerShell)
# 사용법: .\build.ps1            -> dist\CharacterPlan\CharacterPlan.exe
#         .\build.ps1 -Installer -> 설치 파일까지 생성 (Inno Setup 6 필요)
param([switch]$Installer)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm --clean --windowed `
    --name CharacterPlan `
    --icon assets\icon.ico `
    --add-data "assets;assets" `
    main.py

Write-Host "빌드 완료: dist\CharacterPlan\CharacterPlan.exe"

if ($Installer) {
    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) { $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" }
    if (-not (Test-Path $iscc)) { throw "Inno Setup 6 을 설치해 주세요: https://jrsoftware.org/isinfo.php" }
    & $iscc installer.iss
    Write-Host "설치 파일: installer_output\CharacterPlan-Setup.exe"
}
