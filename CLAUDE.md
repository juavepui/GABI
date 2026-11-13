# Cómo comunicar en GABI

Las reglas técnicas del proyecto están en [AGENTS.md](AGENTS.md) y siguen
vigentes. Este fichero añade una regla de **lenguaje**: quien usa GABI y quien
lee las respuestas es un inversor novato, con muy pocos conocimientos sobre
invertir. El trabajo puede ser tan complejo y riguroso como haga falta; la forma
de contarlo tiene que ser sencilla.

Simplificar las palabras nunca significa simplificar el trabajo: no se redondean
conclusiones, no se ocultan dudas y no se cambian números ni cálculos para que
«suenen mejor».

## 1. En el chat (respuestas de la IA)

Todo en español (ver memoria de idioma).

**Empieza por lo que importa.** La primera o las dos primeras frases dicen, en
lenguaje llano, qué se ha hecho o qué se ha descubierto y qué significa para el
usuario. Los detalles técnicos (ficheros, PR, hashes, comandos, tests) van
después, breves, para quien quiera comprobarlos.

**Explica cada término técnico la primera vez que aparece**, entre paréntesis o
con una frase corta. Mejor aún, usa la palabra corriente:

| En vez de…              | Di…                                                                 |
| ----------------------- | ------------------------------------------------------------------- |
| backtest                | prueba con datos del pasado (backtest)                              |
| drawdown máximo         | la mayor caída desde un máximo                                      |
| Sharpe                  | rentabilidad por cada unidad de riesgo (ratio de Sharpe)            |
| sobreajuste / overfit   | que el resultado salga bien por casualidad y no se repita           |
| holdout / periodo reservado | datos que guardamos sin mirar para comprobar al final           |
| point-in-time           | usando solo lo que se sabía en aquella fecha                        |
| factor / score          | criterio con el que se puntúan las empresas / puntuación            |

**Da contexto a los números.** Un número solo no dice nada: «un 8 % al año,
frente al 10 % del índice en el mismo periodo», «la mitad de las veces», «en 9
de cada 10 pruebas».

**Usa ejemplos y comparaciones cotidianas** cuando un concepto sea abstracto
(«diversificar es no poner todos los huevos en la misma cesta»).

**Sé honesto con la incertidumbre**, también en palabras sencillas: «todavía no
está demostrado», «puede haber sido suerte», «lo sabremos en diciembre cuando
haya datos nuevos». Nunca prometas rentabilidades ni presentes un resultado del
pasado como garantía de futuro.

**Frases cortas y estructura ligera.** Una idea por frase. Listas cuando ayuden,
no títulos por obligación. En respuestas largas, termina con un resumen de una o
dos líneas: qué cambia para el usuario y cuál es el siguiente paso, si lo hay.

**Lo exacto sigue siendo exacto.** Nombres de ficheros, funciones, comandos,
identificadores de modelos (`GABI-MF-v2`) y fechas se escriben tal cual; lo que
se explica es qué significan.

## 2. En la aplicación (textos que ve el usuario)

Esta regla se aplica a todo texto nuevo o modificado en `frontend/src/` y a los
textos de ayuda que sirve el backend (glosario, ayudas de métricas, mensajes de
error y avisos).

**Público.** El modo Investor es para un inversor novato: ningún texto debería
necesitar conocimientos previos. El modo Research puede ser más técnico, pero
cada término sigue teniendo su explicación a un clic.

**Cada pantalla responde primero a tres preguntas**, por este orden:

1. ¿Qué estoy viendo?
2. ¿Es bueno, malo o normal?
3. ¿Qué puedo hacer con esto?

La metodología va después, plegada en `HowToRead` («Cómo leer esto»).

**Términos técnicos.** Siglas y jerga (PER, EV/EBITDA, ROIC, Sharpe, drawdown,
CIK…) van siempre con su explicación mediante `Term` (glosario del backend) o
`Hint`. Si el término no existe en el glosario, se añade en el backend
(`backend/src/gabi/domain/research/glossary.py` o
`backend/src/gabi/domain/market/metric_info.py`), no como texto suelto en React:
el backend es la fuente única de definiciones. Las definiciones se escriben como
en el chat: frase llana primero, matiz técnico después.

**Etiquetas y botones** con palabras corrientes y verbos claros («Ver por qué
puntúa así», «Comparar con el mercado»), no con nombres internos de la
implementación.

**Números con unidad y referencia**: %, €/$, periodo («al año», «en 5 años») y,
cuando exista, con qué se compara (índice, media del sector). Las ausencias se
explican («Sin datos: la empresa no ha publicado este informe») en lugar de
mostrar solo «—», «N/A» o `null`.

**Errores y estados vacíos** dicen qué ha pasado y qué puede hacer el usuario,
sin trazas, códigos ni jerga de servidor en modo Investor.

**Avisos honestos.** La aplicación informa y ordena empresas; no da órdenes de
compra o venta. Cuando se muestren resultados históricos, recordar de forma
breve y visible que el pasado no garantiza el futuro y, si aplica, cuánta
evidencia hay detrás (por ejemplo, «probado solo con datos del pasado; aún sin
confirmar con datos nuevos»).

**Límites de esta regla.**

- Cambiar textos no cambia cálculos, filtros, unidades ni la decisión del modo
  Investor/Research, que siguen siendo del backend (ver AGENTS.md).
- Los motores y la configuración congelados no se tocan para reescribir textos;
  si un texto sale de ellos, se adapta en la capa de presentación.
- Los tests (unitarios y e2e) que buscan elementos por su texto se actualizan en
  el mismo cambio.
