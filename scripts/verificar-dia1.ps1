# Verifica el cierre del Día 1: los 4 /health responden y las bases están aisladas.
# Uso: .\scripts\verificar-dia1.ps1  (con docker compose up corriendo)
$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

Write-Host "`n== /health de los 4 servicios ==" -ForegroundColor Cyan
$servicios = @{ productos = 8001; clientes = 8002; prestamos = 8003; inventario = 8004 }
foreach ($s in $servicios.GetEnumerator() | Sort-Object Value) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:$($s.Value)/health" -TimeoutSec 5
        Write-Host ("{0,-11} status={1} database={2}" -f $s.Key, $r.status, $r.database) -ForegroundColor Green
    } catch {
        Write-Host ("{0,-11} NO RESPONDE: {1}" -f $s.Key, $_.Exception.Message) -ForegroundColor Red
    }
}

Write-Host "`n== Aislamiento: el usuario de prestamos intenta entrar a la base de inventario ==" -ForegroundColor Cyan
$env_vars = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.*)$") { $env_vars[$Matches[1]] = $Matches[2] } }
$pw = $env_vars["PRESTAMOS_DB_PASSWORD"]
docker compose exec -T postgres psql "postgresql://prestamos:$pw@localhost:5432/inventario" -c "SELECT 1;" 2>&1 | Write-Host
Write-Host "(Lo esperado: 'permission denied for database inventario')" -ForegroundColor Yellow

Write-Host "`n== Interfaces de infraestructura ==" -ForegroundColor Cyan
foreach ($url in @("http://localhost:15672", "http://localhost:5000")) {
    try {
        $code = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5).StatusCode
        Write-Host "$url -> $code" -ForegroundColor Green
    } catch {
        Write-Host "$url -> NO RESPONDE" -ForegroundColor Red
    }
}
