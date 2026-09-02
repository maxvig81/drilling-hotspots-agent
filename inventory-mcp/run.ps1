# Starts the parts-inventory MCP server and exposes it via a dev tunnel.
#   pwsh -File run.ps1
param(
    [string]$Tunnel = "parts-mcp",
    [int]$Port = 8011
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PORT = "$Port"
$server = Start-Process -FilePath "python" -ArgumentList "server.py" `
    -WorkingDirectory $PSScriptRoot -PassThru
Write-Host "Parts MCP server started (PID $($server.Id)) on http://localhost:$Port"
Start-Sleep -Seconds 3
try {
    devtunnel host $Tunnel
}
finally {
    if (-not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
        Write-Host "Parts MCP server stopped."
    }
}
