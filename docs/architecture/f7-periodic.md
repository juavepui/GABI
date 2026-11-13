# F7.2: mantenimiento periódico (#88)

`gabi.periodic_tasks` se retira. La coordinación vive en
`application/administration/periodic.py`; el dominio Mercado verifica el último
cierre y la tolerancia del 5 %. `infrastructure/storage/periodic.py` lee el
universo y las fechas de precios, gestiona la cola/lock Tiingo y escribe el log.
El puente `infrastructure/legacy/periodic.py` adapta los motores existentes de
refresco, checkpoints, ledger y las pruebas reservadas; rechaza un directorio
distinto del configurado por esos motores, sin modificar configuración global.

## CLI y tareas instaladas

Los comandos equivalentes son:

```powershell
python -m gabi_cli periodic --status
python -m gabi_cli periodic --run
python -m gabi_cli periodic --run --no-refresh
python -m gabi_cli periodic --run --full-refresh
python -m gabi_cli periodic --tiingo
```

Los jobs `refresh`, `maintenance`, `tiingo` y `blind_rebalance` usan el mismo caso
de uso. El scheduler F4 sigue encolando con `gabi_cli schedule daily|tiingo`.
No se reinstalan tareas Windows. Una tarea antigua configurada expresamente con
`-m gabi.periodic_tasks` necesita cambiar sus argumentos a `-m gabi_cli periodic`.
La referencia histórica en el preregistro A3 sellado conserva sus bytes; este
documento establece la sustitución del comando sin modificar el protocolo.

## Lecturas, límites e invalidación

El estado lee exclusivamente archivos locales y conexiones SQLite `mode=ro`
con `query_only`. No inicializa esquemas ni descarga una caché ausente. La
ausencia del universo o de precios deja `precios_al_dia=false`. Las validaciones
se consultan con `SqliteBlindStore` y se comprueba su cadena sin calcular retornos,
incluso si la fecha de desbloqueo ya pasó. Se conservan las claves españolas,
fechas, ausencias, hashes y criterios de registro del mantenimiento anterior.

El universo admite hasta 1.000 símbolos y 1 MB; las fechas máximas se consultan
en lotes de 200, sin cargar series completas. El estado calcula la frescura una
vez por llamada. No mantiene caché: cada consulta vuelve a leer el universo,
precios y marcadores, por lo que cualquier corrección se ve en la siguiente
consulta. La cola admite 1 MB y solo comprueba los archivos de sus símbolos.
El lock Tiingo se crea de forma exclusiva; un fallo libera el lock y no marca
la cola como completada.

## Medición reproducible

Desde la raíz: `.venv/Scripts/python.exe scripts/measure_periodic.py`.
Fixture temporal: 1.000 símbolos, 1.002 precios incluyendo SPY/RSP, sin estudios
reservados ni proveedores. Se compara la lectura de precios de `9be44a8` con
la nueva; metadatos y calendario son iguales en ambas rutas. El calendario se
precalienta; primera y segunda llamada no representan un arranque frío de proceso.

| Métrica | Anterior | Nueva |
| --- | ---: | ---: |
| Consultas de precios por estado | 2.004 | 6 |
| Primera llamada | 1,697 s | 0,020 s |
| Segunda llamada | 1,418 s | 0,020 s |
| Pico de asignaciones Python | 0,301 MiB | 0,285 MiB |

Los JSON de estado coinciden exactamente en esta fixture. La memoria indicada
procede de `tracemalloc`, no del working set total. No mide el rendimiento de
descargas, backtests ni la RAM sobre los datos reales.

Los tests cubren rebalanceos vencidos/futuros, falta de RSP, precios antiguos,
integridad rota, tolerancia exacta del 5 %, ausencia de caché sin efectos,
checkpoints, errores del ledger y exclusión/liberación del lock Tiingo. La
verificación conserva los 18 motores/configuración congelados.
