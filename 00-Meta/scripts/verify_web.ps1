# 本地一键验证 Web 文档站：prepare → build → 链接校验
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)

Write-Host "== prepare_web_docs =="
py -3.12 00-Meta/scripts/prepare_web_docs.py

Write-Host "== mkdocs build =="
py -3.12 -m mkdocs build

Write-Host "== validate_feed_links =="
py -3.12 00-Meta/scripts/validate_feed_links.py

Write-Host "== validate_tabs_links =="
py -3.12 00-Meta/scripts/validate_tabs_links.py

Write-Host "== validate_markdown_links =="
py -3.12 00-Meta/scripts/validate_markdown_links.py --fail

Write-Host "All checks passed."
