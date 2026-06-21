#!/bin/bash
# ================================
# Example: Run baseline evaluation for a model
# ================================
# Usage: bash run_example.sh
#
# Before running:
# 1. Set up the macOS VM environment (see README.md)
# 2. Deploy your model via vLLM and set YOUR_VLLM_URL
# 3. Adjust NUM_WORKERS based on your available VMs
#
# For more model-specific scripts, see scripts/run_*.sh

set -e

# ================================
# Required Environment Variables
# ================================

export MAC_AGENT_BENCH_MAC_HDD_IMG_PATH="/path/to/mac_hdd_ng.img"
export MAC_AGENT_BENCH_BASESYSTEM_IMG_PATH="/path/to/BaseSystem.img"

# For proprietary model APIs (optional):
# export OPENAI_API_KEY="YOUR_API_KEY"
# export OPENAI_BASE_URL="YOUR_OPENAI_BASE_URL"
# export ANTHROPIC_API_KEY="YOUR_API_KEY"
# export ANTHROPIC_BASE_URL="YOUR_ANTHROPIC_BASE_URL"

# ================================
# Configurable constants
# ================================

WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT="${WORK_DIR}/task"
RESULT_ROOT="${WORK_DIR}/results"
LOG_DIR="${WORK_DIR}/logs"

# Model configuration
MODELS=("YOUR_MODEL_NAME")           # e.g. "gemini-3.1-pro-preview", "InternVL3_5-8B"
MODEL_TYPE_LIST=("YOUR_MODEL_TYPE")  # e.g. "gpt", "claude", "qwen3vl", "opencua", "uitars", "guiowl", "xlang_cua"
URL_LIST=("YOUR_VLLM_URL")           # e.g. "http://localhost:8000/v1" (leave "" for proprietary APIs)
MODEL_SUB_DIR="YOUR_RUN_NAME"        # e.g. "internvl35-8b-baseline"

NUM_WORKERS=7
CONFIG_DIR="${WORK_DIR}/config"
CONFIG_PREFIX="qwen3vl_worker"

# ================================
# Preparation
# ================================

cd "${WORK_DIR}" || exit 1
mkdir -p "${RESULT_ROOT}"
mkdir -p "${LOG_DIR}"

RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/eval_dispatch_${RUN_TS}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "WORK_DIR=${WORK_DIR}"
echo "MODELS=${MODELS[*]}"
echo "MODEL_TYPE_LIST=${MODEL_TYPE_LIST[*]}"
echo "MODEL_SUB_DIR=${MODEL_SUB_DIR}"
echo "NUM_WORKERS=${NUM_WORKERS}"

# ================================
# Run evaluation (dynamic dispatch)
# ================================

python parallel_dispatch.py \
    --model "${MODELS[0]}" \
    --model_type "${MODEL_TYPE_LIST[0]}" \
    --model_sub_dir "${MODEL_SUB_DIR}" \
    --url "${URL_LIST[0]}" \
    --num_workers "${NUM_WORKERS}" \
    --config_prefix "${CONFIG_PREFIX}" \
    --config_dir "${CONFIG_DIR}" \
    --result_root "${RESULT_ROOT}" \
    --log_prefix "eval"
