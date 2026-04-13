#!/bin/bash
# REX-US v7 — Progressive Wave Testing (Waves 2-5)
#
# Runs each wave through the /analyze endpoint, which:
#   1. Performs hybrid search (vector + keyword) against rexus_incidents_v3
#   2. Applies CMDB soft family boost + Open problem prioritization (v7 logic)
#   3. Generates focused playbook
#   4. Progressive learning: inserts the incident + embedding into rexus_incidents_v3
#
# After all 4 waves, all 1,398 incidents (waves 2-5) will be in the knowledge base,
# joining the ~500 from wave 1 = ~1,898 total test incidents added to production data.
#
# Prerequisites:
#   - Backend running on http://localhost:8000
#   - Database accessible
#   - OpenAI API key configured

set -e

cd /Users/premkalyan/code/REX-US
PYTHON=/Users/premkalyan/code/REX-US/backend/.venv/bin/python
LOGDIR=/Users/premkalyan/code/REX-US/data/v7_wave_logs
mkdir -p "$LOGDIR"

# Check backend is running
API_HOST="${REXUS_API_BASE:-http://localhost:8000}"
echo "Checking backend at $API_HOST..."
if ! curl -sf "$API_HOST/health" > /dev/null 2>&1; then
    echo "ERROR: Backend not running at $API_HOST"
    echo "Start it with: cd backend && .venv/bin/uvicorn api.main:app --reload"
    exit 1
fi
echo "Backend is healthy."

# DB connection helper (using Python since we may not have psql)
db_query() {
    $PYTHON -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
import psycopg2
from urllib.parse import urlparse, unquote
url = os.getenv('DATABASE_URL','').replace('+asyncpg','').replace('postgresql://','http://')
parsed = urlparse(url)
conn = psycopg2.connect(host=parsed.hostname, port=parsed.port, database=unquote(parsed.path.lstrip('/').split('?')[0]), user=unquote(parsed.username), password=unquote(parsed.password))
cur = conn.cursor()
cur.execute(\"\"\"$1\"\"\")
rows = cur.fetchall()
if cur.description:
    cols = [d[0] for d in cur.description]
    print(' | '.join(cols))
    print('-' * 80)
    for r in rows:
        print(' | '.join(str(v) for v in r))
conn.close()
" 2>&1
}

# Show KB size before starting
echo ""
echo "================================================================"
echo "  REX-US v7 PROGRESSIVE WAVE TESTING — Waves 2 through 5"
echo "  Started: $(date)"
echo "================================================================"

echo ""
echo "Knowledge base before testing:"
db_query "SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE split_group = 'training') as training, COUNT(*) FILTER (WHERE split_group = 'analyzed') as analyzed FROM rexus_incidents_v3 WHERE embedding IS NOT NULL"

# Clear any old v7 wave results for waves 2-5 to avoid duplicates
echo ""
echo "Clearing old wave results for waves 2-5..."
$PYTHON -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
import psycopg2
from urllib.parse import urlparse, unquote
url = os.getenv('DATABASE_URL','').replace('+asyncpg','').replace('postgresql://','http://')
parsed = urlparse(url)
conn = psycopg2.connect(host=parsed.hostname, port=parsed.port, database=unquote(parsed.path.lstrip('/').split('?')[0]), user=unquote(parsed.username), password=unquote(parsed.password))
cur = conn.cursor()
cur.execute(\"DELETE FROM rexus_wave_results WHERE wave IN ('wave_2','wave_3','wave_4','wave_5')\")
deleted = cur.rowcount
conn.commit()
conn.close()
print(f'Cleared {deleted} old results')
" 2>&1

run_wave() {
    local wave=$1
    local total=$2
    local batch_size=50

    echo ""
    echo "================================================================"
    echo "  WAVE: $wave ($total incidents, batch_size=$batch_size)"
    echo "  Started: $(date)"
    echo "================================================================"

    for offset in $(seq 0 $batch_size $((total-1))); do
        local remaining=$((total - offset))
        local this_batch=$batch_size
        if [ $remaining -lt $batch_size ]; then
            this_batch=$remaining
        fi

        echo "  Running batch: offset=$offset count=$this_batch ..."
        $PYTHON backend/scripts/run_wave_test.py \
            --wave "$wave" \
            --count "$this_batch" \
            --offset "$offset" \
            > "$LOGDIR/${wave}_offset${offset}.log" 2>&1

        # Show batch summary
        grep -E "Combined|Exact|Wrong|Missed|Avg confidence" "$LOGDIR/${wave}_offset${offset}.log" | tail -3
    done

    # Wave summary
    echo ""
    echo "--- $wave COMPLETE ---"
    db_query "SELECT problem_match_type, COUNT(*) as count FROM rexus_wave_results WHERE wave = '$wave' GROUP BY problem_match_type ORDER BY count DESC"

    echo ""
    echo "KB size after $wave:"
    db_query "SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE split_group = 'training') as training, COUNT(*) FILTER (WHERE split_group = 'analyzed') as analyzed FROM rexus_incidents_v3 WHERE embedding IS NOT NULL"

    echo "  Completed: $(date)"
}

# Run waves 2-5 progressively
# Wave 1 (500) was already tested with v7
run_wave wave_2 300
run_wave wave_3 300
run_wave wave_4 300
run_wave wave_5 500

echo ""
echo "================================================================"
echo "  ALL WAVES COMPLETE"
echo "  Finished: $(date)"
echo "================================================================"

# Grand summary across all waves (including wave_1 if it exists)
echo ""
echo "RESULTS BY WAVE:"
db_query "SELECT wave, COUNT(*) as total, COUNT(*) FILTER (WHERE problem_match_type = 'exact_match') as exact, COUNT(*) FILTER (WHERE problem_match_type = 'top3_match') as top3, COUNT(*) FILTER (WHERE problem_match_type = 'wrong_suggestion') as wrong, COUNT(*) FILTER (WHERE problem_match_type = 'missed_suggestion') as missed, COUNT(*) FILTER (WHERE problem_match_type IN ('no_problem_no_suggest','suggested_no_actual')) as no_problem FROM rexus_wave_results GROUP BY wave ORDER BY wave"

echo ""
echo "GRAND TOTAL (all waves):"
db_query "SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE problem_match_type = 'exact_match') as exact, COUNT(*) FILTER (WHERE problem_match_type = 'top3_match') as top3, COUNT(*) FILTER (WHERE problem_match_type = 'wrong_suggestion') as wrong, COUNT(*) FILTER (WHERE problem_match_type = 'missed_suggestion') as missed, COUNT(*) FILTER (WHERE problem_match_type IN ('no_problem_no_suggest','suggested_no_actual')) as no_problem FROM rexus_wave_results"

echo ""
echo "FINAL KNOWLEDGE BASE SIZE:"
db_query "SELECT COUNT(*) as total_incidents, COUNT(*) FILTER (WHERE embedding IS NOT NULL) as with_embedding, COUNT(DISTINCT split_group) as split_groups FROM rexus_incidents_v3"

echo ""
echo "Progressive wave testing complete. All test incidents are now in the knowledge base."
echo "Logs saved to: $LOGDIR"
