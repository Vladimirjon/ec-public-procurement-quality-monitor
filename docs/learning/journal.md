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
    también en las sesiones con Claude. Claude aparece como coautor
    (`Co-Authored-By`).
  - Todo cambio llega a `main` por pull request, con el CI en verde antes
    del merge. El gráfico de contribuciones de GitHub solo cuenta los commits
    que llegan a la rama por defecto con un correo vinculado a la cuenta.
  - El primer commit del plan quedó con Claude como autor. No se reescribió
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
