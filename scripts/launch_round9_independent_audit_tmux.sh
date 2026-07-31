#!/usr/bin/env bash
set -euo pipefail

session="arsc_round9_independent"
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log="$workspace/outputs/validity/round9_multimap_independent_audit.log"
audit="$workspace/outputs/validity/round9_multimap_independent_audit.json"
draws="$workspace/outputs/validity/round9_multimap_independent_bootstrap_draws.npz"
python_exe="${ARSC_WSL_PYTHON_EXE:-/mnt/d/anaconda3/envs/Nuclear_Transformer/python.exe}"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "session already exists: $session"
  exit 91
fi
if [[ -e "$audit" || -e "$draws" || -e "$audit.tmp" || -e "$draws.tmp" ]]; then
  echo "independent final or staging output already exists"
  exit 92
fi

run_command="set -o pipefail; cd '$workspace'; '$python_exe' -u scripts/verify_round9_multimap_outputs.py 2>&1 | tee '$log'; code=\${PIPESTATUS[0]}; echo EXIT_CODE=\$code | tee -a '$log'; exit \$code"
printf -v quoted_command '%q' "$run_command"
tmux new-session -d -s "$session" "bash -lc $quoted_command"
echo "started tmux session: $session"
echo "log: $log"
