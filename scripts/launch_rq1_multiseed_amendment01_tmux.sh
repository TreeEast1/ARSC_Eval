#!/usr/bin/env bash
set -euo pipefail

session="arsc_rq1_multiseed"
workspace="/mnt/d/All_Project/cjl/ARSC_space/BDD-OIA_space"
log_path="$workspace/outputs/validity/tmux_rq1_multiseed_amendment01.log"
powershell_exe="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
script_win='D:\All_Project\cjl\ARSC_space\BDD-OIA_space\scripts\run_rq1_multiseed_amendment01.ps1'
python_win='D:\anaconda3\envs\Nuclear_Transformer\python.exe'

if tmux has-session -t "$session" 2>/dev/null; then
    echo "tmux session already exists: $session"
    exit 1
fi

mkdir -p "$(dirname "$log_path")"
run_command="set -o pipefail; cd '$workspace'; '$powershell_exe' -NoProfile -ExecutionPolicy Bypass -File '$script_win' -PythonExe '$python_win' 2>&1 | tee '$log_path'"
printf -v quoted_command '%q' "$run_command"
tmux new-session -d -s "$session" "bash -lc $quoted_command"
echo "started tmux session: $session"
echo "log: $log_path"
