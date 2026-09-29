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
uv run python -m gabi.search_ledger --verify
```

Comprueba exactamente el registro y sus fuentes publicadas, sin red ni snapshots
de precios. CI ejecuta esta verificación. Para una revisión explícita se puede
escribir un destino nuevo con `--write RUTA`; el comando rechaza sobrescribir
un registro existente. El catálogo tiene alcance declarado y no promete recuperar
ensayos que nunca se registraron.
