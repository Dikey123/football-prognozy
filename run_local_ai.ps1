$ErrorActionPreference = 'Stop'

$root = Join-Path $env:LOCALAPPDATA 'KaperAI'
$repo = Join-Path $root 'football-prognozy-main'
$log = Join-Path $root 'local-ai.log'
New-Item -ItemType Directory -Path $root -Force | Out-Null
Start-Transcript -Path $log -Append | Out-Null

try {
    $moscow = [TimeZoneInfo]::FindSystemTimeZoneById('Russian Standard Time')
    $nowMoscow = [TimeZoneInfo]::ConvertTime([DateTimeOffset]::UtcNow, $moscow)
    if ($nowMoscow.TimeOfDay -lt [TimeSpan]::FromHours(12)) {
        Write-Output 'До 12:00 по Москве; запуск при входе отложен до ежедневного триггера.'
        exit 0
    }

    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        $ollamaPath = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        if (Test-Path $ollamaPath) { $ollama = Get-Item $ollamaPath }
    }
    if (-not $ollama) { throw 'Ollama не найдена. Запустите setup_local_ai.ps1.' }
    $ollamaExe = if ($ollama.Source) { $ollama.Source } else { $ollama.FullName }

    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null
    } catch {
        $env:OLLAMA_HOST = '127.0.0.1:11434'
        Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
        $ready = $false
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 2
            try {
                Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null
                $ready = $true
                break
            } catch { }
        }
        if (-not $ready) { throw 'Локальная Ollama не запустилась на 127.0.0.1:11434.' }
    }

    $git = (Get-Command git -ErrorAction Stop).Source
    if (-not (Test-Path (Join-Path $repo '.git'))) {
        if (Test-Path $repo) { throw "Папка $repo занята и не является git-копией; остановка без удаления файлов." }
        & $git clone --single-branch --branch main 'https://github.com/Dikey123/football-prognozy.git' $repo
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось получить отдельную рабочую копию GitHub.' }
    }

    Push-Location $repo
    try {
        & $git config user.name 'kaper-ai-local'
        & $git config user.email 'actions@users.noreply.github.com'
        & $git fetch origin main
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось проверить обновления GitHub.' }

        # Повторно отправляем прошлый результат, если компьютер был без сети.
        & $git add gpt.json
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось подготовить gpt.json.' }
        & $git diff --cached --quiet
        if ($LASTEXITCODE -eq 1) {
            & $git commit -m 'auto: локальное мнение ИИ по матчам'
            if ($LASTEXITCODE -ne 0) { throw 'Не удалось сохранить прежний локальный прогноз.' }
        } elseif ($LASTEXITCODE -ne 0) {
            throw 'Не удалось проверить локальные изменения.'
        }

        & $git pull --rebase origin main
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось синхронизировать прогнозы с GitHub.' }
        & $git push origin main
        if ($LASTEXITCODE -ne 0) { throw 'GitHub не принял предыдущие изменения; проверьте вход Git Credential Manager.' }
        & $git reset --hard origin/main
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось обновить изолированную копию до main.' }

        $pythonPath = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (-not (Test-Path $pythonPath)) {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($pythonCommand -and $pythonCommand.Source -notmatch '\\WindowsApps\\') {
                $pythonPath = $pythonCommand.Source
            } else {
                throw 'Не найдена рабочая версия Python для запуска gen_gpt.py.'
            }
        }

        $env:OLLAMA_MODEL = 'qwen3:4b'
        $env:OLLAMA_URL = 'http://127.0.0.1:11434/api/chat'
        & $pythonPath gen_gpt.py
        if ($LASTEXITCODE -ne 0) { throw "Локальная генерация завершилась с кодом $LASTEXITCODE." }

        & $git add gpt.json
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось подготовить gpt.json к публикации.' }
        & $git diff --cached --quiet
        if ($LASTEXITCODE -eq 1) {
            & $git commit -m 'auto: локальное мнение ИИ по матчам'
            if ($LASTEXITCODE -ne 0) { throw 'Не удалось сохранить новые прогнозы.' }
            & $git push origin main
            if ($LASTEXITCODE -ne 0) { throw 'Не удалось опубликовать прогнозы в GitHub.' }
            Write-Output 'Новые прогнозы локальной модели опубликованы в GitHub main.'
        } elseif ($LASTEXITCODE -eq 0) {
            Write-Output 'Новых прогнозов нет; коммит не создавался.'
        } else {
            throw 'Не удалось проверить результат генерации.'
        }
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_
    exit 1
} finally {
    Stop-Transcript | Out-Null
}

