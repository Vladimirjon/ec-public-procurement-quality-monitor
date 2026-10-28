# Traspaso del Día 20 (nuevo chat)

Este archivo resume dónde quedó el trabajo del Día 20 para continuar en un chat
nuevo. Sustituye a leer la conversación anterior. Léelo junto con
`docs/learning/day-20-prompt.md` (reglas de siempre) y `specs/ingest-command/`.

## 1. Estado exacto (2026-10-22)

- Rama `fix/ingest-audit-hardening`, PR 26 abierto contra `main`, con Auto-fix
  activo y sin auto-merge. Último SHA con CI verde: `c20827d` (workflow `Tests`,
  run 39782097174, 2775 passed en Linux; workflow `harny feedback`, run
  39782097285). Nada de lo siguiente está commiteado.
- La auditoría de la ronda 6 (sobre `c20827d`) **rechazó** por un hallazgo MEDIUM,
  F-27: con un stream de salida cerrado de verdad (pipe cerrado), el proceso sale
  con 120 en lugar de 1, y Python imprime `Exception ignored on flushing
  sys.stdout`. Con stderr cerrado también sale 120, en silencio. El informe está
  en `specs/ingest-command/audit.md`, sin commitear; se conserva como evidencia
  histórica del rechazo. Hallazgos LOW de la ronda 6: F-28 (comportamiento exigido
  sin prueba permanente), F-29 (dos nombres de prueba con `usage`), F-12
  (contabilidad desactualizada).
- Tú elegiste cerrar F-27 con la opción (b) (arreglarlo en el código) y las
  decisiones D-6 a D-9 en su opción A, y D-10 en su opción A (un intento de mejor
  esfuerzo por stream, con la limitación residual declarada, sin mecanismo de
  respaldo). Las specs intent 14, plan 12 y tasks 9 están redactadas por el
  architect y siguen **pendientes de tu aprobación**: las tres líneas `Approval`
  no se han actualizado. Elegir D-10 no se registró como aprobación del conjunto.
- Verificado por el asistente de esta sesión: con un hijo `python -c` y un pipe real, un stdout
  cerrado da 120 con el informe `Exception ignored`, y un stderr cerrado da 120 en
  silencio (Windows, Python 3.13.9). El comando completo `cli.main` en proceso real
  lo reprodujo el auditor, no el asistente.
- La puerta 3 sigue abierta. No hay merge, no hay `Shipped:`, no se archivó
  `specs/ingest-command/`, y no se ha hecho ninguna ingesta real.

Siguiente paso, en este orden, parando donde dice:

1. Tú apruebas (o enmiendas) intent 14, plan 12 y tasks 9. Se registra en las
   líneas `Approval` solo cuando tú lo digas.
2. Test-writer: pruebas de los 12 tokens nuevos del plan Revision 12 (nivel de
   proceso en `tests/process/`, F-28, `neutralize_fault`, `flush_stream_fault`,
   los dos renombres de F-29). Evidencia roja por grupo. Parada.
3. Executor: corrige sin editar pruebas (módulo `interfaces/output_streams.py`
   compartido, usado por `ingest_command.py` y `cli.py`). Checks, evidencia
   verde, diff. Parada antes de commit.
4. Commits sin atribución, push al PR 26, CI sobre el nuevo HEAD (distinguir SHA
   validado de HEAD), auditoría de la ronda 7 con una pasada exhaustiva. Parada:
   puerta 3.
5. Solo después de la puerta 3: bloque B (sellar `Shipped:`, archivar, capacidades)
   y merge con tu OK explícito; luego el bloque C (tu ingesta real).

Reglas que no cambian: sin atribución a Claude en commits, PR, bitácora ni docs;
no aprobar nada en tu nombre; el executor nunca edita pruebas; sin dependencias
nuevas ni red real en pruebas; no leer `.env`; checks en silencio;
`uv run ruff format --check .` tras escribir specs o docs (ruff también formatea
los bloques de Python de los `.md`); la bitácora del Día 20 la escribes tú.

## 2. El recorrido de una ingesta, en lenguaje sencillo

Imagina que `ingest` es una bibliotecaria que pide, una por una, las páginas de un
catálogo público (SERCOP) y guarda lo que recibe de dos maneras: una copia exacta
en una carpeta y un registro ordenado en una base de datos.

1. **Arranque.** Lee tus datos de conexión (variables `POSTGRES_*`), construye el
   cliente que hablará con SERCOP y aplica en PostgreSQL las migraciones que falten
   (crear las tablas la primera vez). Si algo de esto falla, no se escribe nada y
   sale con 2 (error de uso) o 1.
2. **Un solo ingest a la vez.** Toma un candado en la base (la "exclusión"). Si
   otro `ingest` lo tiene, se niega a empezar.
3. **Limpieza de lo anterior.** Si una ejecución previa quedó marcada `running`
   (por ejemplo, se cortó la luz), la cierra como `failed`, después de copiar a
   PostgreSQL cualquier observación que solo existiera en la carpeta.
4. **Abrir la ejecución.** Crea una fila en `ingestion_run` con un identificador
   como `ingest-20251022t120000z-0123abcd`, el alcance (año, comprador, páginas) y
   el estado `running`. Imprime el identificador por stderr.
5. **Página por página.** Para cada página pide la respuesta a SERCOP (sin
   reintentar), guarda la respuesta cruda en `data/raw/` con su huella SHA-256
   (nunca se sobrescribe), anota la observación en la tabla `observation` (qué URL,
   qué código HTTP, cuándo, qué huella) y añade un evento `page-completed` en
   `audit_event`. Si una página falla, se detiene en la primera que falla.
6. **Cierre.** Termina cuando pide la última página que le diste o cuando SERCOP
   indica que ya no hay más (`last-page-reached`). Marca la ejecución `succeeded` o
   `failed`, imprime una sola línea `<identificador> <estado>` por stdout y sale con
   0, 1, 2 o 130 (Ctrl+C).
7. **Si algo se corta.** Un Ctrl+C o un error inesperado intenta anotar un evento
   (`run-interrupted` o `unexpected-error`) y cerrar la ejecución. Si ni eso puede
   (se perdió la conexión, se rechazó la escritura), la deja `running` y la
   siguiente ejecución la cierra. Una ejecución fallida se continúa con
   `--resume <identificador>`.

Lo que se garantiza para que puedas confiar en los datos: lo guardado no se
modifica (disparadores en PostgreSQL), una respuesta solo se anota si su copia
cruda existe, y el estado final que imprime el comando es el que PostgreSQL
confirmó (o `running` si no pudo confirmarlo).

Tablas donde miraremos: `ingestion_run` (una fila por ejecución),
`observation` (una fila por respuesta capturada), `raw_evidence` (una fila por
contenido distinto, con tamaño) y `audit_event` (los hechos de cada ejecución, en
orden).

## 3. Criterio concreto de cierre de F4

Aprobado por Vladimirjon el 2026-10-23 (en el chat nuevo del Día 20). Esta
aprobación cubre solo el criterio de cierre; no aprueba intent 14, plan 12 ni
tasks 9, cuyas líneas `Approval` siguen sin tocar:

**F4 se cierra (puerta 3) cuando se cumplen las cuatro condiciones:**

1. No queda abierto ningún hallazgo de **clase A** (ver abajo), de cualquier
   severidad.
2. La suite pasa completa con la base de datos (sin pruebas saltadas) y en CI sobre
   el HEAD del PR, y `ruff`, `mypy` y el doctor están limpios.
3. La auditoría más reciente audita ese mismo HEAD y su veredicto es APROBADO o
   APROBADO CON RESERVAS.
4. Las reservas que queden están escritas, con su razón, en `audit.md` y en
   `tasks.md` § Carried reservations, y tú las aceptaste por escrito.

**Clase A, bloquea el cierre** (defecto que compromete datos o incumple el alcance
acordado):

- Se puede perder, duplicar, sobrescribir o corromper una observación o su copia
  cruda.
- El estado final que se imprime o se guarda contradice lo que realmente ocurrió
  (por ejemplo, una ejecución marcada `succeeded` sin que sus páginas estén
  guardadas, o `running` impreso para una ejecución confirmada).
- Se escribe en PostgreSQL algo que la spec prohíbe, o se ignora el candado de
  ingest único.
- Se filtra un secreto, una URL, una cabecera o un cuerpo en stdout, stderr o
  logs.
- Un criterio de aceptación (AC) explícito de `intent.md` o una promesa escrita en
  el README no se cumple.
- Un camino exigido por el plan no tiene ninguna prueba que fallaría si se
  quitara, **y** ese camino toca datos o estado de la ejecución.

**Clase B, puede quedar pendiente como reserva o mejora** (no compromete datos ni
alcance):

- Redacción o orden de mensajes que la spec deja libres.
- Pruebas permanentes extra para caminos que ya se verificaron con
  experimentos y no tocan datos.
- Nombres de pruebas, contabilidad y texto desactualizado de las specs (F-12,
  F-29).
- Casos de doble fallo extremos (Ctrl+C en el instante exacto de un rechazo ya
  contestado) cuya consecuencia es un mensaje o un estado `running` que el
  siguiente `ingest` cierra, sin pérdida de datos.
- Mejoras de ergonomía (nuevos comandos, otras fuentes, reintentos).

**Cómo clasificaría los hallazgos abiertos hoy** (para que lo revises):

| Hallazgo | Clase | Razón |
|---|---|---|
| F-27 (exit 120 con pipe cerrado) | A | Incumple AC14 y AC15 y una promesa del README, aunque no daña datos: el estado guardado es correcto. Ya decidiste corregirlo con (b). |
| F-28 (pruebas permanentes que faltan) | B | Los caminos son correctos (verificados con experimentos); falta protección contra regresiones, sobre todo del manejo de salida, no de datos. |
| F-29 (nombres con `usage`) | B | No afecta el comportamiento. |
| F-12 (texto desactualizado) | B | Contabilidad. |
| F-23 (rechazo y Ctrl+C en su línea) | B | Decidido en D-2: se conserva el comportamiento actual, sin pérdida de datos. |
| Limitaciones de F-20 (líneas 388-389 y 598) | B | Aceptadas, con experimentos que muestran el comportamiento previsto. |

Regla práctica para las observaciones nuevas: antes de abrir una ronda, preguntar
"¿esto puede hacer que haya datos incorrectos o ausentes, o rompe un AC o una
promesa del README?". Si sí, es clase A. Si no, se anota como reserva y no abre una
ronda nueva.

## 4. Tu hito: tres páginas reales y su comprobación con SQL

Condición previa: gate 3 cerrada, PR 26 fusionado con tu OK explícito, Compose
arriba y `.env` en su sitio (lo llenas tú; nadie lo lee ni lo imprime). Hasta
entonces **no se ejecuta la ingesta real**.

Tareas pequeñas, una por vez (cada una con qué compruebas, por qué y una pregunta
de comprobación). El chat nuevo las presenta de una en una y espera tu respuesta
antes de pasar a la siguiente:

1. **Leer el esquema.** Abre `migrations/0001_initial_schema.sql` y localiza las
   cuatro tablas. Por qué: sabrás qué filas deben existir después. Pregunta: ¿qué
   tabla tiene una fila por respuesta y cuál una por contenido distinto?
2. **Comprobar el punto de partida.** Con Compose arriba, cuenta las filas de las
   cuatro tablas con `psql`. Por qué: para saber qué cambió la ingesta y no
   confundirlo con datos previos. Pregunta: ¿qué valor esperas para cada tabla?
3. **Revisar el comando.** Lee, sin ejecutar, el comando de la ingesta
   (`--year 2025 --buyer "EMPRESA ELÉCTRICA QUITO S.A. E.E.Q." --first-page 1
   --last-page 3`) y di qué hace cada opción. Por qué: sabrás qué páginas se
   pedirán. Pregunta: ¿cuántas observaciones esperas si SERCOP responde bien?
4. **Ejecutar (tú, tras el merge).** Corre el comando desde la raíz del
   repositorio. Registra solo el código de salida y la línea de stdout. Por qué: es
   lo único que el comando afirma por sí mismo. Pregunta: ¿qué significa que salga
   `running` en lugar de `succeeded`?
5. **Leer la ejecución en SQL.** Consulta `ingestion_run` por el identificador que
   imprimió. Por qué: comprobar que el estado guardado coincide con el impreso.
   Pregunta: ¿qué debe cumplirse entre `status` y `finished_at`?
6. **Leer los eventos.** Consulta `audit_event` de esa ejecución en orden. Por qué:
   es la historia de lo que pasó. Pregunta: ¿qué eventos esperas por cada página?
7. **Leer las observaciones.** Consulta `observation` de esa ejecución: secuencia,
   URL, código HTTP, huella. Por qué: es el registro de cada respuesta. Pregunta:
   ¿qué secuencias y códigos esperas?
8. **Unir con la evidencia cruda.** Une `observation` con `raw_evidence` por
   `content_hash` y compara tamaños. Por qué: cada observación debe apuntar a un
   contenido guardado. Pregunta: ¿qué significaría una observación sin su fila en
   `raw_evidence`?
9. **Comprobar contra el disco.** Verifica que existe el archivo de cada huella en
   `data/raw/` y que su SHA-256 coincide. Por qué: la copia cruda es la prueba que
   respalda la base. Pregunta: ¿qué haría falta para que una huella coincidiera sin
   que el contenido fuera el mismo?
10. **Comparar con las observaciones previas.** Contrasta lo recibido (solo
    conteos y códigos, nada de contenido) con `docs/sources/sercop-observations.md`
    (reserva U1). Por qué: es la primera vez que se compara con la fuente real.
    Pregunta: ¿qué diferencia te haría detenerte y abrir un hallazgo?

Reglas del hito: `data/raw/` no va a git; ningún contenido de respuestas en docs ni
en logs; se registran solo el código de salida, la línea de stdout, los conteos y
la comparación. El glosario ("ejecución de ingesta" frente a `ingestion_run`) se
decide al inicio del Día 22, no hoy. La bitácora del Día 20 la escribes tú.

Si el bloque de correcciones se alarga, la ingesta real pasa al inicio del Día 21
y el Día 22 no se mueve.

## 5. Prompt para pegar en el chat nuevo

Hoy sigo el Día 20 en un chat nuevo del mismo proyecto. Lee `AGENTS.md`,
`docs/learning/day-20-handoff.md` (estado, criterio de cierre y plan de mi hito) y
`docs/learning/day-20-prompt.md` (reglas de siempre); luego
`specs/ingest-command/tasks.md` § Working state y § Checkpoint, y el informe de la
ronda 6 en `specs/ingest-command/audit.md`. No aprobar nada por mí: intent 14, plan
12 y tasks 9 siguen pendientes de mi aprobación. Primero dame un resumen corto del
estado (cinco líneas), repite el criterio de cierre de F4 y pregunta si lo apruebo;
después espera mis instrucciones. No ejecutes la ingesta real, no hagas merge, no
selles `Shipped:`, no archives specs. Para mi hito (tres páginas reales y SQL),
guíame con una tarea pequeña por vez, con qué compruebo, por qué y una pregunta de
comprobación; no me pidas decidir detalles internos de Python sin darme una
recomendación y el efecto que tiene.
