#!/usr/bin/env bash
set -euo pipefail

session="arsc_round8_independent_audit"
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_path="$workspace/outputs/validity/round8_graded_response_independent_audit_tmux.log"
python_exe="${ARSC_WSL_PYTHON_EXE:-/mnt/d/anaconda3/envs/Nuclear_Transformer/python.exe}"

if tmux has-session -t "$session" 2>/dev/null; then
    echo "tmux session already exists: $session"
    exit 1
fi

if [[ -e "$workspace/outputs/validity/round8_graded_response_independent_audit.json" ]] \
    || [[ -e "$workspace/outputs/validity/round8_graded_response_independent_bootstrap_draws.npz" ]]; then
    echo "independent audit output already exists; refusing to overwrite"
    exit 1
fi

mkdir -p "$(dirname "$log_path")"
run_command="set -o pipefail; cd '$workspace'; '$python_exe' scripts/verify_round8_graded_response_outputs.py 2>&1 | tee '$log_path'; code=\${PIPESTATUS[0]}; echo EXIT_CODE=\$code | tee -a '$log_path'; exit \$code"
printf -v quoted_command '%q' "$run_command"
tmux new-session -d -s "$session" "bash -lc $quoted_command"
echo "started tmux session: $session"
echo "log: $log_path"
