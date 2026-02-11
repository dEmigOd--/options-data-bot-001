# Quick check: is TWS/IB Gateway listening on the API port?
# Run with: .\scripts\check_tws_port.ps1
# Or: .\scripts\check_tws_port.ps1 -Port 7496

param([int]$Port = 7497)

$hostName = "127.0.0.1"
Write-Host "1. Checking if anything is LISTENING on ${hostName}:$Port..." -ForegroundColor Cyan
$listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listeners) {
    Write-Host "   OK: Port $Port is in use (TWS/IBG may be listening)." -ForegroundColor Green
} else {
    Write-Host "   No listener on $Port. Is TWS running with API enabled on this port?" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "2. Testing TCP connect to ${hostName}:$Port..." -ForegroundColor Cyan
try {
    $result = Test-NetConnection -ComputerName $hostName -Port $Port -WarningAction SilentlyContinue
    if ($result.TcpTestSucceeded) {
        Write-Host "   OK: Connection succeeded. Firewall is not blocking." -ForegroundColor Green
    } else {
        Write-Host "   Failed: TcpTestSucceeded = $($result.TcpTestSucceeded)" -ForegroundColor Red
    }
} catch {
    Write-Host "   Error: $_" -ForegroundColor Red
    Write-Host "   (Connection refused usually means nothing is listening, not firewall on localhost.)" -ForegroundColor Gray
}
