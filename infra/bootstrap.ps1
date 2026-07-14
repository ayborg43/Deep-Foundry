param(
    [switch]$Force,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$infraDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$templatePath = Join-Path $infraDir ".env.example"
$outputPath = if ($OutputPath) {
    [IO.Path]::GetFullPath($OutputPath)
} else {
    Join-Path $infraDir ".env"
}

if ((Test-Path $outputPath) -and -not $Force) {
    throw "infra/.env already exists. Back it up, or rerun with -Force to replace it."
}

function New-RandomBase64Url([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$content = [IO.File]::ReadAllText($templatePath)
$values = [ordered]@{
    APP_ENV = "production"
    DJANGO_SECRET_KEY = New-RandomBase64Url 64
    DJANGO_DEBUG = "false"
    FIELD_ENCRYPTION_KEY = (New-RandomBase64Url 32) + "="
    DB_PASSWORD = New-RandomBase64Url 32
    MINIO_ROOT_PASSWORD = New-RandomBase64Url 32
    INTERNAL_API_TOKEN = New-RandomBase64Url 48
}
foreach ($entry in $values.GetEnumerator()) {
    $content = [regex]::Replace(
        $content,
        "(?m)^$([regex]::Escape($entry.Key))=.*$",
        "$($entry.Key)=$($entry.Value)"
    )
}
[IO.File]::WriteAllText($outputPath, $content, (New-Object Text.UTF8Encoding($false)))
Write-Host "Created infra/.env with generated production secrets."
Write-Host "Set DJANGO_ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS, and WEB_APP_URL to your domain before deployment."
