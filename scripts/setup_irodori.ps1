# Irodori-TTS を準備するスクリプト（Windows PowerShell 用）。
#
# やること:
#   1. vendor フォルダに Irodori-TTS を GitHub から取得（clone）
#   2. uv sync で必要なライブラリを入れる（NVIDIA GPU 向け cu128）
#
# 実行（プロジェクト直下で）:
#   powershell -ExecutionPolicy Bypass -File scripts/setup_irodori.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$vendorDir = Join-Path $projectRoot "vendor"
$irodoriDir = Join-Path $vendorDir "Irodori-TTS"

if (-not (Test-Path $vendorDir)) {
    New-Item -ItemType Directory -Path $vendorDir | Out-Null
}

if (-not (Test-Path $irodoriDir)) {
    Write-Host "Irodori-TTS を取得します..."
    git clone https://github.com/Aratako/Irodori-TTS.git $irodoriDir
} else {
    Write-Host "Irodori-TTS は取得済みです。"
}

Write-Host "必要なライブラリを入れます（uv sync、初回は数分かかります）..."
Push-Location $irodoriDir
try {
    uv sync --extra cu128
} finally {
    Pop-Location
}

Write-Host "Irodori-TTS の準備ができました。"
