# CharacterPlan 빌드 스크립트 (Windows PowerShell)
# 사용법: .\build.ps1            -> dist\CharacterPlan\CharacterPlan.exe
#         .\build.ps1 -Installer -> 설치 파일까지 생성 (Inno Setup 6 필요)
#         .\build.ps1 -Installer -Version 0.2.3 -> 버전 번호를 넣어서 빌드
param([switch]$Installer, [string]$Version = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt pyinstaller

if ($Version) {
    # 앱이 자기 버전을 알 수 있게 app\version.py 에 써 넣는다 (자동 업데이트 비교용)
    Set-Content -Path app\version.py -Encoding utf8 -Value "__version__ = `"$Version`""
}

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
    if ($Version) { & $iscc "/DAppVersion=$Version" installer.iss } else { & $iscc installer.iss }
    if ($LASTEXITCODE -ne 0) { throw "설치 파일 만들기 실패" }
    Write-Host "설치 파일: installer_output\CharacterPlan-Setup.exe"
}
