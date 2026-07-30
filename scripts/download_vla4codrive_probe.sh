#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${project_root}/data/external/VLA4CoDrive_probe_repo"
repository="https://github.com/SayedPedramHaeri/VLA4CoDrive.git"
commit="d8d6b290b7acfe1ae89b75f2d72fc8f94deeef61"

if [[ ! -d "${target}/.git" ]]; then
  git clone \
    --filter=blob:none \
    --no-checkout \
    --depth 1 \
    "${repository}" \
    "${target}"
fi

git -C "${target}" sparse-checkout init --no-cone
git -C "${target}" sparse-checkout set --no-cone \
  "/Action/clearNight/Vehicle_1/Town10HD_WeatherclearNight_scene001_win*.json" \
  "/Language/clearNight/Vehicle_1/Town10HD_WeatherclearNight_scene001_win*.json" \
  "/Vision/clearNight/Vehicle_1/Town10HD_WeatherclearNight_scene001_win*.mp4" \
  "/Vision/clearNight/Labels_2D/COCO/instances_all.json" \
  "/README.md" \
  "/LICENSE"
git -C "${target}" checkout --detach "${commit}"

printf 'commit=%s\n' "$(git -C "${target}" rev-parse HEAD)"
printf 'files=%s\n' "$(find "${target}" -type f -not -path '*/.git/*' | wc -l)"
du -sh "${target}"
