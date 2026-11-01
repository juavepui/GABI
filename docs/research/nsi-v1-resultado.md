# Resultado exploratorio de NSI-v1 (#252)

**Decisión según el preregistro: `abandon`.** La evaluación tiene un defecto de
ejecución en 2011–2015, declarado más abajo. Con ese defecto, la regla que se
aplica es «exceso neto ≤ 0». Sin la ventana defectuosa, la decisión sigue siendo
la misma por la segunda regla: cota inferior negativa en dos de las tres
ventanas. La decisión final la toma el propietario.

**Datos:**
- Artefacto: [`nsi-v1/resultado.json`](nsi-v1/resultado.json).
- Preregistro: [`nsi-v1/preregistro.json`](nsi-v1/preregistro.json) y
  [enmienda 1](nsi-v1/enmienda-1.json).
- Historia observada de julio de 2011 a julio de 2025. **Nunca cuenta como
  evidencia independiente.**

## Cifras en euros

Cuenta de 11.000 € más 700 € al mes, con rentabilidad ponderada en el tiempo.

| Configuración | Anualizado | S&P 500 | Exceso | Máx. DD (índice) | Rotación | Caja media |
|---|---:|---:|---:|---:|---:|---:|
| Primaria (Top-20 BASE) | 10,0 % | 14,8 % | −4,8 pp | −35,2 % (−33,1 %) | 0,8× | 42,9 % |
| STRESS (Top-20) | 9,8 % | 14,8 % | −5,0 pp | −35,2 % | 0,8× | 42,9 % |
| Top-30 BASE | 10,2 % | 14,8 % | −4,7 pp | −37,1 % | 0,8× | 42,5 % |
| Equiponderado del universo (comparador) | 5,7 % | — | — | −34,1 % | — | — |

**Configuración primaria por ventanas.** Exceso medio anual y cota inferior
unilateral (bootstrap de bloques de 12 meses, α = 0,05/3):

| Ventana | Exceso medio | Cota inferior |
|---|---:|---:|
| 2011–2016 | −11,1 pp | −19,2 pp | ← **defectuosa** |
| 2016–2021 | −1,9 pp | −10,4 pp |
| 2021–2025 | +0,9 pp | −5,5 pp |

**Alfa FF5+UMD:** −0,7 pp anual, con un intervalo del 95 % de [−4,3; +2,9]
(t = −0,4). Las cargas son mercado 0,64, SMB 0,35, HML 0,25, RMW 0,49, CMA −0,04
y momentum 0,01.

## Defecto de ejecución en 2011–2015

- **Qué pasó.** El archivo histórico de precios de 2010–2015 solo tiene cierre y
  cierre ajustado, sin apertura ni volumen. El motor V3 ejecuta en la apertura
  de la sesión siguiente, así que no pudo comprar nada en esas ventanas:
  - 1.500 órdenes quedaron bloqueadas como `absent`;
  - la estrategia estuvo **100 % en caja de 2011 a 2015**;
  - desde 2016, con precios de Yahoo, la caja baja al 5–16 %.
- **Por qué no se vio antes.** La comparación V2/V3 de #249 solo usó el periodo
  de 2016 a 2025, y los tests usan series sintéticas con apertura.
- **Consecuencias para el resultado:**
  - La ventana 2011–2016, el exceso del conjunto, la caja media y el alfa están
    contaminados por esos años en caja. El alfa incluye meses sin exposición.
  - El comparador equiponderado sufre el mismo defecto: 5,7 %.
- **Además, en 2016–2025** quedaron sin precio entre 1 y 5 valores
  seleccionados por año (por ejemplo DFS, CTXS, CBS, GPS y SEE). Su peso también
  quedó en caja.

## Lectura

- **Las dos ventanas válidas no muestran ventaja.**
  - En 2016–2021 el exceso fue de −1,9 pp, con una cota inferior de −10,4 pp.
  - En 2021–2025 fue de +0,9 pp, con una cota inferior de −5,5 pp.
  - La regla «cota inferior negativa en al menos dos de las tres ventanas» se
    cumple sin usar la ventana defectuosa, así que la decisión `abandon` no
    depende del defecto.
- **Cargas factoriales.** Corregir el defecto no podría cambiar la decisión
  sin cambiar las reglas después de ver los datos. Las cargas (RMW 0,49 y CMA ≈ 0)
  indican que lo que capta la selección se parece más a calidad que a la prima
  de inversión.
- **Riesgo.** La volatilidad (86 % de la del índice) y el drawdown (−2,1 pp
  peor) cumplen los límites preregistrados, pero eso no compensa la falta de
  exceso.

## Pendiente

- El propietario decide si se acepta el abandono y se registra en el ledger de
  #60 como intento observado.
- El defecto del motor V3 con el archivo de 2010–2015 (sin apertura ni volumen)
  queda como limitación conocida para cualquier evaluación futura de ese
  periodo.
