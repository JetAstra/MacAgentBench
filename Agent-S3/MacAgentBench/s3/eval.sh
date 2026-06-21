#!/bin/bash
# ================================
# Parallel evaluation with multiple macOS containers
# ================================
# Usage: sudo bash parallel_eval.sh
set -e

WORK_DIR=evaluation/MacAgentBench/Agent-S3/MacAgentBench/s3
LOG_DIR="${WORK_DIR}/logs"
CONFIG_FILE_BASE=evaluation/MacAgentBench/config

MODEL=gpt-5.4
GROUND_MODEL=bytedance/ui-tars-1.5-7b
MODEL_URL=xxx
GROUND_URL=xxx
MODEL_API_KEY=xxx
GROUND_API_KEY=xxx
TEST_CONFIG_BASE_DIR=evaluation/MacAgentBench/tasks

RESULT_DIR_BASE=gpt_results

MAX_SOLVING_TIME=600
MAX_STEPS=50
TEST_ALL_META_PATH=all_tasks.json

export MAC_AGENT_BENCH_MAC_HDD_IMG_PATH=evaluation/MacAgentBench/resources/macos/resources/macos/mac_hdd_ng.img
export MAC_AGENT_BENCH_BASESYSTEM_IMG_PATH=evaluation/MacAgentBench/resources/macos/resources/macos/BaseSystem.img

mkdir -p "${LOG_DIR}"

# Group 1: 180 tasks
GROUP_1=(
  "multi_app"          
  "new_clawhub"        
  "new_sherpa_onnx_tts" 
  "new_video_frames"   
  "vscode"             
  "new_github"         
  "numbers"            
  "new_gifgrep"        
  "new_whisper"        
  "notes"              
  "terminal"           
  "calendar"           
  "clock"              
  "finder"             
  "reminders"          
  "safari"             
  "keynote"            
  "new_songsee"        
  "new_apple_notes"    
  "new_obsidian"       
  "new_peekaboo"       
  "mac_system_settings" 
  "new_reminders"      
  "new_himalaya"       
  "pages"              
  "new_blogwatcher"    
  "new_tmux"           
  "new_weather"        
)

# ================================
# Run one worker
# ================================
run_worker() {
    local WORKER_ID=$1
    shift
    local DOMAINS=("$@")
    local CONFIG_FILE="${CONFIG_FILE_BASE}/parallel_worker_${WORKER_ID}.yaml"
    local WORKER_LOG="${LOG_DIR}/parallel_$(date +%Y%m%d_%H%M%S)_worker_${WORKER_ID}.log"

    echo "[Worker ${WORKER_ID}] Starting with ${#DOMAINS[@]} domains: ${DOMAINS[*]}"
    echo "[Worker ${WORKER_ID}] Config: ${CONFIG_FILE}"
    echo "[Worker ${WORKER_ID}] Log: ${WORKER_LOG}"

    python run.py \
        --provider_name "docker" \
        --headless \
        --num_envs 1 \
        --max_steps $MAX_STEPS \
        --max_solving_time $MAX_SOLVING_TIME \
        --domain "${DOMAINS[@]}" \
        --test_all_meta_path $TEST_ALL_META_PATH \
        --result_dir "${RESULT_DIR_BASE}_${WORKER_ID}" \
        --region "us-east-1" \
        --model_provider "openai" \
        --model $MODEL \
        --model_url $MODEL_URL \
        --model_api_key $MODEL_API_KEY \
        --model_temperature 1.0 \
        --ground_model $GROUND_MODEL \
        --ground_provider "openai" \
        --ground_url $GROUND_URL \
        --ground_api_key $GROUND_API_KEY \
        --grounding_width 1920 \
        --grounding_height 1080 \
        --sleep_after_execution 3 \
        --macos_config $CONFIG_FILE \
        --test_config_base_dir $TEST_CONFIG_BASE_DIR
        > "${WORKER_LOG}" 2>&1

    echo "[Worker ${WORKER_ID}] Done!"
}

# ================================
# Launch all workers in parallel
# ================================
cd "${WORK_DIR}"

echo "============================================"
echo "eval: 1 workers"
echo "Task root: ${TEST_CONFIG_BASE_DIR}"
echo "Result dir base: ${RESULT_DIR_BASE}"
echo "============================================"

run_worker 1 "${GROUP_1[@]}" &
PID1=$!

echo ""
echo "All 4 workers launched. PIDs: $PID1"
echo "Logs: ${LOG_DIR}/parallel_worker_*.log"
echo ""
echo "Waiting for all workers to finish..."

wait $PID1 && echo "[Worker 1] ✓" || echo "[Worker 1] ✗ (exit $?)"

echo ""
echo "============================================"
echo "All workers finished!"
echo "============================================"
