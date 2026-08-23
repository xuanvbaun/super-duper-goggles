$ErrorActionPreference = "Stop"

$DataDir = Join-Path $PSScriptRoot "backend\data"
$SettingsFile = Join-Path $DataDir "tunnel-settings.json"
$TokenFile = Join-Path $DataDir "tunnel-token.txt"

Write-Host "OSINT News Console - configure fixed Cloudflare URL" -ForegroundColor Cyan
Write-Host "Before continuing, create a remotely-managed Cloudflare Tunnel and map its public hostname to http://127.0.0.1:5173."
Write-Host "Type REMOVE as the URL to return to a random temporary address."

$PublicUrl = (Read-Host "Fixed HTTPS URL, for example https://news.example.com").Trim()
if ($PublicUrl -eq "REMOVE") {
    Remove-Item -LiteralPath $SettingsFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $TokenFile -Force -ErrorAction SilentlyContinue
    Write-Host "Fixed URL configuration removed. The next start will use a random temporary address." -ForegroundColor Green
    exit 0
}

$ParsedUrl = $null
if (-not [Uri]::TryCreate($PublicUrl, [UriKind]::Absolute, [ref]$ParsedUrl) -or $ParsedUrl.Scheme -ne "https") {
    throw "The fixed URL must be a valid https:// address."
}
$PublicUrl = $PublicUrl.TrimEnd("/")

$SecureToken = Read-Host "Tunnel token (the eyJ... value from Cloudflare)" -AsSecureString
$Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
try {
    $PlainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
}
if ($PlainToken.Length -lt 40) {
    throw "The tunnel token appears incomplete."
}

New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
[IO.File]::WriteAllText($TokenFile, $PlainToken, [Text.Encoding]::ASCII)
@{ public_url = $PublicUrl } | ConvertTo-Json | Set-Content -LiteralPath $SettingsFile -Encoding UTF8
$PlainToken = $null

& icacls.exe $TokenFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not tighten file permissions automatically. Keep backend\data\tunnel-token.txt private."
}

Write-Host "Fixed URL saved: $PublicUrl" -ForegroundColor Green
Write-Host "Restart start-local.bat to use it. Never upload tunnel-token.txt to GitHub."
