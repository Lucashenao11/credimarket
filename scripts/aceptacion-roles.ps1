# Pruebas de aceptación de roles y aislamiento (prueba 13) con la API real.
# Uso: .\scripts\aceptacion-roles.ps1   (con docker compose up corriendo y ~15 s de espera tras arrancar)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$envv = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.*)$") { $envv[$Matches[1]] = $Matches[2] } }

$fallos = 0
function Login($u, $p) {
    (Invoke-RestMethod -Method Post -Uri "http://localhost:8002/auth/login" -ContentType "application/json" `
        -Body (@{ usuario = $u; password = $p } | ConvertTo-Json)).access_token
}
function Llamar($metodo, $url, $token, $cuerpo, $clave) {
    $h = @{}
    if ($token) { $h["Authorization"] = "Bearer $token" }
    if ($clave) { $h["Idempotency-Key"] = $clave }
    $args2 = @{ Method = $metodo; Uri = $url; Headers = $h; UseBasicParsing = $true }
    if ($cuerpo) { $args2["Body"] = ($cuerpo | ConvertTo-Json); $args2["ContentType"] = "application/json" }
    try { $r = Invoke-WebRequest @args2; return @{ codigo = [int]$r.StatusCode; cuerpo = $r.Content } }
    catch { return @{ codigo = [int]$_.Exception.Response.StatusCode; cuerpo = "" } }
}
function Verificar($nombre, $obtenido, $esperado) {
    if ($obtenido -eq $esperado) { Write-Host ("  OK   {0}: {1}" -f $nombre, $obtenido) -ForegroundColor Green }
    else { Write-Host ("  FALLO {0}: obtuvo {1}, esperaba {2}" -f $nombre, $obtenido, $esperado) -ForegroundColor Red; $script:fallos++ }
}

$admin = Login "admin" $envv["DEMO_ADMIN_PASSWORD"]
$ana   = Login "ana"   $envv["DEMO_CLIENTE_PASSWORD"]
$beto  = Login "beto"  $envv["DEMO_CLIENTE_PASSWORD"]
$P = "http://localhost:8003"
$solicitud = @{ producto_id = 1; cantidad = 1; plazo_meses = 12 }

Write-Host "`n== 13. Aislamiento entre clientes ==" -ForegroundColor Cyan
$r = Llamar "Post" "$P/prestamos" $ana $solicitud ([guid]::NewGuid().ToString())
Verificar "ana crea una solicitud (202 o 201)" ($(if ($r.codigo -in 201, 202) { "ok" } else { $r.codigo })) "ok"
$idAna = ($r.cuerpo | ConvertFrom-Json).id
Verificar "ana ve su solicitud" (Llamar "Get" "$P/prestamos/$idAna" $ana).codigo 200
Verificar "beto pide la solicitud de ana" (Llamar "Get" "$P/prestamos/$idAna" $beto).codigo 404
Verificar "beto pide el historial de ana" (Llamar "Get" "$P/prestamos/$idAna/historial" $beto).codigo 404
Verificar "beto intenta cancelar la de ana" (Llamar "Post" "$P/prestamos/$idAna/cancelar" $beto).codigo 404
$lista = (Llamar "Get" "$P/prestamos" $beto).cuerpo | ConvertFrom-Json
Verificar "la lista de beto no incluye la de ana" (@($lista | Where-Object { $_.id -eq $idAna }).Count) 0
Verificar "ana consulta el perfil de beto" (Llamar "Get" "http://localhost:8002/clientes/CLI-DEMO-0002" $ana).codigo 403

Write-Host "`n== Roles: operaciones solo de administrador ==" -ForegroundColor Cyan
Verificar "cliente entrega un préstamo" (Llamar "Post" "$P/prestamos/$idAna/entregar" $ana).codigo 403
Verificar "cliente consulta la info del modelo (permitido a autenticados)" (Llamar "Get" "$P/modelo/info" $ana).codigo 200
Verificar "cliente usa la predicción manual" (Llamar "Post" "$P/riesgo/predict" $ana @{}).codigo 403
Verificar "cliente ve existencias" (Llamar "Get" "http://localhost:8004/existencias" $ana).codigo 403
Verificar "cliente crea un producto" (Llamar "Post" "http://localhost:8001/productos" $ana @{ nombre = "x"; categoria = "x"; precio_cop = 1 }).codigo 403
Verificar "cliente lista todos los clientes" (Llamar "Get" "http://localhost:8002/clientes" $ana).codigo 403
Verificar "admin crea una solicitud (no es cliente)" (Llamar "Post" "$P/prestamos" $admin $solicitud ([guid]::NewGuid().ToString())).codigo 403
Verificar "admin ve existencias" (Llamar "Get" "http://localhost:8004/existencias" $admin).codigo 200

Write-Host "`n== Sin credenciales ==" -ForegroundColor Cyan
Verificar "préstamos sin token" (Llamar "Get" "$P/prestamos" $null).codigo 401
Verificar "inventario sin token" (Llamar "Get" "http://localhost:8004/existencias" $null).codigo 401
Verificar "token manipulado" (Llamar "Get" "$P/prestamos" ($ana + "x")).codigo 401

Write-Host ""
if ($fallos -eq 0) { Write-Host "Todas las comprobaciones pasaron." -ForegroundColor Green } else { Write-Host "$fallos comprobaciones fallaron." -ForegroundColor Red; exit 1 }
