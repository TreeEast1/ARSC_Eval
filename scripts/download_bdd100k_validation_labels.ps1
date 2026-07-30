param(
    [string]$OutputPath = "data/external/bdd100k/validation_samples.json"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = Join-Path $projectRoot $OutputPath
$targetDirectory = Split-Path -Parent $target
New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null

# This is a public Hugging Face mirror of the official BDD100K validation
# FiftyOne export. It contains the validation image names and object labels;
# no image pixels are downloaded.
$source = "https://huggingface.co/datasets/Hanshiya/bdd100k/resolve/main/samples.json?download=true"
& curl.exe `
    --fail `
    --location `
    --retry 30 `
    --retry-all-errors `
    --retry-delay 3 `
    --retry-max-time 3600 `
    --continue-at - `
    $source `
    --output $target
if ($LASTEXITCODE -ne 0) {
    throw "curl failed with exit code $LASTEXITCODE"
}

$item = Get-Item -LiteralPath $target
$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $target
[pscustomobject]@{
    source = $source
    output = $item.FullName
    bytes = $item.Length
    sha256 = $hash.Hash
} | ConvertTo-Json
