# Demostración de Clientes: login, autorización e importación CSV idempotente (prueba 12).
# Uso: .\scripts\demo-clientes.ps1   (con docker compose up corriendo)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$base = "http://localhost:8002"

$envv = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.*)$") { $envv[$Matches[1]] = $Matches[2] } }

function Login($usuario, $password) {
    $body = @{ usuario = $usuario; password = $password } | ConvertTo-Json
    (Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/json" -Body $body).access_token
}
function Estado($bloque) {
    try { & $bloque | Out-Null; return 200 } catch { return [int]$_.Exception.Response.StatusCode }
}

Write-Host "`n== Login ==" -ForegroundColor Cyan
$admin = Login "admin" $envv["DEMO_ADMIN_PASSWORD"]
$ana   = Login "ana"   $envv["DEMO_CLIENTE_PASSWORD"]
Write-Host "Tokens emitidos para admin y ana."

Write-Host "`n== Autorización ==" -ForegroundColor Cyan
$hAna = @{ Authorization = "Bearer $ana" }
Write-Host ("ana consulta sus datos (CLI-DEMO-0001):  {0}  (esperado 200)" -f (Estado { Invoke-RestMethod "$base/clientes/CLI-DEMO-0001" -Headers $hAna }))
Write-Host ("ana consulta a beto   (CLI-DEMO-0002):  {0}  (esperado 403)" -f (Estado { Invoke-RestMethod "$base/clientes/CLI-DEMO-0002" -Headers $hAna }))
Write-Host ("sin token:                              {0}  (esperado 401)" -f (Estado { Invoke-RestMethod "$base/clientes/CLI-DEMO-0001" }))

Write-Host "`n== Importación CSV (dos veces el mismo archivo) ==" -ForegroundColor Cyan
foreach ($intento in 1, 2) {
    $json = curl.exe -s -H "Authorization: Bearer $admin" -F "archivo=@scripts/datos/clientes_demo.csv" "$base/clientes/importar"
    $r = $json | ConvertFrom-Json
    Write-Host ("Intento {0}: insertados={1}  ya_existian={2}  errores={3}" -f $intento, $r.insertados, $r.ya_existian, $r.errores) -ForegroundColor Green
    if ($intento -eq 1) {
        $r.filas | Where-Object { $_.resultado -eq "error" } | ForEach-Object { Write-Host ("   fila {0}: {1}" -f $_.fila, $_.detalle) -ForegroundColor Yellow }
    }
}
Write-Host "(Esperado: intento 1 -> 5, 0, 3   |   intento 2 -> 0, 5, 3)"
