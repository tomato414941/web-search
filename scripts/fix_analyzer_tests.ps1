# Fix analyzer.analyze -> analyzer.tokenize in test files
$ErrorActionPreference = "Stop"

Get-ChildItem -Path "frontend\tests" -Recurse -Filter "*.py" | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    if ($content -match 'analyzer\.analyze') {
        $content = $content -replace 'analyzer\.analyze', 'analyzer.tokenize'
        Set-Content $_.FullName -Value $content -NoNewline
        Write-Host "Fixed: $($_.Name)"
    }
}

Write-Host "Replacement complete"
