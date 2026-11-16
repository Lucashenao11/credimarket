# Demostración de la API de Préstamos: solicitud, idempotencia HTTP (200 / 409), aislamiento entre clientes e historial.
# Uso: .\scripts\demo-prestamos.ps1   (con docker compose up corriendo: clientes, productos, prestamos)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$pre = "http://localhost:8003"

$envv = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.*)$") { $envv[$Matches[1]] = $Matches[2] } }
function Login($usuario, $clave) {
    $b = @{ usuario = $usuario; password = $clave } | ConvertTo-Json
    @{ Authorization = "Bearer " + (Invoke-RestMethod -Method Post -Uri "http://localhost:8002/auth/login" -ContentType "application/json" -Body $b).access_token }
}
$ana = Login "ana" $envv["DEMO_CLIENTE_PASSWORD"]
$beto = Login "beto" $envv["DEMO_CLIENTE_PASSWORD"]
$admin = Login "admin" $envv["DEMO_ADMIN_PASSWORD"]

# Devuelve estado HTTP y cuerpo sin lanzar excepción en 4xx
function Pedir($metodo, $url, $headers, $cuerpo) {
    try {
        $p = @{ Method = $metodo; Uri = $url; Headers = $headers; ContentType = "application/json"; UseBasicParsing = $true }
        if ($cuerpo) { $p.Body = ($cuerpo | ConvertTo-Json) }
        $r = Invoke-WebRequest @p
        [pscustomobject]@{ Codigo = [int]$r.StatusCode; Cuerpo = ($r.Content | ConvertFrom-Json); Replay = $r.Headers["Idempotent-Replay"] }
    } catch {
        $resp = $_.Exception.Response
        $txt = ""
        if ($resp) { $txt = $_.ErrorDetails.Message }
        [pscustomobject]@{ Codigo = [int]$resp.StatusCode; Cuerpo = $txt; Replay = $null }
    }
}
function Solicitar($headers, $clave, $producto, $plazo) {
    $h = @{} + $headers; $h["Idempotency-Key"] = $clave
    Pedir "Post" "$pre/prestamos" $h @{ producto_id = $producto; cantidad = 1; plazo_meses = $plazo }
}
$sufijo = Get-Random

Write-Host "`n== Modelo activo ==" -ForegroundColor Cyan
$info = Invoke-RestMethod -Uri "$pre/modelo/info" -Headers $ana
Write-Host "versión=$($info.model_version)  umbral=$($info.umbral)"

Write-Host "`n== 1. Ana solicita el producto 1 a 12 meses ==" -ForegroundColor Cyan
$clave = "demo-$sufijo-a"
$r1 = Solicitar $ana $clave 1 12
$p = $r1.Cuerpo
Write-Host ("HTTP {0}  estado={1}  monto={2}  cuota={3}  prob={4}  motivo={5}" -f $r1.Codigo, $p.estado, $p.monto_cop, $p.cuota_cop, $p.probabilidad_incumplimiento, $p.motivo)
Write-Host "(El monto sale de la cotización de Productos v$($p.version_cotizacion); Ana no lo envía.)"

Write-Host "`n== 2. La MISMA petición otra vez (misma clave, mismo contenido) ==" -ForegroundColor Cyan
$r2 = Solicitar $ana $clave 1 12
Write-Host ("HTTP {0}  mismo id: {1}  Idempotent-Replay={2}  (esperado 200, True, true)" -f $r2.Codigo, ($r2.Cuerpo.id -eq $p.id), $r2.Replay)

Write-Host "`n== 3. La misma clave con contenido distinto (plazo 24) ==" -ForegroundColor Cyan
$r3 = Solicitar $ana $clave 1 24
Write-Host ("HTTP {0}  (esperado 409)" -f $r3.Codigo)

Write-Host "`n== 4. Beto usa la MISMA clave: es otro cliente, no hay conflicto ==" -ForegroundColor Cyan
$r4 = Solicitar $beto $clave 1 12
Write-Host ("HTTP {0}  cliente={1}  id distinto: {2}" -f $r4.Codigo, $r4.Cuerpo.cliente_id, ($r4.Cuerpo.id -ne $p.id))

Write-Host "`n== 5. Ana intenta ver el préstamo de Beto ==" -ForegroundColor Cyan
$r5 = Pedir "Get" "$pre/prestamos/$($r4.Cuerpo.id)" $ana $null
Write-Host ("HTTP {0}  (esperado 404)" -f $r5.Codigo)

Write-Host "`n== 6. Historial del préstamo ==" -ForegroundColor Cyan
(Invoke-RestMethod -Uri "$pre/prestamos/$($p.id)/historial" -Headers $ana) |
    ForEach-Object { Write-Host ("   {0} -> {1}  {2}" -f $_.estado_anterior, $_.estado_nuevo, $_.motivo) }

Write-Host "(El flujo completo por el broker -aprobación, cancelación, evento tardío- está en .\scripts\demo-flujo.ps1)" -ForegroundColor DarkGray
Write-Host "`nListo." -ForegroundColor Green
