<#
.SYNOPSIS
  批量修复系列详情页顶部 blockquote：把"连续多 strong 无空 > 分隔" 改成"每行间插入 > 空行"
  只动第一个 blockquote；其他 blockquote 不碰

.EXAMPLE
  pwsh -File scripts/fix_quote_separator.ps1           # dry run
  pwsh -File scripts/fix_quote_separator.ps1 -Do       # 实际写入
#>
[CmdletBinding()]
param(
    [switch]$Do
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot | Split-Path -Parent
$excludeParts = @("node_modules", ".git", ".tmp", "reader", "scripts", ".idea", "docs")

function Test-Excluded {
    param([string]$Path, [string[]]$Excludes)
    $rel = Resolve-Path -Path $Path -Relative
    foreach ($p in $rel.Split([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)) {
        if ($Excludes -contains $p) { return $true }
    }
    return $false
}

function Test-QuoteLine {
    param([string]$Line)
    return $Line -match '^\s*>'
}

function Test-EmptyQuoteLine {
    param([string]$Line)
    return $Line -match '^\s*>\s*$'
}

function Test-StrongQuoteLine {
    param([string]$Line)
    return $Line -match '^\s*>\s*\*\*'
}

function Find-FirstBlockquote {
    param([string[]]$Lines)
    $start = -1
    for ($i = 0; $i -lt $Lines.Length; $i++) {
        if (Test-QuoteLine -Line $Lines[$i]) { $start = $i; break }
    }
    if ($start -lt 0) { return $null }
    $end = $start
    for ($i = $start; $i -lt $Lines.Length; $i++) {
        if (Test-QuoteLine -Line $Lines[$i]) { $end = $i + 1 } else { break }
    }
    return @{ Start = $start; End = $end }
}

function Fix-FirstBlockquote {
    param([string]$Text)
    # 探测行尾
    $sep = "`n"
    if ($Text.Contains("`r`n")) { $sep = "`r`n" }
    $lines = $Text -split "`r?`n"
    $rng = Find-FirstBlockquote -Lines $lines
    if ($null -eq $rng) { return $null }
    $s = $rng.Start; $e = $rng.End
    $block = $lines[$s..($e - 1)]
    $strongCount = 0; $emptyCount = 0
    foreach ($ln in $block) {
        if (Test-StrongQuoteLine -Line $ln) { $strongCount++ }
        elseif (Test-EmptyQuoteLine -Line $ln) { $emptyCount++ }
    }
    if ($strongCount -lt 2 -or $emptyCount -gt 0) { return $null }
    $newBlock = @()
    for ($i = 0; $i -lt $block.Length; $i++) {
        $newBlock += $block[$i]
        if ($i -lt $block.Length - 1) { $newBlock += ">" }
    }
    $newLines = @()
    if ($s -gt 0) { $newLines += $lines[0..($s - 1)] }
    $newLines += $newBlock
    if ($e -lt $lines.Length) { $newLines += $lines[$e..($lines.Length - 1)] }
    $joined = $newLines -join $sep
    if ($Text.EndsWith("`n")) { $joined += $sep }
    return $joined
}

$files = Get-ChildItem -Path $root -Recurse -Filter "*.md" -ErrorAction SilentlyContinue |
    Where-Object { -not (Test-Excluded -Path $_.FullName -Excludes $excludeParts) }
Write-Host "Scanning $($files.Count) md files..."
$fixed = @()
foreach ($f in $files) {
    try {
        $text = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
    } catch {
        Write-Host "  read fail: $($f.FullName): $_"
        continue
    }
    $newText = Fix-FirstBlockquote -Text $text
    if ($null -eq $newText) { continue }
    if ($Do) {
        [System.IO.File]::WriteAllText($f.FullName, $newText, [System.Text.Encoding]::UTF8)
    }
    $fixed += $f.FullName.Substring($root.Length + 1)
}
Write-Host "Would fix $($fixed.Count) files:"
$fixed | Select-Object -First 30 | ForEach-Object { Write-Host "  $_" }
if ($fixed.Count -gt 30) { Write-Host "  ... and $($fixed.Count - 30) more" }
if (-not $Do) { Write-Host "`nDry run. Use -Do to actually write." }
