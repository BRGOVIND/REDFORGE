<#
Read-only preflight for a copied Windows release candidate. Run inside the
disposable rehearsal VM before executing the installer. A matching checksum
proves identity with the tested bytes, not safety or signing.
#>
param(
    [Parameter(Mandatory = $true)][string]$SetupPath,
    [Parameter(Mandatory = $true)][string]$SetupSha256,
    [Parameter(Mandatory = $true)][string]$PortableZipPath,
    [Parameter(Mandatory = $true)][string]$PortableSha256,
    [string]$SourceZipPath,
    [string]$SourceSha256
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Confirm-Artifact([string]$Path, [string]$ExpectedHash) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $item = Get-Item -LiteralPath $resolved
    if (-not $item.PSIsContainer -and $item.Length -gt 0) {
        $actual = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash
        if ($actual -ne $ExpectedHash.ToUpperInvariant()) {
            throw "SHA-256 mismatch: $resolved (actual $actual)"
        }
        return [pscustomobject]@{ Path = $resolved; Bytes = $item.Length; SHA256 = $actual }
    }
    throw "Not a non-empty file: $resolved"
}

function Confirm-Zip([string]$Path, [string[]]$Required) {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
        foreach ($name in $names) {
            if ($name.StartsWith('/') -or $name -match '^[A-Za-z]:/' -or
                @($name.Split('/') | Where-Object { $_ -eq '..' }).Count -gt 0) {
                throw "Unsafe ZIP entry: $name"
            }
        }
        foreach ($suffix in $Required) {
            if (-not @($names | Where-Object { $_ -eq $suffix -or $_.EndsWith('/' + $suffix) }).Count) {
                throw "Missing ZIP entry: $suffix"
            }
        }
        return $names.Count
    } finally {
        $archive.Dispose()
    }
}

$setup = Confirm-Artifact $SetupPath $SetupSha256
$portable = Confirm-Artifact $PortableZipPath $PortableSha256
$portableEntries = Confirm-Zip $portable.Path @(
    'RedForge.exe', 'resources/app.asar', 'resources/backend/redforge-backend.exe',
    'resources/backend/VERSION', 'LICENSE.txt'
)
$signature = (Get-AuthenticodeSignature -LiteralPath $setup.Path).Status
$version = (Get-Item -LiteralPath $setup.Path).VersionInfo.ProductVersion
Write-Output "Setup: $($setup.Bytes) bytes; SHA-256 $($setup.SHA256); signature $signature; version $version"
Write-Output "Portable: $($portable.Bytes) bytes; SHA-256 $($portable.SHA256); ZIP entries $portableEntries"

if ($SourceZipPath) {
    if (-not $SourceSha256) { throw 'SourceSha256 required with SourceZipPath' }
    $source = Confirm-Artifact $SourceZipPath $SourceSha256
    $sourceEntries = Confirm-Zip $source.Path @(
        'VERSION', 'LICENSE', 'install.cmd', 'install.sh',
        'backend/requirements.lock', 'cli/redforge/local_http.py'
    )
    Write-Output "Source: $($source.Bytes) bytes; SHA-256 $($source.SHA256); ZIP entries $sourceEntries"
}

if ($signature -ne 'Valid') {
    Write-Warning 'Windows installer signature is not valid. Internal VM testing only; consumer release blocked.'
}
