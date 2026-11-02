<#
install_postgres_windows.ps1
Automates cleanup of stale Chocolatey locks, installs PostgreSQL via Chocolatey,
creates database and DB user, and sets DATABASE_URL environment variable.

USAGE: Right-click -> Run with PowerShell (Run as Administrator)
#>

function Assert-RunningAsAdmin {
    $current = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $current.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
        Write-Error "This script must be run as Administrator. Right-click and choose 'Run as Administrator'."
        exit 1
    }
}

Assert-RunningAsAdmin

param(
    [Parameter(Mandatory=$false)]
    [string]$PostgresPassword = $(Read-Host -AsSecureString "Enter password for new DB user 'hias_writer'" | ConvertFrom-SecureString -AsPlainText),
    [Parameter(Mandatory=$false)]
    [string]$DbName = "hias_storage",
    [Parameter(Mandatory=$false)]
    [string]$DbUser = "hias_writer"
)

Write-Host "Starting Chocolatey cleanup and PostgreSQL install..." -ForegroundColor Cyan

# Stop any running chocolatey processes
Try {
    Get-Process -Name choco -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
} Catch { }

# Confirm before removing directories
$confirm = Read-Host "About to remove possible stale Chocolatey lock folders (C:\ProgramData\chocolatey\lib-bad and C:\ProgramData\chocolatey\lib\postgresql*). Continue? (Y/N)"
if ($confirm -ne 'Y' -and $confirm -ne 'y') {
    Write-Host "Aborting by user request." -ForegroundColor Yellow
    exit 0
}

$pathsToRemove = @(
    'C:\ProgramData\chocolatey\lib-bad',
    'C:\ProgramData\chocolatey\lib\postgresql*',
    'C:\ProgramData\chocolatey\lib\postgresql18*'
)

foreach ($p in $pathsToRemove) {
    Try {
        if (Test-Path $p) {
            Write-Host "Removing $p" -ForegroundColor Yellow
            Remove-Item -Path $p -Recurse -Force -ErrorAction Stop
        }
    } Catch {
        Write-Warning "Failed to remove $p: $_. Exception.Message"
    }
}

# Install PostgreSQL via Chocolatey
Write-Host "Installing PostgreSQL via Chocolatey..." -ForegroundColor Cyan
choco install postgresql -y
if ($LASTEXITCODE -ne 0) {
    Write-Error "Chocolatey install failed (exit code $LASTEXITCODE). Check C:\ProgramData\chocolatey\logs\chocolatey.log for details.";
    exit 2
}

# Refresh environment variables in this session if refreshenv is available
Try { refreshenv } Catch { }

# Find psql.exe
$psqlPath = Get-Command psql -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue
if (-not $psqlPath) {
    # Try typical Program Files path
    $pgRoot = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($pgRoot) {
        $candidate = Join-Path $pgRoot.FullName 'bin\psql.exe'
        if (Test-Path $candidate) { $psqlPath = $candidate }
    }
}

if (-not $psqlPath) {
    Write-Error "psql not found in PATH and Postgres install path not found. Please open a new shell or add psql to PATH."
    exit 3
}

Write-Host "Using psql at: $psqlPath" -ForegroundColor Green

# Prompt for postgres superuser password if needed (interactive)
Write-Host "Creating database and DB user (requires postgres superuser)." -ForegroundColor Cyan
$pgSuper = Read-Host "If 'postgres' superuser requires a password to run psql non-interactively, enter it now (leave blank to run interactive psql)" -AsSecureString
$pgSuperPlain = ""
if ($pgSuper -and $pgSuper.Length -gt 0) { $pgSuperPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgSuper)) }

# Create user and DB using psql
$createUserSql = "CREATE USER $DbUser WITH PASSWORD '${PostgresPassword}' NOSUPERUSER NOCREATEDB NOCREATEROLE;"
$createDbSql = "CREATE DATABASE $DbName OWNER $DbUser;"

Write-Host "Running SQL to create user and database..." -ForegroundColor Cyan
# Use interactive psql if no super password provided
if ($pgSuperPlain -eq "") {
    & $psqlPath -U postgres -c $createUserSql
    if ($LASTEXITCODE -ne 0) { Write-Warning "User creation may have failed." }
    & $psqlPath -U postgres -c $createDbSql
    if ($LASTEXITCODE -ne 0) { Write-Warning "Database creation may have failed." }
} else {
    # Inline password via PGPASSWORD environment for one-shot commands
    $env:PGPASSWORD = $pgSuperPlain
    & $psqlPath -U postgres -c $createUserSql
    & $psqlPath -U postgres -c $createDbSql
    Remove-Item Env:PGPASSWORD
}

# Persist DATABASE_URL (user-scope)
$databaseUrl = "postgresql://$DbUser:$PostgresPassword@localhost:5432/$DbName"
setx DATABASE_URL $databaseUrl | Out-Null
Write-Host "DATABASE_URL saved to user environment variables." -ForegroundColor Green

# Optionally apply schema if a schema file exists in repo
$schemaPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..\app\sql\schema.sql' | Resolve-Path -ErrorAction SilentlyContinue
if ($schemaPath) {
    Write-Host "Applying schema from $schemaPath" -ForegroundColor Cyan
    & $psqlPath -U postgres -d $DbName -f $schemaPath
    if ($LASTEXITCODE -ne 0) { Write-Warning "Applying schema returned a non-zero exit code." }
}

Write-Host "PostgreSQL install and DB setup complete. Restart any open terminals to pick up the new environment variable." -ForegroundColor Green
Write-Host "Next: activate your Python venv and install requirements in storage-service, then run the app." -ForegroundColor Cyan

exit 0
