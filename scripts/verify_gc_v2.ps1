# GC v2 升级终态验证脚本
$root = "C:\Users\deepLife\Documents\GitHub\smc-pub\01-Mechanism\Runtime\ART\03-GC系统"
$subdirs = @("01-基础理论", "02-Heap与分配器", "03-CMS-GC", "04-CC-GC", "05-Generational-CC", "06-Reference与Finalizer", "07-GC调度与触发", "08-GC与其他子系统", "09-GC诊断与治理")

Write-Output "==== GC v2 升级终态验证 ===="
Write-Output "目标根目录: $root"
Write-Output ""

$totalCount = 0
$totalSize = 0
$v1Mark = 0
$v2Upgrade = 0
$noV2Mark = 0
$no618 = 0
$noAppendix = 0
$noDecisionLog = 0

foreach ($sub in $subdirs) {
    $subPath = Join-Path $root $sub
    if (-not (Test-Path $subPath)) {
        Write-Output "[!] 目录不存在: $subPath"
        continue
    }
    $files = Get-ChildItem -Path $subPath -Recurse -Filter "*.md" | Where-Object { $_.FullName -notlike "*\appendix\*" -and $_.Name -ne "README.md" }
    $subCount = $files.Count
    $subSize = ($files | Measure-Object -Property Length -Sum).Sum
    $totalCount += $subCount
    $totalSize += $subSize

    $subV1Mark = 0
    $subV2Upgrade = 0
    foreach ($f in $files) {
        $content = Get-Content $f.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
        $allText = $content -join "`n"
        if ($allText -match "v1\s*旧稿标记") { $subV1Mark++ }
        if ($allText -match "v2\s*升级") { $subV2Upgrade++ }
    }

    $sizeKB = [math]::Round($subSize / 1KB, 1)
    Write-Output "$sub -> $subCount 篇 / $sizeKB KB  (v1旧稿标记=$subV1Mark  v2升级=$subV2Upgrade)"
    $v1Mark += $subV1Mark
    $v2Upgrade += $subV2Upgrade
}

Write-Output ""
Write-Output "==== 汇总 ===="
$totalSizeKB = [math]::Round($totalSize / 1KB, 1)
$totalSizeMB = [math]::Round($totalSize / 1MB, 2)
Write-Output "GC 系列总文件数: $totalCount 篇 (期望 99)"
Write-Output "GC 系列总大小: $totalSizeKB KB / $totalSizeMB MB"
Write-Output "v1 旧稿标记段残留: $v1Mark 篇 (期望 0)"
Write-Output "v2 升级标识: $v2Upgrade 篇 (期望 99)"
