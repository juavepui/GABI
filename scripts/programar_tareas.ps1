# Programa las tareas periódicas de GABI en el Programador de tareas de Windows (#46).
# OPCIONAL: solo se ejecuta si el propietario lo decide. Para quitarlas:
#   Unregister-ScheduledTask -TaskName "GABI - worker local" -Confirm:$false
#   Unregister-ScheduledTask -TaskName "GABI - tareas diarias" -Confirm:$false
#   Unregister-ScheduledTask -TaskName "GABI - Tiingo mensual" -Confirm:$false
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo "backend\.venv\Scripts\python.exe"
# Las tareas ya instaladas con la antigua .venv conservan ese intérprete;
# puede reinstalarse GABI editable allí sin volver a registrar tareas.
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $repo ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Instala primero el backend: uv sync --project backend --locked --all-groups"
}

# El worker es un proceso aparte. Se inicia al abrir sesión y continúa aunque
# se cierre el navegador. Las tareas programadas solo encolan comandos.
$worker = New-ScheduledTaskAction -Execute $python -Argument "-m gabi_cli worker" -WorkingDirectory $repo
$workerTrigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "GABI - worker local" -Action $worker -Trigger $workerTrigger `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0)) `
    -Description "GABI #66: ejecuta la cola persistente local" -Force
Start-ScheduledTask -TaskName "GABI - worker local"

# De martes a sábado a las 23:30 (hora española), después del cierre de Nueva York:
# encola refresco y mantenimiento; este conserva las comprobaciones #43/#44.
$daily = New-ScheduledTaskAction -Execute $python -Argument "-m gabi_cli schedule daily" -WorkingDirectory $repo
$dailyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday, Wednesday, Thursday, Friday, Saturday -At 23:30
Register-ScheduledTask -TaskName "GABI - tareas diarias" -Action $daily -Trigger $dailyTrigger `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Description "GABI #46: datos y pruebas ciegas" -Force

# El día 2 de cada mes: reanuda la cola de Tiingo del #44 (se detiene sola al agotar el cupo).
$tiingo = New-ScheduledTaskAction -Execute $python -Argument "-m gabi_cli schedule tiingo" -WorkingDirectory $repo
$monthly = New-ScheduledTaskTrigger -Once -At "2026-10-02 10:00"
$monthly.Repetition = (New-ScheduledTaskTrigger -Once -At "2026-10-02 10:00" `
    -RepetitionInterval (New-TimeSpan -Days 30) -RepetitionDuration (New-TimeSpan -Days 900)).Repetition
Register-ScheduledTask -TaskName "GABI - Tiingo mensual" -Action $tiingo -Trigger $monthly `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 3)) `
    -Description "GABI #44: precios de empresas desaparecidas" -Force
