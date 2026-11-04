# Genera los secretos locales la primera vez: .env y el par de llaves RSA para los JWT.
# Uso (desde la raíz del repositorio):  .\scripts\setup.ps1
# Es idempotente: si .env o las llaves ya existen, no los sobrescribe.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Nueva-Clave {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

if (Test-Path ".env") {
    Write-Host ".env ya existe; no se modifica."
} else {
    $contenido = Get-Content ".env.example" | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=cambiar$") { "$($Matches[1])=$(Nueva-Clave)" } else { $_ }
    }
    # UTF-8 sin BOM, para que docker compose lo lea sin problemas
    [System.IO.File]::WriteAllLines("$raiz\.env", $contenido)
    Write-Host ".env creado con contraseñas aleatorias."
}

New-Item -ItemType Directory -Force -Path "secrets" | Out-Null
if ((Test-Path "secrets\jwt_private.pem") -and (Test-Path "secrets\jwt_public.pem")) {
    Write-Host "Las llaves JWT ya existen; no se modifican."
} else {
    # Usa un contenedor con OpenSSL para no exigir OpenSSL instalado en Windows
    docker run --rm -v "${raiz}\secrets:/out" alpine:3.20 sh -c `
      "apk add --no-cache openssl >/dev/null && openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out /out/jwt_private.pem && openssl rsa -in /out/jwt_private.pem -pubout -out /out/jwt_public.pem"
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron generar las llaves JWT." }
    Write-Host "Llaves JWT creadas en secrets\."
}
Write-Host "Listo. Ahora ejecuta: docker compose up --build"
