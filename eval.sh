#!/bin/bash

# ================================
# Required Environment Variables
# ================================

# Path to system image files used by the container
export MACOS_ARENA_MAC_HDD_IMG_PATH="/home/fuyikun/Documents/ckpt/all4/mac_hdd_ng.img"
export MACOS_ARENA_BASESYSTEM_IMG_PATH="/home/fuyikun/Documents/BaseSystem.img"

# Optional: export keys for GPT-based models if used
# export OPENAI_API_KEY="your-api-key-here"
# export ANTHROPIC_API_KEY="your-api-key-here"

# ================================
# Configurable constants
# ================================

WORK_DIR="/home/fuyikun/Documents/OS-Mac/evaluation/MacOSArena"
TASK_ROOT="${WORK_DIR}/task"

# DOMAINS: Task domain to evaluate.
#          Use "single_app" to test all single-app tasks,
#          or "multi_app" to test all cross-app tasks.
DOMAINS=(
  "new_apple_notes"
  "new_blogwatcher"
  "new_clawhub"
  "new_gifgrep"
  "new_github"
  "new_himalaya"
  "new_obsidian"
  "new_peekaboo"
  "new_reminders"
  "new_sherpa_onnx_tts"
  "new_songsee"
  "new_tmux"
  "new_video_frames"
  "new_weather"
  "new_whisper"
  "keynote"
  "numbers"
  "pages"
)

# MODELS: List of agent model names to evaluate.
#         Use ("none") for planner + grounder agent (requires PLANNER_EXECUTOR_MODEL).
MODELS=("openclaw")


# MODEL_TYPE_LIST: Explicit model types matching MODELS
MODEL_TYPE_LIST=("openclaw")

# URL_LIST: Model API URLs for each agent in MODELS (same order).
URL_LIST=("")

# PLANNER_EXECUTOR_MODEL: List of (planner, executor) pairs. Used if MODELS=("none")
# EXEC_MODEL_URL_LIST: URL list for each executor
PLANNER_EXECUTOR_MODEL=()
EXEC_MODEL_URL_LIST=()

# MODEL_SUB_DIR: Subdirectory under RESULT_ROOT/{model_name}/ to store logs of this evaluation run.
MODEL_SUB_DIR="claude-opus-4-6-thinking"

# DEBUG_OPENCLAW: Set to true to disable recording while debugging startup/gateway issues.
DEBUG_OPENCLAW=false

# CONFIG_FILE: Path to YAML configuration file
CONFIG_FILE="config/default_config_linux.yaml"  # For Linux
# CONFIG_FILE="config/default_config.yaml"      # For WSL

# RESULT_ROOT: Root directory to store all agent evaluation outputs
RESULT_ROOT="${WORK_DIR}/results"
LOG_DIR="${WORK_DIR}/logs"

# ================================
# Preparation
# ================================

cd "${WORK_DIR}" || exit 1
mkdir -p "${RESULT_ROOT}"
mkdir -p "${LOG_DIR}"

RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/eval_${RUN_TS}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "WORK_DIR=${WORK_DIR}"
echo "TASK_ROOT=${TASK_ROOT}"
echo "DOMAINS=${DOMAINS[*]}"
echo "MODELS=${MODELS[*]}"
echo "RESULT_ROOT=${RESULT_ROOT}"
echo "CONFIG_FILE=${CONFIG_FILE}"
echo "DEBUG_OPENCLAW=${DEBUG_OPENCLAW}"
echo "LOG_FILE=${LOG_FILE}"

# ================================
# Run evaluation
# ================================

# ⚠️ NOTE:
# This command requires `sudo` because the evaluation will remove and start Docker containers before each task.
# Make sure that the `python` used under sudo is still the one from your conda environment.
# You can check it via `sudo which python`, and replace `python` with the absolute path if needed.
# (i.e., the result of `which python` in your activated conda environment).

sudo \
  MACOS_ARENA_MAC_HDD_IMG_PATH="${MACOS_ARENA_MAC_HDD_IMG_PATH}" \
  MACOS_ARENA_BASESYSTEM_IMG_PATH="${MACOS_ARENA_BASESYSTEM_IMG_PATH}" \
  /home/fuyikun/miniconda3/envs/eval/bin/python -m batch_run \
  --task_root "${TASK_ROOT}" \
  --domains "${DOMAINS[@]}" \
  --models "${MODELS[@]}" \
  --url_list "${URL_LIST[@]}" \
  --model_type_list "${MODEL_TYPE_LIST[@]}" \
  --planner_executor_model "${PLANNER_EXECUTOR_MODEL[@]}" \
  --exec_model_url_list "${EXEC_MODEL_URL_LIST[@]}" \
  --model_sub_dir "${MODEL_SUB_DIR}" \
  --config_file "${CONFIG_FILE}" \
  --result_root "${RESULT_ROOT}" \
  $( [ "${DEBUG_OPENCLAW}" = "true" ] && printf '%s' "--disable_recording" )
