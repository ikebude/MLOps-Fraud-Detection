#!/bin/bash
###############################################################################
# start-producer.sh - Start the Transaction Producer with Health Checks
#
# This script validates the environment, checks database connectivity,
# and starts the transaction producer with proper error handling.
#
# Usage:
#   ./scripts/start-producer.sh [--env-file .env] [--port 5001] [--no-docker]
#
# Environment Variables:
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
#   PRODUCER_INTERVAL, PRODUCER_BATCH_SIZE, LOG_LEVEL
###############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENV_FILE="${1:-.env}"
PRODUCER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/producer"
LOG_FILE="${PRODUCER_DIR}/producer.log"
HEALTH_CHECK_PORT="5001"
DOCKER_MODE="true"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --port)
            HEALTH_CHECK_PORT="$2"
            shift 2
            ;;
        --no-docker)
            DOCKER_MODE="false"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to print colored output
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }

# Header
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Transaction Producer - Startup Script     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# Load environment
if [ -f "$ENV_FILE" ]; then
    print_info "Loading environment from: $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
    print_success "Environment loaded"
else
    print_warning "No .env file found at $ENV_FILE"
    print_info "Using defaults (may fail if not set in environment)"
fi

# Defaults
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-transactions_db}"
DB_USER="${DB_USER:-fraud_user}"
PRODUCER_INTERVAL="${PRODUCER_INTERVAL:-0.5}"
PRODUCER_BATCH_SIZE="${PRODUCER_BATCH_SIZE:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Display configuration
print_info "Configuration:"
echo "  Database Host: $DB_HOST:$DB_PORT"
echo "  Database Name: $DB_NAME"
echo "  Database User: $DB_USER"
echo "  Interval: ${PRODUCER_INTERVAL}s"
echo "  Batch Size: $PRODUCER_BATCH_SIZE"
echo "  Log Level: $LOG_LEVEL"
echo ""

# Check if password is set
if [ -z "$DB_PASSWORD" ]; then
    print_error "DB_PASSWORD is not set"
    print_info "Please set DB_PASSWORD in your .env file or environment"
    exit 1
fi

# Function to check database connectivity
check_database() {
    print_info "Checking database connectivity..."
    
    local max_retries=5
    local retry_count=0
    local retry_delay=2
    
    while [ $retry_count -lt $max_retries ]; do
        if nc -zv "$DB_HOST" "$DB_PORT" &>/dev/null; then
            print_success "Database is reachable"
            return 0
        else
            retry_count=$((retry_count + 1))
            if [ $retry_count -lt $max_retries ]; then
                print_warning "Database not reachable (attempt $retry_count/$max_retries). Retrying in ${retry_delay}s..."
                sleep $retry_delay
                retry_delay=$((retry_delay * 2))
            fi
        fi
    done
    
    print_error "Database is not reachable after $max_retries attempts"
    return 1
}

# Function to check Python dependencies
check_dependencies() {
    print_info "Checking Python dependencies..."
    
    local missing_deps=()
    
    # Check key dependencies
    for pkg in psycopg2 faker jsonschema dotenv; do
        if ! python3 -c "import ${pkg}" 2>/dev/null; then
            missing_deps+=("$pkg")
        fi
    done
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_error "Missing Python dependencies: ${missing_deps[*]}"
        print_info "Install with: pip install -r producer/requirements.txt"
        return 1
    fi
    
    print_success "All dependencies are available"
    return 0
}

# Function to check table existence
check_transactions_table() {
    print_info "Checking transactions table..."
    
    # Create temporary .pgpass for authentication
    local pgpass_dir=$(mktemp -d)
    local pgpass_file="$pgpass_dir/.pgpass"
    echo "$DB_HOST:$DB_PORT:$DB_NAME:$DB_USER:$DB_PASSWORD" > "$pgpass_file"
    chmod 600 "$pgpass_file"
    
    if PGPASSFILE="$pgpass_file" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -c "SELECT 1 FROM information_schema.tables WHERE table_name='transactions' LIMIT 1;" &>/dev/null; then
        print_success "Transactions table exists"
        rm -rf "$pgpass_dir"
        return 0
    else
        print_warning "Transactions table not found"
        print_info "Producer will create it on startup"
        rm -rf "$pgpass_dir"
        return 0
    fi
}

# Function to show health check info
show_health_check_info() {
    echo ""
    print_info "Health Check Information:"
    echo "  When producer is running, check status with:"
    echo ""
    echo "  ${YELLOW}curl http://localhost:${HEALTH_CHECK_PORT}/health${NC}"
    echo ""
    echo "  This returns:"
    echo "  - Status (healthy/unhealthy)"
    echo "  - Transactions generated"
    echo "  - Fraud count"
    echo "  - Generation rate (txn/sec)"
    echo ""
}

# Pre-flight checks
print_info "Running pre-flight checks..."
echo ""

if ! check_database; then
    print_error "Pre-flight check failed"
    exit 1
fi

if ! check_dependencies; then
    print_error "Pre-flight check failed"
    exit 1
fi

if ! check_transactions_table; then
    print_warning "Could not verify transactions table, but producer will attempt to create it"
fi

echo ""
print_success "All pre-flight checks passed"
echo ""

# Start producer
print_info "Starting transaction producer..."
echo ""
echo "Log output:" "$LOG_FILE"
echo "To view: tail -f \"$LOG_FILE\""
echo ""
echo -e "${GREEN}Producer is starting... (Press Ctrl+C to stop)${NC}"
echo ""

# Export environment for producer script
export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
export PRODUCER_INTERVAL PRODUCER_BATCH_SIZE LOG_LEVEL

# Create startup timestamp
START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$START_TIME] Producer started" >> "$LOG_FILE"

# Run producer with logging
cd "$PRODUCER_DIR"

if [ "$DOCKER_MODE" = "true" ]; then
    # Docker mode - assume we're in container
    python3 main.py 2>&1 | tee -a "$LOG_FILE"
else
    # Local mode
    python3 main.py 2>&1 | tee -a "$LOG_FILE"
fi

# Cleanup on exit
trap 'print_info "Shutting down producer..."; exit 0' EXIT INT TERM

EOF_MARKER





