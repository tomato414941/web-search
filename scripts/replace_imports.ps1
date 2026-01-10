# Bulk import replacement script
$ErrorActionPreference = "Stop"

# Shared package: web_search.core/db → shared.core/db
Get-ChildItem -Path "shared\src" -Recurse -Filter "*.py" | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace 'from web_search\.core', 'from shared.core'
    $content = $content -replace 'from web_search\.db', 'from shared.db'
    $content = $content -replace 'import web_search\.core', 'import shared.core'
    $content = $content -replace 'import web_search\.db', 'import shared.db'
    Set-Content $_.FullName -Value $content -NoNewline
}

# Frontend package: update all imports
Get-ChildItem -Path "frontend" -Recurse -Filter "*.py" | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    # Shared imports
    $content = $content -replace 'from web_search\.core', 'from shared.core'
    $content = $content -replace 'from web_search\.db', 'from shared.db'
    # Frontend own imports
    $content = $content -replace 'from web_search\.api', 'from frontend.api'
    $content = $content -replace 'from web_search\.services', 'from frontend.services'
    $content = $content -replace 'from web_search\.indexer', 'from frontend.indexer'
    # Crawler imports (tests may reference crawler)
    $content = $content -replace 'from web_search\.crawler', 'from crawler.crawler'
    Set-Content $_.FullName -Value $content -NoNewline
}

# Crawler package: update all imports
Get-ChildItem -Path "crawler" -Recurse -Filter "*.py" | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    # Shared imports
    $content = $content -replace 'from web_search\.core', 'from shared.core'
    $content = $content -replace 'from web_search\.db', 'from shared.db'
    # Frontend imports (shouldn't exist but just in case)
    $content = $content -replace 'from web_search\.indexer', 'from frontend.indexer'
    # Crawler own imports
    $content = $content -replace 'from web_search\.crawler', 'from crawler.crawler'
    Set-Content $_.FullName -Value $content -NoNewline
}

Write-Host "Import replacement complete"
