#!/bin/bash

# ================================
# Required Environment Variables
# ================================

export MAC_AGENT_BENCH_MAC_HDD_IMG_PATH="/home/fuyikun/Documents/ckpt/all6/mac_hdd_ng.img"
export MAC_AGENT_BENCH_BASESYSTEM_IMG_PATH="/home/fuyikun/Documents/BaseSystem.img"

# ================================
# Configurable constants
# ================================

WORK_DIR="/home/fuyikun/Documents/MacAgentBench"
TASK_ROOT="${WORK_DIR}/tasks"
RESULT_ROOT="${WORK_DIR}/results"
LOG_DIR="${WORK_DIR}/logs"

MODELS=("OpenCUA-32B")
MODEL_TYPE_LIST=("xlang_cua")
URL_LIST=("YOUR_VLLM_URL")
MODEL_SUB_DIR="opencua-32b-baseline"

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
LOG_FILE="${LOG_DIR}/opencua_32b_baseline_dispatch_${RUN_TS}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "WORK_DIR=${WORK_DIR}"
echo "TASK_ROOT=${TASK_ROOT}"
echo "MODELS=${MODELS[*]}"
echo "MODEL_TYPE_LIST=${MODEL_TYPE_LIST[*]}"
echo "MODEL_SUB_DIR=${MODEL_SUB_DIR}"
echo "NUM_WORKERS=${NUM_WORKERS}"
echo "RESULT_ROOT=${RESULT_ROOT}"
echo "LOG_FILE=${LOG_FILE}"

# ================================
# Run evaluation (dynamic dispatch)
# ================================

/home/fuyikun/miniconda3/envs/eval/bin/python parallel_dispatch.py \
    --model "${MODELS[0]}" \
    --model_type "${MODEL_TYPE_LIST[0]}" \
    --model_sub_dir "${MODEL_SUB_DIR}" \
    --url "${URL_LIST[0]}" \
    --num_workers "${NUM_WORKERS}" \
    --config_prefix "${CONFIG_PREFIX}" \
    --config_dir "${CONFIG_DIR}" \
    --result_root "${RESULT_ROOT}" \
    --log_prefix "opencua_32b_baseline"
