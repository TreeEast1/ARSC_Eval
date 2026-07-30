param(
    [string]$Target = "data/external/VLA4CoDrive_probe_repo"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$targetPath = [System.IO.Path]::GetFullPath(
    (Join-Path $projectRoot $Target)
)
$repository = "https://github.com/SayedPedramHaeri/VLA4CoDrive.git"
$commit = "d8d6b290b7acfe1ae89b75f2d72fc8f94deeef61"

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git failed with exit code $LASTEXITCODE`: git $Arguments"
    }
}

function Invoke-GitWithRetry {
    param(
        [string[]]$GitArguments,
        [int]$Attempts = 10
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        & git @GitArguments
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($attempt -eq $Attempts) {
            throw "git failed after $Attempts attempts: git $GitArguments"
        }
        Write-Warning (
            "git attempt $attempt/$Attempts failed; retrying in 5 seconds"
        )
        Start-Sleep -Seconds 5
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $targetPath ".git"))) {
    Invoke-Git clone `
        --filter=blob:none `
        --no-checkout `
        --depth 1 `
        $repository `
        $targetPath
}

$origin = & git -C $targetPath remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    Invoke-Git -C $targetPath remote add origin $repository
} elseif ($origin.Trim() -ne $repository) {
    throw "unexpected origin: $origin"
}

Invoke-Git -C $targetPath config http.version HTTP/1.1
Invoke-Git -C $targetPath config http.lowSpeedLimit 1
Invoke-Git -C $targetPath config http.lowSpeedTime 600
Invoke-GitWithRetry -GitArguments @(
    "-C", $targetPath,
    "fetch",
    "--depth", "1",
    "--filter=blob:none",
    "origin",
    "main"
)
Invoke-Git -C $targetPath sparse-checkout init --no-cone
Invoke-Git -C $targetPath sparse-checkout set --no-cone `
    "/Action/clearNight/Vehicle_1/Town10HD_WeatherclearNight_scene001_win*.json" `
    "/Language/clearNight/Vehicle_1/Town10HD_WeatherclearNight_scene001_win*.json" `
    "/Vision/clearNight/Vehicle_1/Town10HD_WeatherclearNight_scene001_win*.mp4" `
    "/Vision/clearNight/Labels_2D/COCO/instances_all.json" `
    "/README.md" `
    "/LICENSE"
Invoke-GitWithRetry -GitArguments @(
    "-C", $targetPath,
    "checkout",
    "--detach",
    $commit
)

$head = (& git -C $targetPath rev-parse HEAD).Trim()
$files = @(
    Get-ChildItem -LiteralPath $targetPath -Recurse -File |
        Where-Object { $_.FullName -notlike "*\.git\*" }
)
$bytes = ($files | Measure-Object -Property Length -Sum).Sum
[pscustomobject]@{
    repository = $repository
    commit = $head
    files = $files.Count
    bytes = $bytes
    target = $targetPath
} | ConvertTo-Json
