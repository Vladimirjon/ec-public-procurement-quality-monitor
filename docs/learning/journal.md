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

> Borrador redactado por Claude a partir de lo que expliqué en la sesión.
> Lo revisaré y lo reescribiré con mis palabras cuando repase.

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
