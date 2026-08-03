# cleanup-temp.ps1
# Clean up temporary files from audit step 1
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName Microsoft.VisualBasic

$REPO_ROOT = 'C:\Users\deepLife\Documents\GitHub\smc-pub'
$files = @(
    '00-Meta\audit-delete-list.md',
    '00-Meta\scripts\test-trash.txt',
    '00-Meta\scripts\audit_step1_apply.py'
)
foreach ($f in $files) {
    $full = Join-Path $REPO_ROOT $f
    if (Test-Path -LiteralPath $full) {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
            $full, 'OnlyErrorDialogs', 'SendToRecycleBin'
        )
        Write-Host ('  [OK] deleted: ' + $f)
    } else {
        Write-Host ('  [SKIP] not found: ' + $f)
    }
}
Write-Host '[DONE]'
