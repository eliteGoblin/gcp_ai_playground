#!/bin/bash
# Script to run coaching with full logging for analysis

# Configuration
CONVERSATION_ID="${1:-a1b2c3d4-toxic-agent-test-0001}"
LOG_FILE="coach_debug_$(date +%Y%m%d_%H%M%S).log"

echo "=== Coaching Debug Run ===" | tee "$LOG_FILE"
echo "Conversation: $CONVERSATION_ID" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Started: $(date)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Activate venv
source .venv/bin/activate

# Set environment variables
export GOOGLE_APPLICATION_CREDENTIALS=/home/parallels/.config/gcloud/vertex-ai-demo-key.json
export GCP_PROJECT_ID=vertexdemo-481519
export RAG_GCS_BUCKET=vertexdemo-481519-cc-kb-docs
export RAG_DATA_STORE_ID=cc-knowledge-base

# Enable full prompt logging
export CC_LOG_FULL_PROMPT=true
export CC_LOG_LEVEL_PROMPT=INFO

# Set Python logging to DEBUG
export PYTHONUNBUFFERED=1

# Reset conversation status to ENRICHED so we can re-coach
echo "=== Resetting conversation status ===" | tee -a "$LOG_FILE"
bq query --use_legacy_sql=false "
UPDATE \`vertexdemo-481519.conversation_coach.conversation_registry\`
SET status = 'ENRICHED', coached_at = NULL
WHERE conversation_id = '$CONVERSATION_ID'
" 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "=== Running coaching with DEBUG logging ===" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Run coaching with full debug logging
python -c "
import logging
import sys

# Configure root logger to show everything
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Import and run
from cc_coach.services.coaching import CoachingOrchestrator

orchestrator = CoachingOrchestrator(allow_fallback=False)
result = orchestrator.generate_coaching('$CONVERSATION_ID')

print()
print('=== COACHING RESULT ===')
print(f'Overall Score: {result.overall_score}')
print(f'Call Type: {result.call_type}')
print(f'RAG Context Used: {result.rag_context_used}')
print(f'Citations: {result.citations}')
print()
print('Coaching Points:')
for cp in result.coaching_points:
    print(f'  - {cp.title}')
" 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "=== Completed: $(date) ===" | tee -a "$LOG_FILE"
echo "Log saved to: $LOG_FILE"
