#!/usr/bin/env bash
set -euo pipefail

session="arsc_bdd_train_v5_gate"
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_path="$workspace/outputs/validity/tmux_bdd100k_train_v5_gate_amendment01.log"
python_exe="${ARSC_WSL_PYTHON_EXE:-/mnt/d/anaconda3/envs/Nuclear_Transformer/python.exe}"

if tmux has-session -t "$session" 2>/dev/null; then
    echo "tmux session already exists: $session"
    exit 1
fi

mkdir -p "$(dirname "$log_path")"
run_command="set -o pipefail; cd '$workspace'; '$python_exe' scripts/analyze_bdd100k_train_v5_gate.py 2>&1 | tee '$log_path'; code=\${PIPESTATUS[0]}; echo EXIT_CODE=\$code | tee -a '$log_path'; exit \$code"
printf -v quoted_command '%q' "$run_command"
tmux new-session -d -s "$session" "bash -lc $quoted_command"
echo "started tmux session: $session"
echo "log: $log_path"
