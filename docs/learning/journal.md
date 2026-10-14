# Bitácora de aprendizaje

Una entrada por sesión, la más reciente al final. Escríbela tú: es tu
registro de aprendizaje y la memoria que retomamos en cada sesión nueva.
Ver [plan.md](plan.md).

## Plantilla

```markdown
## Día N: <título> (AAAA-MM-DD)

- **Objetivo:**
- **Qué hice:**
- **Qué aprendí (con mis palabras):**
- **Decisiones tomadas (ID del plan y resumen):**
- **Verificación (comando y resultado):**
- **Dudas abiertas:**
- **Respuestas de autoevaluación:**
- **Siguiente paso:**
```

---

## Día 0: Preparación del plan (2026-10-01)

- **Objetivo:** dejar listo el plan del mes.
- **Qué se hizo:** se creó `docs/learning/plan.md` (30 sesiones, 8 features,
  13 decisiones pendientes y evolución del CI/CD) y esta bitácora.
- **Estado inicial del harness** (`node .sdd/doctor/run-doctor.mjs`):
  28 OK, 2 omitidos y 2 avisos.
  - Aviso `security:git-hooks-active`: falta
    `git config core.hooksPath .sdd/git-hooks`. Se corrige el Día 1.
  - Aviso `security:gitleaks`: gitleaks no está instalado en local. Se
    corrige el Día 1; el CI ya lo ejecuta.
  - Omitido `knowledge-base`: `specs/current/` todavía no existe. Aparece
    después de la primera feature archivada.
- **Estado del CI:** `harny-feedback.yml` solo ejecuta el escaneo de
  secretos. El stack de harny está vacío, así que no corren lint ni tipos.
  Se activa el Día 4.
- **Roles harny activos:** solo `sdd-architect`. Los otros cuatro se
  habilitan el Día 4 (decisión D-06).
- **Flujo con GitHub (decidido el Día 0):**
  - Los commits se firman como autor `Vladimirjon <vladimirpasquel11@gmail.com>`,
    sin líneas de coautoría.
  - Todo cambio llega a `main` por pull request, con el CI en verde antes
    del merge. El gráfico de contribuciones de GitHub solo cuenta los commits
    que llegan a la rama por defecto con un correo vinculado a la cuenta.
  - El primer commit del plan quedó con otro autor. No se reescribió
    porque `.claude/settings.json` prohíbe `git push --force`, y eso es
    correcto: el historial publicado no se reescribe.
- **Siguiente paso:** Día 1, orientación.

## Día 1: Orientación (2026-10-01)

- **Objetivo:** entender la arquitectura del proyecto y el método SDD, y dejar
  el doctor de harny sin avisos.
- **Qué hice:** leí `AGENTS.md`, `README.md`, `docs/architecture.md`, los tres
  ADR, `docs/ai-assisted-development.md` y los skills `sdd-conductor` y
  `harny-propose`. Instalé gitleaks con winget. Investigué
  `git update-index --chmod=+x` y los permisos de los hooks.
- **Qué aprendí (con mis palabras):**
  - **Hexagonal:** el hexágono es solo un dibujo, el número de lados no
    importa. Lo importante es que el dominio va en el centro y las
    dependencias apuntan hacia adentro. Las capas externas (infraestructura e
    interfaz) rodean al núcleo.
  - **Dominio:** es código Python normal con las reglas de negocio. No lee
    archivos, no llama a internet y no toca la base de datos.
  - **Puerto:** no es un puerto de red (80, 443). Es una interfaz definida en
    `application`, como un enchufe. El **adaptador** de `infrastructure` es
    quien lo implementa (PostgreSQL, disco, SERCOP).
  - **Interfaces:** aquí es el CLI, la puerta de entrada, no una pantalla.
  - **Por qué `domain` no importa `psycopg`:** si lo hiciera, quedaríamos
    atados a una sola base de datos. Con puertos y adaptadores podemos cambiar
    PostgreSQL por otra cosa sin tocar el negocio.
  - **Evidencia cruda:** es la respuesta original de SERCOP. No tiene sentido
    modificarla, porque todo el trabajo se basa en ella.
  - **chmod +x:** `git update-index --chmod=+x` no cambia el archivo, cambia el
    metadato que git guarda (de `100644` a `100755`, el bit de ejecución).
    Windows no tiene bit de ejecución, así que git ejecuta el hook igual. En
    Linux y macOS, un hook sin ese bit se ignora en silencio.
  - **Monolito modular:** de momento no trabajamos con sistemas distribuidos.
  - **`.sdd`:** son las siglas de Specification-Driven Development. Es la
    carpeta del harness, y el punto inicial la hace "oculta" por convención.
- **Decisiones tomadas (ID del plan y resumen):** ninguna del registro D-01 a
  D-13 (empiezan el Día 3). Decisión local del día: **corregir** el modo de
  los hooks de `100644` a `100755` con `git update-index --chmod=+x`
  (`pre-commit` y `pre-push`). Motivo: costo mínimo, sin riesgo en Windows y
  el repositorio queda igual en Linux y macOS. El CI no invoca los hooks y una
  clonación nueva no los activa, así que el riesgo real era bajo.
- **Verificación (comando y resultado):** `node .sdd/doctor/run-doctor.mjs`:
  30 OK, 2 omitidos, 0 avisos, 0 fallos. gitleaks 8.30.1 instalado. Tras la
  instalación hubo que abrir una terminal nueva para que gitleaks entrara en
  el PATH.
- **Dudas abiertas:**
  - Me interesa probar un adaptador con otra base de datos (MongoDB o MySQL)
    para ver el efecto de los puertos. Cambiar la base del proyecto sería una
    decisión de arquitectura y requiere aprobación.
- **Respuestas de autoevaluación:**
  - *¿Por qué `domain` no puede importar `psycopg`?* Porque quedaría atado a
    PostgreSQL. Los puertos y adaptadores permiten cambiar de base sin tocar
    el negocio.
  - *¿Qué pasaría si sobrescribiera una respuesta cruda?* Perdería la
    evidencia original de SERCOP, que es la base de todo lo demás.
- **Siguiente paso:** Día 2, conocer la fuente de datos (OCDS y portal de
  SERCOP).

## Día 2: Conocer la fuente de datos (2026-10-02 al 2026-10-03)

- **Objetivo:** entender el estándar OCDS y observar cómo se comporta el portal
  de datos abiertos de SERCOP para consultar los procesos de E.E.Q.
- **Qué hice:** leí el estándar Open Contracting Data Standard. Exploré el
  portal de SERCOP con la pestaña Network de las herramientas del navegador,
  revisé los paquetes y repetí las consultas desde mi terminal. Al principio me
  daba 429 y tuve que ajustar los parámetros. Para las consultas pedí ayuda a
  ChatGPT. Escribí `docs/sources/sercop-observations.md` con lo observado. Además
  se configuró la protección de `main` y otras buenas prácticas del repositorio
  (PR #4), que el plan tenía para el Día 27.
- **Qué aprendí (con mis palabras):**
  - **OCDS:** es un modelo común de datos para publicar de forma estandarizada
    los datos y documentos de las contrataciones, ya sean bienes, obras o
    servicios.
  - **OCID:** significa Open Contracting ID y distingue mayúsculas de
    minúsculas. Lleva el prefijo `ocds-`, seis caracteres alfanuméricos que
    identifican a quien publica, y después el identificador interno del proceso.
  - **Release:** la información de un proceso de contratación en un momento
    dado. No se edita: si algo cambia, se publica otro release.
  - **Record:** el registro de un OCID. Reúne sus releases.
  - **Etapas (ciclo de vida):**
    - `planning`: qué se contrata y cómo.
    - `tender`: el procedimiento para seleccionar un proveedor.
    - `award`: qué proveedor se eligió y por qué valor.
    - `contract`: los eventos de la firma entre comprador y proveedor.
    - `implementation`: la ejecución hasta su terminación.
  - **Del portal:** el buscador de SERCOP usa `GET /PLATAFORMA/api/search_ocds`.
    Filtrando por año 2025 y por el comprador E.E.Q., sin palabra clave, dio 284
    procesos en 29 páginas. Con la palabra clave `ELECTRICA QUITO` dio solo 3. La
    palabra clave **restringe** el resultado, así que no sirve para traer todo.
  - **Campos:** algunos procesos traen `suppliers` y `budget` en `null`, así que
    hay que tratarlos como opcionales.
  - **Límite de uso:** las respuestas traen `X-RateLimit-Limit: 60` y un contador
    `X-RateLimit-Remaining`. El 429 que vi viene de `/api/record`. No sé cuánto
    dura la ventana ni a quién se le cuenta.
  - **Lo que me costó:** no tenía por dónde empezar con "explora el portal".
    Necesité que cada paso venga con una técnica sugerida y una pregunta de
    comprobación.
- **Decisiones tomadas (ID del plan y resumen):** ninguna del registro D-01 a
  D-13. Decisión local: configurar desde ya la protección de `main` (PR y check
  `feedback` obligatorios, borrado automático de ramas, Dependabot), en lugar de
  esperar al Día 27. Queda registrada en `docs/repository-settings.md`.
- **Verificación (comando y resultado):** `node .sdd/doctor/run-doctor.mjs`:
  30 OK, 2 omitidos, 0 avisos, 0 fallos.
- **Dudas abiertas:** quedaron anotadas en el documento de observaciones, y las
  retomo el Día 12 cuando haga falta para el adaptador:
  - Qué significa `local=1`.
  - La ventana exacta del límite de uso y a quién se le cuenta.
  - Si el 429 trae `Retry-After` y en qué formato viene su cuerpo.
  - Qué pasa al pedir una página fuera de rango.
  - Si se puede filtrar directamente por el RUC de E.E.Q. o por `buyerId`.
- **Respuestas de autoevaluación:**
  - *¿Qué es un contrato observado frente a uno inventado y por qué `AGENTS.md`
    lo prohíbe?* Trabajamos con datos reales, y no tendría sentido inventar
    contratos cuando ya consulto la propia aplicación web. Lo que me faltaba:
    el riesgo es asumir cómo se comporta la fuente sin haberlo visto (por
    ejemplo, el significado de `local=1`), porque el código falla en silencio.
    Observado es lo que vi, con fecha y evidencia.
  - *¿Por qué un release inmutable encaja con el ADR 0002?* Porque el ADR dice
    que no se debe modificar la información cruda y un release es una foto que
    SERCOP no edita. Lo que me faltaba: el release viene tal cual lo publica la
    fuente, y normalizarlo es un trabajo posterior sobre una copia (F5).
- **Siguiente paso:** Día 3, decisiones de toolchain (D-01 a D-05) y ADR 0004.

## Día 3: Decisiones de toolchain (2026-10-03 al 2026-10-04)

- **Objetivo:** decidir las herramientas de Python (D-01 a D-05) y escribir el
  ADR 0004 frase por frase.
- **Qué hice:** aprendí qué es un ADR (Architecture Decision Record) y revisé el
  ADR 0003 como ejemplo. Comprobé que mi `.venv` usa Python 3.13.9 y solo tiene
  `pip`. Decidí D-01 a D-05 y escribí `docs/adr/0004-python-toolchain.md` frase
  por frase, con contexto, decisión, alternativas y consecuencias. Instalé `uv`
  con winget (versión 0.12.23).
- **Qué aprendí (con mis palabras):**
  - **ADR:** es la trazabilidad que dejamos para el futuro y para nosotros
    mismos sobre el repositorio: cuáles eran las prioridades en ese momento y
    cómo se construyó el proyecto.
  - **Contexto frente a decisión:** yo describí como contexto algo que era una
    decisión (usar adaptadores). El contexto es la situación y el problema; la
    decisión es lo que elegimos hacer.
  - **venv:** restringe el área donde trabajamos, no complicamos al resto de
    proyectos ni lo hacemos más pesado con tantas dependencias. En la carrera
    instalaba todo a nivel global.
  - **Poetry frente a `uv`:** elegiría Poetry para publicar una librería. Como
    aquí no se busca publicar, elegí `uv` con `uv.lock`, que mantiene una
    versión de cada paquete.
  - **Cadena de herramientas:** `ruff` revisa y formatea el estilo, `mypy`
    comprueba que los tipos sean los correctos, `pytest` ejecuta las pruebas, y
    `uv` hace que, si alguien clona el repositorio en otra máquina, también le
    funcione con las mismas dependencias.
- **Decisiones tomadas (ID del plan y resumen):**
  - **D-01:** Python `>=3.13`, CI con 3.13. Pierdo que versiones inferiores no
    puedan usar el proyecto, y no me importa porque no es una librería.
  - **D-02:** `uv` con `uv.lock`. Descarté Poetry porque no busco publicar
    paquetes.
  - **D-03:** `ruff`. Pierdo familiaridad con `flake8` y `black`.
  - **D-04:** `mypy`, estricto en `domain`. Se podría endurecer capa por capa
    en el futuro.
  - **D-05:** `pytest`. Pierdo no tener cero dependencias.
- **Verificación (comando y resultado):** `node .sdd/doctor/run-doctor.mjs`:
  30 OK, 2 omitidos, 0 avisos, 0 fallos. `git diff --check` sin problemas.
- **Dudas abiertas:** ninguna que haya expresado hoy.
- **Respuestas de autoevaluación:**
  - *¿Qué cambia con el ADR y por qué?* Nos casamos con decisiones importantes
    de cómo desarrollamos: en lugar de `pip` y de instalar en global, usamos un
    venv gestionado por `uv` y el archivo `uv.lock`.
  - *¿Cómo puede fallar?* Si alguien no sigue las indicaciones de las
    dependencias y `uv.lock` queda desactualizado, el proyecto puede fallar en
    otra máquina.
  - *¿Qué demostraría que funciona?* Que alguien clone el repositorio en otra
    máquina y le funcione con las dependencias que fijamos.
  - *¿Qué alternativa descartaste y qué perdiste?* Poetry (no busco publicar),
    `flake8` y `black` (pierdo familiaridad), `unittest` (pierdo cero
    dependencias) y `mypy` estricto en todo (más fricción con librerías, y se
    puede endurecer después).
- **Siguiente paso:** Día 4, configurar harny por completo y el primer CI real.

## Día 4: Configurar harny por completo y el primer CI real (2026-10-05)

- **Objetivo:** reinstalar harny con los 5 roles y el stack `python`, y dejar el
  CI listo para revisar Python con `ruff` y `mypy`.
- **Qué hice:** clono el código fuente de harny en una carpeta fuera del
  proyecto (`harny-source`) y veo qué cambió desde mi instalación del 26 de
  septiembre: un solo commit, que cambia el formato de las specs. Instalo sus
  dependencias con `npm ci --ignore-scripts`, compilo y leo la ayuda de `init`.
  Hago un ensayo con `--dry-run` y después ejecuto `init` en la rama
  `chore/day-4-harny-full-install`. Abro el PR #9 y el check `feedback` pasa en
  verde.
- **Qué aprendí (con mis palabras):**
  - **Por qué clonar:** harny no está en npm, así que el programa que genera los
    archivos solo existe en su código fuente. Mi repo solo tiene los archivos ya
    generados.
  - **De dónde sale lo instalado:** `init` copia la carpeta `templates` del
    clon hacia mi proyecto.
  - **Roles:** son los cinco agentes del pipeline (architect, test-writer,
    executor, auditor y documentation). El doctor no es un rol.
  - **Stack:** `python` es el perfil que ya trae harny, con `ruff` y `mypy`.
  - **Formato nuevo de las specs:** `contract.md` y `roadmap.md` se fusionaron
    en `execution-plan.md`. Ahora son `intent`, `execution-plan` y `tasks`, y el
    auditor agrega `audit.md`.
  - **Lo que me costó:** sentí que armar el comando de `init` y revisar el diff
    eran demasiadas vueltas para algo que no tiene que ver con el proyecto.
    Esperaba que harny fuera fácil.
- **Decisiones tomadas (ID del plan y resumen):**
  - **D-06:** los 5 roles y el stack `python`.
  - Actualizar a la versión actual de harny (commit `466c636`) en lugar de
    quedarme con la instalación del 26 de septiembre.
  - Instalar las dependencias del clon con `npm ci --ignore-scripts`.
  - No incluir `.mcp.json` (Context7). Pierdo que los agentes consulten
    documentación de librerías, y lo reviso en los Días 12 y 15.
  - Volver `actions/checkout` a `v7`, porque harny lo había regresado a `v5` y
    deshacía el PR de Dependabot.
- **Verificación (comando y resultado):** `node .sdd/doctor/run-doctor.mjs`: 29
  OK, 2 omitidos, 0 avisos, 0 fallos. `git diff --check` sin problemas. El check
  `feedback` del PR #9 pasó en verde.
- **Dudas abiertas:**
  - `ruff` y `mypy` se omiten mientras no estén instalados, y todavía no hay
    `pyproject.toml`, así que el CI pasa sin revisar código. Cobra sentido en F0.
  - Un `harny update` futuro puede volver a bajar `checkout` a `v5`.
  - Cada reinstalación necesita `core.autocrlf=false` en el clon: en Windows, Git
    convirtió los archivos a CRLF y harny falló al leerlos.
- **Respuestas de autoevaluación:**
  - *¿Qué pasa cuando el agente termina un turno con un error de lint?* No la
    respondí hoy. La retomo en el Día 5.
- **Siguiente paso:** Día 5, F0 `project-skeleton`, specs, con el formato nuevo
  de tres archivos.

## Día 5: F0 `project-skeleton`, specs (2026-10-05 al 2026-10-07)

- **Objetivo:** tener aprobadas las tres specs de F0 (`intent`, `execution-plan` y
  `tasks`) para empezar a construir el Día 6.
- **Qué hice:** no tenía criterios propios para F0 y se lo dije, así que cambiamos
  el orden: el architect redactó primero y yo juzgué lo que escribió. Revisé
  `intent.md` (13 criterios) y aprobé la revisión 2 después de contestar las 6
  preguntas abiertas. Luego aprobé `execution-plan.md` y `tasks.md`. Todavía no hay
  commit ni PR; falta cerrar la bitácora.
- **Qué aprendí (con mis palabras):**
  - **Para qué sirve cada archivo:** `intent` dice qué debe ser verdad al final,
    `execution-plan` dice cómo y con qué restricciones, `tasks` dice en qué orden, y
    `audit` lo escribe solo el auditor.
  - **Un buen criterio** tiene un comando y un resultado que se puede ver. Con el
    ejemplo de `--verbose` lo expliqué así: con la bandera obtengo los detalles de la
    ejecución, sin ella solo lo mínimo, y un riesgo es que la bandera cambie la salida
    o cargue el procesamiento.
  - **Sobre `uv`:** pensé que se encargaba de todo. Me corrigieron: `uv` instala y
    fija versiones, pero no crea las capas, ni el comando `--version`, ni hace que
    el check de GitHub revise el código.
  - **Lo que me costó:** quedarme sin saber qué escribir cuando me pidieron criterios
    desde cero. Me pesó el método, y dije que esto era para dejar un proceso
    auditable y que no esperaba tantas preguntas ni archivos técnicos largos.
    Acordamos preguntarme solo lo estrictamente necesario.
- **Decisiones tomadas (ID del plan y resumen):**
  - **Nombre de la feature:** `project-skeleton`.
  - **Programa de empaquetado:** `uv_build`, que es de `uv`.
  - **Instalar `uv` en CI:** la acción oficial `astral-sh/setup-uv`, con versión fija.
    La elegí porque Dependabot vigila su versión.
  - **Comando y versión:** `ec-procurement-quality` y `0.1.0`.
  - **Comando sin argumentos:** queda para el primer comando real.
  - **Pasos de CI:** llevan un comentario y una nota en
    `docs/repository-settings.md` para restaurarlos si harny los borra.
  - **Hooks locales:** solo corren `ruff` y `mypy` con `.venv` en `PATH`; queda
    documentado como limitación y no se arregla en F0.
  - **`uv` en CI:** sin fijar su versión; `--locked` hace que falle con ruido si hay
    desacuerdo con `uv.lock`.
  - **Orden de F0:** el executor prepara el toolchain (O1) antes de las pruebas en
    rojo, porque sin `pyproject.toml` `pytest` ni corre.
- **Verificación (comando y resultado):** `node .sdd/doctor/run-doctor.mjs`: 29 OK,
  2 omitidos, 0 avisos, 0 fallos. `git diff --check` sin problemas. `git status`
  muestra solo `specs/` sin seguimiento.
- **Dudas abiertas:**
  - El texto exacto de los errores de `uv` en AC2 y AC3 y el SHA de `setup-uv`
    se confirman al implementar.
  - Una actualización de harny puede borrar los pasos de CI que agregaremos; el AC10
    es la alarma.
  - `src/ec_procurement_quality/` no puede tener 3 o más archivos propios o el
    doctor avisa.
- **Respuestas de autoevaluación:** no respondí hoy qué pasa cuando el agente termina
  un turno con un error de lint (viene del Día 4). Queda pendiente.
- **Siguiente paso:** Día 6, F0 en rojo y verde. Aprobar las pruebas en rojo, aprobar
  el veredicto del auditor y escribir a mano `.github/workflows/tests.yml`. Antes,
  hacer el commit y el PR de las specs de hoy.

## Día 6: F0, rojo, verde, auditoría y CI de pruebas (2026-10-07 al 2026-10-09)

- **Objetivo:** ejecutar el pipeline de F0 con `sdd-conductor` y dejar el CI de
  pruebas en verde.
- **Qué hice:** el executor preparó el toolchain (O1) en la rama
  `feat/project-skeleton`. El test-writer escribió las pruebas en rojo y yo las
  aprobé en la puerta 2. El executor las puso en verde (O2 a O6), hice los
  commits y abrí el PR #11. Escribí a mano `.github/workflows/tests.yml`. El
  auditor rechazó la primera ronda y, tras revisar la spec, aprobó con
  reservas en la segunda. La documentación archivó F0. Todo está subido al PR,
  que sigue abierto y con los 2 checks en verde.
- **Qué aprendí (con mis palabras):**
  - **Carpetas vacías de `src/`:** pregunté de dónde salían. Las había creado
    yo a mano en agosto, antes de harny. Decidí borrarlas porque "no tienen
    ninguna correlación" con la arquitectura actual.
  - **Imports relativos en `domain`:** entendía que a nivel 1 podía importar
    libremente y que de ahí en adelante no. Me corrigieron: los puntos no son
    niveles de permiso, solo la ruta hacia otro archivo. La regla es que lo que
    importe tiene que estar dentro de `domain` o ser de la biblioteca estándar.
  - **Lo que no expliqué con mis palabras hoy:** TDD (por qué la prueba falla
    primero) y la pregunta de `from ... import x` en `domain/models/user.py`.
  - **Lo que me costó:** el ejemplo de los puntos en los imports relativos. Hizo
    falta un segundo ejemplo con carpetas y archivos para que quedara claro.
- **Decisiones tomadas (ID del plan y resumen):**
  - **Puerta 2:** aprobé las pruebas en rojo, después de borrar las carpetas
    vacías para que fallaran por `ModuleNotFoundError`.
  - **Cobertura en CI:** agregar `pytest-cov`, con el fin de mejorar el
    funcionamiento futuro del CI. Mi criterio: con mis decisiones busco que no
    dejemos deuda técnica.
  - **Auto-fix del PR #11:** activado.
  - **Puerta 3, ronda 1:** el auditor rechazó porque `tests.yml` y `pytest-cov`
    estaban fuera del alcance escrito. Elegí la opción A: revisar la spec.
  - **Spec revisada:** aprobé la intent revisión 3 (AC14 a AC16) y el plan
    revisión 2.
  - **Puerta 3, ronda 2:** acepté el veredicto "aprobado con reservas".
- **Verificación (comando y resultado):**
  - `uv run pytest`: 7 pasan, cobertura 100 % de 10 líneas.
  - `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy .`: sin
    errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos (sin
    `uv run` salen 30 ok y 1 omitido, `pytest`).
  - `git diff --check` limpio.
  - PR #11: `feedback` y `Tests` en verde, mergeable.
- **Dudas abiertas:**
  - `tests` pasó a ser check obligatorio de `main` el 2026-10-09. Pedí que lo
    hicieran por mí, pero cambiar una regla de seguridad del repositorio lo hago
    yo: ejecuté el comando de `gh api` que me dieron. `docs/repository-settings.md`,
    el README y el CHANGELOG quedaron actualizados.
  - Reservas aceptadas del auditor (F3, F4 y F7): no se probó en GitHub que un
    import sin usar o un test roto pongan el check en rojo, y los hooks locales
    saltan `ruff` y `mypy` si `.venv` no está en el `PATH`.
  - Ver si el `_index.md` de `specs/current/` quedó con buena forma.
  - Un `harny init` o `update` puede borrar los tres pasos manuales de
    `harny-feedback.yml`.
- **Respuestas de autoevaluación:**
  - *¿Qué pasa cuando el agente termina un turno con un error de lint?* (viene
    del Día 4) Cuando el agente termina un turno con un error de lint, el hook lo
    detecta y le comunica el problema. En GitHub Actions, ese error sí hace
    fallar el check `feedback`. Aclaración: el hook solo corre `ruff` y `mypy` si
    `.venv` está en el `PATH`, y el agente tiene que corregir el error antes de
    poder terminar el turno.
- **Siguiente paso:** Día 7, repaso de la semana 1: explicar la arquitectura y el
  pipeline sin mirar, quiz de 10 preguntas y escribir la retrospectiva. El PR #11
  se mergea al cerrar el Día 6.

## Día 7: Repaso de la semana 1 (2026-10-09)

- **Objetivo:** explicar sin mirar la arquitectura y el pipeline harny, responder
  el quiz de 10 preguntas y cerrar la semana 1 con una retrospectiva.
- **Qué hice:** expliqué la arquitectura y los pasos del pipeline con mis
  palabras, respondí las 10 preguntas del quiz (incluidas las dos pendientes del
  Día 6) y revisé el estado del repositorio. El PR #11 de F0 ya estaba mergeado
  en `main` (commit `c9159c9`).
- **Qué aprendí (con mis palabras):**
  - **Arquitectura:** `domain` guarda las reglas del negocio, como recetas que
    no dependen de un proveedor; `application` coordina los casos de uso y pide
    servicios mediante puertos; `infrastructure` conecta esos puertos con
    SERCOP, PostgreSQL o el disco; `interfaces` traduce lo que pide el usuario
    por el CLI. Así, cambiar cómo se consulta o guarda información no obliga a
    cambiar las reglas del dominio. Hoy solo hay un esqueleto y el CLI ofrece
    `--version`.
  - **Pipeline:** specs (`sdd-architect`, puerta 1) → pruebas en rojo
    (`sdd-test-writer`, puerta 2: que fallen por la razón correcta) →
    implementación en verde (`sdd-executor`, sin tocar las pruebas) → auditoría
    (`sdd-auditor`, puerta 3: aceptar o rechazar el veredicto) → documentación
    (`sdd-documentation`, automática). `sdd-conductor` coordina el orden y las
    pausas, pero no reemplaza mi criterio en las puertas.
  - **Hooks y CI:** los hooks locales dan retroalimentación rápida (`ruff` y
    `mypy` si `.venv` está en el `PATH`); GitHub Actions repite `ruff` y `mypy`
    en `feedback`, escanea secretos y corre las pruebas con cobertura en
    `Tests`. Los hooks ayudan durante el trabajo y el CI verifica el PR.
  - **TDD (pendiente del Día 6):** una prueba debe fallar primero por la
    funcionalidad que falta, para demostrar que de verdad detecta el
    comportamiento esperado; si falla por un error de la prueba, su resultado no
    valida nada.
  - **Imports relativos (pendiente del Día 6):** `from ...application import
    UseCase` desde `domain/models/user.py` es válido como sintaxis, porque sube
    hasta `ec_procurement_quality`, pero no está permitido como regla de
    arquitectura: importa una capa externa. Los puntos marcan una ruta, no
    permisos.
- **Retrospectiva de la semana 1:**
  - **Lo que salió bien:** F0 quedó mergeado con `feedback` y `Tests` en verde y
    obligatorios en `main`; el Día 2 dejó observaciones reales de SERCOP con
    fecha; el ADR 0004 dejó el toolchain decidido; y las dos pendientes del Día 6
    quedaron resueltas.
  - **Lo que me costó:** no saber por dónde empezar cuando el paso es abierto
    (Día 2: "explora el portal"; Día 5: criterios desde cero), el exceso de
    vueltas del `init` de harny (Día 4) y el ejemplo de los puntos en los
    imports relativos (Día 6).
  - **Lo que funcionó mejor:** que cada paso traiga una técnica sugerida y una
    pregunta de comprobación, que me pregunten solo lo estrictamente necesario y
    que me den un ejemplo resuelto antes de pedirme algo.
  - **Lo que haría distinto:** pedir ese ejemplo resuelto desde el inicio de cada
    día y cerrar las preguntas de autoevaluación el mismo día, para no
    arrastrarlas.
- **Decisiones tomadas (ID del plan y resumen):** ninguna del registro D-01 a
  D-13 hoy.
- **Verificación (comando y resultado):**
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`: 7
    pasan, cobertura 100 % de 10 líneas.
  - `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy .`: sin
    errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio.
- **Dudas abiertas (heredadas del Día 6):**
  - No se probó en GitHub que un import sin usar o un test roto pongan el check
    en rojo (reserva del auditor, F3, F4 y F7).
  - Los hooks locales saltan `ruff` y `mypy` si `.venv` no está en el `PATH`.
  - Un `harny init` o `update` puede borrar los tres pasos manuales de
    `harny-feedback.yml`.
  - Ver si el `_index.md` de `specs/current/` quedó con buena forma.
- **Respuestas de autoevaluación:**
  - *¿Por qué `domain` no puede importar `psycopg`?* Porque eso lo acoplaría a
    PostgreSQL; las reglas del negocio deben poder funcionar aunque cambie la
    base de datos.
  - *¿Qué pasaría si sobrescribiera una respuesta cruda?* Perdería la evidencia
    exacta que permite reproducir o investigar el procesamiento (ADR 0002).
  - *Tres preguntas de cada puerta:* ¿qué cambia y por qué?, ¿cómo puede
    fallar?, ¿qué prueba demuestra que funciona?
  - *¿Por qué `main` exige `feedback` y `tests`?* `feedback` exige lint, tipos y
    escaneo de secretos; `tests` exige que pasen las pruebas. Al ser checks
    requeridos y estrictos, `main` no acepta el PR si alguno falla o si la rama
    no está actualizada con `main`.
  - *¿Qué significa que `Tests` reporte cobertura sin mínimo?* El CI muestra la
    cobertura, pero no falla por estar debajo de un porcentaje. Las pruebas que
    fallen sí hacen fallar el check.
- **Siguiente paso:** Día 8, modelo de dominio: escribir a mano `docs/glossary.md`
  (proceso de contratación, evidencia cruda, ejecución de ingesta, regla de
  calidad y hallazgo de calidad).

## Día 8: Modelo de dominio (2026-10-09)

- **Objetivo:** definir el lenguaje ubicuo del proyecto en `docs/glossary.md`
  (proceso de contratación, evidencia cruda, ejecución de ingesta, regla de
  calidad y hallazgo de calidad) y responder si un hallazgo de calidad es una
  entidad o un objeto de valor.
- **Qué hice:** vi el ejemplo completo de un término (proceso de contratación)
  y decidí cambiar la forma de trabajo: en lugar de escribir yo los cuatro
  restantes a mano, pedí que las definiciones se redactaran con los principios
  de *Fundamentals of Data Engineering* (Reis y Housley) y que yo las aprobara
  una por una. Revisé y aprobé evidencia cruda, ejecución de ingesta, regla de
  calidad y hallazgo de calidad, cada uno con definición, invariantes y ejemplo
  sintético, y aprobé el borrador de la autoevaluación.
- **Qué aprendí (con mis palabras):**
  - Mi criterio de hoy: con el glosario definido, "todo debe estar claro" para
    las features que siguen, así que prioricé aprobar definiciones revisadas
    antes que redactarlas yo.
  - **Lo que no expliqué con mis palabras hoy:** la diferencia entre entidad y
    objeto de valor. La respuesta de autoevaluación fue un borrador que aprobé,
    no una que redacté yo.
- **Decisiones tomadas (ID del plan y resumen):**
  - Ninguna del registro D-01 a D-13 hoy.
  - **Forma de trabajo del glosario:** definiciones redactadas con los
    principios del libro y aprobadas por mí término por término. Esto cambia la
    marca 🧑 (escribirlo a mano) que traía el plan para hoy.
  - **Idioma del glosario:** inglés, como el resto de la documentación técnica
    del repositorio, con el término en español entre paréntesis en cada título.
  - **Dejado fuera a propósito del glosario:** si las respuestas de error (por
    ejemplo un `429`) cuentan como evidencia, cómo se guarda la obtención
    repetida de un mismo contenido, y la severidad, los umbrales y la ejecución
    de las reglas. Cada uno se decide en la feature que lo necesita.
- **Verificación (comando y resultado):**
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`: 7
    pasan, cobertura 100 % de 10 líneas.
  - `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy .`: sin
    errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio.
- **Dudas abiertas:**
  - ¿Las respuestas de error (`429`, respuestas incompletas) se preservan como
    evidencia cruda? Se decide en F1 (ADR 0002 solo las menciona como
    preocupación).
  - Cómo representa el almacén que dos ejecuciones obtuvieron el mismo contenido
    sin duplicarlo (D-07, Día 9).
  - Severidad, umbrales y ejecución de las reglas de calidad (F6).
  - Explicar con mis palabras entidad vs objeto de valor antes de escribir el
    puerto y el objeto de valor del hash (Día 10).
  - Siguen abiertas las dudas heredadas del Día 7 (checks que fallan, hooks sin
    `.venv` en el `PATH`, `harny init` o `update` y `_index.md` de
    `specs/current/`).
- **Respuestas de autoevaluación:**
  - *¿Un hallazgo de calidad es una entidad o un objeto de valor?* Es un
    **objeto de valor**. No tiene identidad propia que persista: se define por
    su regla y versión, su sujeto, su evidencia y el valor observado, y dos
    hallazgos con esos mismos valores son el mismo (por eso reevaluar no
    duplica). Es inmutable y no tiene ciclo de vida: si el dato se corrige,
    aparece otro hallazgo o ninguno, y el original no se edita. Un proceso de
    contratación sí es entidad, porque sigue siendo el mismo (`ocid`) aunque su
    monto cambie. La base de datos le pondrá una clave por fila, pero eso es un
    detalle de persistencia, no identidad del dominio. Si un hallazgo tuviera
    estado (abierto, resuelto, asignado), pasaría a ser entidad; hoy no está en
    el alcance.
- **Siguiente paso:** Día 9, F1 `raw-evidence-store`: decido D-07 y escribo el
  ADR sobre la disposición del almacén crudo, y reviso las specs de F1 en la
  puerta 1.

## Día 9: F1 `raw-evidence-store`, decisiones y specs (2026-10-09)

- **Objetivo:** decidir D-07 (disposición del almacén crudo), dejar el ADR
  correspondiente y revisar en la puerta 1 las specs de F1. Entraban dos
  preguntas del Día 8: si las respuestas de error (un `429`) se preservan como
  evidencia cruda, y cómo se representa que dos ejecuciones obtuvieron el mismo
  contenido sin duplicarlo.
- **Qué hice:** vi el concepto con un ejemplo resuelto (contenido direccionado
  por hash, escritura atómica y append-only) y decidí D-07 y las dos preguntas
  eligiendo las opciones recomendadas. Pedí un borrador del ADR en lugar de
  escribirlo desde cero, lo revisé y lo aprobé como ADR 0005. El architect
  redactó las tres specs de F1; revisé el resumen de la puerta 1 (qué cambia,
  cómo puede fallar y qué lo prueba) y aprobé `intent.md` y `execution-plan.md`
  (revisión 1). Pedí formalizar en el glosario los términos del almacén.
- **Qué aprendí (con mis palabras):**
  - Hoy no expliqué el concepto con mis palabras: decidí a partir del ejemplo
    resuelto y de la recomendación con su motivo.
  - **Mi criterio sobre el glosario:** "formalízalos, si se pueden simplificar,
    si es que ya cumplen dentro de otro término y si no, defínelos formalmente
    y que ya sean utilizables."
- **Decisiones tomadas (ID del plan y resumen):**
  - **D-07:** contenido por hash más observaciones aparte. Los bytes se
    guardan una sola vez en `objects/<sha256>`, y cada respuesta obtenida deja
    un registro JSON en `observations/<ejecución>/<secuencia>.json`. Mismo
    contenido en dos ejecuciones son dos observaciones y un solo objeto.
    Descarté una carpeta por ejecución con copia de los bytes, porque repite
    contenido idéntico y no muestra que dos ejecuciones obtuvieron lo mismo.
  - **Respuestas de error:** se preservan como evidencia cruda, con su status y
    sus cabeceras de respuesta (sin `Set-Cookie`), y nunca se normalizan. Así
    queda la evidencia que faltó el Día 2 para saber si el `429` trae
    `Retry-After`. Descarté guardar solo las respuestas 2xx.
  - **ADR 0005:** aceptado. Sin compresión ni retención en la v1 y sin
    dependencias nuevas (`hashlib` es de la biblioteca estándar).
  - **Puerta 1:** aprobada la revisión 1 de `intent.md` (13 criterios) y de
    `execution-plan.md`. El `Approval` quedó en `intent.md`.
  - **Glosario:** "observación" pasa a ser término propio. "Objeto" no se
    agrega: queda dentro de evidencia cruda, como el contenido guardado. Se
    ajustaron evidencia cruda e ejecución de ingesta para que concuerden.
  - **Forma de trabajo:** el ADR llegó como borrador para aprobar, no escrito a
    mano. Esto cambia la marca 🧑 que traía el plan para hoy, igual que el
    glosario del Día 8.
- **Verificación (comando y resultado):**
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`: 7
    pasan, cobertura 100 % de 10 líneas.
  - `uv run ruff check .`, `uv run ruff format --check .` (56 archivos) y
    `uv run mypy .`: sin errores. `ruff format` también revisa los bloques de
    código de los `.md`: un bloque de `execution-plan.md` lo hacía fallar y el
    architect lo corrigió.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio.
- **Dudas abiertas:**
  - Una "observación" también es el nombre de mis notas sobre la fuente
    (`docs/sources/sercop-observations.md`). Se dejó el nombre porque el ADR y
    las specs ya lo usan, y el glosario aclara la diferencia. Renombrarlo
    obligaría a rehacer specs ya aprobadas.
  - Al archivar F1 se retira de `project-toolchain` PT-3 la cláusula de que las
    capas "solo contienen lo necesario para ser paquetes", y crece el conteo de
    PT-6.
  - F4 deberá generar ids de ejecución que no sean nombres reservados de
    Windows (`con`, `nul`...).
  - El almacén necesita un sistema de archivos con enlaces duros (`os.link`);
    en NTFS y ext4 funciona.
  - Explicar con mis palabras entidad vs objeto de valor antes de escribir el
    objeto de valor del hash y el puerto (Día 10, heredada del Día 8).
  - Siguen abiertas las dudas heredadas del Día 7 (checks que fallan, hooks sin
    `.venv` en el `PATH`, `harny init` o `update` y `_index.md` de
    `specs/current/`).
- **Respuestas de autoevaluación:** el plan no trae preguntas para hoy.
- **Siguiente paso:** Día 10, F1 en rojo y verde: el test-writer escribe las
  pruebas en rojo (puerta 2); yo escribo el objeto de valor `ContentHash` y el
  puerto `RawEvidenceStore`; el executor implementa el resto y el adaptador de
  disco.

## Día 10: F1, rojo y verde (2026-10-09)

- **Objetivo:** pasar la puerta 2 con las pruebas en rojo de F1, escribir yo a
  mano el objeto de valor `ContentHash` y el puerto `RawEvidenceStore`, y dejar
  el resto de F1 en verde con el executor. Además, registrar mi respuesta de
  entidad frente a objeto de valor, pendiente desde el Día 8.
- **Qué hice:** el test-writer escribió 126 pruebas nuevas en tres archivos más
  una prueba de capas, y todas fallaron por `ModuleNotFoundError` de los
  nombres fijados en el plan. Revisé el resumen de la puerta 2 (qué cambia, cómo
  puede fallar y qué lo prueba) y aprobé. Después de ver un ejemplo resuelto de
  un caso parecido (un código postal y una libreta de direcciones), escribí a
  mano `domain/content_hash.py` y `application/raw_evidence_store.py`. No pedí
  pistas por niveles. Se revisaron y no tuvieron hallazgos. El executor escribió
  `Observation` y los errores (O2), el adaptador de disco (O4), la migración
  (O5), los documentos (O6) y la verificación (O7). Abrí la rama
  `feat/raw-evidence-store` y el PR.
- **Qué aprendí (con mis palabras):**
  - **Entidad frente a objeto de valor:** "Una entidad se identifica por quién
    es; un objeto de valor, por qué contiene. Dos `ContentHash` con el mismo
    valor son iguales aunque sean instancias distintas; el hexdigest es
    inmutable y si cambiara dejaría de darnos fiabilidad."
  - **Lo que me costó:** hoy no expresé dificultades.
- **Decisiones tomadas (ID del plan y resumen):**
  - Ninguna del registro D-01 a D-13 hoy.
  - **Puerta 2:** aprobé las pruebas en rojo de F1.
  - **Forma de trabajo:** ejemplo resuelto antes de escribir `ContentHash` y el
    puerto, y revisión de lo que escribí antes de seguir con el executor.
- **Verificación (comando y resultado):**
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`: 133
    pasan (7 de F0 y 126 nuevas), cobertura 93 % de 236 líneas.
  - Pruebas clave: `duplicate` (el mismo contenido dos veces deja un objeto y dos
    observaciones, sin reescribir el objeto) y `conflict` (contenido distinto
    bajo la misma identidad es `EvidenceIntegrityError` y no sobrescribe).
  - `uv run ruff check .`, `uv run ruff format --check .` (63 archivos) y
    `uv run mypy .` (15 archivos): sin errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio. `pyproject.toml` y `uv.lock` sin cambios.
    `data/raw/` sigue ignorado por git.
- **Dudas abiertas:**
  - El auditor (Día 11) debe revisar lo que el executor agregó sobre lo fijado:
    `validate_execution_id` y `validate_sequence` públicas en `domain`,
    `TypeError` para contenido que no es `bytes`, JSON solo ASCII y modo `0600`
    de los archivos en POSIX.
  - Las pruebas tratan como conflicto repetir la misma identidad con distinto
    `status`, cabeceras u hora de captura, no solo con distinto contenido. Sale
    de comparar la observación por sus bytes (plan, paso 3).
  - Texto desactualizado en specs ya aprobadas: `intent.md` y
    `execution-plan.md` dicen que el ADR 0005 está `Proposed` y que la intención
    espera aprobación; `tasks.md` § Baseline describe la situación anterior. El
    ADR está `Accepted`. Cambiar la intención exige re-aprobarla, así que lo
    decido el Día 11 con el auditor.
  - La ruta POSIX del adaptador (sincronizar el directorio) solo se probó en un
    guion desechable bajo WSL; el CI de GitHub (Ubuntu) la ejecuta por primera
    vez en este PR.
  - Al archivar F1 hay que actualizar `project-toolchain` PT-3 y PT-6.
  - F4 deberá generar ids de ejecución que no sean nombres reservados de
    Windows (`con`, `nul`...), y el almacén necesita enlaces duros (`os.link`).
  - Siguen abiertas las dudas heredadas del Día 7 (checks que fallan, hooks sin
    `.venv` en el `PATH`, `harny init` o `update` y `_index.md` de
    `specs/current/`).
  - Cerrada: entidad frente a objeto de valor (heredada del Día 8).
- **Respuestas de autoevaluación:**
  - *¿Entidad u objeto de valor?* "Una entidad se identifica por quién es; un
    objeto de valor, por qué contiene." `ContentHash` es un objeto de valor:
    dos con el mismo valor son iguales aunque sean instancias distintas, y su
    hexdigest es inmutable.
- **Siguiente paso:** Día 11, F1: auditoría (puerta 3) y documentación. Leo
  `audit.md` completo y explico cada hallazgo con mis palabras, decido qué hago
  con el texto desactualizado de las specs y hago el merge de F1.

## Día 11: F1, auditoría y documentación (2026-10-09)

- **Objetivo:** pasar la puerta 3 de F1 (auditoría), cerrar los hallazgos del
  auditor, archivar la feature con la documentación y dejar el PR #15 listo
  para el merge.
- **Qué hice:** antes de auditar pedí dejar las specs al día: la revisión 2
  corrige que el ADR 0005 ya estaba `Accepted` y registra lo que el executor
  agregó sobre lo fijado; la aprobé. El auditor aprobó con reservas en la
  ronda 1 (A1 media; A2, A3 y A4 bajas). Pedí resolver A1 a A4: el architect
  hizo la revisión 3, el test-writer escribió 4 pruebas `race` y se corrigió el
  texto. La ronda 2 cerró A1 a A4 y encontró A5 (un descuido de texto en
  `tasks.md`), que también se cerró. Aprobé la revisión 3, las pruebas nuevas y
  el veredicto. Documentación archivó F1 en `specs/archived/` y actualizó
  `specs/current/` (`project-toolchain` y la capacidad nueva `raw-evidence`).
  Todo está en el PR #15, con `feedback` y `Tests` en verde en Ubuntu.
- **Qué aprendí (con mis palabras):**
  - **Formato de los bytes del registro:** "El contrato exigible es la
    estructura y semántica del registro descritas en las specs; no se exigirán
    el orden de claves, la indentación ni el salto de línea exactos.
    `schema_version` permite distinguir formatos, pero no resuelve por sí solo
    la compatibilidad: si el formato cambia, habrá que versionarlo y actualizar
    cómo se leen las versiones anteriores."
  - **Ramas sin prueba:** "Que una rama no esté probada no es automáticamente
    un defecto; el auditor puede señalarla si ve un riesgo o un incumplimiento
    concreto." Pedí evaluar por separado `0600` y la publicación atómica: son
    aspectos de permisos e integridad, y el CI corre en Ubuntu, así que no
    aplica la limitación de Windows para cubrirlos allí.
  - **Hoy no expliqué cada hallazgo con mis palabras.** Pregunté si A1 a A4 se
    habían resuelto y me lo explicaron en simple: A1 era que ninguna prueba
    vigilaba que el almacén nunca sobrescribe (ahora hay 4 que fallan si se
    rompe), y A2, A3 y A4 eran texto de las specs.
  - **Lo que me costó:** no pude seguir la explicación de los hallazgos tal
    como venía en la puerta 3 y tuve que pedir que me dijeran si estaban
    resueltas.
- **Decisiones tomadas (ID del plan y resumen):**
  - Ninguna del registro D-01 a D-13 hoy.
  - **Revisión 2 de las specs:** aprobada. Es solo texto: ADR 0005 `Accepted` y
    lo que el executor agregó.
  - **Formato del registro:** "as built", no contrato (arriba).
  - **Comportamientos sin prueba:** no requieren prueba en esta puerta salvo
    riesgo concreto. `0600` se registra como incidental, no como garantía.
  - **A1 a A4:** resolverlos todos antes de documentar, en lugar de aceptar las
    reservas y dejarlas para F2. Motivo: que no dejemos deuda técnica.
  - **Puerta 3:** aprobé la revisión 3, las pruebas `race` y el veredicto de la
    ronda 2 (aprobado con reservas, sin hallazgos abiertos).
- **Verificación (comando y resultado):**
  - `uv run pytest --cov=ec_procurement_quality --cov-report=term-missing`: 137
    pasan (7 de F0 y 130 nuevas), cobertura 94 %.
  - Con la versión rota a propósito (`os.replace` en lugar de `os.link`), las 4
    pruebas `race` fallan. Con el código real pasan.
  - `uv run ruff check .`, `uv run ruff format --check .` (65 archivos) y
    `uv run mypy .` (15 archivos): sin errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio. `pyproject.toml` y `uv.lock` sin cambios.
  - PR #15: `feedback` y `Tests` en verde en el commit `ba761b2`, incluidas las
    pruebas `race` en Ubuntu.
- **Dudas abiertas:**
  - El auditor dejó reservas bajas que ahora viven en
    `specs/current/raw-evidence.md`: comportamientos sin prueba (por ejemplo
    las validaciones de lectura), escritores concurrentes reales (sin probar y
    fuera de alcance) y la sincronización del directorio en POSIX.
  - `audit.md` conserva A5 como "Open" en el historial de la ronda 2; está
    cerrado en `tasks.md` y en mi aceptación.
  - `specs/current/_index.md` lo regeneró la documentación con la forma de F0;
    no lo revisé línea por línea.
  - Si cambia el formato del registro de observaciones hay que versionarlo y
    seguir leyendo las versiones anteriores (F3 y F5 lo leerán).
  - F4 deberá generar ids de ejecución que no sean nombres reservados de
    Windows (`con`, `nul`...), y el almacén necesita enlaces duros (`os.link`).
  - Siguen abiertas las dudas heredadas del Día 7 (checks que fallan, hooks sin
    `.venv` en el `PATH` y `harny init` o `update`).
- **Respuestas de autoevaluación:** el plan trae para hoy leer `audit.md` y
  explicar cada hallazgo con mis palabras. Pedí que me lo explicaran, así que
  no lo respondí yo (ver "Qué aprendí").
- **Siguiente paso:** merge de F1 (PR #15) y Día 12, F2 `sercop-source-adapter`:
  decidir D-08 (cliente HTTP, recomendación `httpx`), preparar 2 o 3 fixtures
  mínimos y sanitizados a partir de mis observaciones del Día 2, y revisar las
  specs que citen solo `docs/sources/sercop-observations.md` en la puerta 1.

## Día 12: F2 `sercop-source-adapter`, specs (2026-10-10)

- **Objetivo:** decidir D-08 (cliente HTTP), revisar la decisión sobre
  `.mcp.json` (Context7), tener fixtures mínimos y sanitizados, y pasar la puerta
  1 con las specs de F2 basadas solo en `docs/sources/sercop-observations.md`.
- **Qué hice:**
  - **Cierre del Día 11:** el "Siguiente paso" de esa entrada era el merge del
    PR #15. Está hecho: `main` quedó en el commit `fff0f2d`, con `feedback` y
    `Tests` en verde, la rama borrada y F1 archivado.
  - **Fuente:** pregunté si bastaba con lo observado el Día 2 o si convenía
    volver a pedir, porque "esto no se trata de cuando yo pierda la paciencia,
    sino de cómo funciona la página y cómo es en la vida real". Aprobé 7 pedidos
    acotados. Se enviaron 6 (el #6 se reemplazó por el #5, 29 minutos después).
    Se detuvieron a mitad por la regla de parada (`Remaining` bajó de 20) y se
    retomaron después de una pausa que yo avisé que había pasado.
  - **Decisiones:** apruebo `httpx`, incluyo `record` en F2 y dejo `.mcp.json`
    fuera. Pregunté qué hacía y qué quitaba excluirlo antes de decidir.
  - **Specs:** el architect redactó `intent`, `execution-plan` y `tasks` de F2
    (14 criterios). Revisé el resumen de la puerta 1 (qué cambia, cómo puede
    fallar y qué lo prueba) y aprobé la revisión 1.
- **Qué aprendí (con mis palabras):**
  - **Criterio para observar la fuente:** lo que importa es cómo funciona la
    página en la vida real, no cuánta paciencia tenga yo ni lo que alcance a
    reconstruir de mis notas.
  - **`.mcp.json`:** "habíamos dejado eso afuera para no crear una
    dependencia".
  - **Hoy no expliqué el concepto con mis palabras** (timeouts, reintentos con
    backoff, límites de tasa y pruebas sin red): lo vi con un ejemplo resuelto.
    No respondí la pregunta opcional del final (qué pasa con un 429 que provocó
    un reintento).
  - **Lo que me costó:** pedí que me explicaran qué hacía el servidor MCP y qué
    quitaba excluirlo, y la primera explicación tenía un error que se corrigió.
- **Lo observado hoy de la fuente (con ayuda; quedó en
  `docs/sources/sercop-observations.md`, sección del 2026-10-10):**
  - La respuesta de búsqueda trae `total`, `page`, `pages` y `data` en la raíz;
    `amount` y `budget` vienen como texto y `suppliers` y `budget` pueden ser
    `null`.
  - Una página fuera de rango (`page=30` con `pages=29`) devuelve 200 con
    `data` vacío, no un error.
  - Sin `local=1` la página 1 salió byte por byte igual: no cambió nada en esa
    consulta.
  - `api/record` respondió 200 con un paquete OCDS; los montos ahí son números.
  - El contador de uso bajó cerca de 1 punto por segundo entre pedidos, no por
    cantidad de pedidos. Una primera hipótesis ("unas 13 unidades por pedido")
    resultó equivocada. Encaja con un cupo compartido con otros, pero es una
    inferencia.
  - Cada pedido tardó entre 5,9 y 12 s.
- **Decisiones tomadas (ID del plan y resumen):**
  - **D-08:** `httpx`, cliente sincrónico, importado solo en `infrastructure`,
    con `MockTransport` en las pruebas. Es la primera dependencia de ejecución;
    la agrega la primera tarea del executor (`uv add`), no el PR de hoy.
    **ADR 0006** aceptado.
  - **`.mcp.json` (Context7):** se mantiene excluido (decisión del Día 4
    confirmada).
  - **Alcance de F2:** `search_ocds` y `api/record`. Sin filtro por RUC ni
    `buyerId` y sin darle significado a `local=1`.
  - **Reintentos:** el adaptador hace un pedido por llamada y no reintenta.
    Reintentar y esperar le toca a F4, para guardar cada respuesta antes de
    cualquier espera.
  - **Comprobación de `page`:** se rechaza una respuesta cuyo `page` no coincide
    con el pedido (la respuesta igual se guarda como evidencia).
  - **Ritmo y timeouts por defecto** (decisión del proyecto, no observados,
    configurables): 5 s entre pedidos; 60 s de enfriamiento tras un 429 o con
    `Remaining` menor que 20; timeouts de 10 s y 30 s de lectura.
  - **Fixtures:** 4 archivos en `tests/fixtures/sercop/` con su procedencia;
    `search_no_results.json` está marcado como inferido.
  - **Puerta 1:** aprobada la revisión 1 de `intent.md` (14 criterios), del plan
    y de las tareas.
- **Verificación (comando y resultado):**
  - `uv run pytest`: 137 pasan (sin pruebas nuevas hoy).
  - `uv run ruff check .`, `uv run ruff format --check .` (70 archivos) y
    `uv run mypy .` (15 archivos): sin errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio. `pyproject.toml` y `uv.lock` sin cambios.
- **Dudas abiertas:**
  - Qué significa `local=1`, la ventana exacta y a quién se le cuenta el límite
    (solo se sabe que se renueva en 29 minutos o menos), el cuerpo del 429 y
    si trae `Retry-After` (no se provocó), qué devuelve `record` para un `ocid`
    inexistente, si su estructura varía entre registros y el filtro por RUC o
    `buyerId`.
  - Si `httpx` pide distinto que mi `curl` y SERCOP responde distinto: no está
    verificado; se verá en la primera ingesta real (Día 20).
  - Un 200 guardado puede tener el cuerpo truncado: F5 deberá revalidarlo.
  - F4 deberá mantener el logger `httpcore` por debajo de `DEBUG`, porque con el
    transporte real registra cabeceras.
  - Al archivar F2 se modifica `project-toolchain` PT-11 ("dependencias
    vacías") y crece el conteo de PT-6, PT-10 y PT-11.
  - `specs/current/_index.md`: se comprobó que los rangos de requisitos (CLI 3,
    PT 12, RE 12) y las fechas coinciden con los documentos de capacidad; no lo
    revisé línea por línea. Queda decidir si se cierra.
  - Siguen abiertas las dudas heredadas del Día 7 (checks que fallan, hooks sin
    `.venv` en el `PATH` y `harny init` o `update`).
- **Respuestas de autoevaluación:** el plan no trae preguntas para hoy.
- **Siguiente paso:** Día 13, F2 en rojo y verde: el executor agrega `httpx`
  (O1); el test-writer escribe las pruebas en rojo (puerta 2); el executor
  implementa; y yo reviso línea por línea cómo se manejan los errores HTTP. El PR
  de hoy sigue abierto hasta el merge de F2.

## Día 13: F2 `sercop-source-adapter`, rojo y verde (2026-10-10)

- **Objetivo:** agregar `httpx` (O1), pasar la puerta 2 con las pruebas en rojo,
  implementar el adaptador hasta verde (O3 a O5) y revisar yo línea por línea
  cómo se manejan los errores HTTP.
- **Qué hice:**
  - **Cierre del Día 12:** el PR #16 tenía `feedback` y `Tests` en verde y era
    mergeable. La sesión no lo tenía enlazado y Auto-fix aparecía apagado:
    lo enlacé y lo activé.
  - **O1:** `uv add httpx`. Revisé el diff de `pyproject.toml` y `uv.lock` y la
    versión resuelta (0.28.1) y aprobé antes de seguir.
  - **Puerta 2:** pruebas en rojo con transporte simulado y guardia de red.
    Fallaban por la razón correcta (`ModuleNotFoundError` de los módulos de F2
    y el `AssertionError` del chequeo de capas). Aprobé.
  - **O3 a O5:** `domain/source_response.py`, `application/procurement_source.py`
    e `infrastructure/sercop_source.py`, sin tocar las pruebas.
  - **Revisión de errores HTTP:** leí el adaptador completo con un mapa de las
    cinco ramas. Mis hallazgos llevaron a la revisión 2 de la spec (abajo).
  - **Revisión 2:** el architect revisó `intent`, `execution-plan` y `tasks`.
    Aprobé la revisión 2, el test-writer escribió las pruebas nuevas en rojo
    (O2b), aprobé la puerta 2 otra vez y el executor las pasó a verde (O5b).
    Volví a leer los bloques que cambiaron.
- **Qué aprendí (con mis palabras):**
  - **Por qué no se amplía el almacén:** "RFC 9110 define los códigos fuera de
    ese rango como inválidos, así que no se amplía el almacén para guardarlos."
  - **Las cinco ramas (mis respuestas de comprobación):**
    1. Si falla la conexión antes de recibir estado y cabeceras, no hay
       respuesta que guardar: sale `SourceTransportError` con `response=None` y
       F4 trata el error según su política de ejecución y reintentos.
    2. Un corte durante el cuerpo da `SourceTransportError` con la respuesta
       parcial (estado, cabeceras, bytes recibidos y hora de captura). No es
       "incompleta" porque el corte se detecta antes de evaluar si un cuerpo
       completo de estado 200 cumple el formato.
    3. Solo el 200 llega a la validación. 204 y 302 son errores de estado y no
       se siguen redirecciones. El adaptador conserva `Retry-After` pero no lo
       interpreta: un 429 activa el enfriamiento configurado.
    4. Un 200 con JSON válido pero otra página sale como
       `IncompleteResponseError` con la respuesta completa. Como llegó completa,
       F4 puede conservarla como evidencia.
    5. Un `data` vacío es éxito. Quien llama consulta `is_beyond_last_page` y
       `total`.
  - **Cómo quedó el flujo tras mi relectura:** "se valida que el adaptador siga
    abierto, se valida la entrada, se construye el request, se espera y se
    envía. El hook captura estado, cabeceras y cuerpo antes de que HTTPX procese
    Location; luego el mapeo de resultados ocurre fuera del except. El finally
    registra el fin del intento y actualiza el ritmo también cuando se propaga
    una excepción. Las seis ramas de `_outcome` corresponden al plan."
  - **Hoy no anoté qué fue lo que más me costó.**
- **Hallazgos de mi revisión del adaptador (se llevaron al architect):**
  - Un estado fuera de 100 a 599 rompía la respuesta tipada: `RawResponse` lo
    rechaza con un `ValueError` antes de que `_outcome` pueda mapearlo, y se
    pierde la respuesta. Quedó cerrado en la revisión 2.
  - `base_url` aceptaba usuario y contraseña: `httpx` los toma como Basic Auth y
    quedan en la URL y en el log. Quedó cerrado: se rechaza al construir.
  - `base_url` no validaba la autoridad ni el puerto, y el error de `httpx` se
    posponía hasta construir el request, fuera del mapeo tipado. Quedó cerrado:
    se valida al construir y da `ValueError`.
  - Al cerrar la familia, el architect encontró cuatro más: un `Location` mal
    formado en un 3xx perdía o rompía la respuesta; un comprador u `ocid` largo
    fallaba después de esperar; llamar tras `close()` esperaba antes de fallar; y
    una excepción que escapaba no contaba para el ritmo. Todos cerrados.
- **Decisiones tomadas (ID del plan y resumen):**
  - **D-08 (ejecución):** `httpx` 0.28.1, con `httpcore` 1.0.9, `h11` 0.16.0,
    `anyio` 4.15.1, `certifi` 2026.7.22 e `idna` 3.20 como transitivas.
    `pyproject.toml` solo gana `httpx>=0.28.1`.
  - **Revisión 2 de la spec:** aprobada. Un estado fuera de 100 a 599 sale como
    error de transporte sin respuesta y sin guardar sus bytes; el rango de F1 no
    se amplía.
  - **Puerta 2:** aprobada dos veces (pruebas de la revisión 1 y pruebas de la
    revisión 2).
  - **Mecanismo del `Location`:** un gancho de respuesta de `httpx` captura la
    respuesta antes de que el cliente procese `Location`.
  - **Seis ramas, no cinco:** el estado fuera de rango es una rama nueva; los
    comentarios ya revisados conservan su texto y solo cambió el número.
  - **Regla "no encadenar `InvalidURL`":** no tiene prueba; queda para la
    revisión del auditor (O9).
  - **Pendiente a propósito:** O6 a O9 (migración, documentación, suite y
    auditoría) son del Día 14, según el plan.
- **Verificación (comando y resultado):**
  - `uv run pytest`: 453 pasan (137 de antes y 316 nuevas).
  - `uv run ruff check .`, `uv run ruff format --check .` (75 archivos) y
    `uv run mypy .` (20 archivos): sin errores.
  - `uv lock --check`, `uv sync --locked` y
    `uv run ec-procurement-quality --version` (0.1.0): bien.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos. Sin
    `uv run` el doctor salta la comprobación de `pytest`.
  - `git diff --check` limpio. Ninguna prueba nombra el host real.
  - Los módulos de F1, `interfaces/cli.py` y los fixtures no cambiaron desde la
    puerta 1; `pyproject.toml` solo agrega `httpx`.
- **Dudas abiertas:**
  - Si `httpx` pide distinto que mi `curl` y SERCOP responde distinto: sigue sin
    verificarse; se verá en la primera ingesta real (Día 20).
  - Los valores de ritmo (5 s, 20, 60 s) y los timeouts son decisiones del
    proyecto, no observadas.
  - Los bytes de un estado fuera de 100 a 599 no se guardan.
  - F4 debe mantener el logger `httpcore` por debajo de `DEBUG`, y F5 debe
    revalidar un 200 guardado porque puede estar truncado o inservible.
  - El estado de la captura vive en la instancia: sirve para un cliente
    sincrónico de un solo hilo; habría que revisarlo si aparece concurrencia.
  - Al archivar F2 se modifican `project-toolchain` (PT-3, PT-11 y los conteos de
    PT-6 y PT-10) y se crea la capacidad `source-access`.
  - `specs/current/_index.md`: sigue sin revisarse línea por línea.
  - Siguen abiertas las dudas heredadas del Día 7 (checks que fallan, hooks sin
    `.venv` en el `PATH` y `harny init` o `update`).
- **Respuestas de autoevaluación:** el plan no trae preguntas para hoy; las
  cinco de comprobación por rama están arriba.
- **Siguiente paso:** Día 14, F2: el executor hace O6 a O8 (evidencia de
  migración, documentación y suite contra la línea base), el auditor escribe
  `audit.md` (O9), puerta 3, documentación y merge del PR #16. Retrospectiva de
  la semana 2.

## Día 14: F2 `sercop-source-adapter`, auditoría y repaso de la semana 2 (2026-10-11 al 2026-10-12)

- **Objetivo:** cerrar F2: pasar la puerta 2 de la revisión 5, dejar verde el
  adaptador, pasar la re-auditoría (ronda 4) y la puerta 3, documentar, archivar
  las specs y dejar listo el merge del PR #16. Además, la retrospectiva de la
  semana 2.
- **Qué hice:**
  - **PR #16:** lo enlacé a la sesión y dejé Auto-fix activo, sin auto-merge.
  - **Puerta 2 (O2e):** el test-writer agregó 71 pruebas (890 pasaron a 961
    coleccionadas); 44 fallaban por la razón correcta contra `1cd2f1e` y 27 ya
    pasaban porque fijan comportamiento existente. Aprobé.
  - **O5e y O8d:** el executor cambió solo `infrastructure/sercop_source.py`:
    nombra la clase de `httpx` más cercana (F-9), lee el estado como `int`
    exacto, conserva la primera excepción si falla el cierre del stream (D-1) y
    documenta la regla de un solo hilo (R-11). Suite: 961 pasan.
  - **Auditoría, ronda 4 (puerta 3):** APPROVED WITH RESERVATIONS, sin hallazgos
    bloqueantes. F-8, F-9, F-10 y R-11 quedaron resueltos. Aprobé la puerta 3 y
    pedí cerrar F-11, F-12 y N-17 con el architect, según mi regla de no dejar
    deuda.
  - **Cierres de texto:** salieron F-13 a F-16 y N-21 y N-22 (solo texto). Se
    cerraron con el architect y el executor (comentarios y docstring, sin tocar
    ninguna línea ejecutable), con dos relecturas acotadas del auditor y una regla
    de parada para no entrar en un ciclo sin fin.
  - **Commit y push:** `b939248`. En el PR #16, `Tests` mostró `961 passed` y
    `feedback` `2 of 2 command(s) ran`, ambos `success` sobre esa cabeza (R-12
    cerrado).
  - **Documentación y archivo:** README, CHANGELOG, la nueva capacidad
    `specs/current/source-access.md`, `project-toolchain.md` e `_index.md`; las
    specs de F2 quedaron en `specs/archived/sercop-source-adapter/` con
    `Shipped: 2026-10-12`.
- **Qué aprendí (con mis palabras):**
  - **Hoy no expliqué nada con mis palabras.** Lo que sí hice fueron preguntas
    para entender el proceso: si con la puerta 2 terminaba el día, qué estaba
    fallando cuando tardaba, qué había pasado con un comando que apareció como
    `[killed]` y para qué serviría probar la ruta N-21.
  - **Lo que me explicaron (no es mi redacción):** los 44 `failed` de la puerta 2
    son rojo a propósito; el comando `[killed]` fue un intérprete colgado del
    auditor en su carpeta temporal, sin efecto en el repositorio; la prueba de
    N-21 protegería una rama de `_send` que solo alcanza un transporte inyectado,
    así que su valor práctico es bajo.
- **Decisiones tomadas (ID del plan y resumen):**
  - **Puertas 2 y 3:** aprobadas hoy.
  - **N-21:** "dejo anotado ese caso límite, no para ahora, pero que quede
    documentado". Queda como limitación conocida de la capacidad `source-access`
    y en `CHANGELOG.md`, con el reproductor para una prueba posterior. No es
    parte del PR #16.
  - **Relectura del auditor de O7f y O5g:** aprobada, una sola vez, con regla de
    parada.
  - **Nada nuevo del registro D-01 a D-13.**
- **Verificación (comando y resultado):**
  - `uv run pytest`: 961 pasan (137 de F1 y base, y 824 del adaptador).
  - `uv run ruff check .`, `uv run ruff format --check .` (76 archivos) y
    `uv run mypy .` (20 archivos): sin errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos;
    `--only spec-state`: sin fallos.
  - `git diff --check` limpio. Las pruebas ganaron 646 líneas y no perdieron
    ninguna desde `1cd2f1e`.
- **Dudas abiertas:**
  - N-21 (sin prueba), R-6 y R-7 (aceptados) y R-11 (regla documentada, sin
    mecanismo).
  - Si SERCOP responde a `httpx` como a mi `curl`: sigue sin verificarse hasta
    la primera ingesta real.
  - Revisar línea por línea `specs/current/_index.md` y confirmar las
    severidades que el agente de documentación asignó en `source-access.md`
    (LOW, MED en U1).
  - El README ahora tiene reglas operativas en el punto del adaptador; decidir
    si se deja o se revierte.
  - Las dudas heredadas del Día 7 (checks que fallan, hooks sin `.venv` en el
    `PATH`, `harny init` o `update`).
- **Retrospectiva de la semana 2 :**
  - **Lo que salió bien:** F1 (almacén de evidencia) quedó mergeado; F2 pasó la
    puerta 1, la puerta 2 en cada una de sus cinco revisiones y la puerta 3 hoy;
    el adaptador se prueba sin salir a la red; y la regla de no dejar deuda
    funcionó: cada hallazgo se cerró en las specs y no con parches en el código.
  - **Lo que me costó:** seguir los hallazgos en la puerta 3 cuando llegan como
    una lista de IDs (Día 11: pedí que me dijeran si estaban resueltos); entender
    qué hacía el servidor MCP (Día 12); y que cada ronda de auditoría abría otra
    revisión de las specs (cinco en total) y hoy llevó la auditoría a cuatro
    rondas, con dos relecturas acotadas más.
  - **Lo que haría distinto:** pedir desde el inicio de cada puerta una frase por
    hallazgo (qué estaba mal, qué se hizo y si está cerrado), y fijar de entrada
    cuándo se deja un caso límite como nota aceptada en lugar de abrir otra
    revisión.
  - **Pendiente de tu parte:** corregir lo que no sea cierto y añadir con tus
    palabras qué fue lo que más te costó entender.
- **Respuestas de autoevaluación:** el plan no trae preguntas para hoy.
- **Siguiente paso:** Día 15: PostgreSQL y Docker Compose. (Corregido el
  2026-10-13: el merge del PR #16 ya se hizo el 2026-10-12, `main` en `6a9e64d`;
  antes decía que faltaba.)

## Día 15: PostgreSQL y Docker Compose (2026-10-13)

- **Objetivo:** decidir D-10, D-11 y D-12, dejar escrito el ADR de persistencia,
  tener un `compose.yaml` solo con PostgreSQL y conectarme a la base. Hoy no hay
  feature SDD ni puertas: es preparación de F3.
- **Qué hice:**
  - **Bitácora del Día 14:** corregí la línea "Siguiente paso" (el merge del
    PR #16 ya se había hecho) en la rama `docs/day-15-postgres-compose`.
  - **Decisiones:** aprobé D-10, D-11 y D-12 tal como las recomendó la tabla.
  - **Docker:** estaba instalado pero apagado; abrí Docker Desktop y la base
    quedó arriba y `healthy` (PostgreSQL 18.6). No tengo `psql` en Windows: me
    conecté con el que trae el contenedor.
  - **`.env`:** lo creé yo mismo y era igual que `.env.example`. Después cambié
    la contraseña y DBeaver me dijo `password authentication failed`.
  - **Interfaz:** pedí ver la base en una interfaz y me conecté con DBeaver, que
    ya tenía instalado.
  - **ADR 0007:** lo revisé y dije "apruebo"; pasó a `Accepted`.
  - **Plan frente a hoy:** el plan decía que yo escribía a mano el ADR y el
    `compose.yaml`; hoy los redactó el agente por mi pedido y yo los revisé y
    aprobé.
- **Qué aprendí (con mis palabras):**
  - **Hoy no expliqué nada con mis palabras.** Lo que sí hice fueron preguntas:
    "no tengo ni creado usuario ni nada, o tú ya lo creaste" y "qué es lo del
    ADR 0007 que me dices".
  - **Lo que me explicaron (no es mi redacción):** el usuario `ecpq_dev` lo creó
    el propio contenedor al arrancar la primera vez, con lo que decía `.env`
    entonces; PostgreSQL guarda la contraseña dentro del volumen, así que
    cambiar `.env` después no la cambia y hay que usar `ALTER ROLE` o borrar el
    volumen; y un ADR es la hoja donde queda escrito qué se decidió, por qué y
    qué se descartó.
- **Decisiones tomadas (ID del plan y resumen):**
  - **D-10:** `psycopg` 3 síncrono con SQL explícito, sin ORM; solo
    `infrastructure` lo importa.
  - **D-11:** archivos SQL numerados en `migrations/` y un ejecutor propio
    mínimo; un archivo ya aplicado no se edita.
  - **D-12:** Docker Compose solo con PostgreSQL, imagen `postgres:18`, puerto
    solo en `127.0.0.1` y volumen nombrado.
  - **ADR 0007:** aceptado. El esquema de tablas, la variante `binary` o de
    código fuente de `psycopg` y el contrato exacto del ejecutor quedan para la
    spec de F3.
  - **Interfaz:** DBeaver, sin agregar servicios al repositorio.
- **Verificación (comando y resultado):**
  - `uv run pytest`: 961 pasan, igual que el Día 14.
  - `uv run ruff check .`, `uv run ruff format --check .` (78 archivos) y
    `uv run mypy .` (20 archivos): sin errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio.
  - `docker compose config` válido; `docker compose up -d --wait` deja el
    servicio `healthy`; `psql` conecta como `ecpq_dev` a `ecpq_dev`.
  - Autenticación por red: acepta la contraseña vigente y rechaza una
    incorrecta.
- **Dudas abiertas:**
  - `specs/current/_index.md` dice que los ADR van de 0001 a 0006; es un archivo
    derivado y se regenera con `harny-sync` al archivar F3.
  - Variante de `psycopg` y contrato del ejecutor de migraciones: a la spec de
    F3 (Día 16).
  - La contraseña de mi `.env` es mía y local; `.env.example` solo lleva valores
    falsos. Hoy `.env.example` desapareció del disco al crear mi `.env` y hubo
    que volver a crearlo.
  - Siguen abiertas las dudas del Día 14 (N-21, R-6, R-7, R-11 y la
    verificación contra el portal real) y las heredadas del Día 7.
  - **Pendiente de tu parte:** corregir lo que no sea cierto y añadir con tus
    palabras qué te costó entender de hoy.
- **Respuestas de autoevaluación:** el plan no trae preguntas para hoy.
- **Siguiente paso:** Día 16: F3 `postgres-persistence`, specs. Diseñar en
  papel `ingestion_run`, `raw_evidence` y `audit_event` con sus claves y
  restricciones, y luego las specs y la puerta 1. (Corregido el 2026-10-13: el
  merge del PR #17 ya se hizo, `main` en `3aac942`; antes decía que faltaba.)

## Día 16: F3 `postgres-persistence`, specs (2026-10-13)

- **Objetivo:** dejar diseñadas las tablas de F3 y llevar sus specs hasta la
  puerta 1.
- **Qué hice:**
  - **Merge del PR #17** (ADR 0007 y Compose) con mi OK; `main` quedó en
    `3aac942`.
  - **Diseño de tablas:** el agente me dio un borrador y yo decidí: cuatro tablas
    (`ingestion_run`, `raw_evidence`, `observation` y `audit_event`),
    inmutabilidad en la base de datos y tres estados de ejecución (`running`,
    `succeeded` y `failed`).
  - **Specs de F3:** el architect las escribió (revisión 1) con 17 criterios, 12
    resultados y 10 puntos abiertos para mí.
  - **Puerta 1, mis respuestas:** acepté `psycopg[binary]`; en el punto 6 elegí
    la B (la migración inicial la escribe el executor y yo la reviso línea por
    línea); acepté los otros ocho puntos.
  - **Tres hallazgos:** pegué tres hallazgos sobre la revisión 1 (AC11, el
    aislamiento de las pruebas y la igualdad de JSON). Los verifiqué contra las
    specs, eran ciertos y el architect los cerró en la revisión 2.
  - **Dependabot:** pedí que el punto 10 quedara fuera de F3 pero que su
    corrección abarcara el ADR 0006 y el ADR 0007; el PR #18 se mergeó
    (`c00fa2d`).
  - **Aprobación:** dije "apruebo" sobre la revisión 2; quedó registrada en la
    línea `Approval` de `intent.md`.
  - **PR de Dependabot:** al agregar el ecosistema `uv` aparecieron tres PR
    (#19, #20 y #21). Pregunté "qué pasó con los PR" y dije "sigue". Se
    mergearon #19 (`setup-uv`), #20 (`uv-build` 0.13) y #21 (`ruff` 0.17.0); el
    #21 fallaba porque `ruff` 0.17 reporta dos `# noqa: DTZ001` sobrantes en
    pruebas de F1, y se quitaron en su propia rama.
- **Qué aprendí (con mis palabras):**
  - **Hoy no expliqué nada con mis palabras.** Lo que sí hice fue una pregunta
    ("está bien que el `.env.example` se mantenga en el repo en público") y
    decisiones: cuatro tablas, inmutabilidad, estados, `psycopg` y la opción B.
  - **Lo que me explicaron (no es mi redacción):** `.env.example` es normal en un
    repo público porque solo lleva valores falsos y el escaneo de secretos corre
    en cada commit; en Python `True == 1`, así que repetir una ejecución con
    `{"x": true}` pasaba como la misma que `{"x": 1}` y por eso la comparación
    tiene que distinguir tipos; si la conexión se cae justo durante el commit el
    resultado queda desconocido, y un error de conexión no prueba que no se
    escribió nada; y Dependabot solo vigilaba `github-actions`, no los paquetes
    de Python.
- **Decisiones tomadas (ID del plan y resumen):**
  - **D-10 (concretada):** `psycopg[binary]>=3.3.6`; el `uv.lock` pasa de 22 a 25
    paquetes. La dependencia la agrega la tarea O1, no hoy.
  - **D-11 (concretada):** una transacción por archivo de migración con su fila
    de control, checksum de lo ya aplicado, un candado que falla al instante y
    función de biblioteca, sin comando de CLI.
  - **Puntos 3, 4, 5, 7, 8 y 9 de la puerta 1:** aceptados como se
    recomendaron (ajustes de conexión sin contraseña visible, pruebas de
    integración que se saltan en local y fallan en CI, servicio `postgres:18` en
    el job `tests`, hora guardada como instante, eventos sin clave de
    idempotencia y restricciones extra en el esquema).
  - **Migración inicial:** la escribe el executor y yo la reviso línea por línea;
    cambia lo que decía el plan del Día 17.
  - **Revisión 2:** aprobada hoy.
- **Verificación (comando y resultado):**
  - `uv run pytest`: 961 pasan, sin cambios de código míos hoy (solo los dos
    `# noqa` que se quitaron en el #21).
  - `uv run ruff check .`, `uv run ruff format --check .` (81 archivos) y
    `uv run mypy .` (20 archivos): sin errores, también con `ruff` 0.17.0 y
    `uv-build` 0.13 después de actualizar la rama con `main`. `ruff format`
    encontró un bloque
    de código sin formato dentro de `execution-plan.md` (ruff también formatea
    los bloques de Python de los `.md`) y lo corregí con el formateador.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - `git diff --check` limpio.
  - La base de Compose sigue `healthy` y no quedaron bases ni esquemas de
    prueba.
- **Dudas abiertas:**
  - La caída durante el commit queda documentada y sin prueba, porque haría
    falta un proxy que entienda el protocolo de PostgreSQL.
  - El glosario dice "ejecución de ingesta" y la tabla se llama
    `ingestion_run`; falta decidir si se agrega "run" como palabra de la tabla.
  - `specs/current/_index.md` sigue diciendo que los ADR llegan hasta el 0006; se
    regenera con `harny-sync` al archivar F3.
  - Siguen abiertas las dudas del Día 14 (N-21, R-6, R-7, R-11 y la
    verificación contra el portal real) y las heredadas del Día 7.
  - **Pendiente de tu parte:** corregir lo que no sea cierto y añadir con tus
    palabras qué te costó entender de hoy.
- **Respuestas de autoevaluación:** el plan no trae preguntas para hoy.
- **Siguiente paso:** Día 17: el executor agrega `psycopg` (O1), el
  test-writer escribe las pruebas en rojo contra PostgreSQL real (puerta 2), el
  executor escribe la migración inicial (yo la reviso línea por línea) y el
  resto de F3, se agrega el servicio `postgres:18` al job `tests`, y luego
  auditoría (puerta 3) y documentación. (Corregido el 2026-10-13: el merge del
  PR #22 ya se hizo, `main` en `e74a41a`; antes decía que faltaba.)

## Día 17: F3 `postgres-persistence`, implementación e integración en CI (2026-10-14)

- **Objetivo:** llevar F3 desde las pruebas en rojo hasta la auditoría
  (puerta 3), con el servicio `postgres:18` en CI y la documentación.
- **Qué hice:**
  - **Línea base nueva:** `tasks.md` § Baseline decía `3aac942`; la registré
    sobre `e74a41a` (ruff 0.17.0, `uv_build` 0.13, 81 archivos de formato, 961
    pruebas).
  - **O1:** `psycopg[binary]` 3.3.6 y el marcador `integration`; el `uv.lock`
    pasó de 22 a 25 paquetes.
  - **Puerta 2:** el test-writer escribió las pruebas en rojo contra la base de
    Compose. Las revisé y las aprobé. Aprobé también la aclaración de AC6 y
    pedí que quedara en `intent.md` y `execution-plan.md`, no solo en
    `tasks.md`.
  - **O3 a O7:** tipos de dominio y puerto, la migración inicial, el runner, los
    ajustes y el adaptador. En O5 paré y revisé `0001_initial_schema.sql` línea
    por línea.
  - **O8 y PR #23:** el servicio `postgres:18` en el job `tests`; abrí el PR y
    activé Auto-fix sin auto-merge.
  - **O9 a O11 y O12:** evidencias, documentación y la auditoría independiente.
  - **Puerta 3:** aprobé F1 y la puerta. Luego vino la documentación, el
    archivo de las specs en `specs/archived/postgres-persistence/` y la
    regeneración de `specs/current/_index.md`.
- **Qué aprendí (con mis palabras):**
  - **Lo que escribí yo (mi revisión de la migración):** el CHECK de
    `headers` solo exige que sea un arreglo y rechaza `Set-Cookie` en el índice
    0; no valida que cada elemento sea un par `[nombre, valor]` ni que sean
    texto. Esa forma completa la valida el dominio y el adaptador. Pedí cambiar
    solo el comentario, sin ampliar el alcance de la spec aprobada. También
    comprobé que el `$` de la expresión regular de PostgreSQL exige el final
    real de la cadena.
  - **Lo que me explicaron (no es mi redacción):**
    - Un `TRUNCATE` simple sobre una tabla referenciada por otra falla con
      `0A000` antes de llegar al trigger; con `CASCADE` o sobre las tablas
      hoja sí llega y da `23000`. La tabla queda igual de protegida.
    - `same_json` acepta `object` en sus parámetros porque valida el valor él
      mismo en ejecución; con `JsonValue` las pruebas aprobadas no pasaban
      `mypy`.
    - Las pruebas de integración se saltan en local y fallan en CI: sin eso, CI
      podría quedar verde sin probar la base.
  - **Pendiente de tu parte:** escribir con tus palabras qué te costó entender
    de las restricciones y los triggers de la migración.
- **Decisiones tomadas (ID del plan y resumen):**
  - **O5, revisión de la migración:** ajustar solo el comentario del CHECK de
    `headers`; ningún SQL cambió.
  - **AC6:** `TRUNCATE` simple sobre `raw_evidence` o `ingestion_run` acepta
    `23000` o `0A000` con las filas intactas; con `CASCADE` y sobre
    `observation` y `audit_event` se exige `23000`.
  - **F1 de la auditoría:** aprobada la firma `same_json(object, object)`, junto
    con las reglas ratificadas en F3 y F4 (sustituto suelto en los ajustes, NUL
    y archivo solo de espacios en las migraciones, texto no ASCII y enteros JSON
    demasiado largos).
  - **Puerta 3:** aprobada con la auditoría "aprobado con reservas".
- **Verificación (comando y resultado):**
  - `uv run --env-file .env pytest --cov=ec_procurement_quality
    --cov-report=term-missing`: 1307 pasan, 0 saltadas, cobertura total 96 %
    (961 de la línea base y 346 nuevas).
  - `uv run pytest -q` sin base: 1132 pasan y 175 saltadas, cada una con su
    motivo.
  - `CI=true uv run pytest tests/integration -q`: errores y salida distinta de
    cero, ninguna saltada.
  - `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy .`
    (34 archivos): sin errores.
  - `uv run node .sdd/doctor/run-doctor.mjs`: 31 ok, 0 avisos, 0 fallos.
  - PR #23: `tests` y `feedback` en verde; el log de CI muestra el servicio
    `postgres:18` y las pruebas de integración pasando sin saltadas.
  - Sin bases `ecpq_test_` sobrantes en Compose.
- **Dudas abiertas:**
  - El glosario sigue diciendo "ejecución de ingesta" y la tabla se llama
    `ingestion_run`; no lo toqué, falta decidir.
  - F5 de la auditoría: aquí los hooks de `ruff` y `mypy` salen "skipped"
    porque `.venv` no está en el `PATH`; lo cubre el job `feedback` de CI.
  - La caída justo durante el commit sigue documentada y sin prueba.
  - La conexión compartida en `postgres_settings.py` y `REPEATABLE READ` para
    lecturas quedan como recomendaciones para F4 (N3 y N5 de la auditoría).
  - Siguen abiertas las dudas del Día 14 y las heredadas del Día 7.
- **Respuestas de autoevaluación:** el plan no trae preguntas para hoy.
- **Siguiente paso:** el merge del PR #23 solo con tu OK explícito. Luego Día
  18: F4 `ingest-command`, specs; escribir con tus palabras los criterios de
  idempotencia y reanudación antes de pedírselos al agente (D-09).
