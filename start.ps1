# Arranca GABI en local: API, interfaz React y worker en http://127.0.0.1:<Port>.
# Uso, desde cualquier carpeta:
#   .\start.ps1                 # instala/compila solo si falta o está desactualizado
#   .\start.ps1 -Install        # fuerza uv sync + npm ci + build (tras git pull)
#   .\start.ps1 -Port 8010      # otro puerto local
#   .\start.ps1 -NoBrowser      # no abre el navegador
# Ctrl+C detiene el servidor y el worker.
param(
    [int]$Port = 8000,
    [switch]$Install,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$frontend = Join-Path $repo "frontend"

function Invoke-Step([string]$Description, [scriptblock]$Command) {
    Write-Host "==> $Description" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Falló: $Description (código $LASTEXITCODE)" }
}

foreach ($tool in "uv", "npm") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "No se encuentra '$tool' en el PATH. Consulta README.md (Instalación)."
    }
}

Push-Location $repo
try {
    if ($Install -or -not (Test-Path (Join-Path $repo "backend\.venv"))) {
        Invoke-Step "Instalando backend (uv sync)" { uv sync --project backend --locked --all-groups }
    }

    $lock = Get-Item (Join-Path $frontend "package-lock.json")
    $modules = Join-Path $frontend "node_modules\.package-lock.json"
    if ($Install -or -not (Test-Path $modules) -or (Get-Item $modules).LastWriteTime -lt $lock.LastWriteTime) {
        Invoke-Step "Instalando frontend (npm ci)" { npm --prefix frontend ci }
    }

    # Recompila si falta el build o algún fuente del frontend es más reciente.
    $index = Join-Path $frontend "dist\index.html"
    $needsBuild = $Install -or -not (Test-Path $index)
    if (-not $needsBuild) {
        $built = (Get-Item $index).LastWriteTime
        $sources = @(Get-ChildItem (Join-Path $frontend "src"), (Join-Path $frontend "public") -Recurse -File -ErrorAction SilentlyContinue) +
            @(Get-ChildItem $frontend -File | Where-Object { $_.Name -in "index.html", "package.json", "vite.config.ts" })
        $needsBuild = [bool]($sources | Where-Object { $_.LastWriteTime -gt $built } | Select-Object -First 1)
    }
    if ($needsBuild) {
        Invoke-Step "Compilando frontend (npm run build)" { npm --prefix frontend run build }
    }

    $url = "http://127.0.0.1:$Port"
    if (-not $NoBrowser) {
        # Abre el navegador cuando el servidor responda, sin bloquear el arranque.
        Start-Job -ArgumentList $url {
            param($url)
            for ($i = 0; $i -lt 60; $i++) {
                try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process $url; return } catch { Start-Sleep -Milliseconds 500 }
            }
        } | Out-Null
    }

    Write-Host "==> Arrancando GABI en $url (Ctrl+C para detener)" -ForegroundColor Green
    uv run --project backend python -m gabi_cli serve --port $Port
}
finally {
    Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
    Pop-Location
}
