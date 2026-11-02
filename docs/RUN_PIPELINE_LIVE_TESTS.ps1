$ErrorActionPreference = "Stop"
$script:StartedServiceProcesses = @()
$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Test-HealthEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSeconds = 5
    )

    try {
        Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSeconds | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Wait-ForHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HealthEndpoint -Uri $Uri) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Ensure-ServiceRunning {
    param(
        [Parameter(Mandatory = $true)][string]$ServiceName,
        [Parameter(Mandatory = $true)][string]$HealthUri,
        [Parameter(Mandatory = $true)][string]$RelativeServiceDir
    )

    if (Test-HealthEndpoint -Uri $HealthUri) {
        Write-Host "$ServiceName is already healthy." -ForegroundColor DarkGreen
        return
    }

    $serviceDir = (Resolve-Path (Join-Path $script:RepoRoot $RelativeServiceDir)).Path
    Write-Host "Starting $ServiceName..." -ForegroundColor DarkCyan
    $proc = Start-Process -FilePath "python" -ArgumentList "-m", "app.main" -WorkingDirectory $serviceDir -WindowStyle Hidden -PassThru
    $script:StartedServiceProcesses += $proc

    if (-not (Wait-ForHealth -Uri $HealthUri -TimeoutSeconds 30)) {
        try { $proc.Refresh() } catch {}
        if ($proc.HasExited) {
            throw "$ServiceName failed to start (process exited with code $($proc.ExitCode))."
        }
        throw "$ServiceName did not become healthy at $HealthUri within timeout."
    }

    Write-Host "$ServiceName is healthy." -ForegroundColor Green
}

function Ensure-PipelineServicesHealthy {
    Write-Host "Checking health endpoints..." -ForegroundColor Cyan
    Ensure-ServiceRunning -ServiceName "Ingestion Service" -HealthUri "http://127.0.0.1:8002/health" -RelativeServiceDir "ingestion-service"
    Ensure-ServiceRunning -ServiceName "Recognition Service" -HealthUri "http://127.0.0.1:8003/health" -RelativeServiceDir "recognition-service"
    Ensure-ServiceRunning -ServiceName "Intelligence Service" -HealthUri "http://127.0.0.1:8004/health" -RelativeServiceDir "intelligence-service"
    Write-Host "All 3 services are healthy." -ForegroundColor Green
}

function Stop-StartedServices {
    if ($script:StartedServiceProcesses.Count -eq 0) {
        return
    }

    Write-Host "Stopping services started by this script..." -ForegroundColor DarkGray
    foreach ($proc in $script:StartedServiceProcesses) {
        try {
            $proc.Refresh()
            if (-not $proc.HasExited) {
                Stop-Process -Id $proc.Id -Force -ErrorAction Stop
                Write-Host "Stopped process $($proc.Id)." -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "Warning: Failed to stop process $($proc.Id): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

function Post-Json {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][object]$Body
    )
    return Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20)
}

function Invoke-Pipeline {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Raw
    )

    $ing = Post-Json -Uri "http://127.0.0.1:8002/ingest" -Body $Raw
    $rec = Post-Json -Uri "http://127.0.0.1:8003/recognize" -Body $ing
    $intelReq = @{
        recognition_event = $rec
        context = @{
            camera_id = $ing.camera_id
            zone = $ing.zone
        }
    }
    $intel = Post-Json -Uri "http://127.0.0.1:8004/process" -Body $intelReq

    return @{
        ingestion = $ing
        recognition = $rec
        intelligence = $intel
        final_event = $intel.final_event
    }
}

function Find-StatusCase {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedStatus,
        [Parameter(Mandatory = $true)][int]$ImageSize,
        [int]$MaxAttempts = 200
    )

    # Use future UTC timestamps so previous in-memory student history does not force
    # transition anomalies from older events.
    $base = [datetime]::UtcNow.AddDays(1)
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        $ts = $base.AddSeconds($i * 31).ToString("yyyy-MM-ddTHH:mm:ssZ")
        $raw = @{
            timestamp = $ts
            camera_id = "GATE-MAIN"
            zone = "GATE_MAIN"
            sequence_num = 600000 + $i
            image_data = @{
                format = "jpeg"
                size = $ImageSize
                url = "sim://live-test/$ExpectedStatus-$i.jpg"
            }
        }

        try {
            $result = Invoke-Pipeline -Raw $raw
            if ($result.final_event.status -eq $ExpectedStatus) {
                return @{
                    payload = $raw
                    result = $result
                }
            }
        } catch {
            continue
        }
    }

    throw "Could not find a payload producing status '$ExpectedStatus' in $MaxAttempts attempts."
}

try {
    Ensure-PipelineServicesHealthy

    Write-Host "Finding AUTO case..." -ForegroundColor Cyan
    $autoCase = Find-StatusCase -ExpectedStatus "AUTO" -ImageSize 12013
    Write-Host "AUTO found: $($autoCase.result.final_event.trace_id)" -ForegroundColor Green

    Write-Host "Finding REVIEW case..." -ForegroundColor Cyan
    $reviewCase = Find-StatusCase -ExpectedStatus "REVIEW" -ImageSize 12000
    Write-Host "REVIEW found: $($reviewCase.result.final_event.trace_id)" -ForegroundColor Green

    Write-Host "Finding REJECT case..." -ForegroundColor Cyan
    $rejectCase = Find-StatusCase -ExpectedStatus "REJECT" -ImageSize 12026
    Write-Host "REJECT found: $($rejectCase.result.final_event.trace_id)" -ForegroundColor Green

    Write-Host "Testing duplicate handling (same event twice)..." -ForegroundColor Cyan
    $dupFirst = Invoke-Pipeline -Raw $autoCase.payload
    $dupSecond = Invoke-Pipeline -Raw $autoCase.payload

    $duplicateOk = $false
    $duplicateMetadata = $dupSecond.intelligence.intelligence_event.metadata
    if ($dupSecond.final_event.status -eq "REJECT" -and $duplicateMetadata.ignored_duplicate -eq $true) {
        $duplicateOk = $true
    }

    Write-Host "Testing structured error case (missing image)..." -ForegroundColor Cyan
    $errorCaseOk = $false
    try {
        $bad = @{
            timestamp = "2026-04-28T22:30:00Z"
            camera_id = "GATE-MAIN"
            zone = "GATE_MAIN"
            sequence_num = 999999
        }
        Invoke-Pipeline -Raw $bad | Out-Null
    } catch {
        $body = $_.ErrorDetails.Message
        if (-not $body) {
            $resp = $_.Exception.Response
            if ($resp) {
                $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
                $body = $reader.ReadToEnd()
            }
        }
        if ($body -match "ERR_INVALID_PAYLOAD") {
            $errorCaseOk = $true
        }
    }

    $summary = [PSCustomObject]@{
        AutoStatus = $autoCase.result.final_event.status
        ReviewStatus = $reviewCase.result.final_event.status
        RejectStatus = $rejectCase.result.final_event.status
        DuplicateSecondStatus = $dupSecond.final_event.status
        DuplicateIgnored = [bool]$duplicateOk
        ErrorCaseHandled = [bool]$errorCaseOk
    }

    Write-Host ""
    Write-Host "=== LIVE TEST SUMMARY ===" -ForegroundColor Yellow
    $summary | Format-List

    if (-not $duplicateOk) {
        throw "Duplicate handling check failed."
    }
    if (-not $errorCaseOk) {
        throw "Error handling check failed."
    }
    if ($summary.AutoStatus -ne "AUTO" -or $summary.ReviewStatus -ne "REVIEW" -or $summary.RejectStatus -ne "REJECT") {
        throw "Status coverage check failed."
    }

    Write-Host ""
    Write-Host "All live tests passed." -ForegroundColor Green
} finally {
    Stop-StartedServices
}
