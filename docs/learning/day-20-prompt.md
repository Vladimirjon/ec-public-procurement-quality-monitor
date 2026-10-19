# Prompt para el Día 20

Hoy es el Día 20 del plan (F4 `ingest-command`: cierre del endurecimiento,
auditoría y primera ejecución real acotada). Lee `docs/learning/plan.md`
(Día 20 y Día 21), la última entrada de `docs/learning/journal.md` (Día 19),
`specs/current/_index.md` y `specs/ingest-command/{intent.md, execution-plan.md,
tasks.md, audit.md}`, sobre todo `tasks.md` § Working state ("Plan for Day 20")
y la ronda 4 de `audit.md`. No reabras decisiones ya tomadas ni cambies las
specs sin pasar por el architect: si ves una contradicción, devuélvela como
hallazgo para mí.

## Estado de partida

- El PR #25 ya está integrado en `main` (`eca3cc4`, 2026-10-19), por mi petición.
  La puerta 3 NO está cerrada: la auditoría de las rondas 1 a 4 rechazó; la
  ronda 4 dejó abiertos F-21 (MEDIUM), F-22, F-20 (línea 1530) y F-12.
- Los cambios pendientes están en la rama `fix/ingest-audit-hardening`
  (cortada de `main`): intent Revision 11, plan Revision 9 y tasks Revision 6,
  pendientes de mi aprobación. El resto de F-01 a F-20 está resuelto.
- La feature no está entregada: sin `Shipped:`, sin archivo, sin ejecución real.

## Antes de tocar nada

1. `git fetch` y `git checkout fix/ingest-audit-hardening` (o créala desde
   `main` actualizado si no existe); borra las ramas locales ya fusionadas
   (`feat/ingest-command`).
2. Línea base en silencio y registro en tasks.md § Baseline si difiere:
   `uv sync --locked`; `pytest` con y sin `--env-file .env`; `ruff check`;
   `ruff format --check`; `mypy`; doctor. Si Docker está apagado, arráncalo y
   `docker compose up -d --wait`. No leas ni imprimas mi `.env`.

## Trabajo de hoy, en este orden (para y espera mi OK en cada parada)

- **A1 (mía):** aprobar, enmendar o rechazar intent 11, plan 9 y tasks 6.
  Registras mi aprobación en las líneas `Approval` solo cuando yo la diga.
- **A2:** (opcional, si lo pido) el architect revisa toda la zona de
  recuperación y limpieza en una sola pasada buscando huecos vecinos; luego el
  test-writer escribe las pruebas rojas con los tokens del plan Revision 9
  (`reconnect_close_interrupt`, `reconnect_loss_line_interrupt`,
  `reconnect_false_close_interrupt`, `exit_code_reconnect_close_interrupt`,
  `final_close_error`, `final_close_interrupt`, `exit_code_final_close_*`,
  `generic_fallback`). Registras la evidencia roja. No hagas push de commits
  rojos a un PR con Auto-fix activo.
- **A3:** yo digo quién corrige `run_ingest` (lo registras en O10). El arreglo
  sigue el registro explícito del repositorio actual. Corrige también el
  to-do del README y el texto desactualizado de F-12.
- **A4:** checks en silencio, commit, push, PR con Auto-fix activo y sin
  auto-merge, `tests` y `feedback` verdes.
- **A5:** auditoría ronda 5. Pide al auditor UNA pasada exhaustiva: todo lo que
  sospeche, no solo lo último arreglado. Parada: puerta 3 (mía). Si solo quedan
  hallazgos LOW, el veredicto puede ser APROBADO CON RESERVAS.
- **B (tras puerta 3):** O11 (`harny-document` y `harny-sync`: sellar
  `Shipped:`, archivar `specs/ingest-command/`, capacidades). El merge del PR de
  endurecimiento solo con mi OK explícito. La bitácora del Día 20 la escribo yo.
- **C (yo, tras el merge):** primera ingesta real acotada desde la raíz del
  repositorio, con Compose arriba y `.env` en su sitio:
  `uv run --env-file .env ec-procurement-quality ingest --year 2025 --buyer "EMPRESA ELÉCTRICA QUITO S.A. E.E.Q." --first-page 1 --last-page 3`.
  Registra solo el código de salida, la línea de stdout, los conteos y la
  comparación con `docs/sources/sercop-observations.md` (reserva U1).
  `data/raw/` no va a git; ningún contenido de respuestas en docs ni logs.

Si el tiempo no alcanza, para en la última parada cerrada y deja el siguiente
paso escrito en tasks.md § Working state. Si el bloque A se alarga, C pasa al
inicio del Día 21 y el Día 22 no se mueve. El glosario ("ejecución de ingesta"
frente a `ingestion_run`) se decide al inicio del Día 22, con las specs de F5;
no lo toques hoy.

## Reglas de siempre

Guía breve, una frase por hallazgo, sin ejercicios; sin atribución a Claude en
ningún lado (commits, PR, bitácora, docs); no apruebes nada en mi nombre ni
marques casillas de tasks.md sin evidencia; ninguna credencial real en
archivos, logs ni docs; checks en silencio; el executor nunca edita pruebas;
sin dependencias nuevas ni red real en pruebas; ruff también formatea los
bloques de Python de los .md (`uv run ruff format --check .` tras escribir
specs o docs). Auto-fix se activa al abrir el PR, sin auto-merge; el merge solo
con mi OK explícito. Al cerrar: bitácora del Día 20 con mis palabras, checks en
silencio, commit y push, y avísame con "listo".
