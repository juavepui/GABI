# Plataformas gratuitas de aplicación, jobs y acceso remoto para GABI

## ¿Cubren las plataformas gratuitas de aplicación el almacenamiento persistente y la disponibilidad 24/7 de GABI?

### Takeaway
Las cuatro plataformas de aplicación analizadas no cubren conjuntamente el despliegue completo de GABI, sus actualizaciones y su almacenamiento mutable de forma gratuita. Esto no descarta máquinas virtuales gratuitas, investigadas por otro agente; tampoco significa que no exista almacenamiento gratuito de objetos con capacidad suficiente.

### Cited Findings

Consulta de documentación oficial: 28 de septiembre de 2026. Los límites indicados corresponden a las páginas oficiales consultadas, con el matiz histórico expresamente señalado en Streamlit.

| Plataforma | RAM / CPU de la opción indicada | Disco y persistencia | Continuidad y principal bloqueo |
|---|---|---|---|
| Streamlit Community Cloud | 690 MB–2,7 GB RAM; 0,078–2 cores, cifras aproximadas publicadas **con fecha febrero de 2024**, sujetas a cambios | Máximo 50 GB en esa misma referencia histórica; la persistencia de archivos locales y SQLite no está garantizada | Duerme tras 12 horas sin tráfico. El dataset completo supera el límite publicado y las escrituras locales no son durables. [Recursos y sueño](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app), [SQLite local](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data) |
| Render Free | 512 MB RAM / 0,1 CPU | Sistema de archivos efímero; no admite disco persistente gratuito | Duerme tras 15 minutos sin tráfico; arranque aproximado de un minuto. Los archivos escritos se pierden al dormir, reiniciar o desplegar. [Compute](https://render.com/docs/compute-plans), [Free](https://render.com/docs/free) |
| Railway Free | Hasta 0,5 GB RAM / 1 vCPU por servicio | Volumen persistente de solo 0,5 GB | Existe Free permanente con $1 de crédito mensual, precedido de prueba $5/30 días. El volumen por sí solo excluye la DB y el dataset de GABI. [Precios actuales](https://railway.com/pricing), [Volúmenes](https://docs.railway.com/volumes/reference) |
| Hugging Face Spaces CPU Basic | 16 GB RAM / 2 vCPU | 50 GB de disco **no persistente** | CPU Basic no cobra por hora, pero crear o duplicar un Space compute Gradio/Docker exige plan pagado. Static Spaces son gratis; hay excepción de hasta 2 Gradio ZeroGPU por cuenta personal elegible. CPU Basic duerme tras 48 horas sin uso; para evitar sueño se requiere hardware pagado. [Overview](https://huggingface.co/docs/hub/spaces-overview), [Sueño](https://huggingface.co/docs/hub/spaces-gpus) |

- Streamlit advierte que sus límites pueden cambiar sin aviso y que la app puede ralentizarse o dejar de funcionar al alcanzarlos; la cifra 2,7 GB no debe presentarse como RAM dedicada garantizada. — [Manage your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)
- Render ofrece 750 horas gratuitas por workspace/mes, pero excluye discos persistentes y one-off jobs del servicio web Free. Su Postgres gratuito tiene 1 GB y caduca a los 30 días. — [Deploy for Free](https://render.com/docs/free)
- Hugging Face Hub sí publica **100 GB de almacenamiento privado para Free**, aplicables a repositorios models/datasets/buckets. El almacenamiento público es best-effort, con requisitos de uso responsable. — [Storage limits](https://huggingface.co/docs/hub/storage-limits)
- Sus Storage Buckets son almacenamiento de objetos parecido a S3. No tienen el historial Git de los repositorios de datasets. — [Storage Buckets](https://huggingface.co/docs/hub/storage-buckets)
- Cloudflare R2 incluye 10 GB-mes de almacenamiento Standard gratis, 1 millón de operaciones Class A y 10 millones Class B mensuales; no equivale a 100 GB gratis. — [R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- SQLite recomienda ejecutar lecturas/escrituras en la máquina que alberga la DB. WAL depende de memoria compartida y no funciona como DB compartida entre clientes sobre un filesystem de red. — [SQLite over a network](https://www.sqlite.org/useovernet.html), [Write-Ahead Logging](https://www.sqlite.org/wal.html)

### Inferences

- Con las medidas locales comunicadas por el coordinador (89,29 GB decimales en `data`, equivalentes a 83,16 GiB; DB activa 12,33 GB), ninguna de las cuatro plataformas de aplicaciones permite copiar el dataset completo a un disco gratuito durable y continuar como ahora. Incluso excluir archivos antiguos no resuelve la falta de persistencia de Streamlit/Render/HF.
- Esos 100 GB privados de Hugging Face admiten el volumen actual como archivos/objetos, en principio, con aproximadamente 10,7 GB de margen. No resuelven por sí solos el alojamiento de Python, un disco local durable de SQLite, el sueño del proceso ni los jobs. Backups/versiones y crecimiento pueden agotar rápidamente el margen.
- Guardar una copia cerrada consistente de SQLite en un bucket puede servir como archivo o respaldo. Usar el bucket como fichero SQLite activo no es una sustitución directa del disco local; haría falta rediseñar descarga, copia consistente, sincronización y coordinación de escritores. La aplicación conservaría un requisito de espacio local para trabajar.
- En particular, subir la DB al repositorio GitHub y confiar en redeploys no conserva automáticamente los cambios que produzcan las descargas o actualizaciones de la aplicación.

### Gaps

- No se ha ejecutado GABI en estos proveedores: no hay medida del pico de RAM real ni rendimiento de sus backtests en cada plan. El tamaño de la DB en disco no exige por sí mismo cargarla íntegra en RAM.
- Las páginas actuales de Hugging Face dicen expresamente **crear/duplicar** un nuevo Space compute con plan de pago. No explican exhaustivamente el trato retrospectivo de todos los Spaces existentes; no inferir que un Space antiguo gratuito desaparezca.
- La página de almacenamiento de Spaces no devolvió un cuerpo documental legible en la consulta; se evita reproducir como actuales los antiguos precios de almacenamiento persistente. El carácter no persistente del disco por defecto sí consta en Overview.

## ¿Qué jobs gratuitos sirven para actualizar o descargar datos de GABI?

### Takeaway
Hay ejecución gratuita limitada de jobs, pero no implica almacenamiento durable gratuito para los resultados ni un servidor web 24/7. Para una DB activa de 12,33 GB y un dataset de 89,29 GB, GitHub Actions hosted no constituye una solución completa.

### Cited Findings

- Render Cron Jobs cobran por ejecución, con **mínimo $1 al mes por servicio cron**; pueden programarse y ejecutarse manualmente. No pueden montar/acceder a discos persistentes; duración máxima de una ejecución, 12 horas. — [Cron Jobs](https://render.com/docs/cronjobs)
- Railway cron arranca un servicio con un calendario, espera que termine, admite intervalos mínimos de 5 minutos UTC y salta ejecuciones si la anterior sigue activa. La hora exacta puede variar unos minutos. — [Cron Jobs](https://docs.railway.com/cron-jobs)
- Railway Free aporta $1 de crédito al mes; prueba inicial $5/30 días. CPU, RAM y almacenamiento del plan gratuito son los indicados arriba. — [Pricing](https://railway.com/pricing)
- Hugging Face Jobs requiere saldo de créditos positivo y factura por minuto. CPU Basic para Jobs cuesta $0,01/h, con 2 vCPU, 16 GB RAM y 50 GB de almacenamiento efímero: el CPU Basic de Jobs tiene precio aunque el de Spaces no cobre por hora. — [Jobs pricing](https://huggingface.co/docs/hub/jobs-pricing)
- GitHub Actions standard hosted es gratis para repos públicos; GitHub Free privado incluye 2.000 minutos/mes, 500 MB de artefactos y 10 GB de caché por repositorio. Sin método de pago, se bloquea uso al agotar cuota; larger runners son de pago. — [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- Cada job standard hosted, salvo la opción single CPU, se ejecuta en una VM nueva. Ubuntu standard privado: 2 CPU, 8 GB RAM y 14 GB SSD; público: 4 CPU, 16 GB RAM y 14 GB SSD. — [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- Los jobs GitHub hosted tienen máximo de 6 horas por ejecución. — [Actions limits](https://docs.github.com/en/actions/reference/limits)
- `schedule` puede retrasarse o perder ejecuciones bajo alta carga; intervalo mínimo 5 minutos. En repos públicos se desactiva tras 60 días sin actividad en el repositorio. También existen disparadores manuales `workflow_dispatch`. — [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

### Inferences

- GitHub Actions es útil para tareas pequeñas y acotadas que envían sus resultados a un almacén externo ya resuelto. El SSD hosted de 14 GB no admite todo `data`; la DB activa sola dejaría muy poco margen para checkout, dependencias, descargas, WAL y temporales. Caché/artefactos gratuitos tampoco alojan la DB completa.
- 2.000 minutos/mes equivalen a unos 66,7 minutos diarios en un mes de 30 días, si se dedica toda la cuota a esa tarea. Es una ilustración matemática, no una medición del tiempo de actualización real de GABI.
- Un runner self-hosted local evita la cuota de compute hosted y trabaja con el disco existente, pero sigue dependiendo del PC. Tampoco convierte el PC apagado en un servidor disponible.
- Meter un scheduler dentro del proceso de una app que hiberna no garantiza actualizaciones nocturnas. Un cron externo puede disparar una petición, pero no aporta el disco durable ni garantiza que un trabajo largo termine.
- Para un despliegue en VM con disco suficiente, cron/systemd pueden ejecutar trabajos en la misma máquina que SQLite. La viabilidad gratuita de esa VM pertenece a la investigación complementaria de infraestructura.

### Gaps

- No se ha hallado en las páginas de Community Cloud consultadas un producto gratuito de jobs separado y durable; no afirmar que Streamlit prohíbe todo hilo/scheduler propio, sino que la hibernación impide usarlo como garantía 24/7.
- No se ha medido el tiempo mensual de los jobs concretos de GABI; la cuota gratis de Actions no prueba que quepan sus actualizaciones.

## ¿Podemos seguir en local y acceder remotamente sin pagar alojamiento?

### Takeaway
Sí: para uso personal, Tailscale permite acceso remoto privado a GABI manteniendo la DB y las descargas en el PC. La disponibilidad exige que ese PC permanezca encendido, sin suspensión, conectado y con GABI ejecutándose; no es nube independiente del PC.

### Cited Findings

- Plan Personal actual: **$0 gratis indefinidamente**, hasta 6 usuarios, dispositivos de usuario ilimitados, hasta 3 grupos ACL y hasta 50 recursos etiquetados inicialmente. — [Tailscale pricing](https://tailscale.com/pricing)
- Tailscale Serve comparte un servicio local dentro de la red privada Tailscale (tailnet). La documentación distingue Serve de Funnel, que publica al conjunto de internet. — [Serve command](https://tailscale.com/docs/reference/tailscale-cli/serve)
- Serve puede exponer un servidor de desarrollo local mediante URL HTTPS accesible solo a miembros del tailnet. — [Share local dev server](https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-team)

### Inferences

- Esta vía conserva capacidad de RAM, disco y jobs que ya tienen en el PC, y permite entrar desde portátil/móvil autorizado. No requiere copiar 89 GB a un proveedor ni publicar abiertamente la aplicación.
- Para uso personal bajo el plan indicado, no habría cuota de hosting; siguen existiendo electricidad, conexión a internet y mantenimiento del PC. No prometer servicio 24/7 si el equipo se apaga, se suspende o pierde conexión.
- La opción concreta sería GABI local como servicio con arranque automático, jobs en el programador de Windows y acceso privado mediante Tailscale. Es recomendación de arquitectura, no una configuración realizada.

### Gaps

- No se ha creado cuenta, conectado dispositivo, desplegado aplicación ni cambiado configuración. No se ha probado acceso remoto en la red real del usuario.
- El plan Personal es para particulares/uso personal; si el propósito concreto cambia a empresa habrá que revisar la elegibilidad, sin extrapolar gratuidad empresarial.
