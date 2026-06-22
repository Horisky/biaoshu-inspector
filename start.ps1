# 启动标书规范性检测独立服务
# 用法：右键“使用 PowerShell 运行”，或在本目录执行 .\start.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 优先使用主项目同款 conda 环境（依赖已齐）；否则回退系统 python
$python = "C:\Users\tiany\anaconda3\envs\bidgen\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "使用 Python: $python" -ForegroundColor Cyan
Write-Host "启动中 → http://localhost:8100" -ForegroundColor Green
& $python server.py
