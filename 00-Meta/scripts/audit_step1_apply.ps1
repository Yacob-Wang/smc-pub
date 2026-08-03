# audit_step1_apply.ps1
# smc-pub content audit step 1: bulk delete
# Uses Microsoft.VisualBasic.FileIO.FileSystem to send files to recycle bin.
# Equivalent to mavis-trash but bypasses node dependency.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
$OutputEncoding = [Console]::OutputEncoding

Add-Type -AssemblyName Microsoft.VisualBasic

$REPO_ROOT = 'C:\Users\deepLife\Documents\GitHub\smc-pub'
$LIST_MD = Join-Path $REPO_ROOT '00-Meta\audit-delete-list.md'

# Parse markdown list: - `path` (NNNN chars) -- A_xxx
$pattern = '^\-\s+`([^`]+)`\s+\(\d+\s+\S+\)\s+\u2014\s+([A-E])_'

$targets = @()
Get-Content -LiteralPath $LIST_MD -Encoding UTF8 | ForEach-Object {
    if ($_ -match $pattern) {
        $path = $matches[1]
        $cat = $matches[2]
        if ($cat -in @('A','B','D','E')) {
            $targets += [PSCustomObject]@{ Path = $path; Category = $cat }
        }
    }
}

Write-Host ('[INFO] parsed ' + $targets.Count + ' targets (A/B/D/E)')
Write-Host ''

# Validate existence
$missing = $targets | Where-Object { -not (Test-Path -LiteralPath (Join-Path $REPO_ROOT $_.Path)) }
if ($missing) {
    Write-Host '[ERROR] missing files:'
    $missing | ForEach-Object { Write-Host ('  - ' + $_.Path) }
    exit 1
}

# Execute deletion
$success = 0
$fail = 0
foreach ($t in $targets) {
    $fullPath = Join-Path $REPO_ROOT $t.Path
    try {
        if (Test-Path -LiteralPath $fullPath -PathType Container) {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
                $fullPath,
                'OnlyErrorDialogs',
                'SendToRecycleBin'
            )
        } else {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
                $fullPath,
                'OnlyErrorDialogs',
                'SendToRecycleBin'
            )
        }
        Write-Host ('  [OK]   [' + $t.Category + '] ' + $t.Path)
        $success++
    } catch {
        Write-Host ('  [FAIL] [' + $t.Category + '] ' + $t.Path + ': ' + $_.Exception.Message)
        $fail++
    }
}

Write-Host ''
Write-Host ('[DONE] success=' + $success + ' fail=' + $fail)

# Cleanup empty directories
Write-Host ''
Write-Host '[STEP] cleaning empty directories'
$dirsToCheck = @(
    '01-Mechanism\Kernel\DM\_archive',
    '_archive',
    '05-Governance\AI-Debug',
    '05-Governance\CrossPlatform',
    '05-Governance\LowEnd',
    '05-Governance\OEM-BSP',
    '05-Governance\PerfMem',
    '05-Governance\Security'
)
$cleaned = 0
foreach ($d in $dirsToCheck) {
    $full = Join-Path $REPO_ROOT $d
    if (Test-Path -LiteralPath $full -PathType Container) {
        $items = Get-ChildItem -LiteralPath $full -Force | Where-Object { -not $_.Name.StartsWith('.') }
        if (-not $items) {
            Remove-Item -LiteralPath $full -Recurse -Force
            Write-Host ('  [OK] cleaned: ' + $d)
            $cleaned++
        } else {
            Write-Host ('  [SKIP] not empty: ' + $d + ' (' + $items.Count + ' items)')
        }
    }
}
Write-Host ('[DONE] cleaned ' + $cleaned + ' empty directories')
