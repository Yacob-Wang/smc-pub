[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Input,
    [Parameter(Position = 1)]
    [string]$Output,
    [Parameter(Position = 2)]
    [ValidateSet("A4", "Letter")]
    [string]$PaperSize = "A4"
)

$ErrorActionPreference = "Stop"
try {
    Write-Output "step 1: validate input"
    if (-not (Test-Path $Input -PathType Leaf)) { Write-Error "not found"; exit 1 }
    $Input = (Resolve-Path $Input).Path
    Write-Output "  input = $Input"

    Write-Output "step 2: default output"
    if (-not $Output) { $Output = [System.IO.Path]::ChangeExtension($Input, ".pdf") }
    else { $Output = [System.IO.Path]::GetFullPath($Output) }
    $outputDir = Split-Path $Output
    if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }
    Write-Output "  output = $Output"

    Write-Output "step 3: find edge"
    $edgePaths = @(
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )
    $edge = $null
    foreach ($p in $edgePaths) { if (Test-Path $p) { $edge = $p; break } }
    Write-Output "  edge = $edge"

    Write-Output "step 4: kill msedge"
    Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500

    Write-Output "step 5: temp userdata"
    $userData = Join-Path $env:TEMP ("html2pdf_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Path $userData -Force | Out-Null
    Write-Output "  userdata = $userData"

    Write-Output "step 6: file URI"
    $htmlUri = "file:///" + ($Input -replace "\\", "/")
    Write-Output "  uri = $htmlUri"

    Write-Output "step 7: render"
    $tempPdf = Join-Path $env:TEMP ("html2pdf_" + [guid]::NewGuid().ToString("N").Substring(0, 8) + ".pdf")
    $proc = Start-Process -FilePath $edge -ArgumentList @(
        "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--user-data-dir=$userData", "--print-to-pdf=$tempPdf", $htmlUri
    ) -Wait -PassThru -RedirectStandardError "$env:TEMP\html2pdf_err.log" -RedirectStandardOutput "$env:TEMP\html2pdf_out.log" *>&1 | Out-Null
    Start-Sleep -Seconds 2
    Write-Output "  temppdf exists = $(Test-Path $tempPdf)"

    Write-Output "step 8: move"
    try {
        Move-Item -Path $tempPdf -Destination $Output -Force
        Write-Output "  moved ok"
    } catch {
        Write-Output "  move failed: $($_.Exception.Message)"
        throw
    }

    Write-Output "step 9: report"
    $f = Get-Item $Output
    $content = [System.IO.File]::ReadAllText($Output)
    $pageCount = ([regex]::Matches($content, "/Type\s*/Page[^s]")).Count
    Write-Output "  pages = $pageCount, size = $($f.Length)"

    Write-Output "step 10: cleanup"
    Remove-Item -Recurse -Force $userData -ErrorAction SilentlyContinue
    Write-Output "  cleanup done"
    Write-Output "DONE"
} catch {
    Write-Output "CAUGHT at step: $($_.Exception.Message)"
    Write-Output $_.ScriptStackTrace
    exit 1
}
