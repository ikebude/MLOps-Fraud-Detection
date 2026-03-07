<#
.SYNOPSIS
    Start the Transaction Producer with Pre-flight Checks

.DESCRIPTION
    This script validates the environment, checks database connectivity,
    and starts the transaction producer with proper error handling.

.PARAMETER EnvFile
    Path to .env file (default: .env)

.PARAMETER Verbose
    Show detailed output during startup

.EXAMPLE
    .\scripts\start-producer.ps1
    .\scripts\start-producer.ps1 -EnvFile "custom.env" -Verbose

.NOTES
    Requires: Python 3.8+, PostgreSQL client tools
#>

param(
    [string]$EnvFile = ".env",
    [switch]$Verbose
)

# Set error action preference
$ErrorActionPreference = "Continue"

# Colors
$Info = "Cyan"
$Success = "Green"
$Warning = "Yellow"
$Error = "Red"

# Functions
function Write-Info { Write-Host "[INFO]" -ForegroundColor $Info -NoNewline; Write-Host " $args" }
function Write-Success { Write-Host "[✓]" -ForegroundColor $Success -NoNewline; Write-Host " $args" }
function Write-Warning { Write-Host "[WARN]" -ForegroundColor $Warning -NoNewline; Write-Host " $args" }
function Write-Error { Write-Host "[✗]" -ForegroundColor $Error -NoNewline; Write-Host " $args" }

function Load-EnvFile {
    param([string]$FilePath)
    
    if (Test-Path $FilePath) {
        Write-Info "Loading environment from: $FilePath"
        $content = Get-Content $FilePath
        foreach ($line in $content) {
            if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) { continue }
            $key, $value = $line -split '=', 2
            [Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), [EnvironmentVariableTarget]::Process)
        }
        Write-Success "Environment loaded"
        return $true
    }
    else {
        Write-Warning "No .env file found at $FilePath"
        Write-Info "Using defaults (may fail if not set in environment)"
        return $false
    }
}

function Check-Database {
    Write-Info "Checking database connectivity..."
    
    $host = $env:DB_HOST ?? "127.0.0.1"
    $port = $env:DB_PORT ?? "5432"
    
    $maxRetries = 5
    $retryCount = 0
    $retryDelay = 2
    
    while ($retryCount -lt $maxRetries) {
        try {
            $tcpClient = New-Object System.Net.Sockets.TcpClient
            $tcpClient.Connect($host, [int]$port)
            $tcpClient.Close()
            Write-Success "Database is reachable"
            return $true
        }
        catch {
            $retryCount++
            if ($retryCount -lt $maxRetries) {
                Write-Warning "Database not reachable (attempt $retryCount/$maxRetries). Retrying in ${retryDelay}s..."
                Start-Sleep -Seconds $retryDelay
                $retryDelay *= 2
            }
        }
    }
    
    Write-Error "Database is not reachable after $maxRetries attempts"
    return $false
}

function Check-Dependencies {
    Write-Info "Checking Python dependencies..."
    
    $missingDeps = @()
    $deps = @("psycopg2", "faker", "jsonschema", "dotenv")
    
    foreach ($pkg in $deps) {
        $result = & python3 -c "import $pkg" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $missingDeps += $pkg
        }
    }
    
    if ($missingDeps.Count -gt 0) {
        Write-Error "Missing Python dependencies: $($missingDeps -join ', ')"
        Write-Info "Install with: pip install -r producer\requirements.txt"
        return $false
    }
    
    Write-Success "All dependencies are available"
    return $true
}

function Check-TransactionsTable {
    Write-Info "Checking transactions table..."
    
    $host = $env:DB_HOST ?? "127.0.0.1"
    $port = $env:DB_PORT ?? "5432"
    $dbname = $env:DB_NAME ?? "transactions_db"
    $user = $env:DB_USER ?? "fraud_user"
    $password = $env:DB_PASSWORD
    
    if ([string]::IsNullOrEmpty($password)) {
        Write-Warning "DB_PASSWORD not set, skipping table check"
        return $true
    }
    
    try {
        $pgpassword = $password
        $output = & psql -h $host -p $port -U $user -d $dbname -c "SELECT 1 FROM information_schema.tables WHERE table_name='transactions' LIMIT 1;" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Transactions table exists"
            return $true
        }
    }
    catch {
        Write-Warning "Could not verify transactions table (producer will create it on startup)"
        return $true
    }
    
    Write-Warning "Could not verify transactions table (producer will create it on startup)"
    return $true
}

# Main Script
Write-Host ""
Write-Host "╔════════════════════════════════════════════╗" -ForegroundColor $Info
Write-Host "║  Transaction Producer - Startup Script     ║" -ForegroundColor $Info
Write-Host "╚════════════════════════════════════════════╝" -ForegroundColor $Info
Write-Host ""

# Load environment
$envLoaded = Load-EnvFile $EnvFile
Write-Host ""

# Set defaults
$DB_HOST = $env:DB_HOST ?? "127.0.0.1"
$DB_PORT = $env:DB_PORT ?? "5432"
$DB_NAME = $env:DB_NAME ?? "transactions_db"
$DB_USER = $env:DB_USER ?? "fraud_user"
$PRODUCER_INTERVAL = $env:PRODUCER_INTERVAL ?? "0.5"
$PRODUCER_BATCH_SIZE = $env:PRODUCER_BATCH_SIZE ?? "1"
$LOG_LEVEL = $env:LOG_LEVEL ?? "INFO"

# Display configuration
Write-Info "Configuration:"
Write-Host "  Database Host: $DB_HOST`:$DB_PORT" -ForegroundColor Gray
Write-Host "  Database Name: $DB_NAME" -ForegroundColor Gray
Write-Host "  Database User: $DB_USER" -ForegroundColor Gray
Write-Host "  Interval: ${PRODUCER_INTERVAL}s" -ForegroundColor Gray
Write-Host "  Batch Size: $PRODUCER_BATCH_SIZE" -ForegroundColor Gray
Write-Host "  Log Level: $LOG_LEVEL" -ForegroundColor Gray
Write-Host ""

# Check password
if ([string]::IsNullOrEmpty($env:DB_PASSWORD)) {
    Write-Error "DB_PASSWORD is not set"
    Write-Info "Please set DB_PASSWORD in your .env file or environment"
    exit 1
}

# Pre-flight checks
Write-Info "Running pre-flight checks..."
Write-Host ""

if (-not (Check-Database)) {
    Write-Error "Pre-flight check failed"
    exit 1
}

if (-not (Check-Dependencies)) {
    Write-Error "Pre-flight check failed"
    exit 1
}

if (-not (Check-TransactionsTable)) {
    Write-Warning "Could not verify transactions table, but producer will attempt to create it"
}

Write-Host ""
Write-Success "All pre-flight checks passed"
Write-Host ""

# Start producer
Write-Info "Starting transaction producer..."
Write-Host ""
Write-Host "Log output: producer\producer.log" -ForegroundColor Gray
Write-Host "To view: Get-Content producer\producer.log -Tail 50 -Wait" -ForegroundColor Gray
Write-Host ""
Write-Host "Producer is starting... (Press Ctrl+C to stop)" -ForegroundColor $Success
Write-Host ""

# Create logs directory if needed
$logsDir = Join-Path (Get-Location) "producer"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

# Start producer
$startTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$startTime] Producer started" | Out-File -FilePath "producer\producer.log" -Append

Push-Location producer
try {
    & python3 main.py 2>&1 | Tee-Object -FilePath "..\producer\producer.log" -Append
}
finally {
    Pop-Location
    Write-Info "Producer shutdown complete"
}





