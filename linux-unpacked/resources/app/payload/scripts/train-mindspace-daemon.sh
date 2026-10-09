#!/usr/bin/env bash
#===============================================================================
# MindSpace Training Daemon
# ========================
# Runs in the background, watches for new auto-learn data, syncs to MindSpace's
# trainer directory, and triggers progressive training on GPU 1 (40% memory).
#
# Usage:
#   ./scripts/train-mindspace-daemon.sh start          # Start daemon
#   ./scripts/train-mindspace-daemon.sh stop           # Stop daemon
#   ./scripts/train-mindspace-daemon.sh restart        # Restart daemon
#   ./scripts/train-mindspace-daemon.sh status         # Check daemon status
#   ./scripts/train-mindspace-daemon.sh train-now      # Single training run
#   ./scripts/train-mindspace-daemon.sh dry-run        # Preview tiers without training
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ─── Configuration ─────────────────────────────────────────────────────────
MINDSPACE_DIR="/media/final-flash1/a47f2c6e-f5fa-4e60-bcea-95767738c074/MindSpace"
AUTO_LEARN_DIR="$PROJECT_ROOT/backend/knowledge/auto-learn"
DAEMON_LOG="/tmp/mindspace-daemon.log"
PID_FILE="/tmp/mindspace-daemon.pid"
GPU_DEVICE="cuda:1"
MEMORY_FRACTION="0.4"
TARGET_ACC="80"
MAX_EPOCHS_PER_TIER="5"
POLL_INTERVAL="300"
MIN_TRAIN_INTERVAL="900"
INITIAL_TRAINED_FILE="/tmp/mindspace-initial-trained"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()    { echo -e "[$(date '+%H:%M:%S')] $1" | tee -a "$DAEMON_LOG"; }
info()   { log "${GREEN}INFO${NC}  $1"; }
warn()   { log "${YELLOW}WARN${NC}  $1"; }
error()  { log "${RED}ERROR${NC} $1"; }

# ─── Prerequisites ─────────────────────────────────────────────────────────
check_prereqs() {
    [ -d "$MINDSPACE_DIR" ] || { error "MindSpace not found: $MINDSPACE_DIR"; return 1; }
    [ -f "$MINDSPACE_DIR/scripts/progressive_train.py" ] || { error "progressive_train.py not found"; return 1; }
    nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | grep -q "^1$" || warn "GPU 1 not found"
    [ -d "$AUTO_LEARN_DIR" ] || mkdir -p "$AUTO_LEARN_DIR"
    command -v python3 &>/dev/null || { error "python3 not found"; return 1; }
    if [ -f "$MINDSPACE_DIR/requirements.txt" ]; then
        pip3 install -q -r "$MINDSPACE_DIR/requirements.txt" 2>/dev/null || warn "pip had issues"
    fi
    python3 -c "import torch; print(f'Torch {torch.__version__}')" 2>/dev/null || warn "PyTorch not available"
    info "All prerequisites met"
    return 0
}

# ─── Sync auto-learn data to MindSpace trainer ─────────────────────────────
sync_auto_learn_data() {
    local trainer_dir="$MINDSPACE_DIR/trainer"
    mkdir -p "$trainer_dir"

    # 1. Write consolidated auto-learn datasheet (overwrite to avoid duplicates)
    local out="$trainer_dir/datasheet-auto-learn.jsonl"
    > "$out"
    local count=0
    for f in "$AUTO_LEARN_DIR"/interactions-*.jsonl; do
        [ -f "$f" ] || continue
        cat "$f" >> "$out"
        count=$(( count + $(grep -c '.' "$f" 2>/dev/null || echo 0) ))
    done
    info "Synced $count auto-learn records to datasheet-auto-learn.jsonl"

    # 2. Copy local project datasheets that the external doesn't have yet
    local local_trainer="$PROJECT_ROOT/MindSpace/trainer"
    if [ -d "$local_trainer" ]; then
        for f in "$local_trainer"/*.jsonl; do
            [ -f "$f" ] || continue
            local base="$(basename "$f")"
            [ "$base" = "datasheet-auto-learn.jsonl" ] && continue
            [ -f "$trainer_dir/$base" ] && continue
            cp "$f" "$trainer_dir/$base"
            info "Copied local: $base"
        done
    fi
    return 0
}

# ─── Run progressive training ──────────────────────────────────────────────
run_training() {
    local start_time=$(date +%s)
    info "Starting progressive training on $GPU_DEVICE (memory: ${MEMORY_FRACTION}, batch: 4)..."
    info "  target-acc: ${TARGET_ACC}% | max-epochs: ${MAX_EPOCHS_PER_TIER}"

    cd "$MINDSPACE_DIR"
    python3 scripts/progressive_train.py \
        --device "$GPU_DEVICE" \
        --memory-fraction "$MEMORY_FRACTION" \
        --target-acc "$TARGET_ACC" \
        --max-epochs-per-tier "$MAX_EPOCHS_PER_TIER" \
        --model-type lstm \
        --batch-size 4 \
        --lr 0.001 \
        --seq-len 64 \
        --embed-dim 64 \
        --hidden-dim 64 \
        2>&1 | tee -a "$DAEMON_LOG"

    local exit_code=$?
    local duration=$(( $(date +%s) - start_time ))
    cd "$PROJECT_ROOT"

    if [ $exit_code -eq 0 ]; then
        info "Training completed in ${duration}s"
        touch "$INITIAL_TRAINED_FILE"
        curl -s -X POST http://localhost:3001/api/auto-learn/record \
            -H 'Content-Type: application/json' \
            -d '{"type":"feedback","content":"MindSpace training completed on cuda:1","metadata":{"gpu":"cuda:1","memory_fraction":"0.4","duration_s":"'"$duration"'"}}' \
            >/dev/null 2>&1 || true
    else
        error "Training failed (exit: $exit_code, ${duration}s)"
    fi
    return $exit_code
}

# ─── Polling loop ──────────────────────────────────────────────────────────
poll_loop() {
    info "Polling loop started (interval: ${POLL_INTERVAL}s, min-retrain: ${MIN_TRAIN_INTERVAL}s)"
    local last_train_time=0
    local trigger_file="/tmp/mindspace-daemon-trigger"
    local backoff=1

    while true; do
        local now=$(date +%s)
        local elapsed=$(( now - last_train_time ))
        local effective_interval=$(( MIN_TRAIN_INTERVAL * backoff ))
        local should_train=false

        if [ -f "$trigger_file" ]; then
            local ttime=$(stat -c %Y "$trigger_file" 2>/dev/null || echo 0)
            [ "$ttime" -gt "$last_train_time" ] && should_train=true && info "Trigger file detected"
        fi

        if [ "$should_train" = false ] && [ $elapsed -ge "$effective_interval" ]; then
            local dc=$(find "$AUTO_LEARN_DIR" -name 'interactions-*.jsonl' -newer "$INITIAL_TRAINED_FILE" 2>/dev/null | wc -l)
            { [ "$dc" -gt 0 ] || [ ! -f "$INITIAL_TRAINED_FILE" ]; } && should_train=true
        fi

        if [ "$should_train" = true ] && [ $elapsed -ge "$effective_interval" ]; then
            rm -f "$trigger_file"
            info "Training (backoff: ${backoff}x)..."
            sync_auto_learn_data
            if run_training; then
                last_train_time=$(date +%s); backoff=1
            else
                backoff=$(( backoff * 2 )); [ "$backoff" -gt 8 ] && backoff=8
                warn "Backoff: ${backoff}x"
            fi
        elif [ "$should_train" = true ]; then
            info "Too soon (${elapsed}s < ${effective_interval}s with ${backoff}x backoff)"
        fi
        sleep "$POLL_INTERVAL"
    done
}

# ─── Commands ──────────────────────────────────────────────────────────────
cmd_start() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null && { error "Already running"; exit 1; }
    check_prereqs || exit 1
    sync_auto_learn_data
    nohup "$0" _poll >> "$DAEMON_LOG" 2>&1 &
    local pid=$!; echo "$pid" > "$PID_FILE"
    info "Daemon started (PID: $pid) | GPU: $GPU_DEVICE @ ${MEMORY_FRACTION}% | Log: $DAEMON_LOG"
}

cmd_stop() {
    [ ! -f "$PID_FILE" ] && { warn "No PID file"; exit 1; }
    local pid=$(cat "$PID_FILE")
    kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null && info "Stopped (PID: $pid)" || warn "Not running"
    rm -f "$PID_FILE"
}

cmd_status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        info "Daemon: RUNNING (PID: $(cat "$PID_FILE"))"
    else
        info "Daemon: STOPPED"
    fi
    echo ""
    echo "  GPU 1:"; nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader -i 1 2>/dev/null || echo "  N/A"
    echo ""
    echo "  Auto-learn files: $(find "$AUTO_LEARN_DIR" -name 'interactions-*.jsonl' 2>/dev/null | wc -l)"
    echo "  MindSpace datasheets: $(find "$MINDSPACE_DIR/trainer" -name 'datasheet-*.jsonl' 2>/dev/null | wc -l)"
    echo "  Initial trained: $([ -f "$INITIAL_TRAINED_FILE" ] && echo 'Yes' || echo 'No')"
    echo ""
    tail -5 "$DAEMON_LOG" 2>/dev/null || echo "  (no log)"
}

cmd_train_now() { check_prereqs || exit 1; sync_auto_learn_data; run_training; }
cmd_dry_run() {
    check_prereqs || exit 1
    cd "$MINDSPACE_DIR"
    python3 scripts/progressive_train.py --dry-run --device "$GPU_DEVICE" --memory-fraction "$MEMORY_FRACTION" 2>&1
    cd "$PROJECT_ROOT"
}

# ─── Main ──────────────────────────────────────────────────────────────────
case "${1:-help}" in
    start)      cmd_start ;;
    stop)       cmd_stop ;;
    restart)    cmd_stop; sleep 2; cmd_start ;;
    status)     cmd_status ;;
    train-now)  cmd_train_now ;;
    dry-run)    cmd_dry_run ;;
    _poll)      poll_loop ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|train-now|dry-run}"
        exit 1
        ;;
esac
