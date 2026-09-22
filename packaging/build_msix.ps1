# Builds dist\store\MonitorWidget_<version>.msix from the sources.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1
#   powershell ... -Sign            # signs with a local test certificate
#
# The Store resigns the package itself, so -Sign is only there to install the
# package on this machine and try it before submitting.
#
# Needs PyInstaller and the Windows SDK (makeappx.exe, signtool.exe).

param([switch]$Sign)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$staging = Join-Path $root "dist\MonitorWidget"
$output = Join-Path $root "dist\store"

# ---------------------------------------------------------------- version
$versionFile = Join-Path $root "monitor_widget\version.py"
$match = Select-String -Path $versionFile -Pattern '__version__\s*=\s*"([^"]+)"'
if (-not $match) { throw "Version not found in $versionFile" }
$version = $match.Matches[0].Groups[1].Value
$packageVersion = "$version.0"
Write-Host "Monitor Widget $version"

# ---------------------------------------------------------------- the app
Push-Location $root
try {
    python -m PyInstaller --noconfirm --clean packaging\monitor_widget.spec
} finally {
    Pop-Location
}
if (-not (Test-Path (Join-Path $staging "MonitorWidget.exe"))) {
    throw "PyInstaller did not produce MonitorWidget.exe"
}

# ------------------------------------------------- manifest and pictures
Copy-Item (Join-Path $PSScriptRoot "msix\Assets") $staging -Recurse -Force
$manifest = Get-Content (Join-Path $PSScriptRoot "msix\AppxManifest.xml") -Raw
$manifest = $manifest -replace 'Version="0\.0\.0\.0"', "Version=`"$packageVersion`""
Set-Content -Path (Join-Path $staging "AppxManifest.xml") -Value $manifest -Encoding UTF8

# ---------------------------------------------------------------- packing
$sdk = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "x64\makeappx.exe") } |
    Sort-Object Name -Descending | Select-Object -First 1
if (-not $sdk) { throw "makeappx.exe not found: install the Windows SDK" }
$makeappx = Join-Path $sdk.FullName "x64\makeappx.exe"
$signtool = Join-Path $sdk.FullName "x64\signtool.exe"

New-Item -ItemType Directory -Force -Path $output | Out-Null
$package = Join-Path $output "MonitorWidget_$packageVersion.msix"
& $makeappx pack /o /d $staging /p $package
if ($LASTEXITCODE -ne 0) { throw "makeappx failed" }

# ------------------------------------------------- local test signature
if ($Sign) {
    $subject = "CN=FBE8A2FE-0B1A-4DC6-9A37-26D917854488"
    $certificate = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Subject -eq $subject } | Select-Object -First 1
    if (-not $certificate) {
        $certificate = New-SelfSignedCertificate -Type Custom -Subject $subject `
            -KeyUsage DigitalSignature -FriendlyName "Monitor Widget test" `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
        Write-Host "Test certificate created. Import it into" `
            "'Trusted People' (certlm.msc) before installing the package."
    }
    & $signtool sign /fd SHA256 /a /sha1 $certificate.Thumbprint $package
    if ($LASTEXITCODE -ne 0) { throw "signtool failed" }
}

Write-Host "Package ready: $package"
