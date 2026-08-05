# Start FastAPI in detached PowerShell, fully independent of this shell.
# 工作目录自动定位到项目根 (脚本所在 tools/ 的父目录), 跨用户/跨路径通用.
$script = @"
Set-Location "$PSScriptRoot\.."
`$proc = Start-Process -FilePath "python" -ArgumentList "main.py" `
    -RedirectStandardOutput "uvicorn.out.log" `
    -RedirectStandardError "uvicorn.err.log" `
    -WindowStyle Hidden `
    -PassThru
Write-Host "Started PID=`$(`$proc.Id)"
"@
$tmp = [System.IO.Path]::GetTempFileName() + ".ps1"
[System.IO.File]::WriteAllText($tmp, $script, [System.Text.Encoding]::UTF8)
$ps = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",$tmp -WindowStyle Hidden -PassThru
Write-Host "Launcher PID=$($ps.Id) script=$tmp"
Start-Sleep -Seconds 1
