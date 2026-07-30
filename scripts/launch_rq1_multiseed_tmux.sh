#!/usr/bin/env bash
set -euo pipefail

session="arsc_rq1_multiseed"
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_path="$workspace/outputs/validity/tmux_rq1_multiseed.log"
powershell_exe="${ARSC_POWERSHELL_EXE:-powershell.exe}"
script_win="$(wslpath -w "$workspace/scripts/run_rq1_multiseed.ps1")"
python_win="${ARSC_PYTHON_EXE:-python}"

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
