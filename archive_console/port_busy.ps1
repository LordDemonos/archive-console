<#
  Exit 0 if LocalPort has any LISTEN socket, else exit 1.
  Used by start_archive_console.bat (after health check failed).
#>
param(
    [Parameter(Mandatory = $true)]
    [int] $Port
)

$c = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count
if ($c -gt 0) { exit 0 }
exit 1
