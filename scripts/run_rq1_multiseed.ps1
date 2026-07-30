param(
    [string]$PythonExe = "python",
    [int]$BootstrapReplicates = 2000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Seeds = @(43, 44, 45, 46, 47)

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

foreach ($seed in $Seeds) {
    $config = "configs/rq1_seed$seed.yaml"
    $outputDir = "outputs/validity/rq1_seed_$seed"
    Invoke-Stage -Seed $seed -Stage "paired_design_preflight" -Arguments @(
        "scripts/verify_paired_design.py",
        "--config", $config,
        "--output", "$outputDir/paired_design_check.json"
    )
}

Invoke-Stage -Seed 0 -Stage "freeze_protocol" -Arguments @(
    "scripts/freeze_rq1_protocol.py"
)

foreach ($seed in $Seeds) {
    $config = "configs/rq1_seed$seed.yaml"
    $checkpointDir = "checkpoints/validity/rq1_seed_$seed"
    $outputDir = "outputs/validity/rq1_seed_$seed"

    foreach ($model in @("action_only", "joint")) {
        $last = "$checkpointDir/${model}_last.pt"
        $arguments = @(
            "scripts/train_model.py",
            "--config", $config,
            "--model", $model,
            "--device", "cuda",
            "--epochs", "5"
        )
        if (Test-Path -LiteralPath $last) {
            $arguments += @("--resume", $last)
        }
        Invoke-Stage -Seed $seed -Stage "train_$model" -Arguments $arguments
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
    event = "rq1_multiseed_pipeline_completed"
    seeds = $Seeds
    time = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress)
