# DevAssist-AI Manual PR Review Test
# Simulates a GitHub webhook payload to trigger a review

# ── CONFIG — edit these ────────────────────────────────────────────────────
$REPO       = "Hari-Oggy/Mutli-direction-Code-translator-AST"
$PR_NUMBER  = 2
$BRANCH     = "HAREESH14-patch-1"   # source branch shown on GitHub PR
$COMMIT_SHA = "7f7ea13bcbab69818a59366a6a8330942b56705a"
# ──────────────────────────────────────────────────────────────────────────

$payload = @{
    action = "opened"
    number = $PR_NUMBER
    pull_request = @{
        number = $PR_NUMBER
        title  = "Python file edits - real PR review"
        state  = "open"
        draft  = $false
        user   = @{ login = "Hari-Oggy" }
        head   = @{ ref = $BRANCH; sha = $COMMIT_SHA }
        base   = @{ ref = "main" }
        html_url = "https://github.com/$REPO/pull/$PR_NUMBER"
    }
    repository = @{
        id        = 123456
        full_name = $REPO
    }
    sender = @{ login = "Hari-Oggy" }
} | ConvertTo-Json -Depth 10

Write-Host "Sending webhook to backend for PR #$PR_NUMBER on $REPO..." -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod `
        -Uri "http://localhost:8000/api/v3/github/webhook" `
        -Method POST `
        -ContentType "application/json" `
        -Headers @{ "X-GitHub-Event" = "pull_request" } `
        -Body $payload

    Write-Host "SUCCESS!" -ForegroundColor Green
    Write-Host ($response | ConvertTo-Json -Depth 5)
} catch {
    Write-Host "ERROR:" -ForegroundColor Red
    Write-Host $_.Exception.Message
}