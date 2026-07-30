param(
    [string]$PythonExe = "python",
    [int]$BootstrapReplicates = 2000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

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
        time = (Get-Date).ToString("o")
    } | ConvertTo-Json -Compress)
}

# Revalidate the independent-review amendment and all seed-43 artifacts.
Invoke-Stage -Seed 43 -Stage "amendment01_preflight" -Arguments @(
    "scripts/freeze_rq1_amendment01.py"
)

# Reviewer-required restart boundary: no seed-43 retraining or recalibration.
Invoke-Stage -Seed 43 -Stage "evaluate_rq1" -Arguments @(
    "scripts/evaluate_rq1_seed.py",
    "--config", "configs/rq1_seed43.yaml",
    "--action-checkpoint",
    "checkpoints/validity/rq1_seed_43/action_only_best_action.pt",
    "--joint-checkpoint",
    "checkpoints/validity/rq1_seed_43/joint_best_action.pt",
    "--action-calibration",
    "outputs/validity/rq1_seed_43/calibration_action_only.json",
    "--joint-calibration",
    "outputs/validity/rq1_seed_43/calibration_joint.json",
    "--device", "cuda",
    "--bootstrap-replicates", "$BootstrapReplicates",
    "--bootstrap-seed", "20260774"
)

foreach ($seed in @(44, 45, 46, 47)) {
    $config = "configs/rq1_seed$seed.yaml"
    $checkpointDir = "checkpoints/validity/rq1_seed_$seed"
    $outputDir = "outputs/validity/rq1_seed_$seed"

    foreach ($model in @("action_only", "joint")) {
        Invoke-Stage -Seed $seed -Stage "train_$model" -Arguments @(
            "scripts/train_model.py",
            "--config", $config,
            "--model", $model,
            "--device", "cuda",
            "--epochs", "5"
        )
    }
    Invoke-Stage -Seed $seed -Stage "calibrate_action_only" -Arguments @(
        "scripts/calibrate.py",
        "--config", $config,
        "--checkpoint", "$checkpointDir/action_only_best_action.pt",
        "--model", "action_only",
        "--output", "$outputDir/calibration_action_only.json",
        "--device", "cuda"
    )
    Invoke-Stage -Seed $seed -Stage "calibrate_joint" -Arguments @(
        "scripts/calibrate.py",
        "--config", $config,
        "--checkpoint", "$checkpointDir/joint_best_action.pt",
        "--model", "joint",
        "--output", "$outputDir/calibration_joint.json",
        "--device", "cuda"
    )
    Invoke-Stage -Seed $seed -Stage "evaluate_rq1" -Arguments @(
        "scripts/evaluate_rq1_seed.py",
        "--config", $config,
        "--action-checkpoint", "$checkpointDir/action_only_best_action.pt",
        "--joint-checkpoint", "$checkpointDir/joint_best_action.pt",
        "--action-calibration", "$outputDir/calibration_action_only.json",
        "--joint-calibration", "$outputDir/calibration_joint.json",
        "--device", "cuda",
        "--bootstrap-replicates", "$BootstrapReplicates",
        "--bootstrap-seed", "$(20260731 + $seed)"
    )
}

Invoke-Stage -Seed 0 -Stage "aggregate_five_seeds" -Arguments @(
    "scripts/aggregate_rq1_multiseed.py",
    "--replicates", "$BootstrapReplicates",
    "--bootstrap-seed", "20260731"
)

Write-Output (@{
    event = "rq1_multiseed_amendment01_pipeline_completed"
    seeds = @(43, 44, 45, 46, 47)
    time = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress)
