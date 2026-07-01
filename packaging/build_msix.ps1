# =============================================================================
# Multi Voice Studio - MSIX build script (with self-sign for local testing)
#
#   Usage (normal PowerShell is fine; .venv-build not required):
#       powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1
#
#   Steps:
#     1) Locate makeappx.exe / signtool.exe from the Windows SDK
#     2) Copy AppxManifest.xml and Assets into the dist folder
#     3) Pack into .msix with makeappx
#     4) Sign with a self-signed cert (subject == Publisher) for local install test
#     5) Export the cert (.cer) and print install instructions
#
#   NOTE: For Store submission, signing is NOT required (the Store signs it).
#         The self-sign here is only to install/test locally.
#   (ASCII-only on purpose: PowerShell 5.1 reads .ps1 as the system codepage,
#    so non-ASCII would be garbled.)
# =============================================================================

param(
    [string]$DistDir   = "F:\mvs-build\dist\MultiVoiceStudio",
    [string]$OutMsix   = "F:\mvs-build\MultiVoiceStudio.msix",
    [string]$Publisher = "CN=E5A55C73-7E5B-4BF9-B37E-C562F23A3A5E"
)

$ErrorActionPreference = "Stop"
$pkgDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # packaging\

function Find-SdkTool($name) {
    $root = "C:\Program Files (x86)\Windows Kits\10\bin"
    $hit = Get-ChildItem $root -Recurse -Filter $name -ErrorAction SilentlyContinue |
           Where-Object { $_.FullName -match "\\x64\\" } |
           Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $hit) {
        $hit = Get-ChildItem $root -Recurse -Filter $name -ErrorAction SilentlyContinue |
               Sort-Object FullName -Descending | Select-Object -First 1
    }
    if (-not $hit) { throw "$name not found (check the Windows SDK)." }
    return $hit.FullName
}

$makeappx = Find-SdkTool "makeappx.exe"
$signtool = Find-SdkTool "signtool.exe"
Write-Host "makeappx : $makeappx"
Write-Host "signtool : $signtool"

if (-not (Test-Path $DistDir)) { throw "dist folder not found: $DistDir" }

# --- 2) Copy manifest + icons into dist ---
Write-Host "Copying AppxManifest.xml and Assets into dist..."
Copy-Item (Join-Path $pkgDir "AppxManifest.xml") (Join-Path $DistDir "AppxManifest.xml") -Force
# Stamp version from single source (version.txt) into the copied manifest.
$verFile = Join-Path (Split-Path -Parent $pkgDir) "version.txt"
if (Test-Path $verFile) {
    $ver = (Get-Content $verFile -Raw).Trim()
    $manifestDst = Join-Path $DistDir "AppxManifest.xml"
    $mtext = (Get-Content $manifestDst -Raw) -replace '(?<=\s)Version="[0-9][0-9.]*"', ('Version="' + $ver + '"')
    [System.IO.File]::WriteAllText($manifestDst, $mtext, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Stamped AppxManifest Version = $ver (from version.txt)"
} else { Write-Host "WARNING: version.txt not found; using AppxManifest as-is." }
$assetsSrc = Join-Path $pkgDir "Assets"
$assetsDst = Join-Path $DistDir "Assets"
if (-not (Test-Path $assetsSrc)) { throw "Assets missing. Run: python scripts\make_msix_assets.py" }
New-Item -ItemType Directory -Force -Path $assetsDst | Out-Null
Copy-Item (Join-Path $assetsSrc "*") $assetsDst -Recurse -Force

# --- 3) Pack (large: this takes a while) ---
Write-Host "Packing MSIX (large payload, please wait)..."
& $makeappx pack /o /d $DistDir /p $OutMsix
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed (exit $LASTEXITCODE)." }
Write-Host "Packed: $OutMsix"

# --- 4) Self-sign for local testing ---
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $Publisher } | Select-Object -First 1
if (-not $cert) {
    Write-Host "Creating self-signed cert (subject=$Publisher)..."
    $cert = New-SelfSignedCertificate -Type Custom -Subject $Publisher `
        -KeyUsage DigitalSignature -FriendlyName "Multi Voice Studio (test)" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
}
Write-Host "Signing... (thumbprint=$($cert.Thumbprint))"
& $signtool sign /fd SHA256 /sha1 $cert.Thumbprint $OutMsix
if ($LASTEXITCODE -ne 0) { throw "signing failed (exit $LASTEXITCODE)." }

$cerPath = Join-Path (Split-Path -Parent $OutMsix) "MVS_Test.cer"
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

Write-Host ""
Write-Host "===== DONE ====="
Write-Host "MSIX : $OutMsix"
Write-Host "Cert : $cerPath"
Write-Host ""
Write-Host "To install/test locally, in an ADMIN PowerShell run:"
Write-Host "  Import-Certificate -FilePath `"$cerPath`" -CertStoreLocation Cert:\LocalMachine\TrustedPeople"
Write-Host "  Add-AppxPackage `"$OutMsix`""
Write-Host ""
Write-Host "For Store submission, signing is not needed (upload this .msix to Partner Center)."
