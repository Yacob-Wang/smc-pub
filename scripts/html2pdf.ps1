# html2pdf.ps1 - HTML to PDF converter using Microsoft Edge headless
#
# Usage:
#   .\html2pdf.ps1 -Html "resume.html"
#   .\html2pdf.ps1 -Html "resume.html" -Pdf "D:\output\resume.pdf"
#   .\html2pdf.ps1 -Html "resume.html" -PaperSize A4
#
# Notes:
#   - Requires Microsoft Edge (Chromium) installed at default location.
#   - Honors @page CSS rules from the HTML (size: A4 / margin etc.).
#   - Kills leftover msedge.exe before rendering to avoid file lock conflicts.
#   - Writes PDF to a unique temp file first, then moves to target (handles "file in use").
#   - Verifies page count by scanning /Type /Page markers in the output PDF.
#
# PowerShell 5.1 quirks:
#   - Param names use $Html / $Pdf (not $Input / $Output) because $Input is a
#     reserved pipeline enumerator.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Html,

    [Parameter(Position = 1)]
    [string]$Pdf,

    [Parameter(Position = 2)]
    [ValidateSet("A4", "Letter")]
    [string]$PaperSize = "A4"
)

$ErrorActionPreference = "Stop"

# ---------- 1. Validate input ----------
if (-not (Test-Path -Path $Html -PathType Leaf)) {
    Write-Error "Input HTML not found: $Html"
    exit 1
}
$Html = (Resolve-Path -Path $Html).Path

# ---------- 2. Default output path ----------
if (-not $Pdf) {
    $Pdf = [System.IO.Path]::ChangeExtension($Html, ".pdf")
} else {
    $Pdf = [System.IO.Path]::GetFullPath($Pdf)
}
$pdfDir = Split-Path -Path $Pdf
if (-not (Test-Path -Path $pdfDir)) {
    New-Item -ItemType Directory -Path $pdfDir -Force | Out-Null
}

# ---------- 3. Find Edge ----------
$edgePaths = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
)
$edge = $null
foreach ($p in $edgePaths) { if (Test-Path -Path $p) { $edge = $p; break } }
if (-not $edge) {
    Write-Error "Microsoft Edge (Chromium) not found. Install Edge or set the path manually."
    exit 1
}

# ---------- 4. Kill leftover msedge ----------
Get-Process msedge -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  killing leftover msedge PID=$($_.Id)"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 500

# ---------- 5. Temp user data dir (avoid cache) ----------
$userData = Join-Path -Path $env:TEMP -ChildPath ("html2pdf_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $userData -Force | Out-Null

# ---------- 6. Build file URI ----------
$htmlUri = "file:///" + ($Html -replace "\\", "/")

# ---------- 7. Render to temp PDF first (avoid file lock) ----------
$tempPdf = Join-Path -Path $env:TEMP -ChildPath ("html2pdf_" + [guid]::NewGuid().ToString("N").Substring(0, 8) + ".pdf")

Write-Host ""
Write-Host "html2pdf - rendering"
Write-Host "  html  : $Html"
Write-Host "  pdf   : $Pdf"
Write-Host "  paper : $PaperSize"
Write-Host "  engine: $edge"
Write-Host ""

$proc = Start-Process -FilePath $edge -ArgumentList @(
    "--headless=new",
    "--disable-gpu",
    "--no-pdf-header-footer",
    "--user-data-dir=$userData",
    "--print-to-pdf=$tempPdf",
    $htmlUri
) -Wait -PassThru -RedirectStandardError "$env:TEMP\html2pdf_err.log" -RedirectStandardOutput "$env:TEMP\html2pdf_out.log" *>&1 | Out-Null

Start-Sleep -Seconds 2

# ---------- 8. Verify + move ----------
if (-not (Test-Path -Path $tempPdf)) {
    Write-Error "PDF not generated. See $env:TEMP\html2pdf_err.log"
    if (Test-Path -Path "$env:TEMP\html2pdf_err.log") { Get-Content -Path "$env:TEMP\html2pdf_err.log" -Tail 10 }
    exit 1
}

# Move temp PDF to final destination (overwrites if target is not locked)
try {
    Move-Item -Path $tempPdf -Destination $Pdf -Force
} catch {
    # Fallback: write to a timestamped filename if target is locked
    $stamp = Get-Date -Format "HHmmss"
    $Pdf = [System.IO.Path]::GetDirectoryName($Pdf) + "\" + [System.IO.Path]::GetFileNameWithoutExtension($Pdf) + "_$stamp.pdf"
    Move-Item -Path $tempPdf -Destination $Pdf -Force
    Write-Warning "Target was locked, wrote to: $Pdf"
}

# ---------- 9. Report ----------
$f = Get-Item -Path $Pdf
$content = [System.IO.File]::ReadAllText($Pdf)
$pageCount = ([regex]::Matches($content, "/Type\s*/Page[^s]")).Count

Write-Host "OK  PDF generated"
Write-Host ("  path : {0}" -f $f.FullName)
Write-Host ("  size : {0:N0} bytes ({1:N1} KB)" -f $f.Length, ($f.Length / 1024))
Write-Host ("  pages: {0}" -f $pageCount)
Write-Host ""

# ---------- 10. Cleanup ----------
Remove-Item -Path $userData -Recurse -Force -ErrorAction SilentlyContinue

exit 0
