# Planes de análisis de las pruebas ciegas prospectivas (#42)

Planes fijados antes de ver ningún dato prospectivo. Código:
`gabi.prospective_plan`.

## Prueba ciega de GABI (id 1): [gabi-id1.json](gabi-id1.json)

- **Revisión**: una única, en el desbloqueo del **2029-09-21**, con 12
  trimestres. El propietario decidió no prolongarla (2026-09-27).
- **Prueba principal**: exceso trimestral del Top-20 ciego frente al SPY, z
  unilateral con α = 5 % (umbral 1,645).
- **Prueba secundaria**: exceso frente a RSP (S&P 500 equiponderado), con
  corrección de Holm.
- **Combinación**: Stouffer ponderado por la raíz del número de trimestres, con
  los 18 trimestres acreditados de 2011-07 a 2015-10. 2016–2025 queda fuera
  porque es la muestra de diseño.
- **Potencia**: si el efecto futuro fuese el observado en 2011–2025, **26 %
  sola y 48 % combinada**. No cruzar el umbral en 2029 no demostrará que GABI
  no funcione; cruzarlo sí sería evidencia a favor.

## Hipótesis de valor (id 3)

Diseño secuencial con umbrales O'Brien-Fleming (gasto de alfa de Lan-DeMets):

| Revisión | Trimestres | Umbral z |
| --- | ---: | ---: |
| 2029-12-21 | 12 | 3,39 |
| 2032-12-21 | 24 | 2,28 |
| 2036-12-21 | 40 | 1,68 |

La prueba principal es el IC prospectivo de sección cruzada. Detalle en el
[preregistro del #43](../value-hypothesis/PREREGISTRO.md).

## Integridad

- Ambas pruebas deben registrar su próximo rebalanceo el **2026-12-21**, con
  los precios refrescados antes. Desde Investigación → Validaciones ciegas (interfaz React) o con
  `blind_validation.record_rebalance`.
- Las cadenas de hashes (`verify_integrity`) deben estar íntegras en cada
  revisión.
