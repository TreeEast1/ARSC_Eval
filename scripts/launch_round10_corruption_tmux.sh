#!/usr/bin/env bash
set -euo pipefail

SESSION="arsc_round10_formal"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_EXE="/mnt/d/anaconda3/envs/Nuclear_Transformer/python.exe"
GO_PATH="${PROJECT_ROOT}/outputs/validity/round10_preformal_reviewer_decision.json"
FINAL_DIR="${PROJECT_ROOT}/outputs/validity/round10_corruption_formal_attempt01"
STAGING_DIR="${PROJECT_ROOT}/outputs/validity/round10_corruption_formal_attempt01.staging"
LOG_PATH="${PROJECT_ROOT}/outputs/validity/round10_corruption_formal_attempt01.log"
INDEX_PATH="${PROJECT_ROOT}/outputs/validity/round10_corruption_artifact_index.json"

test -f "${GO_PATH}"
test ! -e "${FINAL_DIR}"
test ! -e "${STAGING_DIR}"
test ! -e "${LOG_PATH}"
test ! -e "${INDEX_PATH}"
test -x "${PYTHON_EXE}"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "tmux session already exists: ${SESSION}" >&2
  exit 1
fi

COMMAND="cd '${PROJECT_ROOT}' && set -o pipefail; PYTHONPATH=src '${PYTHON_EXE}' -u scripts/analyze_round10_corruption.py --device auto 2>&1 | tee '${LOG_PATH}'; code=\${PIPESTATUS[0]}; echo EXIT_CODE=\${code} | tee -a '${LOG_PATH}'; exit \${code}"
tmux new-session -d -s "${SESSION}" "${COMMAND}"
echo "started ${SESSION}; log=${LOG_PATH}"
