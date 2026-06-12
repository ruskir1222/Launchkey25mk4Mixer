# =================================================================
# Launchkey Mixer — Self-signing script
# =================================================================
# Generates a self-signed code-signing certificate (one-time) and
# signs LaunchkeyMixer.exe + LaunchkeyMixerSetup.exe.
#
# This is FREE but Windows SmartScreen will still show
# "Unknown publisher" because the cert isn't from a trusted CA.
# Self-signing reduces some warnings vs. unsigned, but for a fully
# trusted cert you need a paid one (~$100/year) from Sectigo/DigiCert.
#
# Usage (from offline\ folder):
#     powershell -ExecutionPolicy Bypass -File sign.ps1
# =================================================================

$ErrorActionPreference = 'Stop'

$CertSubject  = 'CN=Launchkey Mixer (Self-Signed), O=ruskir1222'
$CertStore    = 'Cert:\CurrentUser\My'
$CertFile     = Join-Path $PSScriptRoot 'launchkey-mixer.pfx'
$CertPassword = 'launchkey-mixer'  # Local-only; change if you publish externally
$FilesToSign  = @(
    (Join-Path $PSScriptRoot 'dist\LaunchkeyMixer.exe'),
    (Join-Path $PSScriptRoot 'installer\LaunchkeyMixerSetup.exe')
) | Where-Object { Test-Path $_ }

if (-not $FilesToSign) {
    Write-Host "[sign] No .exe files found to sign. Run build_windows.bat first." -ForegroundColor Yellow
    exit 0
}

# 1) Find or create the cert
$cert = Get-ChildItem -Path $CertStore | Where-Object { $_.Subject -eq $CertSubject } | Select-Object -First 1
if (-not $cert) {
    Write-Host "[sign] Generating new self-signed certificate..." -ForegroundColor Cyan
    $cert = New-SelfSignedCertificate `
        -Subject $CertSubject `
        -Type CodeSigningCert `
        -KeySpec Signature `
        -KeyUsage DigitalSignature `
        -KeyExportPolicy Exportable `
        -CertStoreLocation $CertStore `
        -NotAfter (Get-Date).AddYears(3)
    Write-Host "[sign] Cert created with thumbprint $($cert.Thumbprint)" -ForegroundColor Green
}

# 2) Export to .pfx (so other tools / CI can use it if needed)
if (-not (Test-Path $CertFile)) {
    $securePass = ConvertTo-SecureString -String $CertPassword -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $CertFile -Password $securePass | Out-Null
    Write-Host "[sign] Cert exported to $CertFile" -ForegroundColor Green
}

# 3) Locate signtool.exe (Windows SDK)
$signTool = Get-Command 'signtool.exe' -ErrorAction SilentlyContinue
if (-not $signTool) {
    $candidates = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match 'x64' } | Sort-Object FullName -Descending
    if ($candidates) { $signTool = $candidates[0].FullName }
}
if (-not $signTool) {
    Write-Host "[sign] signtool.exe not found. Install the Windows 10/11 SDK from:" -ForegroundColor Yellow
    Write-Host "       https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/" -ForegroundColor Yellow
    Write-Host "       (only the 'Signing Tools' component is required, ~70MB)" -ForegroundColor Yellow
    exit 1
}
if ($signTool -is [System.Management.Automation.CommandInfo]) { $signTool = $signTool.Path }
Write-Host "[sign] Using signtool: $signTool"

# 4) Sign each file
foreach ($file in $FilesToSign) {
    Write-Host "[sign] Signing $file ..." -ForegroundColor Cyan
    & $signTool sign /fd SHA256 /sha1 $cert.Thumbprint /td SHA256 /tr 'http://timestamp.digicert.com' $file
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[sign] signtool returned $LASTEXITCODE for $file" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "[sign] Done. $($FilesToSign.Count) file(s) signed." -ForegroundColor Green
