# Reconciliación del registro de búsquedas — #60

El [registro ejecutable](ledger.json) reconcilia los artefactos publicados hasta
el 29 de septiembre de 2026. No calcula retornos, abre bases de datos ni consulta
reservas ciegas. Conserva configuración, muestra, referencias de especificación,
resultado y decisión; cada configuración y cada fuente tiene una huella SHA-256.
Los hashes de texto usan UTF-8 y LF y no sustituyen los hashes originales de
snapshots o resultados canónicos.

## Qué significa el recuento de 34

| Familia de la convención heredada | Entradas | Estado |
| --- | ---: | --- |
| V1 reconstruido (#12): nueve variantes y quince sensibilidades de costes | 24 | Observadas retrospectivamente |
| Umbrales de rotación 5/10 (#23) | 2 | Observados, sin promoción |
| R3 E6 (#36/#37): control y dos variantes, Top-20 | 3 | Control; variantes descartadas |
| VALUE (#43) | 1 | Preregistrada, primera señal 2026-12-21; resultados pendientes |
| QV, QVM y QE (#60) | 3 | Fallan la puerta de auditoría diaria |
| RCF v1 (#60) | 1 | Falla la puerta de auditoría diaria |

Son **33 entradas observadas y una especificación prospectiva**, no 34 estrategias
con resultados observados. Las sensibilidades y controles tampoco son estrategias
independientes. La convención heredada se reproduce para explicar los guards
publicados, sin cambiar sus resultados, alfa ni protocolos retrospectivamente.

Fuera de esa convención se conservan cuatro ejecuciones observadas: el control
V2 de rotación sobre su muestra de 2016–2025 y los tres Top-10 secundarios de R3
sobre 2011–2025. No se suman automáticamente como ensayos independientes: cambian
motor, universo, periodo o tamaño de cartera y pueden repetir decisiones.

También se registran **14 grupos de diagnósticos/reconstrucciones/auditorías**.
Incluyen las 13 pruebas del Factor Zoo y su réplica SIC, los 256 vectores de pesos
del placebo (familia de 257 contando el original), 8.192 trayectorias nulas y
pruebas de cola, sección cruzada, bootstrap, estabilidad y factores académicos.
Son información retrospectiva ya vista que puede influir en diseños posteriores.
Las simulaciones nulas no equivalen a 8.192 estrategias buscadas; las pruebas
académicas no validan la cartera GABI. Las auditorías de inputs añaden cero
configuraciones de inversión.

## Registradas después de la reconciliación (revisión 2)

La revisión 2 (28-10-2026) añade una sección `registered_after_reconciliation`
para las configuraciones preregistradas después del 29-09-2026. No toca las 34
entradas heredadas, sus guards ni sus decisiones.

| Entrada | Estado | Qué se ha observado |
| --- | --- | --- |
| `ensemble/ENS-VQE-v1` (#53) | Prospectiva pendiente | Robustez retrospectiva **sin retornos**: decisión «parcial». Primera revisión prospectiva no antes del 2029-12-21 |

Su preregistro la declara como **una configuración candidata nueva**. Los tres
Top-20 de sus componentes son comparadores diagnósticos, no candidatos. El
mínimo conocido acumulado pasa a **35** (`known_minimum_candidate_configurations`).
Sigue siendo un mínimo: no acredita un recuento global ni control global del
error de selección. El catálogo de Investigación la lista como ensayo
prospectivo, sin resultado.

## Revisión 3 (01-11-2026, #252)

La revisión 3 añade la candidata **NSI-v1**, emisión neta de acciones. Se
preregistró con la aprobación del propietario después de pasar su puerta de
datos, y antes de calcular ningún rendimiento.

| Entrada | Estado | Qué se ha observado |
| --- | --- | --- |
| `issuance/NSI-v1/primary` (Top-20 BASE) | Preregistrada, exploratoria pendiente | Solo la cobertura de datos, sin retornos |
| `issuance/NSI-v1/stress` (Top-20 STRESS) | Ídem | Ídem |
| `issuance/NSI-v1/top30` (Top-30 BASE, sensibilidad) | Ídem | Ídem |

Su presupuesto es de tres configuraciones, y el mínimo conocido acumulado pasa a
**38**. La fase exploratoria reutiliza la historia observada de 2011–2025 y
nunca contará como evidencia independiente.

Las dos puertas de datos de #252 se registran como **auditorías sin
configuraciones de inversión**:
- `cbop_v1_data_gate`: CBOP-v1 se cerró por inviable por cobertura, sin leer
  retornos;
- `nsi_v1_data_gate`: pasa.

## Revisión 4 (01-11-2026, #252)

Se ejecutó la evaluación exploratoria preregistrada de NSI-v1, que marcó
**abandonar**. El propietario aceptó el abandono.
- **Configuración primaria:** −4,8 pp anuales frente al S&P 500 TR en EUR con los
  mismos flujos. El alfa FF5+UMD es de −0,7 pp, con un intervalo de [−4,3; +2,9].
- **Ventanas:** las cotas inferiores son negativas en las dos ventanas válidas.
- **Defecto declarado:** el archivo de precios de 2010–2015 no tiene apertura, y
  la estrategia estuvo en caja esos años.

Las tres entradas pasan a `observed`: la primaria como `abandoned` y las dos de
sensibilidad como `sensitivity_not_decisive`. El mínimo conocido sigue en 38.
Detalle en [docs/research/nsi-v1-resultado.md](../research/nsi-v1-resultado.md).

## Lo que sigue sin poder recuperarse

Se mantienen las cuatro exclusiones documentadas por #12: vectores completos de
tres perturbaciones antiguas, especificaciones originales de factores individuales,
intentos con bugs/coberturas distintas y sesiones V2/optimización/otros rangos no
registradas exhaustivamente. Los nuevos artefactos recuperan algunas ejecuciones
posteriores, pero no reconstruyen cada sesión original, qué se vio ni cuándo se
eligió una regla. No se ha inspeccionado el historial privado de experimentos ni
los resultados de #43/#44 para llenar esos huecos.

Por tanto, **no existe todavía un recuento global acreditado ni control global
del error de selección**. Un Bonferroni sobre 34 o un PBO favorable de una familia
parcial no lo acredita. La migración conservará el registro y estas limitaciones;
no etiquetará un backtest como prueba independiente.

La siguiente hipótesis debe justificar su mecanismo económico, fijar datos y
reglas antes del ensayo, registrarse como familia nueva y reservar una prueba
independiente adecuada. Las muestras #43/#44 conservan sus modelos y usos. No
se promueve ninguno de los cuatro candidatos nuevos ni se modifica RCF para
rescatar una ventana favorable. #60 sigue abierta.

## Verificación

```powershell
uv run python -m gabi_cli research ledger --verify
```

Comprueba exactamente el registro y sus fuentes publicadas, sin red ni snapshots
de precios. CI ejecuta esta verificación. Para una revisión explícita se puede
escribir un destino nuevo con `--write RUTA`; el comando rechaza sobrescribir
un registro existente. El registro se escribió con `python -m gabi.search_ledger --write`
(último commit de ese módulo: 1283bf5); desde ADR 0002 el mismo cálculo vive en
`gabi.domain.research.search_ledger` y produce exactamente el registro publicado.
El catálogo tiene alcance declarado y no promete recuperar
ensayos que nunca se registraron.
