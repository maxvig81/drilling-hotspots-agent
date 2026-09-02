# Starts the Drilling Hotspots Agent MCP server and exposes it via a dev tunnel.
# Run this whenever you want to use the declarative agent in Microsoft 365 Copilot.
#
#   pwsh -File run.ps1
#
# Leave this window open while testing the agent. Ctrl+C stops the tunnel;
# the server process is stopped automatically on exit.
#
# Prerequisite (one-time): create the persistent tunnel and its port, e.g.
#   devtunnel create wells-mcp
#   devtunnel port create wells-mcp -p 8000
#   devtunnel access create wells-mcp -p 8000 --anonymous
# Then read the public URL from `devtunnel show wells-mcp` and put
# "<host>-8000.<cluster>.devtunnels.ms/mcp/" into agent/appPackage/wells-plugin.json.

param(
    [string]$Tunnel = "wells-mcp",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. Start the MCP server (dual-stack loopback).
$env:PORT = "$Port"
$server = Start-Process -FilePath "python" -ArgumentList "server.py" `
    -WorkingDirectory $PSScriptRoot -PassThru
Write-Host "MCP server started (PID $($server.Id)) on http://localhost:$Port"
Start-Sleep -Seconds 3

try {
    # 2. Host the dev tunnel (foreground).
    devtunnel host $Tunnel
}
finally {
    if (-not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
        Write-Host "MCP server stopped."
    }
}
