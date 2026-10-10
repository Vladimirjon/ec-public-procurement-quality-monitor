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
