# Directory and date
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$logDir = Join-Path $scriptDir 'logs'
$date   = Get-Date -Format 'yyyy-MM-dd'

# Logs to rotate
$files = @('out.log', 'err.log')

foreach ($file in $files) {
    $fullPath = Join-Path $logDir $file
    if (Test-Path $fullPath) {
        # Build archive name
        $name    = [System.IO.Path]::GetFileNameWithoutExtension($file)
        $ext     = [System.IO.Path]::GetExtension($file).TrimStart('.')
        $archive = "$name-$date.$ext"

# Move current log to dated archive and recreate
        Move-Item -Path $fullPath -Destination (Join-Path $logDir $archive)
        New-Item -Path $fullPath -ItemType File -Force | Out-Null
    }
}