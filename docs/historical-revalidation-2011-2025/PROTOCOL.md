# Protocolo de la revalidación 2016–2025 y 2011–2025 (issue #35)

Registrado **antes de ejecutar** (2026-09-26). No se modificará tras ver
resultados. Cualquier desviación forzada (un fallo técnico, no un resultado)
se anotará como tal en el informe.

## Qué se reutiliza

- `full_universe_audit`: snapshot congelado de la base, rankings completos con
  hash y backtests V1/V2 Top-10/20.
- `historical_validation`: cobertura por rebalanceo, benchmarks del universo
  cubierto, cotas de sensibilidad, retorno implícito de los excluidos y cortes
  concluyentes.
- `overfitting_audit` (#12) y `factor_stability` (#13).

El único módulo nuevo, `historical_revalidation`, solo los orquesta.

## Configuración fija (la de la auditoría de universo completo)

- Pesos 30/35/25/10 (valor, calidad, momentum, riesgo).
- Top-10 y Top-20. **Principal: Top-20**, el ensayo seleccionado del #12
  (`top20_q`); Top-10 es secundario.
- Cobertura de métricas ≥ 70 % por empresa y ≥ 50 % del universo para ejecutar
  un rebalanceo.
- Rebalanceo trimestral el día 2 de enero, abril, julio y octubre.
- V1: 10 pb por lado.
- V2: 100.000 USD, 1 USD de comisión y 10 pb de spread total, modo validación.
- Rebalanceos de 2016-01-02 a 2025-07-02; la última salida es el 2025-10-02,
  como en la auditoría publicada.
- Serie continua: rebalanceos desde 2010-01-02. Como en el #33, se invierte
  desde el primer trimestre con cobertura suficiente (se espera 2011-07).

## Corrección de datos del #38 (decisión del propietario, 2026-09-26)

Con `edgar.fiscal_alignment()`, cada componente de un ratio debe pertenecer al
ejercicio ancla:

- **Ancla**: el último cierre anual con ingresos; si el emisor no reporta
  ingresos, el último con beneficio neto.
- **Mismo ejercicio**: tolerancia de ±45 días respecto al ancla.
- **Partida que deja de reportarse**: queda **ausente** con motivo
  `stale_component`. No se sustituye por un año anterior ni por cero. Una
  deuda o caja obsoleta deja ausentes el EV y la deuda neta.
- **Partida que nunca se reportó**: se mantiene como hoy (cero en el EV,
  ausente en el ROIC).

La corrección está desactivada por defecto, para que las auditorías congeladas
sigan reproduciéndose. Fórmulas, pesos y umbrales del Composite no cambian.

## Variantes (cada una con su snapshot, rankings con hash y fingerprint de código)

| Variante | Capa | #38 | Rebalanceos |
| --- | --- | --- | --- |
| `operativo` | camino actual por ticker (código de hoy) | no | 2016-01-02 → 2025-07-02 |
| `acreditado` | capa acreditada 2010–2025 (#34) | no | 2016-01-02 → 2025-07-02 |
| `operativo-38` | camino actual por ticker | sí | 2016-01-02 → 2025-07-02 |
| `acreditado-38` (**principal**) | capa acreditada | sí | 2010-01-02 → 2025-07-02 |

La auditoría publicada ([full-universe-audit](../full-universe-audit/README.md))
se generó con código anterior. Recalcular hoy uno de sus rankings (2020-07-02)
sobre su propio snapshot cambia la puntuación en 332 de 501 empresas: son los
cambios posteriores en CAGR, sector y métricas nuevas (#29–#31). Por eso
`operativo` es la base limpia, y las diferencias se descomponen en pasos:

1. publicada → `operativo`: deriva de código y datos desde que se congeló.
2. `operativo` → `acreditado`: efecto de la capa acreditada (composición,
   identidad y precios).
3. `acreditado` → `acreditado-38`: efecto de la corrección #38.
4. `operativo` → `operativo-38`: control, el #38 sobre el camino actual.
5. publicada → `acreditado-38`: cambio total.

Vistas evaluadas: las tres variantes 2016; `acreditado-38` desde 2016-01-02
(cartera nueva en caja, comparable con la publicada) y `acreditado-38` como
serie continua desde 2010-01-02.

## Qué se mide

- **Por paso y rebalanceo (Top-20)**:
  - elegibles;
  - retorno V1;
  - posiciones comunes y Jaccard de las carteras V1 y V2.
- **Atribución de cada posición que sale**, en este orden: fuera de la
  composición, identidad no acreditada, sin precio acreditado, no elegible,
  desplazada por cambio de fundamentales, de precio, de ambos o por otras
  entradas. Un cambio es cualquier diferencia en las métricas del Composite de
  esa empresa.
- **Atribución de cada posición que entra**: miembro ausente en la base, no
  elegible en la base, sube por fundamentales, por precio o por otras salidas.
- **Posiciones V2 de la base que no superarían la acreditación**: sin identidad
  acreditada, sin precio acreditado o fuera de la composición.
- **Métricas V2 por vista**:
  - CAGR neto desde el capital inicial;
  - volatilidad;
  - Sharpe con su error estándar (Lo 2002, `sharpe_standard_error`);
  - drawdown máximo;
  - ES 95 % diario;
  - rotación media y costes;
  - resultado estricto.

  Lo mismo para el tramo realmente invertido.
- **Serie continua**:
  - cobertura por rebalanceo (identidad, precio acreditado, fundamentales,
    elegibles y motivos);
  - benchmarks SPY y universo elegible, equiponderado y ponderado por
    capitalización;
  - retorno implícito de los excluidos, o su no identificabilidad;
  - cotas de sensibilidad;
  - cortes concluyentes (cobertura de precio acreditado ≥ 85 % y elegibles
    ≥ 50 %).
- **Significación**:
  - Error estándar del Sharpe.
  - Exceso trimestral V1 Top-20 frente al SPY: media, t simple y trimestres
    por encima.
  - PBO/DSR (#12): la misma familia documentada de 18 configuraciones sobre los
    36 trimestres 2016-07 → 2025-07, con los rankings de `operativo` y de
    `acreditado-38`. Si una vista no cumple sus requisitos (cobertura ≥ 50 % y
    Top-N completo en cada fecha), se registra el motivo.
  - Estabilidad por régimen (#13): FF5 + Momentum sobre esos mismos 36
    trimestres, con mitades, ventanas móviles y episodios, usando los factores
    ya compuestos del #13 y los retornos V1 Top-20 de `acreditado-38`.

## Regla de conclusión (vista principal: `acreditado-38` desde 2016, V2 Top-20)

- **No sobrevive**: CAGR neto de la estrategia ≤ CAGR del SPY.
- **Sobrevive y es significativa**: supera al SPY, el t del exceso trimestral
  V1 Top-20 es > 1,96 y el DSR es > 0,95.
- **Sobrevive sin significación**: supera al SPY, pero no se cumple alguna de
  las dos condiciones anteriores.

La serie continua, las cotas y los cortes concluyentes matizan la conclusión,
pero no la cambian de categoría. Se informará siempre con su incertidumbre.

## Reproducibilidad

- Cada caché guarda en `manifest.json` el SHA-256 del snapshot, de cada ranking
  y de los ficheros de código y datos que lo determinan.
- El informe guarda los hashes del análisis y de los artefactos.
- Órdenes:
  - `python -m gabi.historical_revalidation --prepare <variante>`;
  - `--evaluate <vista>`;
  - `--summarize`.
