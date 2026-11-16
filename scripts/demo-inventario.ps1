# Demostración de Inventario POR EL BROKER: última unidad con mensajes simultáneos (prueba 4),
# mensaje repetido (prueba 5), liberación repetida (prueba 7) y vencimiento.
# Los comandos se publican en RabbitMQ (API de administración), igual que lo hace Préstamos.
# Uso: .\scripts\demo-inventario.ps1   (con docker compose up corriendo)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$inv = "http://localhost:8004"

$envv = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.*)$") { $envv[$Matches[1]] = $Matches[2] } }
$b = @{ usuario = "admin"; password = $envv["DEMO_ADMIN_PASSWORD"] } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "http://localhost:8002/auth/login" -ContentType "application/json" -Body $b).access_token
$H = @{ Authorization = "Bearer $token" }
$mq = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($envv['RABBITMQ_USER']):$($envv['RABBITMQ_PASSWORD'])"))

function Publicar($ruta, $tipo, $messageId, $payload) {
    $cuerpo = @{ message_id = $messageId; tipo = $tipo; payload = $payload } | ConvertTo-Json -Compress
    $b = @{ properties = @{ delivery_mode = 2; message_id = $messageId; type = $tipo; content_type = "application/json"; headers = @{ "x-reintentos" = 0 } }
            routing_key = $ruta; payload = $cuerpo; payload_encoding = "string" } | ConvertTo-Json -Depth 5
    $r = Invoke-RestMethod -Method Post -Uri "http://localhost:15672/api/exchanges/%2F/credimarket/publish" `
         -Headers @{ Authorization = $mq } -ContentType "application/json" -Body $b
    if (-not $r.routed) { throw "RabbitMQ no enrutó el mensaje $tipo" }
}
function Reservar($mid, $prestamo, $producto, $cantidad) { Publicar "reserva.solicitada" "ReservaSolicitada" $mid @{ prestamo_id = $prestamo; producto_id = $producto; cantidad = $cantidad } }
function Liberar($mid, $prestamo) { Publicar "reserva.liberar" "LiberarReserva" $mid @{ prestamo_id = $prestamo; motivo = "DEMO" } }
function Stock($producto) { $e = Invoke-RestMethod -Uri "$inv/existencias/$producto" -Headers $H; "disponible=$($e.disponible) reservado=$($e.reservado)" }
function Reservas($prefijo) { @(Invoke-RestMethod -Uri "$inv/reservas?limit=500" -Headers $H | Where-Object { $_.prestamo_id -like "$prefijo*" }) }

$producto = Get-Random -Minimum 1000 -Maximum 999999
$sufijo = Get-Random
Invoke-RestMethod -Method Post -Uri "$inv/existencias/$producto/entradas" -Headers $H -ContentType "application/json" -Body '{"cantidad": 1}' | Out-Null
Write-Host "`nProducto $producto creado con 1 unidad: $(Stock $producto)" -ForegroundColor Cyan

Write-Host "`n== Prueba 4: 10 préstamos piden la última unidad AL MISMO TIEMPO ==" -ForegroundColor Cyan
$inicio = (Get-Date).AddSeconds(4)
$jobs = 1..10 | ForEach-Object {
    Start-Job -ArgumentList $_, $inicio, $producto, $sufijo, $mq -ScriptBlock {
        param($n, $inicio, $producto, $sufijo, $mq)
        while ((Get-Date) -lt $inicio) { Start-Sleep -Milliseconds 5 }
        $cuerpo = @{ message_id = "conc-$sufijo-$n"; tipo = "ReservaSolicitada"; payload = @{ prestamo_id = "CONC-$sufijo-$n"; producto_id = $producto; cantidad = 1 } } | ConvertTo-Json -Compress
        $b = @{ properties = @{ delivery_mode = 2; message_id = "conc-$sufijo-$n"; type = "ReservaSolicitada"; content_type = "application/json"; headers = @{ "x-reintentos" = 0 } }
                routing_key = "reserva.solicitada"; payload = $cuerpo; payload_encoding = "string" } | ConvertTo-Json -Depth 5
        (Invoke-RestMethod -Method Post -Uri "http://localhost:15672/api/exchanges/%2F/credimarket/publish" -Headers @{ Authorization = $mq } -ContentType "application/json" -Body $b).routed
    }
}
$jobs | Wait-Job | Out-Null; $jobs | Remove-Job
Start-Sleep -Seconds 6
$res = Reservas "CONC-$sufijo"
Write-Host ("Reservas creadas: {0} (esperado: 1)   |   {1}" -f $res.Count, (Stock $producto)) -ForegroundColor Green

$ganador = $res[0].prestamo_id
Write-Host "`n== Prueba 5: el MISMO mensaje de reserva llega 3 veces ==" -ForegroundColor Cyan
Invoke-RestMethod -Method Post -Uri "$inv/existencias/$producto/entradas" -Headers $H -ContentType "application/json" -Body '{"cantidad": 4}' | Out-Null
1..3 | ForEach-Object { Reservar "rep-$sufijo" "REP-$sufijo" $producto 1 }
Start-Sleep -Seconds 5
Write-Host ("Reservas de REP-{0}: {1} (esperado 1)   |   {2}   (esperado: reservado=2)" -f $sufijo, (Reservas "REP-$sufijo").Count, (Stock $producto)) -ForegroundColor Green

Write-Host "`n== Prueba 7: la cancelación llega dos veces ==" -ForegroundColor Cyan
Liberar "lib-$sufijo-1" $ganador; Liberar "lib-$sufijo-2" $ganador
Start-Sleep -Seconds 5
Write-Host ("Después de dos liberaciones: {0}   (esperado: reservado=1, la unidad vuelve una sola vez)" -f (Stock $producto))

Write-Host "`n== Vencimiento ==" -ForegroundColor Cyan
$p = "VENCE-$sufijo"
Reservar "venc-$sufijo" $p $producto 1
Start-Sleep -Seconds 4
Write-Host "Reserva $p creada   |   $(Stock $producto)"
$ttl = [int]$envv["RESERVA_TTL_SEGUNDOS"]
Write-Host "Esperando $($ttl + 15) segundos a que venza (RESERVA_TTL_SEGUNDOS=$ttl)..."
Start-Sleep -Seconds ($ttl + 15)
$estado = (Reservas $p)[0].estado
Write-Host "Estado de la reserva: $estado (esperado VENCIDA)   |   $(Stock $producto)" -ForegroundColor Green
