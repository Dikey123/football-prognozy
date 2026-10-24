$ErrorActionPreference = 'Stop'

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    $ollamaPath = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $ollamaPath) { $ollama = Get-Item $ollamaPath }
}

if (-not $ollama) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'Установите Ollama с https://ollama.com/download/windows, затем запустите этот файл ещё раз.' }
    & $winget.Source install --id Ollama.Ollama --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить Ollama через winget. Установите её с https://ollama.com/download/windows и повторите запуск.' }
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        $ollamaPath = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        if (Test-Path $ollamaPath) { $ollama = Get-Item $ollamaPath }
    }
}
if (-not $ollama) { throw 'Ollama установлена, но её исполняемый файл не найден. Перезапустите Windows или добавьте Ollama в PATH.' }
$ollamaExe = if ($ollama.Source) { $ollama.Source } else { $ollama.FullName }

try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null
} catch {
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
    Start-Sleep -Seconds 5
}

Write-Output 'Скачиваю локальную модель Qwen3 4B (около 2,5 ГБ); OpenAI API не используется.'
& $ollamaExe pull qwen3:4b
if ($LASTEXITCODE -ne 0) { throw 'Не удалось загрузить модель qwen3:4b.' }

$pythonPath = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path $pythonPath)) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand -or $pythonCommand.Source -match '\\WindowsApps\\') {
        throw 'Для локального запуска нужна рабочая версия Python. Установите Python 3.12 и повторите запуск.'
    }
}

$runner = Join-Path $PSScriptRoot 'run_local_ai.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$userId = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $powershell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At '12:00'),
    (New-ScheduledTaskTrigger -AtLogOn -User $userId)
)
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName 'KaperAI Local Forecasts' -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Description 'Создаёт прогнозы локальной Ollama-моделью и публикует gpt.json. Только когда пользователь вошёл в Windows.' -Force | Out-Null

Write-Output 'Готово: задача запускается каждый день в 12:00 по времени Windows и при входе после 12:00.'
Write-Output 'Для публикации в GitHub на этом компьютере должен быть выполнен вход Git Credential Manager.'

