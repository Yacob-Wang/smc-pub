# pack-content.ps1 — Pack Markdown content for StabilityMatrix Reader APK
# Output: reader/app/src/main/assets/{articles/, catalog.json, link-map.json, articles.db}

param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputDir = (Join-Path $PSScriptRoot "..\reader\app\src\main\assets")
)

$ErrorActionPreference = "Stop"

# 与 scripts/content_policy.py 对齐（唯一真相源）
$PolicyJsonText = & py -3.12 (Join-Path $PSScriptRoot "content_policy.py") --dump-json
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($PolicyJsonText)) {
    throw "Failed to load content_policy.py — Reader pack refuses to run without policy."
}
$ContentPolicy = $PolicyJsonText | ConvertFrom-Json
$ModuleDirs = @($ContentPolicy.public_modules)
$RootFiles = @($ContentPolicy.public_root_files)
if ($RootFiles -notcontains "README.md") {
    $RootFiles = @("README.md") + $RootFiles
}
$MetaNameRegexes = @($ContentPolicy.meta_name_regexes)
$ExcludePrefixes = @($ContentPolicy.exclude_path_prefixes)
$PrivateRootNames = @($ContentPolicy.private_root_names)

# PowerShell ConvertTo-Json unwraps single-element arrays into objects.
# Unary comma forces JSON array output for Kotlin kotlinx.serialization.
function Ensure-JsonArray {
    param([object]$Value)
    if ($null -eq $Value) { return ,@() }
    return ,@($Value)
}

function Test-ExcludedPath {
    param([string]$RelativePath)
    $p = $RelativePath -replace '\\', '/'
    if ($PrivateRootNames -contains $p) { return $true }
    foreach ($prefix in $ExcludePrefixes) {
        $root = $prefix.TrimEnd('/')
        if ($p -eq $root -or $p.StartsWith($prefix)) { return $true }
    }
    # 兼容旧路径名（已迁入 _archive，仍可能残留）
    if ($p -match '^ai_arch/') { return $true }
    if ($p -match '\.bak\.md$') { return $true }
    $name = [IO.Path]::GetFileName($p)
    foreach ($rx in $MetaNameRegexes) {
        if ($name -match $rx) { return $true }
    }
    return $false
}

function Get-ArticleId {
    param([string]$RelativePath)
    $id = $RelativePath -replace '\\', '/'
    if ($id -match '\.md$') { $id = $id -replace '\.md$', '' }
    return $id
}

function Get-TitleFromMarkdown {
    param([string]$Content, [string]$Fallback)
    foreach ($line in ($Content -split "`n")) {
        if ($line -match '^\s*#\s+(.+)$') {
            return $Matches[1].Trim()
        }
    }
    $name = [System.IO.Path]::GetFileNameWithoutExtension($Fallback)
    if ($name -match '^\d+-(.+)$') { return $Matches[1] }
    return $name
}

function Resolve-MdLink {
    param([string]$FromArticleId, [string]$LinkTarget)
    if ([string]::IsNullOrWhiteSpace($LinkTarget)) { return $null }
    if ($LinkTarget -match '^https?://') { return $null }
    if ($LinkTarget -match '^#') { return $null }
    $target = $LinkTarget -replace '\\', '/'
    if ($target -notmatch '\.md$') {
        if ($target.EndsWith('/')) { $target = $target + "README.md" }
        else { $target = $target + ".md" }
    }
    $fromDir = Split-Path $FromArticleId -Parent
    $combined = if ($target.StartsWith('/')) { $target.TrimStart('/') } else {
        $parts = @()
        if ($fromDir) { $parts += ($fromDir -split '/') }
        foreach ($seg in ($target -split '/')) {
            if ($seg -eq '..') { if ($parts.Count -gt 0) { $parts = $parts[0..($parts.Count - 2)] } }
            elseif ($seg -ne '.' -and $seg -ne '') { $parts += $seg }
        }
        $parts -join '/'
    }
    return Get-ArticleId $combined
}

function Resolve-ArticleInSeries {
    param(
        [string]$SeriesDir,
        [string]$FileName,
        [hashtable]$ArticleMeta,
        [string]$RepoRootPath
    )
    $exactId = Get-ArticleId "$SeriesDir/$FileName"
    if ($ArticleMeta.ContainsKey($exactId)) { return $exactId }

    if ($FileName -match '^(\d{2})-') {
        $numPrefix = $Matches[1]
        $dirPath = Join-Path $RepoRootPath ($SeriesDir -replace '/', [IO.Path]::DirectorySeparatorChar)
        if (Test-Path $dirPath) {
            $matchFile = Get-ChildItem -Path $dirPath -Filter "$numPrefix-*.md" -File | Select-Object -First 1
            if ($matchFile) {
                $rel = $matchFile.FullName.Substring($RepoRootPath.Length).TrimStart('\', '/')
                $id = Get-ArticleId $rel
                if ($ArticleMeta.ContainsKey($id)) { return $id }
            }
        }
    }
    return $null
}

function Parse-SeriesReadmeTable {
    param([string]$Content, [string]$SeriesDir)
    $articles = @()
    $order = 0
    foreach ($line in ($Content -split "`n")) {
        if ($line -match '^\|\s*\[(\d+)\]\(\./([^)]+)\)\s*\|') {
            $order++
            $fileName = $Matches[2]
            $articlePath = "$SeriesDir/$fileName"
            $articleId = Get-ArticleId $articlePath
            $articles += [ordered]@{
                order     = $order
                articleId = $articleId
                fileName  = $fileName
            }
        }
        elseif ($line -match '^\|\s*\[(\d+)\]\(([^)]+\.md)\)\s*\|') {
            $order++
            $fileName = $Matches[2] -replace '^\./', ''
            $articlePath = "$SeriesDir/$fileName"
            $articleId = Get-ArticleId $articlePath
            $articles += [ordered]@{
                order     = $order
                articleId = $articleId
                fileName  = $fileName
            }
        }
    }
    return $articles
}

function Parse-PrevNextLinks {
    param([string]$Content, [string]$ArticleId)
    $prev = $null; $next = $null
    if ($Content -match '\*\*上一篇\*\*:\s*\[[^\]]+\]\(([^)]+)\)') {
        $prev = Resolve-MdLink $ArticleId $Matches[1]
    }
    if ($Content -match '\*\*下一篇\*\*:\s*\[[^\]]+\]\(([^)]+)\)') {
        $next = Resolve-MdLink $ArticleId $Matches[1]
    }
    return @{ prev = $prev; next = $next }
}

Write-Host "Repo root: $RepoRoot"
Write-Host "Output:    $OutputDir"

# Clean output
if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
$articlesDir = Join-Path $OutputDir "articles"
New-Item -ItemType Directory -Path $articlesDir -Force | Out-Null

# Collect all markdown files
$allFiles = @()
foreach ($mod in $ModuleDirs) {
    $modPath = Join-Path $RepoRoot $mod
    if (-not (Test-Path $modPath)) { continue }
    Get-ChildItem -Path $modPath -Recurse -Filter "*.md" -File | ForEach-Object {
        $rel = $_.FullName.Substring($RepoRoot.Length).TrimStart('\', '/')
        if (-not (Test-ExcludedPath $rel)) {
            $allFiles += $rel
        }
    }
}
foreach ($rf in $RootFiles) {
    $fp = Join-Path $RepoRoot $rf
    if (Test-Path $fp) { $allFiles += $rf }
}
$allFiles = $allFiles | Sort-Object -Unique

Write-Host "Found $($allFiles.Count) markdown files"

# Article metadata map
$articleMeta = @{}
$linkMap = @{}

foreach ($rel in $allFiles) {
    $articleId = Get-ArticleId $rel
    $srcPath = Join-Path $RepoRoot $rel
    $content = [System.IO.File]::ReadAllText($srcPath, [System.Text.Encoding]::UTF8)
    $title = Get-TitleFromMarkdown $content $rel

    # Copy to assets preserving directory structure
    $destPath = Join-Path $articlesDir ($rel -replace '\\', [IO.Path]::DirectorySeparatorChar)
    $destDir = Split-Path $destPath -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    [System.IO.File]::WriteAllText($destPath, $content, [System.Text.UTF8Encoding]::new($false))

    $articleMeta[$articleId] = @{
        id      = $articleId
        title   = $title
        relPath = $rel
        content = $content
    }

    # Link map entries (multiple keys per article)
    $linkMap[$articleId] = $articleId
    $linkMap[$rel] = $articleId
    $linkMap["./$rel"] = $articleId
    $linkMap["/$rel"] = $articleId
    $linkMap[($rel -replace '\\', '/')] = $articleId
}

# Build catalog: modules -> series -> articles
$modules = @()

# Root module for top-level files
$rootArticles = @()
foreach ($rf in $RootFiles) {
    if ($allFiles -contains $rf) {
        $id = Get-ArticleId $rf
        $rootArticles += [ordered]@{
            id    = $id
            title = $articleMeta[$id].title
            order = $rootArticles.Count + 1
        }
    }
}
if ($rootArticles.Count -gt 0) {
    $modules += [ordered]@{
        id     = "_root"
        title  = "总览与路线图"
        series = @([ordered]@{
            id          = "_root/main"
            title       = "仓库总览"
            readmePath  = "README"
            readmeId    = (Get-ArticleId "README.md")
            articles    = (Ensure-JsonArray $rootArticles)
        })
    }
}

foreach ($modName in $ModuleDirs) {
    $modPath = Join-Path $RepoRoot $modName
    if (-not (Test-Path $modPath)) { continue }

    $modTitle = switch ($modName) {
        "Linux_Kernel"       { "Linux Kernel" }
        "Runtime"            { "Runtime / ART" }
        "Android_Framework"  { "Android Framework" }
        "App"                { "App 应用层" }
        "Tools"              { "Tools 工具" }
        "Hook"               { "Hook 专题" }
        "AI_Native_X"        { "AI Native X" }
        default              { $modName }
    }

    $seriesList = @()
    $assignedArticles = [System.Collections.Generic.HashSet[string]]::new()

    # Find series README files
    $readmeFiles = Get-ChildItem -Path $modPath -Recurse -Filter "*.md" -File |
        Where-Object {
            $n = $_.Name
            ($n -match '^README' -or $n -match '^readme') -and
            -not (Test-ExcludedPath ($_.FullName.Substring($RepoRoot.Length).TrimStart('\', '/')))
        } | Sort-Object FullName

    foreach ($readme in $readmeFiles) {
        $readmeRel = $readme.FullName.Substring($RepoRoot.Length).TrimStart('\', '/')
        $seriesDir = Split-Path $readmeRel -Parent
        if ($seriesDir -eq '') { $seriesDir = $modName }
        $seriesDir = $seriesDir -replace '\\', '/'
        $readmeId = Get-ArticleId $readmeRel
        $readmeContent = [System.IO.File]::ReadAllText($readme.FullName, [System.Text.Encoding]::UTF8)
        $seriesTitle = Get-TitleFromMarkdown $readmeContent $readmeRel

        $tableArticles = Parse-SeriesReadmeTable $readmeContent ($seriesDir -replace '\\', '/')
        $seriesArticles = @()

        if ($tableArticles.Count -gt 0) {
            foreach ($ta in $tableArticles) {
                $aid = Resolve-ArticleInSeries $seriesDir $ta.fileName $articleMeta $RepoRoot
                if (-not $aid) { continue }
                [void]$assignedArticles.Add($aid)
                $seriesArticles += [ordered]@{
                    id    = $aid
                    title = $articleMeta[$aid].title
                    order = $ta.order
                }
            }
        }
        else {
            # Fallback: all .md in same dir except README
            $dirPath = if ($seriesDir) { Join-Path $RepoRoot ($seriesDir -replace '/', [IO.Path]::DirectorySeparatorChar) } else { $modPath }
            if (Test-Path $dirPath) {
                $order = 0
                Get-ChildItem -Path $dirPath -Filter "*.md" -File |
                    Where-Object { $_.Name -notmatch '^README' -and $_.Name -notmatch '^readme' } |
                    Sort-Object Name | ForEach-Object {
                        $rel = $_.FullName.Substring($RepoRoot.Length).TrimStart('\', '/')
                        $aid = Get-ArticleId $rel
                        if ($articleMeta.ContainsKey($aid)) {
                            $order++
                            [void]$assignedArticles.Add($aid)
                            $seriesArticles += [ordered]@{
                                id    = $aid
                                title = $articleMeta[$aid].title
                                order = $order
                            }
                        }
                    }
            }
        }

        if ($seriesArticles.Count -gt 0 -or $articleMeta.ContainsKey($readmeId)) {
            # Set prev/next within series
            for ($i = 0; $i -lt $seriesArticles.Count; $i++) {
                $aid = $seriesArticles[$i].id
                $content = $articleMeta[$aid].content
                $explicit = Parse-PrevNextLinks $content $aid
                $seriesArticles[$i].prevId = if ($explicit.prev -and $articleMeta.ContainsKey($explicit.prev)) { $explicit.prev }
                    elseif ($i -gt 0) { $seriesArticles[$i - 1].id } else { $null }
                $seriesArticles[$i].nextId = if ($explicit.next -and $articleMeta.ContainsKey($explicit.next)) { $explicit.next }
                    elseif ($i -lt $seriesArticles.Count - 1) { $seriesArticles[$i + 1].id } else { $null }
            }

            $seriesList += [ordered]@{
                id         = $seriesDir
                title      = $seriesTitle
                readmePath = $seriesDir
                readmeId   = $readmeId
                articles   = (Ensure-JsonArray $seriesArticles)
            }
        }
    }

    # Sort series by path for stable browsing (Process before Window, etc.)
    $seriesList = $seriesList | Sort-Object { $_.id }

    # Unassigned articles in module
    $unassigned = @()
    $order = 0
    foreach ($rel in $allFiles) {
        if ($rel -notmatch "^$([regex]::Escape($modName))") { continue }
        $aid = Get-ArticleId $rel
        if ($assignedArticles.Contains($aid)) { continue }
        if ($rel -match 'README' -or $rel -match 'readme') { continue }
        $order++
        $unassigned += [ordered]@{
            id    = $aid
            title = $articleMeta[$aid].title
            order = $order
        }
    }
    if ($unassigned.Count -gt 0) {
        $seriesList += [ordered]@{
            id         = "$modName/_misc"
            title      = "其他文章"
            readmePath = $null
            readmeId   = $null
            articles   = (Ensure-JsonArray $unassigned)
        }
    }

    if ($seriesList.Count -gt 0) {
        $modules += [ordered]@{
            id     = $modName
            title  = $modTitle
            series = (Ensure-JsonArray $seriesList)
        }
    }
}

$catalog = [ordered]@{
    version      = 1
    articleCount = $allFiles.Count
    generatedAt  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    modules      = (Ensure-JsonArray $modules)
}

$catalogJson = $catalog | ConvertTo-Json -Depth 20 -Compress:$false
$catalogPath = Join-Path $OutputDir "catalog.json"
[System.IO.File]::WriteAllText($catalogPath, $catalogJson, [System.Text.UTF8Encoding]::new($false))

# Validate catalog.json: every module.series must be a JSON array
$parsedCatalog = Get-Content $catalogPath -Raw | ConvertFrom-Json
for ($i = 0; $i -lt $parsedCatalog.modules.Count; $i++) {
    $mod = $parsedCatalog.modules[$i]
    if ($mod.series -isnot [System.Array]) {
        throw "catalog.json invalid: modules[$i] ($($mod.id)).series is not an array (PowerShell single-element unwrap bug)"
    }
}

$linkMapJson = $linkMap | ConvertTo-Json -Depth 3 -Compress:$false
[System.IO.File]::WriteAllText((Join-Path $OutputDir "link-map.json"), $linkMapJson, [System.Text.UTF8Encoding]::new($false))

# Build FTS SQLite database
$dbPath = Join-Path $OutputDir "articles.db"
if (Test-Path $dbPath) { Remove-Item $dbPath -Force }

$sqlLines = @(
    "CREATE VIRTUAL TABLE articles_fts USING fts4(path, title, body, tokenize=unicode61);"
)
$sqlFile = Join-Path $env:TEMP "pack-content-$(Get-Random).sql"
$dbEsc = $dbPath -replace "'", "''"

foreach ($rel in $allFiles) {
    $articleId = Get-ArticleId $rel
    $meta = $articleMeta[$articleId]
    $pathEsc = $articleId -replace "'", "''"
    $titleEsc = $meta.title -replace "'", "''"
    $bodyEsc = $meta.content -replace "'", "''"
    $sqlLines += "INSERT INTO articles_fts(path, title, body) VALUES('$pathEsc', '$titleEsc', '$bodyEsc');"
}

[System.IO.File]::WriteAllText($sqlFile, ($sqlLines -join "`n"), [System.Text.UTF8Encoding]::new($false))

$sqlite3 = (Get-Command sqlite3 -ErrorAction SilentlyContinue).Source
if (-not $sqlite3) {
    Write-Warning "sqlite3 not found; skipping articles.db generation"
}
else {
    & $sqlite3 $dbPath ".read $sqlFile"
    Remove-Item $sqlFile -Force -ErrorAction SilentlyContinue
    Write-Host "Created articles.db"
}

Write-Host "Pack complete: $($allFiles.Count) articles -> $OutputDir"
exit 0
