#!/usr/bin/env bash
set -euo pipefail

session="arsc_round9_formal"
workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_path="$workspace/outputs/validity/round9_multimap_formal.log"
python_exe="${ARSC_WSL_PYTHON_EXE:-/mnt/d/anaconda3/envs/Nuclear_Transformer/python.exe}"

if tmux has-session -t "$session" 2>/dev/null; then
    echo "tmux session already exists: $session"
    exit 1
fi

if [[ ! -e "$workspace/outputs/validity/round9_independent_reviewer_decision.json" ]]; then
    echo "independent reviewer decision is missing"
    exit 1
fi

for output in \
    round9_multimap_results.json \
    round9_multimap_primitives.npz \
    round9_multimap_bootstrap_draws.npz \
    round9_multimap_point_diagnostics.csv \
    round9_multimap_bootstrap_summary.csv \
    round9_multimap_formal.log; do
    if [[ -e "$workspace/outputs/validity/$output" ]]; then
        echo "formal output already exists: $output"
        exit 1
    fi
done
if compgen -G "$workspace/outputs/validity/round9_multimap_*.attempt01.tmp" >/dev/null; then
    echo "formal staging output already exists; refusing to start"
    exit 1
fi

mkdir -p "$(dirname "$log_path")"
run_command="set -o pipefail; cd '$workspace'; '$python_exe' -u scripts/analyze_round9_multimap.py 2>&1 | tee '$log_path'; code=\${PIPESTATUS[0]}; echo EXIT_CODE=\$code | tee -a '$log_path'; exit \$code"
printf -v quoted_command '%q' "$run_command"
tmux new-session -d -s "$session" "bash -lc $quoted_command"
echo "started tmux session: $session"
echo "log: $log_path"
