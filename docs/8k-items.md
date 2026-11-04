# 8-K por código «Item», sin IA (#292)

Un 8-K es el aviso que una empresa de EE. UU. envía a la SEC cuando pasa algo
importante. La propia empresa marca de qué trata con códigos «Item» (por
ejemplo 2.02 = resultados). El índice `submissions` de la SEC trae esos códigos
en el campo `items`. GABI los traduce con una tabla fija y versionada,
`8k-items-v1` (`backend/src/gabi/domain/market/current_reports.py`). No lee el
texto del documento ni usa IA.

## Reglas

- Se guardan los formularios `8-K` y `8-K/A`. Un 8-K/A corrige o completa uno
  anterior y se clasifica igual.
- Un 8-K puede marcar varios Items. Se muestran todos, en el orden de la SEC y
  sin repetir ninguno.
- Un código que no está en la tabla sale como «Sin clasificar (Item X)». GABI no
  intenta adivinarlo. Es el caso de la numeración anterior a 2004, de las erratas
  y de los Items futuros.
- Piden revisar una idea abierta (#247) los Items 1.03 (quiebra), 3.01 (aviso de
  exclusión de bolsa), 4.01 (cambio de auditor) y 4.02 (las cuentas anteriores
  ya no son fiables). La alerta es de tipo `8k` y solo pide revisar; nunca es una
  orden de compra ni de venta. Las alertas pasan a `idea-alerts-v2`.

| Items | Categoría |
| --- | --- |
| 1.01, 1.02 | Contrato importante (firma o fin) |
| 1.03 | Quiebra o administración judicial |
| 1.04 | Seguridad en minas |
| 1.05 | Incidente de ciberseguridad importante |
| 2.01 | Compra o venta de activos completada |
| 2.02 | Resultados |
| 2.03, 2.04 | Deuda nueva o que vence antes de tiempo |
| 2.05, 2.06 | Reestructuración o deterioro |
| 3.01 | Aviso de exclusión de bolsa |
| 3.02, 3.03 | Emisión de acciones o cambio de derechos de los accionistas |
| 4.01 | Cambio de auditor |
| 4.02 | Las cuentas anteriores ya no son fiables (reexpresión) |
| 5.01 | Cambio de control de la empresa |
| 5.02 | Cambio de directivos o consejeros |
| 5.03–5.06 | Estatutos, código ético u otros cambios de gobierno |
| 5.07, 5.08 | Votaciones de accionistas |
| 6.01–6.05 | Valores respaldados por activos |
| 7.01 | Comunicación al mercado |
| 8.01 | Otros hechos |
| 9.01 | Estados financieros y anexos |

## Descarga y lectura

- **Descarga.** Cada sincronización SEC (`edgar.synchronize_issuer`, usada por
  «Actualizar datos») ya descarga el índice `submissions`. Ahora también guarda
  sus 8-K en `sec_current_reports`, sin ninguna petición más. En la ficha, el
  botón «Descargar los 8-K de esta empresa» lanza un trabajo explícito
  (`company_sync` con `dataset=current_reports`) que solo descarga ese índice.
- **Lectura.** `GET /api/v1/companies/{symbol}/current-reports` solo lee. No
  crea la tabla ni descarga nada.
- **Tests.** Usan filas reales del índice (Super Micro Computer, Apple y
  Microsoft), presentadas antes de 2025-07-02:
  `backend/tests/fixtures/sec_8k_submissions.json`.
