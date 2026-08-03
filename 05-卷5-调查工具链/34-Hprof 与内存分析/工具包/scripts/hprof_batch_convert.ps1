<#
.SYNOPSIS
    hprof 批量转换脚本(Windows PowerShell)

.DESCRIPTION
    把 Android binary hprof 批量转换为标准 Java HPROF

.PARAMETER InputPath
    输入路径(目录或文件,默认当前目录)

.EXAMPLE
    .\hprof_batch_convert.ps1
    .\hprof_batch_convert.ps1 -InputPath C:\Users\foo\hprof\
    .\hprof_batch_convert.ps1 -InputPath dump.hprof

.NOTES
    依赖:hprof-conv(Android SDK platform-tools)
    配套文档:Android_Framework_Layer/Hprof/02-hprof解析工具链.md §2.2
#>

[CmdletBinding()]
param(
    [string]$InputPath = ".",
    [string]$HprofConvPath = ""
)

# ====== 配置 ======
$OutputSuffix = "_converted"

# ====== 颜色输出 ======
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Error { param($msg) Write-Host $msg -ForegroundColor Red }
function Write-Warning { param($msg) Write-Host $msg -ForegroundColor Yellow }

# ====== 检查 hprof-conv ======
if (-not $HprofConvPath) {
    # 尝试默认路径
    $candidates = @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\hprof-conv.exe",
        "$env:ANDROID_HOME\platform-tools\hprof-conv.exe",
        "$env:ANDROID_SDK_ROOT\platform-tools\hprof-conv.exe"
    )
    
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $HprofConvPath = $candidate
            break
        }
    }
    
    if (-not $HprofConvPath) {
        # 从 PATH 中查找
        $hprofConvInPath = Get-Command hprof-conv -ErrorAction SilentlyContinue
        if ($hprofConvInPath) {
            $HprofConvPath = $hprofConvInPath.Source
        }
    }
}

if (-not $HprofConvPath -or -not (Test-Path $HprofConvPath)) {
    Write-Error "✗ hprof-conv 未找到"
    Write-Host "  请设置 -HprofConvPath 参数指向 hprof-conv.exe"
    Write-Host "  或把 hprof-conv 加入 PATH"
    Write-Host ""
    Write-Host "  默认路径:"
    Write-Host "    Windows: `$env:LOCALAPPDATA\Android\Sdk\platform-tools\hprof-conv.exe"
    Write-Host "    或设置 ANDROID_HOME / ANDROID_SDK_ROOT 环境变量"
    exit 1
}

# ====== 收集 hprof 文件 ======
$HprofFiles = @()

if (Test-Path $InputPath -PathType Container) {
    # 目录模式:递归查找
    $HprofFiles = Get-ChildItem -Path $InputPath -Filter "*.hprof" -Recurse -File
} elseif (Test-Path $InputPath -PathType Leaf) {
    # 单文件模式
    $HprofFiles = Get-Item $InputPath
} else {
    Write-Error "✗ 输入路径无效: $InputPath"
    exit 1
}

if ($HprofFiles.Count -eq 0) {
    Write-Warning "⚠ 未找到 .hprof 文件"
    exit 0
}

# ====== 批量转换 ======
$total = 0
$success = 0
$failed = 0

Write-Host "=== hprof 批量转换 ===" -ForegroundColor Green
Write-Host "工具路径: $HprofConvPath"
Write-Host "输入: $InputPath"
Write-Host ""

foreach ($inputFile in $HprofFiles) {
    $total++
    
    # 跳过已经是 _converted 的文件
    if ($inputFile.BaseName -like "*$OutputSuffix") {
        Write-Warning "⊘ 跳过(已转换): $($inputFile.Name)"
        continue
    }
    
    # 输出文件
    $outputFile = Join-Path $inputFile.DirectoryName "$($inputFile.BaseName)$OutputSuffix$($inputFile.Extension)"
    
    Write-Host -NoNewline "[$total] $($inputFile.Name) ... "
    
    # 执行转换
    $process = Start-Process -FilePath $HprofConvPath `
        -ArgumentList "`"$($inputFile.FullName)`"", "`"$outputFile`"" `
        -NoNewWindow -Wait -PassThru
    
    if ($process.ExitCode -eq 0 -and (Test-Path $outputFile)) {
        $inputSize = "{0:N1} MB" -f ($inputFile.Length / 1MB)
        $outputSize = "{0:N1} MB" -f ((Get-Item $outputFile).Length / 1MB)
        Write-Success "✓ 成功 ($inputSize → $outputSize)"
        $success++
    } else
        {
            Write-Error "✗ 失败"
            $failed++
        }
}

# ====== 汇总 ======
Write-Host ""
Write-Host "=== 汇总 ===" -ForegroundColor Green
Write-Host "总计: $total"
Write-Host "成功: $success"
Write-Host "失败: $failed"

if ($failed -gt 0) {
    Write-Host ""
    Write-Warning "⚠ 部分文件转换失败,常见原因:"
    Write-Host "  1. 文件损坏(重新 dump)"
    Write-Host "  2. hprof-conv 版本过旧(更新 Android SDK)"
    Write-Host "  3. ID size 不匹配(尝试用其他工具)"
    exit 1
}

exit 0