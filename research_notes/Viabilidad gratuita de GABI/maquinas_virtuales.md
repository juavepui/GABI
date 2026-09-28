# Máquinas virtuales gratuitas permanentes para GABI

Investigación realizada el 28 de septiembre de 2026. No se ha creado ninguna cuenta, contratado servicios ni desplegado la aplicación. Tamaño local aportado por el coordinador: `data` = 89.288.750.430 bytes, 89,29 GB decimales o 83,16 GiB; `gabi.db` = 12,33 GB decimales. Son mediciones locales, no cifras del proveedor.

## ¿Alguna VM gratuita permanente admite todos los datos, RAM y jobs?

### Takeaway

Oracle Cloud Always Free tiene capacidad nominal para alojar los datos actuales y ejecutar GABI en una VM Linux sin contratar un plan de pago. Es la única candidata de las cuatro comparadas para una instalación completa y permanente; la suficiencia de RAM y la compatibilidad ARM aún requieren medición/prueba de la aplicación.

### Cited Findings

- Oracle: A1 ARM ofrece 1.500 OCPU-h y 9.000 GB-h mensuales, equivalentes a **2 OCPU y 12 GB RAM**, repartibles entre una o dos instancias. Ubuntu y Oracle Linux están incluidos. AMD micro: hasta dos VM, 1 GB RAM cada una. — [Recursos Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- Oracle: **200 GB combinados entre boot y discos de datos**, cinco backups de volumen, región principal; ejemplo oficial: boot 50 GB + datos 150 GB. Object Storage: 20 GB combinados para cuenta exclusivamente gratuita. Salida: 10 TB/mes. — [Recursos Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- Google Compute Engine: una `e2-micro` no preemptible, horas equivalentes al mes completo, sólo `us-west1`, `us-central1` o `us-east1`; **30 GB-mes de disco estándar**, 1 GB/mes de salida de Norteamérica, con destinos excluidos. Free Tier sin fecha final, pero modificable con preaviso. — [Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features#compute)
- Google `e2-micro` dispone de **1 GB RAM** y 0,25 vCPU fraccional sostenida, aunque expone dos vCPU con ráfagas. — [Tipos E2 shared-core](https://docs.cloud.google.com/compute/docs/general-purpose-machines#e2_shared-core)
- Google cobra IPv4 externas en VM estándar a **0,005 USD/h**, sólo una hora mensual gratuita por cuenta; una VM “gratis” con IPv4 pública ordinaria no es una instalación de coste total cero. — [Precios oficiales de IP externas](https://cloud.google.com/vpc/network-pricing#ipaddress)
- AWS: para cuentas desde el **15 de julio de 2025**, EC2 se prueba con 100 USD iniciales y hasta otros 100 USD; máximo seis meses o agotamiento del crédito. Para cuentas anteriores, EC2 tenía doce meses desde alta. — [Comparación oficial por fecha de cuenta](https://docs.aws.amazon.com/es_es/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)
- AWS cierra la cuenta gratuita y retira acceso a recursos al agotar el plan; no se puede extender más de seis meses. — [Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/)
- Azure ofrece las VM B1s/B2pts v2/B2ats v2 con 750 horas mensuales durante **doce meses** para clientes nuevos. — [Azure free account](https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account)
- Oferta Microsoft Marketplace: dos discos P6 de 64 GiB, únicamente para cuentas con beneficios gratuitos. — [Free account virtual machine, Microsoft](https://marketplace.microsoft.com/en-us/product/azure-services/microsoft.freeaccountvirtualmachine?tab=Overview)

### Inferences

- Cálculo conservador de Oracle usando GB decimales: **150 − 89,29 = 60,71 GB nominales libres en el disco de datos**. No significa 60,71 GB efectivos exactos: hay formato del volumen, metadatos del sistema de archivos, logs, ficheros temporales y crecimiento. Los 50 GB boot deben contener SO, aplicación y dependencias. En el total 200 GB quedan nominalmente 110,71 GB tras `data`, de los que una parte se dedica al sistema.
- Reservar los 200 GB para una sola VM maximiza el espacio útil para GABI; otras VM consumirían boot de la misma cuota. El objeto gratuito de 20 GB no admite copia completa de `data`, aunque cinco backups nativos de volumen son otra prestación.
- Una segunda copia íntegra de `data` dentro del disco de 150 GB necesitaría otros 89,29 GB y no cabe. No confundir backup nativo de volumen con copias manuales que sí gastan el disco activo.
- Google falla por almacenamiento incluso antes de instalar SO y paquetes. AWS y Azure fallan el requisito de gratuidad permanente; no merece trasladar 89,29 GB sólo para regresar al agotarse una promoción.
- 2 OCPU / 12 GB en funcionamiento continuo durante un mes de 31 días consumen 1.488 OCPU-h y 8.928 GB-h: quedan dentro de las cuotas publicadas de Oracle. No se ha demostrado que 12 GB cubran el pico de GABI cuando usuarios, backtests y actualizaciones se solapan.
- La VM ARM obliga a reinstalar dependencias para Linux ARM y verificar las que contienen binarios. No se debe copiar el entorno virtual Windows ni inferir compatibilidad sólo porque el proyecto está escrito en Python.

### Gaps

- No hay perfil de RAM/CPU de cargas representativas de GABI en esta investigación. No puede prometerse rendimiento ni simultaneidad.
- La documentación Oracle tiene una inconsistencia interna: la sección Compute habla de boot mínimo/default 47 GB y la sección Block Volume de 50 GB. Se usa el ejemplo explícito 50+150 para no depender de 3 GB adicionales.
- La documentación vigente confirma 2 OCPU/12 GB. No se ha encontrado anuncio primario con fecha exacta del cambio. Las guías antiguas que dicen 4 OCPU/24 GB no deben usarse para presupuestar una cuenta nueva.

## ¿Los jobs de actualización y descarga pueden ejecutarse gratis?

### Takeaway

En una VM Linux se pueden ejecutar scripts programados o bajo demanda. La cuota computacional es la de la máquina; una descarga no requiere un producto “jobs” adicional.

### Cited Findings

- Oracle Linux documenta `cron`, horarios diarios y ejecución de scripts/comandos mediante `crontab`; el tutorial permite horarios y argumentos. — [Crontab en Oracle Linux](https://docs.oracle.com/en/learn/ol-crontab/)
- Oracle documenta que `cron` programa tareas tan frecuentemente como cada minuto, y que si la máquina estaba apagada se pierde esa ejecución hasta el siguiente horario. — [Automating System Tasks](https://docs.oracle.com/en/operating-systems/oracle-linux/7/monitoring/monitoring-AutomatingSystemTasks.html)

### Inferences

- Los jobs diarios y los lanzados desde GABI pueden compartir la VM con Streamlit y SQLite; consumen RAM, CPU y disco de esa misma VM. No hay en la documentación de cron citada un límite de duración por invocación como el de una función serverless. Esto no impide que fallen por memoria, disco, reinicio o reclamación.
- Una actualización de larga duración podría seguir ejecutándose sin navegador abierto si se implementa como proceso de fondo/servicio supervisado. Hace falta revisar que el proyecto gestione eso correctamente; aquí sólo se valida la capacidad del proveedor.
- En Oracle la tabla Resource Manager que menciona “dos jobs, 24 horas” trata de **Terraform/provisión de infraestructura**, y no es el límite de los scripts de actualización que corren dentro de una VM. No debe confundirse al responder al usuario.

### Gaps

- No se ha medido volumen futuro de descargas ni duración de los jobs de GABI. Mantenerlos indefinidamente puede superar 150 GB de datos.
- La coexistencia de lecturas de la aplicación y escrituras SQLite requiere verificar bloqueos y transacciones en el código; no es una limitación especial del plan gratuito.

## ¿Puede garantizarse disponibilidad 24/7 sin ningún pago?

### Takeaway

**Oracle permite técnicamente mantener la VM encendida gratis, pero no permite prometer disponibilidad continua 24/7.** Si “gratis y siempre disponible” es una condición estricta, la conclusión conservadora es continuar en local. Si se aceptaran interrupciones, Oracle sería una posibilidad condicionada a capacidad y pruebas.

### Cited Findings

- Oracle: recursos gratuitos durante la vida de la cuenta; crear VM puede fallar por capacidad regional. Puede reclamar VM si durante siete días CPU p95, red y RAM (A1) permanecen cada una por debajo del 20%. — [Recursos Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- Oracle Free Tier **no incluye SLA**; usuarios que sólo consumen Always Free no tienen Oracle Support. — [FAQ oficial Oracle Suecia, en inglés](https://www.oracle.com/se/cloud/free/faq/)
- Oracle puede considerar abandonadas y suspender/terminar cuentas inactivas treinta días. Pide tarjeta y datos válidos; puede aplicar retenciones temporales para verificarla, que se liberan y no son cargos efectivos. — [FAQ Oracle](https://www.oracle.com/cloud/free/faq/)
- La prueba Oracle dura treinta días/300 USD; Always Free no caduca con ella. Normalmente exige móvil y tarjeta, y no carga la tarjeta salvo que se actualice a pago. Antes de acabar la prueba deben respetarse 2 OCPU/12 GB; recursos de pago de la prueba se recuperan si no se actualiza. — [Free Tier oficial](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)
- Azure deshabilita servicios al terminar los treinta días/crédito si no se actualiza la cuenta; tras actualizar, cualquier uso fuera de las franquicias sí se factura. — [Evitar cargos Azure](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account)
- Google exige cuenta de facturación; al acabar la prueba sin actualizar se paran recursos y posteriormente se borran. Cuenta pagada factura los excesos del Free Tier. — [Google Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features)

### Inferences

- Una aplicación personal con sesiones ocasionales y jobs diarios breves puede cumplir los criterios de inactividad de Oracle. Tener Streamlit arrancado no demuestra uso suficiente. No se recomienda fabricar carga ni tráfico para evadir la recuperación.
- Quedarse con cuenta Oracle gratuita, usar sólo recursos permanentes y no activar Pay As You Go respeta el objetivo de cero pagos efectivos indicado por su documentación; sigue exigiendo tarjeta/verificación. Los créditos de la prueba no se deben interpretar como financiación permanente.
- La etiqueta “Always Free eligible” debe acompañarse de comprobación de la cuota total de recursos, especialmente durante el trial. Se requiere dejar margen de disco y preservar copias locales. No trasladar la única copia de la base de datos.
- La falta de SLA más recuperación por inactividad y falta de capacidad deja la disponibilidad bajo condiciones del proveedor. Una única VM tampoco aporta alta disponibilidad técnica aunque no la reclamen.
- La alternativa estricta sería mantener GABI local. Dar acceso remoto al equipo local podría estudiar otra tarea, pero tampoco ofrece acceso 24/7 si el equipo no permanece encendido y conectado.

### Gaps

- No se puede consultar capacidad real de una región ni elegibilidad de la cuenta sin registrarse. No se ha hecho por estar fuera de esta verificación.
- No puede garantizarse que políticas/cuotas gratuitas permanezcan iguales en el futuro, ni el rendimiento o tiempo de recuperación tras retirada de la VM.
