# ADR 0001: monolito modular local con fronteras comprobadas

Fecha: 2026-09-29. Estado: aceptado para orientar las implementaciones de GABI.

## Contexto

GABI necesita cálculos reproducibles, grandes cachés locales, tareas que sigan
sin navegador y una interfaz más clara. F1 separó backend/frontend, pero los
111 módulos Python aún mezclan responsabilidades y existen motores publicados
que no se pueden modificar sin cambiar su procedencia.

## Decisión

Adoptar [la arquitectura de referencia](../architecture.md): dominio/aplicación/
infraestructura en Python, adaptadores FastAPI/CLI y cliente React por capacidades.
Conservar SQLite y `data/`, componer dependencias explícitamente y migrar por flujo
con puentes legacy. Registrar deuda existente; rechazar su ampliación en CI.

## Alternativas y consecuencias

- Mantener código plano reduce trabajo inmediato, pero permite seguir mezclando
  consultas, fuentes, cálculos y presentación.
- Microservicios introducen despliegues, coordinación y fallos de red sin una
  necesidad actual de escalado por equipos o máquinas.
- Reescribir todo de una vez arriesga resultados, hashes y comparaciones. La
  migración gradual conserva adaptadores y cierta deuda durante varias fases.

Las capas añaden unas fronteras, no una jerarquía de objetos para cada función.
La arquitectura no prueba una estrategia ni garantiza una mejora de rendimiento:
equivalencia y coste de cada flujo se verifican al migrarlo. Si cambian los límites
de ejecución o aparece una necesidad medida, un ADR posterior puede sustituir
esta decisión con su plan y controles.
