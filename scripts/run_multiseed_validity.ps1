param(
    [string]$PythonExe = "python",
    [int[]]$Seeds = @(42, 123, 2024, 31415, 271828),
    [int]$BootstrapReplicates = 2000
)

$ErrorActionPreference = "Stop"

$runs = @{
    42 = @{
        Config = "configs/validity_seed42.yaml"
        Slug = "seed_42"
    }
    123 = @{
        Config = "configs/validity_seed123.yaml"
        Slug = "seed_123"
    }
    2024 = @{
        Config = "configs/validity_seed2024.yaml"
        Slug = "seed_2024"
    }
    31415 = @{
        Config = "configs/validity_seed31415.yaml"
        Slug = "seed_31415"
    }
    271828 = @{
        Config = "configs/validity_seed271828.yaml"
        Slug = "seed_271828"
    }
}

function Invoke-Stage {
    param(
        [int]$Seed,
        [string]$Stage,
        [string[]]$Arguments
    )
    $started = Get-Date
    Write-Output (@{
        event = "stage_started"
        seed = $Seed
        stage = $Stage
        time = $started.ToString("o")
    } | ConvertTo-Json -Compress)
    & $PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Seed $Seed stage $Stage failed with exit code $LASTEXITCODE"
    }
    Write-Output (@{
        event = "stage_completed"
        seed = $Seed
        stage = $Stage
        duration_seconds = ((Get-Date) - $started).TotalSeconds
    } | ConvertTo-Json -Compress)
}

foreach ($seed in $Seeds) {
    if (-not $runs.ContainsKey($seed)) {
        throw "No frozen configuration registered for seed $seed"
    }
    $run = $runs[$seed]
    $config = $run.Config
    $slug = $run.Slug
    $checkpointDir = "checkpoints/validity/$slug"
    $outputDir = "outputs/validity/$slug"

    foreach ($model in @("action_only", "joint")) {
        $last = "$checkpointDir/${model}_last.pt"
        $arguments = @(
            "scripts/train_model.py",
            "--config", $config,
            "--model", $model,
            "--device", "cuda"
        )
        if (Test-Path -LiteralPath $last) {
            $arguments += @("--resume", $last)
        }
        Invoke-Stage -Seed $seed -Stage "train_$model" -Arguments $arguments
    }

    Invoke-Stage -Seed $seed -Stage "calibrate" -Arguments @(
        "scripts/calibrate.py",
        "--config", $config,
        "--checkpoint", "$checkpointDir/joint_best_action.pt",
        "--device", "cuda"
    )

    Invoke-Stage -Seed $seed -Stage "paired_bootstrap" -Arguments @(
        "scripts/analyze_internal_validity.py",
        "--config", $config,
        "--action-checkpoint", "$checkpointDir/action_only_best_action.pt",
        "--joint-checkpoint", "$checkpointDir/joint_best_action.pt",
        "--calibration", "$outputDir/calibration.json",
        "--mask-manifest", "data/processed/masks_v3/manifest.jsonl",
        "--cache", "$outputDir/prediction_cache/internal_validity_v3.npz",
        "--output-json", "$outputDir/internal_validity_v3_bootstrap.json",
        "--output-csv", "$outputDir/internal_validity_v3_bootstrap.csv",
        "--device", "cuda",
        "--bootstrap-replicates", "$BootstrapReplicates",
        "--bootstrap-seed", "$(20260730 + $seed)"
    )
}
