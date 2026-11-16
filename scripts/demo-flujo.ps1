# Demostración del flujo completo POR EL BROKER (RabbitMQ): reserva, última unidad, cancelación,
# entrega, y el evento tardío en vivo (Inventario caído -> timeout -> Inventario vuelve).
# Uso: .\scripts\demo-flujo.ps1   (con docker compose up corriendo; tarda unos 2 minutos)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$pre = "http://localhost:8003"; $inv = "http://localhost:8004"; $prod = "http://localhost:8001"

$envv = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.*)$") { $envv[$Matches[1]] = $Matches[2] } }
function Login($usuario, $clave) {
    $b = @{ usuario = $usuario; password = $clave } | ConvertTo-Json
    @{ Authorization = "Bearer " + (Invoke-RestMethod -Method Post -Uri "http://localhost:8002/auth/login" -ContentType "application/json" -Body $b).access_token }
}
$ana = Login "ana" $envv["DEMO_CLIENTE_PASSWORD"]
$admin = Login "admin" $envv["DEMO_ADMIN_PASSWORD"]
$sufijo = Get-Random

function Json($o) { $o | ConvertTo-Json }
function Stock($id) { $e = Invoke-RestMethod -Uri "$inv/existencias/$id" -Headers $admin; "disponible=$($e.disponible) reservado=$($e.reservado)" }
function Estado($id) { (Invoke-RestMethod -Uri "$pre/prestamos/$id" -Headers $ana) }
function Solicitar($clave, $producto) {
    $h = @{} + $ana; $h["Idempotency-Key"] = $clave
    (Invoke-RestMethod -Method Post -Uri "$pre/prestamos" -Headers $h -ContentType "application/json" `
        -Body (Json @{ producto_id = $producto; cantidad = 1; plazo_meses = 12 }))
}
function Esperar($id, $estados, $segundos) {
    $limite = (Get-Date).AddSeconds($segundos)
    do { $e = Estado $id; if ($estados -contains $e.estado) { return $e }; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $limite)
    return (Estado $id)
}
function Nuevo-Producto($unidades) {
    $p = Invoke-RestMethod -Method Post -Uri "$prod/productos" -Headers $admin -ContentType "application/json" `
        -Body (Json @{ nombre = "Demo flujo $sufijo"; categoria = "demo"; precio_cop = 1200000 })
    Invoke-RestMethod -Method Post -Uri "$inv/existencias/$($p.id)/entradas" -Headers $admin -ContentType "application/json" `
        -Body (Json @{ cantidad = $unidades }) | Out-Null
    $p.id
}

Write-Host "`n== 1. Flujo normal: solicitud -> broker -> Inventario reserva -> APROBADA ==" -ForegroundColor Cyan
$p1 = Nuevo-Producto 3
Write-Host "Producto $p1 con 3 unidades: $(Stock $p1)"
$s = Solicitar "flujo-$sufijo-1" $p1
Write-Host "Respuesta inmediata: $($s.estado) (202; el préstamo ya es consultable)"
$e = Esperar $s.id @("APROBADA", "RECHAZADA") 30
Write-Host "Un momento después: $($e.estado)   |   $(Stock $p1)   (esperado APROBADA, reservado=1)"
$aprobado = $s.id

Write-Host "`n== 2. La última unidad, pedida al mismo tiempo por dos solicitudes ==" -ForegroundColor Cyan
$p2 = Nuevo-Producto 1
Write-Host "Producto $p2 con 1 unidad: $(Stock $p2)"
$tok = $ana["Authorization"]
$jobs = 1..2 | ForEach-Object {
    Start-Job -ArgumentList $_, $tok, $pre, $p2, $sufijo -ScriptBlock {
        param($n, $tok, $pre, $p2, $sufijo)
        $h = @{ Authorization = $tok; "Idempotency-Key" = "ultima-$sufijo-$n" }
        $b = @{ producto_id = $p2; cantidad = 1; plazo_meses = 12 } | ConvertTo-Json
        (Invoke-RestMethod -Method Post -Uri "$pre/prestamos" -Headers $h -ContentType "application/json" -Body $b).id
    }
}
$ids = @($jobs | Wait-Job | Receive-Job); $jobs | Remove-Job
$estados = @()
foreach ($id in $ids) { $estados += (Esperar $id @("APROBADA", "CANCELADA_SIN_STOCK", "RECHAZADA") 30).estado }
Write-Host ("Resultados: {0}   |   {1}   (esperado: una APROBADA y una CANCELADA_SIN_STOCK, reservado=1)" -f ($estados -join " / "), (Stock $p2))

Write-Host "`n== 3. Cancelación: la reserva se libera ==" -ForegroundColor Cyan
Write-Host "Antes: $(Stock $p1)"
Invoke-RestMethod -Method Post -Uri "$pre/prestamos/$aprobado/cancelar" -Headers $ana | Out-Null
Start-Sleep -Seconds 4
Write-Host "Después de cancelar: $(Estado $aprobado | ForEach-Object { $_.estado })   |   $(Stock $p1)   (esperado CANCELADA, reservado=0)"

Write-Host "`n== 4. Entrega: Inventario confirma la salida y Préstamos pasa a COMPLETADA ==" -ForegroundColor Cyan
$s4 = Solicitar "flujo-$sufijo-4" $p1
$null = Esperar $s4.id @("APROBADA") 30
Invoke-RestMethod -Method Post -Uri "$pre/prestamos/$($s4.id)/entregar" -Headers $admin | Out-Null
$e4 = Esperar $s4.id @("COMPLETADA") 30
Write-Host "Estado: $($e4.estado)   |   $(Stock $p1)   (esperado COMPLETADA y la unidad fuera de bodega)"

Write-Host "`n== 5. Evento tardío EN VIVO: Inventario caído, timeout, Inventario vuelve ==" -ForegroundColor Cyan
$p5 = Nuevo-Producto 2
Write-Host "Producto $p5 con 2 unidades: $(Stock $p5)"
docker compose stop inventario | Out-Null
Write-Host "Inventario detenido. Solicitando..."
$s5 = Solicitar "flujo-$sufijo-5" $p5
Write-Host "Solicitud: $($s5.estado). Esperando el timeout (60 s)..."
$e5 = Esperar $s5.id @("CANCELADA") 90
Write-Host "Estado: $($e5.estado)  motivo=$($e5.motivo)   (esperado CANCELADA / TIMEOUT_INVENTARIO)"
docker compose start inventario | Out-Null
Write-Host "Inventario de vuelta: procesa la reserva atrasada, responde, y Préstamos pide liberarla..."
Start-Sleep -Seconds 25
$f = Estado $s5.id
Write-Host ("Estado final: {0}  |  {1}   (esperado: sigue CANCELADA y el stock intacto: disponible=2 reservado=0)" -f $f.estado, (Stock $p5)) -ForegroundColor Green
Write-Host "`nListo. Mira http://localhost:15672 (RabbitMQ) para ver las colas." -ForegroundColor Green
