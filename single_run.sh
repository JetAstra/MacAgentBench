#!/bin/bash

# ================================
# Required Environment Variables
# ================================

# Path to system image files used by the container
# 使用 WSL 原生路径以获得更好的 I/O 性能
export MACOS_ARENA_MAC_HDD_IMG_PATH="$HOME/macos-images/mac_hdd_ng.img"
export MACOS_ARENA_BASESYSTEM_IMG_PATH="$HOME/macos-images/BaseSystem.img"

# OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

# ================================
# Configurable constants
# ================================

WORK_DIR="/mnt/d/research/ScaleCUA/evaluation/MacOSArena" # Change to your local path
#CONFIG_FILE="config/default_config_linux.yaml"  # For Linux
 CONFIG_FILE="config/default_config.yaml"      # For WSL

# ================================
# Preparation
# ================================

cd "${WORK_DIR}" || exit 1
mkdir -p results/example_run_1

# ================================
# Run evaluation
# ================================

python -m single_run --config_file "${CONFIG_FILE}"