# Ampliación descriptiva de #48: estabilidad por industria SIC fechada

Se fija el 2026-09-28 **antes de calcular cobertura, IC o estabilidad por estos grupos**. El Factor Zoo original ya fue observado; esta ampliación solo completa un diagnóstico descriptivo y no constituye una nueva prueba confirmatoria ni una búsqueda de factores.

La [documentación oficial de la SEC, sección SUB](https://www.sec.gov/files/financial-statement-data-sets.pdf) especifica que SIC es el código asignado en la fecha de presentación. Hay archivos SUB de 2009–2025 ya archivados localmente por las auditorías de identidad. Se usarán esos documentos, con CIK, accession, fecha de presentación/aceptación y huellas de fuente. La clasificación es la [estructura de divisiones SIC de OSHA](https://www.osha.gov/data/sic-manual), sin convertirla a GICS ni emplear sectores actuales.

Reglas cerradas:

- Conservar los 57 rankings, elegibilidad, percentiles y retornos congelados del Factor Zoo original. Sus huellas se verifican; no se recalculan scores, rankings, retornos ni inferencia primaria/Holm.
- Unir únicamente el `entity_id` CIK del ranking congelado con el **registrante principal** del SUB archivado. No inferir CIK por ticker actual ni atribuir al co-registrante el SIC de su matriz.
- Último 10-K/10-Q o enmienda con presentación y aceptación **anteriores al día de señal**, ambas conocidas, con antigüedad máxima de 400 días. Excluir el mismo día por no disponer de una hora de señal en el ranking. Un dato ausente/inválido en el último filing no se sustituye por un filing anterior. Empates temporales con SIC distintos son ambiguos y quedan sin grupo.
- SIC → divisiones oficiales: A 0100–0999; B 1000–1499; C 1500–1799; D 2000–3999; E 4000–4999; F 5000–5199; G 5200–5999; H 6000–6799; I 7000–8999; J 9100–9799. Otros códigos quedan sin clasificar. Son industrias amplias, distintas de los 11 sectores GICS.
- Las mismas 13 señales y signos orientados. IC Spearman por división/fecha con al menos 30 pares finitos y variación en señal y retorno; los demás grupos/fechas se publican como no estimables, no se unen ni eliminan.
- Resumen descriptivo por señal/división: IC medio, ICIR, fracción de trimestres positivos, número de periodos, pares y las ventanas fijas 2011–15, 2016–20 y 2021–25. Cada trimestre pesa igual. Con menos de 30 periodos se indica soporte temporal insuficiente; no hay p-valores nuevos ni clasificación de robustez.
- Publicar cobertura de identidad/filings/SIC por fecha, por señal y por disponibilidad de retorno, junto con exclusiones, asignaciones y huellas. No imputar sectores a empresas sin retorno ni descartar esa falta de retorno del denominador de cobertura.
- Guardar el suplemento separado del resultado original y mostrarlo en Factor Lab y en los componentes de evidencia. No permite elevar automáticamente la confianza ni seleccionar componentes del ensemble #53.

La ausencia de GICS histórico sigue siendo un límite. Una cobertura parcial SIC se publica como tal; la información nueva no corrige los percentiles globales usados por los rankings originales ni el control sectorial ausente de sus regresiones/placebos.
