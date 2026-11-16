# Demostración de Inventario: última unidad con peticiones simultáneas (prueba 4),
# mensaje repetido (prueba 5), liberación repetida (prueba 7) y vencimiento.
# Uso: .\scripts\demo-inventario.ps1   (con docker compose up corriendo)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$inv = "http://localhost:8004"

$envv = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.*)$") { $envv[$Matches[1]] = $Matches[2] } }
$body = @{ usuario = "admin"; password = $envv["DEMO_ADMIN_PASSWORD"] } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "http://localhost:8002/auth/login" -ContentType "application/json" -Body $body).access_token
$H = @{ Authorization = "Bearer $token" }

function Reservar($prestamo, $producto, $cantidad) {
    $b = @{ prestamo_id = $prestamo; producto_id = $producto; cantidad = $cantidad } | ConvertTo-Json
    (Invoke-RestMethod -Method Post -Uri "$inv/pruebas/reservas" -Headers $H -ContentType "application/json" -Body $b).resultado
}
function Stock($producto) {
    $e = Invoke-RestMethod -Uri "$inv/existencias/$producto" -Headers $H
    "disponible=$($e.disponible) reservado=$($e.reservado)"
}

# Un producto nuevo para cada ejecución, con exactamente 1 unidad
$producto = Get-Random -Minimum 1000 -Maximum 999999
$sufijo = Get-Random
Invoke-RestMethod -Method Post -Uri "$inv/existencias/$producto/entradas" -Headers $H -ContentType "application/json" -Body '{"cantidad": 1}' | Out-Null
Write-Host "`nProducto $producto creado con 1 unidad: $(Stock $producto)" -ForegroundColor Cyan

Write-Host "`n== Prueba 4: 10 préstamos piden la última unidad AL MISMO TIEMPO ==" -ForegroundColor Cyan
$inicio = (Get-Date).AddSeconds(4)   # todos los procesos esperan este instante y disparan juntos
$jobs = 1..10 | ForEach-Object {
    Start-Job -ArgumentList $_, $inicio, $inv, $token, $producto, $sufijo -ScriptBlock {
        param($n, $inicio, $inv, $token, $producto, $sufijo)
        while ((Get-Date) -lt $inicio) { Start-Sleep -Milliseconds 5 }
        $b = @{ prestamo_id = "CONC-$sufijo-$n"; producto_id = $producto; cantidad = 1 } | ConvertTo-Json
        $r = Invoke-RestMethod -Method Post -Uri "$inv/pruebas/reservas" -ContentType "application/json" `
             -Headers @{ Authorization = "Bearer $token" } -Body $b
        "$($r.prestamo_id) -> $($r.resultado)"
    }
}
$resultados = $jobs | Wait-Job | Receive-Job
$jobs | Remove-Job
$resultados | Sort-Object | ForEach-Object { Write-Host "   $_" }
$ganadores = @($resultados | Where-Object { $_ -match "RESERVADA" })
Write-Host ("Reservadas: {0} (esperado: 1)   |   {1}" -f $ganadores.Count, (Stock $producto)) -ForegroundColor Green

$ganador = ($ganadores[0] -split " ")[0]
Write-Host "`n== Prueba 5: el mismo mensaje de reserva llega otra vez ==" -ForegroundColor Cyan
Write-Host ("Reservar de nuevo $ganador -> {0}  (esperado YA_PROCESADA)   |   {1}" -f (Reservar $ganador $producto 1), (Stock $producto))

Write-Host "`n== Prueba 7: la cancelación llega dos veces ==" -ForegroundColor Cyan
foreach ($i in 1, 2) {
    $r = (Invoke-RestMethod -Method Post -Uri "$inv/pruebas/reservas/$ganador/liberar" -Headers $H).resultado
    Write-Host ("Liberar intento {0} -> {1}   |   {2}" -f $i, $r, (Stock $producto))
}
Write-Host "(Esperado: LIBERADA y luego YA_FINALIZADA; la unidad vuelve una sola vez)"

Write-Host "`n== Vencimiento ==" -ForegroundColor Cyan
$p = "VENCE-$sufijo"
Write-Host "Reservar $p -> $(Reservar $p $producto 1)   |   $(Stock $producto)"
$ttl = [int]$envv["RESERVA_TTL_SEGUNDOS"]
Write-Host "Esperando $($ttl + 15) segundos a que venza (RESERVA_TTL_SEGUNDOS=$ttl)..."
Start-Sleep -Seconds ($ttl + 15)
$todas = Invoke-RestMethod -Uri "$inv/reservas" -Headers $H
$estado = ($todas | Where-Object { $_.prestamo_id -eq $p }).estado
Write-Host "Estado de la reserva: $estado (esperado VENCIDA)   |   $(Stock $producto)" -ForegroundColor Green