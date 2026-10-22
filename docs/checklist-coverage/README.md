# Cobertura del checklist fundamental (#170)

Medición de cuántos emisores del universo actual (S&P 500, 503 empresas) pueden
evaluar cada criterio del checklist, y por qué no los demás. Datos locales del
22-10-2026.

```powershell
uv run --project backend python -m gabi_cli market checklist-coverage --output docs/checklist-coverage/after.json
```

El comando es de solo lectura. Evalúa el checklist de cada empresa igual que la ficha,
sobre los hechos SEC ya guardados. No descarga nada ni escribe en SQLite. Tarda unos
100 s con la base real.

La beta queda al 0 % en el CLI porque no consulta el ranking. En la ficha, la beta sale
de la fila del ranking (#169).

## Ficheros

| Fichero | Contenido |
| --- | --- |
| `before.json` | Antes de #170: hechos leídos por símbolo y etiquetas de CAPEX del Composite |
| `after-stored-facts.json` | Con #170 sobre los hechos ya guardados, antes de la nueva sincronización SEC |
| `after-sync-simulation.json` | Simulación tras la sincronización (ver abajo) |
| `after-sync.json` | Medición real tras la sincronización SEC del 22-10-2026 (503/503 emisores, sin fallos) |

Cada informe incluye:
- el porcentaje evaluable de cada criterio, global y por sector;
- los motivos de ausencia;
- los emisores no financieros sin ingresos o sin CAPEX;
- los criterios con valor de cada emisor.

## Causas encontradas

1. **Hechos guardados bajo otro alias del emisor.** La sincronización compara la descarga
   con todos los hechos de la entidad (CIK) y escribe en `edgar_facts`, bajo el símbolo
   actual, solo las filas nuevas. Si el historial se guardó con un ticker anterior
   (PSKY → SKYD) o con la clave histórica `CIK…` (TWLO, DAL…), el símbolo actual solo tiene
   las filas añadidas después. Ocurre en 205 entidades.
   - **Corrección**: el checklist lee los hechos de la entidad
     (`SqliteSecReads.issuer_facts`, sobre `entity_observations`).
   - **Resultado**: TWLO pasa de 3 a 20 criterios con valor y SKYD de 2 a 9.
2. **Cambio de etiqueta sin años comparables.** `_extract_annual_values` toma como base la
   primera etiqueta candidata aunque la empresa dejara de usarla hace años, y solo une la
   nueva si algún año común coincide. Ejemplo: AMZN publica el CAPEX como
   `PaymentsToAcquireProductiveAssets` desde 2017.
   - **Corrección**: el checklist usa `annual_series`, que toma como base la etiqueta
     publicada más recientemente. La regla de unión es la misma.
   - **Resultado**: también corrige ejercicios anclados en años antiguos. Por ejemplo, GE
     aparecía con 2018 y ahora con 2025.
3. **Etiquetas de CAPEX que faltaban.** Se añaden a la lista del checklist, en este orden,
   después de las del Composite (`CHECKLIST_CAPEX_TAGS`):
   - `PaymentsToAcquireProductiveAssets`: CAPEX total; aparece en 82 de los 122 emisores
     sin CAPEX;
   - `PaymentsToAcquireOilAndGasPropertyAndEquipment` y
     `PaymentsToExploreAndDevelopOilAndGasProperties`: inversión de petroleras (APA, EOG…).

   Llegan con la siguiente sincronización SEC explícita. La huella de etiquetas cambia, así
   que cada emisor se reprocesa una vez.

`sec.CAPEX_TAGS`, `sec.REVENUE_TAGS` y `_extract_annual_values` no cambian. El Composite,
el ranking y los 18 motores congelados tampoco.

## Resultado

| Criterio | Antes | Lectura por entidad | Tras sincronizar (simulado) | Tras sincronizar (real) |
|---|---|---|---|---|
| CAGR de ingresos | 92,0 % | 94,0 % | 94,0 % | 94,0 % |
| Margen neto | 89,9 % | 90,3 % | 90,3 % | 90,3 % |
| Cobertura de intereses | 60,2 % | 64,8 % | 64,8 % | 64,8 % |
| Conversión de caja | 83,8 % | 86,1 % | 86,1 % | 86,1 % |
| Margen de CFO | 96,8 % | 99,3 % | 99,3 % | 99,3 % |
| Flujo de caja libre | 69,0 % | 71,3 % | 91,0 % | 91,7 % |
| Intensidad de capital | 70,1 % | 71,3 % | 90,7 % | 91,4 % |
| EV / FCF | 40,0 % | 41,2 % | 51,2 % | 51,6 % |
| FCF yield | 69,0 % | 71,3 % | 91,0 % | 91,7 % |

Porcentaje sobre los emisores a los que aplica cada criterio (432 no financieros en los
criterios de caja y EV). El resto de criterios está en los JSON.

La medición real mejora algo la simulación: DD, DLTR y GE no estaban entre los 126 emisores
simulados y usaban flujos de caja operativos guardados antiguos. Con la sincronización completa
también tienen CAPEX del ejercicio usado.

**Ingresos SEC evaluables**: 427 de 432 emisores no financieros (98,8 %) antes y 429 de 432
(99,3 %) después. Los tres restantes tienen motivo verificado:

| Emisor | Motivo |
| --- | --- |
| APA | Publica los ingresos de 2025 solo con una etiqueta propia; companyfacts no incluye extensiones de la empresa. Su CAPEX sí llega (`PaymentsToExploreAndDevelopOilAndGasProperties`): de 9 a 12 criterios con valor |
| XOM | `sec_cik_map.csv` lo asocia a «ExxonMobil Holdings Corp», un registrante sin 10-K, y no a Exxon Mobil Corp. Es un problema de identidad, no de etiquetas |
| HONA | Honeywell Aerospace, escindida en 2026, aún no ha presentado ningún 10-K |

**Simulación**: para los 126 emisores sin ingresos o sin CAPEX en `before.json`, se descargó
su companyfacts el 22-10-2026 a un directorio temporal y se extrajo con `FACT_TAGS`, como
hará la sincronización. El resto del universo usa los hechos guardados. No se escribió en
`gabi.db`.

## CAPEX que sigue sin dato (34 emisores, real)

Quedan sin dato a propósito, porque ninguna etiqueta equivale al CAPEX total:

- **Inmobiliarias** (10): publican compra y desarrollo de inmuebles
  (`PaymentsToAcquireRealEstate`, `PaymentsToDevelopRealEstateAssets`). Es inversión de
  crecimiento, no CAPEX de mantenimiento.
- **Eléctricas y otras** (LNT, ED, WEC, CMS, LLY, ADP, VZ, ROP…): solo publican partidas
  parciales (`…Other…`, obra en curso). Usarlas infravaloraría el CAPEX.
- **Emisores que dejaron de desglosarlo** (ABNB, APP, CI, VEEV, COP, URI, VLO…): la última
  etiqueta es anterior al ejercicio usado. El criterio muestra «dato de CAPEX de otro
  ejercicio».
