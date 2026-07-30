param(
    [string]$PythonExe = "python",
    [string]$Config = "configs/experiment.yaml",
    [string]$Device = "cuda"
)

$ErrorActionPreference = "Stop"

function Invoke-Stage {
    param([string[]]$Arguments)
    & $PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Stage failed with exit code $LASTEXITCODE`: $Arguments"
    }
}

Invoke-Stage @("scripts/download_data.py", "--data-root", "data")
Invoke-Stage @("scripts/download_pretrained.py", "--artifact", "resnet50")
Invoke-Stage @("scripts/prepare_data.py", "--config", $Config)
Invoke-Stage @("scripts/smoke_test.py", "--config", $Config, "--device", $Device)
Invoke-Stage @("scripts/train_model.py", "--config", $Config, "--model", "action_only", "--device", $Device)
Invoke-Stage @("scripts/train_model.py", "--config", $Config, "--model", "joint", "--device", $Device)
Invoke-Stage @("scripts/calibrate.py", "--config", $Config, "--device", $Device)
Invoke-Stage @("scripts/generate_masks.py", "--config", $Config, "--device", "0")
Invoke-Stage @("scripts/generate_perturbations.py", "--config", $Config)
Invoke-Stage @("scripts/evaluate.py", "--config", $Config, "--device", $Device)
Invoke-Stage @("scripts/verify_outputs.py", "--config", $Config)
