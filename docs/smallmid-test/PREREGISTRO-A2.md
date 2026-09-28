# Ampliación A2 del preregistro #44: precios de Kaggle para las empresas desaparecidas hasta 2021

Escrita el 2026-09-27, **antes de importar los datos y de calcular ningún ranking** (la función se niega si
existe alguno). Especificación exacta en [`preregistro-a2.json`](preregistro-a2.json):

| Campo | Valor |
| --- | --- |
| SHA-256 de la ampliación | `39c274a0be955536f7fc5f132b7e3cb5cf5585aa6fcdcba18a712a5ad5f40428` |
| Amplía | preregistro `99d36edf…` y ampliación A1 `2608251c…`, sin modificarlos |
| Código | `smallmid_test.py`, SHA-256 `b850b1db…` |
| Análisis | sin cambios: las funciones del análisis de A1 conservan su huella `69efba58…` |
| Experimento | id 48, familia `stat_4` |

## Por qué

Con el plan gratuito, Tiingo tarda meses en completar la cola, y el plan gratuito de Financial Modeling Prep
no da precios de empresas desaparecidas. El conjunto público de Kaggle
[*US historical stock prices with earnings data*](https://www.kaggle.com/datasets/tsaustin/us-historical-stock-prices-with-earnings-data)
tiene precios de NASDAQ, NYSE y AMEX de 1998 a junio de 2021, incluidas empresas que dejaron de cotizar.

## Reglas

- **Fuente propia**: `kaggle:tsaustin-us-prices-2021-06:smallmid`, archivada aparte con el hash del zip. No
  toca la caché operativa ni las demás fuentes.
- **Limpieza**:
  - el importador rechaza, igual que en el resto de fuentes, las filas con precios ≤ 0 o incoherentes;
  - se eliminan los picos de un día que se deshacen al día siguiente (subida o bajada de más del 50 % seguida
    de un movimiento de más del 33 % en sentido contrario).
- **Identidad**: cada serie solo se acepta si pasa la comprobación de nivel de precio contra la SEC (#28),
  con la misma regla de 400 días que las demás fuentes.
- **Validación del conjunto**: entre las empresas que tienen serie de Kaggle y de otra fuente, y que pasan
  las dos la comprobación contra la SEC, al menos el **90 %** deben coincidir. Coincidir significa una
  diferencia mediana de cierre inferior al 1 % y menos del 2 % de días con retornos que difieran en más de
  1 punto. Si no se alcanza, Kaggle no se usa en absoluto.
- **Prioridad**: Yahoo, Tiingo, WIKI y, por último, Kaggle.
- **Corte**: solo en rebalanceos hasta el **2021-01-02**. El conjunto termina el 2021-06-01, y una serie que
  acaba ahí no es una empresa desaparecida: tomar ese último precio como salida falsearía el retorno.
- **Cola de Tiingo**: se retiran los símbolos cuyas empresas quedan cubiertas en todas sus fechas del
  universo. La cola original se conserva en `tiingo_symbols.before_a2.txt`.
