# Programa las tareas periódicas de GABI en el Programador de tareas de Windows (#46).
# OPCIONAL: solo se ejecuta si el propietario lo decide. Para quitarlas:
#   Unregister-ScheduledTask -TaskName "GABI - tareas diarias" -Confirm:$false
#   Unregister-ScheduledTask -TaskName "GABI - Tiingo mensual" -Confirm:$false
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"

# De martes a sábado a las 23:30 (hora española), después del cierre de Nueva York:
# refresca datos y registra los rebalanceos vencidos si los precios son del día.
$daily = New-ScheduledTaskAction -Execute $python -Argument "-m gabi.periodic_tasks --run" -WorkingDirectory $repo
$dailyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday, Wednesday, Thursday, Friday, Saturday -At 23:30
Register-ScheduledTask -TaskName "GABI - tareas diarias" -Action $daily -Trigger $dailyTrigger `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Description "GABI #46: datos y pruebas ciegas"

# El día 2 de cada mes: reanuda la cola de Tiingo del #44 (se detiene sola al agotar el cupo).
$tiingo = New-ScheduledTaskAction -Execute $python -Argument "-m gabi.periodic_tasks --tiingo" -WorkingDirectory $repo
$monthly = New-ScheduledTaskTrigger -Once -At "2026-10-02 10:00"
$monthly.Repetition = (New-ScheduledTaskTrigger -Once -At "2026-10-02 10:00" `
    -RepetitionInterval (New-TimeSpan -Days 30) -RepetitionDuration (New-TimeSpan -Days 900)).Repetition
Register-ScheduledTask -TaskName "GABI - Tiingo mensual" -Action $tiingo -Trigger $monthly `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 3)) `
    -Description "GABI #44: precios de empresas desaparecidas"
