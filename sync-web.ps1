# 一键：卷内正文 → docs/ → 本地 MkDocs 预览
# 用法：
#   双击 同步到Web.cmd
#   或: powershell -ExecutionPolicy Bypass -File .\sync-web.ps1
#   仅同步不启动服务: powershell -ExecutionPolicy Bypass -File .\sync-web.ps1 -NoServe
param(
    [switch]$NoServe,
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

function Find-Python {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.12") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )
    foreach ($c in $candidates) {
        try {
            $null = & $c.Exe (@($c.Args) + @("-c", "import sys; print(sys.version_info[:2])")) 2>$null
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch {}
    }
    throw "未找到 Python。请安装 Python 3.12+，或确保 py launcher 可用。"
}

function Test-PortOpen([string]$h, [int]$p) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect($h, $p, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(400)
        $connected = $ok -and $c.Connected
        $c.Close()
        return $connected
    } catch {
        return $false
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 稳知库 · 同步正文到本地 Web" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "仓库: $Root"
Write-Host ""

$py = Find-Python
$pyLabel = (@($py.Exe) + $py.Args) -join " "
Write-Host "[1/3] Python: $pyLabel" -ForegroundColor Green

Write-Host "[2/3] prepare_web_docs.py → 生成 docs/ ..." -ForegroundColor Green
$env:PYTHONUNBUFFERED = "1"
& $py.Exe (@($py.Args) + @("-u", "00-Meta/scripts/prepare_web_docs.py"))
if ($LASTEXITCODE -ne 0) {
    throw "prepare_web_docs.py 失败 (exit $LASTEXITCODE)"
}

$url = "http://${BindHost}:${Port}/smc-pub/"
Write-Host ""
Write-Host "同步完成。站点根: $url" -ForegroundColor Green

if ($NoServe) {
    Write-Host "已按 -NoServe 跳过 mkdocs serve。"
    exit 0
}

Write-Host "[3/3] 启动 / 复用 mkdocs serve ..." -ForegroundColor Green
if (Test-PortOpen $BindHost $Port) {
    Write-Host "端口 $Port 已有服务在跑——新文章已写入 docs/，浏览器刷新即可。" -ForegroundColor Yellow
} else {
    Write-Host "正在后台启动: mkdocs serve -a ${BindHost}:${Port}"
    $serveArgs = @($py.Args) + @("-m", "mkdocs", "serve", "-a", "${BindHost}:${Port}")
    Start-Process -FilePath $py.Exe -ArgumentList $serveArgs -WorkingDirectory $Root -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen $BindHost $Port) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-PortOpen $BindHost $Port)) {
        Write-Host "警告: 未检测到 $Port 监听。可先安装依赖:" -ForegroundColor Yellow
        Write-Host "  pip install -r 00-Meta/scripts/requirements-docs.txt"
    }
}

try { Start-Process $url } catch {}
Write-Host ""
Write-Host "完成。浏览器应已打开；若没有，请手动访问:" -ForegroundColor Cyan
Write-Host "  $url"
Write-Host ""
