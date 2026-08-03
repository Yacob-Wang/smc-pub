Write-Output "hello from ps1"
Write-Output "args: $args"
foreach ($a in $args) { Write-Output "  arg=$a" }
