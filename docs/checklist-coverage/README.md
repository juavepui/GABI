# Cobertura y tasas de cumplimiento del checklist fundamental (#170, #171)

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

## Tasas de cumplimiento y presets de umbrales (#171)

¿Cuántas empresas del S&P 500 cumplen cada umbral? Medición sobre los datos locales del
28-10-2026 (503 emisores), con el mismo comando de solo lectura:

```powershell
uv run --project backend python -m gabi_cli market checklist-coverage --output informe.json --reference backend/src/gabi/resources/checklist_reference.json
```

- `--reference` guarda, por criterio y sector, los valores con veredicto (sin símbolos) y cuántos
  emisores cumplen sin ratio (cobertura de intereses sin deuda). Es
  `backend/src/gabi/resources/checklist_reference.json` (unos 86 kB). La API calcula con ella la
  tasa del umbral vigente, sea el del Excel, uno editado o un preset.
- `pass-rates.json` guarda las tasas de esta medición con cada preset, global y por sector.
- La tasa solo cuenta emisores con veredicto: se excluyen los que no tienen dato y los
  criterios que no aplican a financieras.
- Con menos de 5 valores en el sector no se da tasa de sector.
- La tasa es contexto: no cambia el veredicto, el Composite, el ranking ni la selección.
- Usar un criterio como filtro exige un experimento preregistrado aparte (#60).

Tasas en %; n = emisores con veredicto. «—»: sin valores suficientes o no aplica.

### Umbrales del Excel

| Criterio | Umbral | S&P 500 (n) | Com. | C. disc. | C. básico | Energía | Financ. | Salud | Indust. | Tecno. | Mater. | Inmob. | Utilities |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ev_ebit` | 12 | 7,5 % (214) | 10 | 5 | 0 | 14 | — | 8 | 10 | 9 | 11 | 0 | 5 |
| `insiders_pct` | 0,1 | 11,2 % (502) | 32 | 19 | 15 | 14 | 20 | 7 | 6 | 8 | 8 | 0 | 0 |
| `ev_fcf` | 17 | 16,6 % (223) | 18 | 23 | 21 | 43 | — | 9 | 13 | 20 | 14 | 9 | — |
| `net_debt` | 0 | 16,7 % (264) | 23 | 33 | 5 | 0 | — | 18 | 11 | 34 | 7 | 5 | 0 |
| `ev_ebitda` | 12 | 20,9 % (191) | 33 | 35 | 21 | 57 | — | 19 | 11 | 12 | 36 | 15 | 24 |
| `interest_coverage` | 15 | 25,0 % (280) | 38 | 23 | 10 | 20 | 0 | 29 | 27 | 47 | 15 | 0 | 0 |
| `pe` | 18 | 25,6 % (437) | 38 | 32 | 18 | 26 | 55 | 19 | 17 | 16 | 27 | 9 | 13 |
| `fcf_yield` | 0,04 | 47,2 % (396) | 53 | 56 | 73 | 69 | 100 | 52 | 42 | 36 | 38 | 60 | 4 |
| `gross_margin_change` | 0 | 60,2 % (274) | 86 | 68 | 25 | 75 | — | 49 | 81 | 67 | 53 | 30 | — |
| `cfo_cagr` | 0,05 | 64,0 % (389) | 59 | 70 | 40 | 75 | 80 | 69 | 64 | 72 | 55 | 77 | 42 |
| `shares_change` | 0 | 64,1 % (463) | 58 | 65 | 83 | 47 | 73 | 81 | 82 | 54 | 77 | 24 | 13 |
| `net_debt_to_ebitda` | 2,5 | 64,4 % (191) | 67 | 65 | 71 | 71 | — | 71 | 83 | 76 | 64 | 23 | 6 |
| `roic` | 0,1 | 64,5 % (183) | 78 | 100 | 71 | 14 | — | 65 | 82 | 63 | 56 | 38 | 8 |
| `net_margin` | 0,1 | 64,8 % (454) | 60 | 49 | 39 | 61 | 88 | 58 | 60 | 74 | 39 | 79 | 78 |
| `net_margin_change` | 0 | 65,3 % (418) | 75 | 73 | 29 | 100 | 75 | 51 | 73 | 63 | 50 | 50 | 75 |
| `revenue_cagr` | 0,05 | 67,2 % (473) | 68 | 79 | 27 | 84 | 67 | 79 | 59 | 74 | 59 | 75 | 59 |
| `gross_margin` | 0,3 | 78,1 % (292) | 88 | 74 | 71 | 62 | — | 88 | 77 | 91 | 38 | 58 | 80 |
| `sbc_to_net_income` | 0,2 | 78,6 % (411) | 73 | 73 | 96 | 100 | 81 | 79 | 92 | 43 | 100 | 86 | 100 |
| `fcf` | 0 | 90,2 % (396) | 95 | 98 | 97 | 100 | 100 | 96 | 96 | 95 | 79 | 85 | 21 |
| `cash_conversion` | 1 | 90,3 % (372) | 94 | 82 | 93 | 100 | 100 | 85 | 91 | 87 | 100 | 96 | 100 |
| `net_income` | 0 | 95,6 % (457) | 80 | 98 | 90 | 100 | 100 | 93 | 99 | 96 | 83 | 96 | 100 |

### Preset «Gran empresa S&P 500»

| Criterio | Umbral | S&P 500 (n) | Com. | C. disc. | C. básico | Energía | Financ. | Salud | Indust. | Tecno. | Mater. | Inmob. | Utilities |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ev_ebit` | 20 | 32,7 % (214) | 30 | 63 | 56 | 57 | — | 28 | 33 | 20 | 44 | 8 | 15 |
| `insiders_pct` | 0,01 | 31,5 % (502) | 55 | 47 | 32 | 24 | 41 | 23 | 24 | 37 | 29 | 23 | 3 |
| `ev_fcf` | 25 | 42,6 % (223) | 55 | 45 | 63 | 71 | — | 43 | 40 | 37 | 29 | 36 | — |
| `ev_ebitda` | 16 | 46,1 % (191) | 33 | 59 | 57 | 86 | — | 43 | 38 | 26 | 45 | 38 | 82 |
| `interest_coverage` | 8 | 43,6 % (280) | 38 | 40 | 62 | 40 | 0 | 46 | 55 | 64 | 31 | 0 | 4 |
| `pe` | 25 | 45,1 % (437) | 44 | 55 | 57 | 58 | 70 | 36 | 36 | 23 | 40 | 17 | 74 |

**Lectura**:
- Siete criterios no discriminan en el S&P 500 con el umbral del Excel: los cumple menos de un
  tercio del índice.
  - **Directivos ≥ 10 %**: la mediana es del 0,44 %; solo lo cumplen empresas de fundador.
  - **Cobertura de intereses ≥ 15x**: la mediana es de 6,8x; inmobiliarias y utilities quedan
    a 0.
  - **Múltiplos**: con una mediana de PER de 26,6x y de EV/EBITDA de 16,4x, el S&P 500 cotiza
    por encima de los umbrales pensados para value.
  - **Deuda neta ≤ 0**: también la cumplen pocas (17 %), pero se mantiene: separa a las
    empresas con caja neta, que es lo que mide.
- El preset **«Gran empresa S&P 500»** solo relaja seis umbrales: directivos ≥ 1 %, cobertura
  de intereses ≥ 8x, PER ≤ 25x, EV/EBITDA ≤ 16x, EV/EBIT ≤ 20x y EV/FCF ≤ 25x. Son valores
  redondos cercanos a la mediana de esta medición, así que cada uno lo cumple entre un tercio y
  la mitad del índice. Un test lo comprueba con la referencia empaquetada.
- No se crea un preset por sector. La ficha muestra junto a cada umbral la tasa del índice y
  la de su sector; con eso se ve si un ✘ es propio de la empresa o de todo su sector (por
  ejemplo, la cobertura de intereses en utilities).
- **Directivos**: se mantiene como criterio con umbral, con la tasa a la vista y el aviso de
  clases de acciones que ya tenía. La alarma de ventas de directivos (Form 4) sigue aparte.
  Una alternativa por compras netas de insiders queda como mejora aparte.
