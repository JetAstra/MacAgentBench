# Agent-S3 on MacAgentBench

## Quick Start

### 1. Install dependencies

Create and activate your Python environment, then install the project dependencies from the repository root.

```bash
pip install -e .
pip install python-dotenv wrapt-timeout-decorator pillow
```

The editable install provides the `gui_agents` package. The extra packages above are used by the MacAgentBench evaluation scripts. If your environment already includes them, this step is harmless.

### 2. Prepare MacAgentBench / MacAgentBench resources

Make sure you have the following resources on the machine where you run evaluation:

- MacAgentBench / MacAgentBench task files, organized by domain, for example `tasks/calendar/1_1.json`.
- MacAgentBench macOS image files:
  - `mac_hdd_ng.img`
  - `BaseSystem.img`
- macOS Docker config files, for example:
  - `config/parallel_worker_1.yaml`

Docker must be running before evaluation starts.

### 3. Edit `eval.sh`

Open [`eval.sh`](eval.sh) and update the paths for your local machine:

```bash
WORK_DIR=evaluation/MacAgentBench/Agent-S3/MacAgentBench/s3
CONFIG_FILE_BASE=evaluation/MacAgentBench/config
TEST_CONFIG_BASE_DIR=evaluation/MacAgentBench/tasks

export MAC_AGENT_BENCH_MAC_HDD_IMG_PATH=evaluation/MacAgentBench/resources/macos/resources/macos/mac_hdd_ng.img
export MAC_AGENT_BENCH_BASESYSTEM_IMG_PATH=evaluation/MacAgentBench/resources/macos/resources/macos/BaseSystem.img
```

Also update the model settings and API keys:

```bash
MODEL=...
GROUND_MODEL=...
MODEL_URL=...
GROUND_URL=...
MODEL_API_KEY=...
GROUND_API_KEY=...
```

`MODEL` is the main model used by Agent-S3. `GROUND_MODEL` is used for UI grounding. The endpoints should be OpenAI API compatible.

Do not commit real API keys to public code. For public releases, keep placeholders such as `xxx` in `eval.sh` and let users fill in their own values locally.

### 4. Choose tasks

By default, `eval.sh` runs the domains listed in `GROUP_1`.

To run a smaller smoke test first, edit `GROUP_1` to include only one or two domains:

```bash
GROUP_1=(
  "reminders"
)
```

The task ids are controlled by:

```bash
TEST_ALL_META_PATH=all_tasks.json
```

### 5. Run evaluation

From the repository root, run:

```bash
sudo bash evaluation/MacAgentBench/Agent-S3/MacAgentBench/s3/eval.sh
```

Or enter the script directory and run:

```bash
cd evaluation/MacAgentBench/Agent-S3/MacAgentBench/s3
sudo bash eval.sh
```

The script starts a macOS Docker worker, runs Agent-S3 on the selected domains, and writes logs and results to disk.

## Outputs

Worker logs are written to:

```text
MacAgentBench/s3/logs/
```

Evaluation results are written under:

```text
MacAgentBench/s3/gpt_results_<worker_id>/
└── pyautogui/
    └── screenshot/
        └── <model>/
            └── <domain>/
                └── <example_id>/
                    ├── instruction.txt
                    ├── traj.jsonl
                    ├── result.txt
                    ├── step_0.png
                    └── ...
```

If a run fails, check the worker log first, then inspect the task-level `traj.jsonl`.

## Common Issues

- `No such file or directory`: check `WORK_DIR`, `TEST_CONFIG_BASE_DIR`, and the macOS image paths in `eval.sh`.
- Missing `parallel_worker_1.yaml`: check `CONFIG_FILE_BASE` and make sure the config file exists.
- Docker or SSH connection failure: make sure Docker is running and the macOS Docker config uses valid ports and image paths.
- Model request failure: check `MODEL_URL`, `MODEL_API_KEY`, `GROUND_URL`, and `GROUND_API_KEY`.
- WSL path issue: convert Windows paths to WSL paths. For example, `D:\...` should become `/mnt/d/...`.