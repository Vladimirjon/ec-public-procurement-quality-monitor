# Plan de aprendizaje: 30 sesiones

Guía personal para construir este proyecto de punta a punta en un mes y
aprender en el proceso. El código, los ADR y la documentación técnica del
repositorio siguen en inglés. Este plan y la bitácora están en español
porque son material de estudio.

- Inicio: 2026-10-01
- Duración: 30 sesiones diarias de 2 a 2,5 horas
- Método: Specification-Driven Development con el harness **harny**
- Registro: [journal.md](journal.md), la bitácora diaria

> Este plan no reemplaza a [AGENTS.md](../../AGENTS.md) ni a los ADR. Si algo
> de aquí los contradice, mandan ellos, y este plan se corrige.

---

## 1. Qué vas a tener al final

Un sistema que puedas demostrar y explicar en una entrevista:

1. Un **CLI en Python** que ejecuta lotes acotados de ingesta de datos de
   contratación pública de SERCOP para Empresa Eléctrica Quito (E.E.Q.).
2. **Evidencia cruda inmutable**: cada respuesta original se guarda una sola
   vez, con hash de integridad, y nunca se sobrescribe ([ADR 0002](../adr/0002-immutable-raw-storage.md)).
3. **PostgreSQL** (con Docker Compose) para los datos normalizados, la
   auditoría de cada ejecución y los resultados de calidad.
4. **Reglas de calidad de datos** versionadas (completitud, validez,
   consistencia, unicidad). Cada hallazgo apunta a la evidencia que lo
   produjo.
5. Ingesta **idempotente y reanudable**: repetir una ejecución no duplica
   nada, y una ejecución que se cae se puede retomar.
6. **CI/CD en GitHub Actions**: lint, tipos, pruebas unitarias e integración
   contra PostgreSQL real, escaneo de secretos y publicación automática de
   releases al crear un tag.
7. Un **estudio de caso** de E.E.Q. con resultados agregados (sin datos
   crudos), y un guion para presentarlo en una entrevista.

## 2. Cómo trabajamos

### Roles

| Quién | Qué hace |
|---|---|
| **Tú** | Eres la *puerta humana* de harny: apruebas specs, pruebas y auditorías. Tomas las decisiones de arquitectura. Escribes a mano las partes marcadas con 🧑. |
| **Agentes harny** | `sdd-architect` redacta specs, `sdd-test-writer` escribe pruebas en rojo, `sdd-executor` implementa hasta verde, `sdd-auditor` audita y `sdd-documentation` documenta. |
| **Yo (guía)** | Explico el concepto del día, propongo el paso siguiente, reviso tu trabajo y te hago preguntas. No apruebo nada en tu nombre. |

### La regla que hace que aprendas

La IA puede escribir el código, pero **tú no apruebas lo que no puedas
explicar**. En cada puerta humana tienes que poder responder:

1. ¿Qué cambia y por qué?
2. ¿Cómo puede fallar?
3. ¿Qué prueba demuestra que funciona?

Si no puedes, la puerta queda cerrada hasta que puedas. Además, las tareas
marcadas con 🧑 las escribes tú a mano, y el agente solo las revisa.

### Estructura de cada sesión (unas 2 h)

| Bloque | Tiempo | Qué haces |
|---|---|---|
| Arranque | 10 min | Lees la última entrada de la bitácora y ejecutas `node .sdd/doctor/run-doctor.mjs` |
| Concepto | 20 min | Aprendes el tema del día: te lo explico y tú me lo explicas de vuelta |
| Práctica | 60–90 min | El trabajo del día |
| Verificación | 15 min | Corres los comandos de verificación, revisas el diff y haces commit |
| Cierre | 10 min | Escribes la entrada de la bitácora y respondes las preguntas de autoevaluación |

### Cómo empezar cada sesión conmigo

Abre una sesión nueva y escribe:

> Hoy es el **Día N** del plan. Lee `docs/learning/plan.md` y la última
> entrada de `docs/learning/journal.md`, y guíame.

### Si te atrasas

Los días 7, 14, 21 y 28 son de repaso y sirven de colchón. Si un día no
alcanza, terminas lo pendiente en el siguiente y anotas el desfase en la
bitácora. No te saltes puertas humanas para recuperar tiempo.

---

## 3. El pipeline harny (lo repetirás 7 veces)

```
sdd-architect   → specs/<feature>/{intent,execution-plan,tasks}.md (el auditor agrega audit.md)
   ⛩ PUERTA 1: revisas y apruebas las specs
sdd-test-writer → pruebas en ROJO (fallan porque aún no hay código)
   ⛩ PUERTA 2: revisas que fallen por la razón correcta
sdd-executor    → implementación hasta VERDE, sin tocar las pruebas
sdd-auditor     → audit.md con veredicto
   ⛩ PUERTA 3: aceptas o rechazas el veredicto
sdd-documentation → README/CHANGELOG, archivo de specs, ADR (automático)
```

Lo controla el skill `sdd-conductor`. Los hooks de harny ejecutan lint y
chequeo de tipos al final de cada turno del agente, y el CI repite lo mismo
en cada pull request.

## 4. Las features (porciones verticales)

| # | Feature | Qué entrega | Días |
|---|---|---|---|
| F0 | `project-skeleton` | Paquete Python, capas vacías, comando `--version`, pruebas y CI en verde | 5–6 |
| F1 | `raw-evidence-store` | Almacén inmutable de evidencia cruda en disco local | 9–11 |
| F2 | `sercop-source-adapter` | Puerto y adaptador de la fuente SERCOP, probado con fixtures | 12–14 |
| F3 | `postgres-persistence` | Docker Compose, migraciones y tablas de auditoría | 15–17 |
| F4 | `ingest-command` | Comando `ingest` idempotente y reanudable | 18–20 |
| F5 | `ocds-normalization` | Respuestas crudas convertidas a tablas normalizadas, con cuarentena | 22–23 |
| F6 | `quality-rules` | Motor de reglas y primeras reglas de calidad | 24–26 |
| F7 | `quality-report` | Comando `report` que exporta los hallazgos | 26 |

Los nombres son propuestas. Los confirmas al iniciar cada feature.

## 5. Registro de decisiones pendientes

Según `AGENTS.md`, agregar dependencias, infraestructura, frameworks o
servicios **requiere tu aprobación explícita**. Estas son las decisiones que
te tocarán, cada una con mi recomendación para discutirla ese día:

| ID | Decisión | Día | Recomendación | Por qué |
|---|---|---|---|---|
| D-01 | Versión de Python | 3 | `>=3.13`, y CI con 3.13 | Ya tienes 3.13.9 en `.venv` |
| D-02 | Gestor de paquetes | 3 | `uv` con `uv.lock` | Instalaciones reproducibles, que es un valor central del proyecto |
| D-03 | Lint y formato | 3 | `ruff` | Una sola herramienta rápida; harny ya tiene perfil Python |
| D-04 | Chequeo de tipos | 3 | `mypy`, estricto en `domain` | Tipos explícitos en las reglas de negocio |
| D-05 | Pruebas | 3 | `pytest` | Estándar de facto |
| D-06 | Roles y stack de harny | 4 | Activar los 5 roles y el stack `python` | Hoy solo está el architect y el stack está vacío |
| D-07 | Disposición del almacén crudo | 9 | Ruta por hash SHA-256 y metadatos en un archivo aparte | Inmutabilidad verificable (ADR nuevo) |
| D-08 | Cliente HTTP | 12 | `httpx` | Timeouts y `MockTransport` sin librería extra de mocks |
| D-09 | Framework de CLI | 18 | `argparse` (biblioteca estándar) | La capa `interfaces` es delgada; cero dependencias |
| D-10 | Acceso a PostgreSQL | 15 | `psycopg` 3 con SQL explícito | Aprendes SQL de verdad y el adaptador queda simple |
| D-11 | Migraciones | 15 | Archivos SQL numerados y un pequeño ejecutor propio | Auditable y sin otra dependencia (alternativa: Alembic) |
| D-12 | Docker Compose para PostgreSQL | 15 | Sí, solo PostgreSQL | Ya está previsto en ADR 0003 |
| D-13 | Alcance del CD | 27 | Release de GitHub con wheel y sdist al hacer push de un tag `v*` | Sin PyPI ni imagen Docker: el proyecto es académico (ADR 0003) |

Cada decisión aprobada se registra en la bitácora y, si es arquitectónica,
en un ADR nuevo en `docs/adr/`.

## 6. Evolución del CI/CD

El CI crece junto con el proyecto. Un pipeline que no tiene nada que
verificar no demuestra nada.

| Día | Qué se agrega | Archivo |
|---|---|---|
| Hoy | Escaneo de secretos con gitleaks (ya existe) | `.github/workflows/harny-feedback.yml` |
| 4 | `ruff` y `mypy` mediante el perfil Python de harny | `harny-feedback.yml` (bloque generado) |
| 6 | `pytest` con pruebas unitarias y reporte de cobertura | `.github/workflows/tests.yml` |
| 17 | Pruebas de integración contra PostgreSQL (`services: postgres`) | `tests.yml` |
| 27 | CD: release automática al hacer push de un tag `v*` | `.github/workflows/release.yml` |
| 2 | Protección de `main` (PR y check `feedback` obligatorios), borrado automático de ramas y Dependabot | Configuración de GitHub y [repository-settings.md](../repository-settings.md) |
| 6 | Agregar el check `tests` a los checks obligatorios de `main` | Configuración de GitHub y `repository-settings.md` |
| 27 | Badges de CI en el README | `README.md` |

Para la entrevista, esto te deja una historia concreta: *"Cada PR pasa lint,
tipos, pruebas unitarias, pruebas de integración contra PostgreSQL real y un
escaneo de secretos, y las releases se generan solas a partir de un tag."*

---

## 7. Calendario día por día

Leyenda: 🧑 lo escribes tú a mano · 🤖 lo hace un agente y tú lo revisas ·
⛩ puerta humana · ✅ entregable verificable

### Semana 1: Fundamentos y harness

#### Día 1: Orientación
- **Concepto:** qué es SDD, qué es una arquitectura de puertos y adaptadores
  (hexagonal) y qué problema resuelve este proyecto.
- **Práctica:**
  1. Lee en orden `AGENTS.md`, `README.md`, `docs/architecture.md`, los tres
     ADR y `docs/ai-assisted-development.md`.
  2. Lee `.claude/skills/sdd-conductor/SKILL.md` y
     `.claude/skills/harny-propose/SKILL.md`.
  3. Ejecuta `node .sdd/doctor/run-doctor.mjs`.
  4. Corrige los dos avisos de seguridad:
     `git config core.hooksPath .sdd/git-hooks` e instala gitleaks.
     Ojo: los hooks están guardados en git sin permiso de ejecución
     (`100644`). Git para Windows los ejecuta igual, pero en Linux o macOS
     se ignoran. Investiga `git update-index --chmod=+x` y decide si
     corregirlo.
  5. 🧑 Dibuja en papel las 4 capas y qué puede importar cada una.
- ✅ El doctor da 0 avisos y la bitácora tiene la entrada del Día 1.
- **Autoevaluación:** ¿Por qué `domain` no puede importar `psycopg`? ¿Qué
  pasaría si sobrescribieras una respuesta cruda?

#### Día 2: Conocer la fuente de datos
- **Concepto:** el estándar Open Contracting Data Standard (OCDS): `ocid`,
  `release`, `record`, y las etapas `tender`, `award` y `contract`.
- **Práctica:**
  1. Explora el portal de datos abiertos de SERCOP en el navegador.
  2. Identifica qué consultas permiten filtrar por la entidad E.E.Q.
  3. 🧑 Escribe `docs/sources/sercop-observations.md` con lo que
     **observaste**: URL, parámetros, códigos de respuesta, paginación,
     campos presentes o ausentes y fecha de la observación.
  4. No commitees respuestas completas. Si necesitas un ejemplo, recórtalo y
     sanitízalo.
- ✅ Un documento de observaciones con fechas y sin datos crudos.
- **Autoevaluación:** ¿Qué es un contrato *observado* frente a uno
  *inventado*? ¿Por qué `AGENTS.md` lo prohíbe?

#### Día 3: Decisiones de toolchain
- **Concepto:** qué es un ADR y cómo escribir uno que sirva dentro de un año.
- **Práctica:**
  1. Discutimos D-01 a D-05 y tú decides.
  2. 🧑 Escribe `docs/adr/0004-python-toolchain.md` (contexto, decisión,
     alternativas y consecuencias).
  3. Instala `uv` en tu máquina, si lo apruebas.
- ✅ ADR 0004 aceptado y decisiones registradas en la bitácora.
- **Autoevaluación:** ¿Qué alternativa descartaste y qué perdiste al
  descartarla?

#### Día 4: Configurar harny por completo y el primer CI real
- **Concepto:** feedback computacional: hooks por turno frente a CI. Por qué
  el agente necesita el mismo control que el CI.
- **Práctica:**
  1. harny no está publicado en npm: se instaló desde su código fuente,
     `github.com/Danii2020/harny` (ver el commit `d0b08fc`). Repite ese
     proceso: clona el repositorio, revisa qué cambió desde la instalación
     anterior y lee la ayuda de su comando `init` antes de ejecutarlo.
  2. Vuelve a ejecutar el `init` de harny con los 5 roles y el stack
     `python` (D-06). Decide de nuevo, a conciencia, si incluir `.mcp.json`
     (Context7), que se excluyó a propósito en la primera instalación.
  3. 🧑 Revisa el diff generado archivo por archivo: `.claude/agents/`,
     `.claude/settings.json`, `.sdd/` y el bloque generado de
     `harny-feedback.yml`.
  4. Abre un PR solo con este cambio y observa el workflow en GitHub Actions.
- ✅ Doctor sin fallos y el workflow `harny feedback` corriendo en el PR.
- **Autoevaluación:** ¿Qué pasa cuando el agente termina un turno con un
  error de lint?

#### Día 5: F0 `project-skeleton`, specs
- **Concepto:** qué va en `intent` (criterios de éxito), `execution-plan`
  (reemplaza a `contract` y `roadmap`: restricciones, enfoque y validación),
  `tasks` y `audit`.
- **Práctica:**
  1. 🤖 `sdd-architect` redacta las specs de F0: `pyproject.toml`,
     `src/` con las 4 capas, `--version`, configuración de ruff, mypy y
     pytest.
  2. 🧑 Antes de leer lo que escribió, anota 3 criterios de éxito que tú
     esperarías. Luego compáralos con los suyos.
  3. ⛩ PUERTA 1.
- ✅ `specs/project-skeleton/` aprobado.

#### Día 6: F0, rojo, verde, auditoría y CI de pruebas
- **Concepto:** TDD. Por qué una prueba tiene que fallar primero, y por la
  razón correcta.
- **Práctica:**
  1. 🤖 Test-writer: pruebas en rojo. Ejecútalas y lee el error. ⛩ PUERTA 2.
  2. 🤖 Executor: implementación hasta verde.
  3. 🧑 Crea `.github/workflows/tests.yml` (pytest y cobertura). Te guío
     paso a paso.
  4. 🤖 Auditor. ⛩ PUERTA 3. 🤖 Documentación.
- ✅ PR con todo el CI en verde.

#### Día 7: Repaso de la semana 1
- Explícame en 5 minutos, sin mirar, la arquitectura y el pipeline harny.
- Quiz de 10 preguntas.
- Merge del PR de F0 y retrospectiva en la bitácora.
- Colchón para terminar lo pendiente.

### Semana 2: Evidencia y fuente

#### Día 8: Modelo de dominio
- **Concepto:** lenguaje ubicuo, objetos de valor, entidades e invariantes.
- **Práctica:** 🧑 Escribe `docs/glossary.md` con proceso de contratación,
  evidencia cruda, ejecución de ingesta, regla de calidad y hallazgo de
  calidad. Para cada término: definición, invariantes y ejemplo sintético.
- ✅ Glosario revisado.
- **Autoevaluación:** ¿Un hallazgo de calidad es una entidad o un objeto de
  valor? Justifica tu respuesta.

#### Día 9: F1 `raw-evidence-store`, decisiones y specs
- **Concepto:** almacenamiento direccionado por contenido, escrituras
  atómicas y semántica *append-only*.
- **Práctica:**
  1. Decides D-07 y 🧑 escribes un ADR sobre la disposición del almacén
     crudo.
  2. 🤖 Specs de F1. ⛩ PUERTA 1.
- ✅ ADR y specs aprobados.

#### Día 10: F1, rojo y verde
- 🤖 Pruebas en rojo. ⛩ PUERTA 2.
- 🧑 Implementa tú el **puerto** (la interfaz en `application`) y el objeto
  de valor del hash en `domain`.
- 🤖 Executor implementa el adaptador de disco local.
- **Prueba clave:** guardar dos veces el mismo contenido no duplica nada, y
  guardar contenido distinto bajo la misma identidad es un error explícito.

#### Día 11: F1, auditoría y documentación
- 🤖 Auditor. ⛩ PUERTA 3. 🤖 Documentación.
- 🧑 Lee `audit.md` completo y explica cada hallazgo con tus palabras.
- ✅ Merge de F1.

#### Día 12: F2 `sercop-source-adapter`, specs
- **Concepto:** timeouts, reintentos con backoff, límites de tasa y por qué
  las pruebas nunca deben salir a la red.
- **Práctica:**
  1. Decides D-08.
  2. 🧑 Prepara 2 o 3 fixtures **mínimos y sanitizados** a partir de tus
     observaciones del Día 2.
  3. 🤖 Specs basadas **solo** en `docs/sources/sercop-observations.md`.
     ⛩ PUERTA 1.
- ✅ Specs que citan observaciones reales, no suposiciones.

#### Día 13: F2, rojo y verde
- 🤖 Pruebas en rojo con transporte simulado. ⛩ PUERTA 2.
- 🤖 Executor. 🧑 Revisa línea por línea cómo se manejan los errores HTTP.
- **Prueba clave:** una respuesta incompleta o un 5xx produce un error
  tipado, nunca datos a medias.

#### Día 14: F2, auditoría y repaso de la semana 2
- 🤖 Auditor. ⛩ PUERTA 3. 🤖 Documentación. Merge.
- Retrospectiva: ¿qué te costó más entender? ¿Qué harías distinto?

### Semana 3: Persistencia e ingesta

#### Día 15: PostgreSQL y Docker Compose
- **Concepto:** diseño de esquemas, restricciones `UNIQUE` como mecanismo de
  idempotencia y migraciones.
- **Práctica:**
  1. Decides D-10, D-11 y D-12, y 🧑 escribes el ADR de persistencia.
  2. 🧑 Escribe tú `compose.yaml` (solo PostgreSQL, con credenciales en
     `.env`, que está ignorado, y un `.env.example` con valores falsos).
  3. Levanta la base y conéctate con `psql`.
- ✅ Docker Compose funcionando y el ADR aceptado.

#### Día 16: F3 `postgres-persistence`, specs
- 🧑 Diseña en papel las tablas `ingestion_run`, `raw_evidence` y
  `audit_event`, con sus claves y restricciones.
- 🤖 Specs (compáralas con tu diseño). ⛩ PUERTA 1.

#### Día 17: F3, implementación e integración en CI
- 🤖 Pruebas de integración en rojo contra PostgreSQL real. ⛩ PUERTA 2.
- 🤖 Executor. 🧑 Escribe tú las primeras migraciones SQL.
- 🧑 Agrega el job de integración a `tests.yml` con
  `services: postgres`.
- 🤖 Auditor. ⛩ PUERTA 3. 🤖 Documentación.
- ✅ CI corriendo pruebas de integración en verde.

#### Día 18: F4 `ingest-command`, specs
- **Concepto:** idempotencia, reanudación por puntos de control (checkpoints)
  y códigos de salida de un CLI.
- **Práctica:**
  1. Decides D-09.
  2. 🧑 Escribe tú los criterios de éxito de idempotencia y reanudación antes
     de pedírselos al agente.
  3. 🤖 Specs. ⛩ PUERTA 1.

#### Día 19: F4, rojo y verde
- 🤖 Pruebas en rojo, incluida una ejecución interrumpida a mitad de camino.
  ⛩ PUERTA 2.
- 🤖 Executor. 🧑 Implementa tú el caso de uso en `application`
  (orquestación mediante puertos).

#### Día 20: F4, auditoría y primera ejecución real
- 🤖 Auditor. ⛩ PUERTA 3. 🤖 Documentación. Merge.
- Primera ingesta real **acotada** de E.E.Q. contra SERCOP (pocas páginas).
- ✅ Evidencia cruda en `data/raw/` (ignorado por git) y auditoría en
  PostgreSQL.

#### Día 21: Repaso de la semana 3: romper cosas a propósito
- Interrumpe una ingesta con Ctrl+C y reanúdala.
- Ejecuta la misma ingesta dos veces y demuestra con SQL que no hay
  duplicados.
- Corrompe a mano un archivo crudo y verifica que el sistema lo detecta.
- 🧑 Documenta los tres experimentos en la bitácora.

### Semana 4: Normalización y calidad

#### Día 22: F5 `ocds-normalization`, specs
- **Concepto:** normalización, cuarentena de registros inválidos y linaje
  (cada fila normalizada apunta a su evidencia).
- 🤖 Specs. ⛩ PUERTA 1.

#### Día 23: F5, implementación completa
- 🤖 Rojo. ⛩ PUERTA 2. 🤖 Verde. 🤖 Auditoría. ⛩ PUERTA 3. Documentación.
- **Prueba clave:** volver a normalizar la misma evidencia produce
  exactamente el mismo resultado.

#### Día 24: F6 `quality-rules`, diseño
- **Concepto:** dimensiones de calidad de datos (completitud, validez,
  consistencia, unicidad y oportunidad).
- 🧑 Diseña tú el modelo de una regla: id, dimensión, severidad, versión y
  descripción.
- 🧑 Propón 5 reglas concretas para E.E.Q. basadas en lo que observaste.
- 🤖 Specs. ⛩ PUERTA 1.

#### Día 25: F6, rojo y verde
- 🤖 Pruebas en rojo. ⛩ PUERTA 2.
- 🧑 Implementa tú **dos** reglas en `domain`. El executor implementa el
  resto y la persistencia de los hallazgos.

#### Día 26: F6 auditoría y F7 `quality-report`
- 🤖 Auditor de F6. ⛩ PUERTA 3. Documentación.
- F7 (pequeña): comando `report` que exporta los hallazgos a CSV o Markdown.
  Pipeline completo, con sus 3 puertas.

#### Día 27: CD, releases y presentación del repo
- **Concepto:** versionado semántico, changelog y releases reproducibles.
- **Práctica:**
  1. Decides D-13.
  2. 🧑 Escribe `.github/workflows/release.yml`: al hacer push de un tag
     `v*` construye wheel y sdist y crea un GitHub Release con las notas
     del `CHANGELOG.md`.
  3. Agrega badges de CI al README. (La protección de `main` ya se configuró
     el Día 2.)
  4. Publica `v0.9.0` como prueba.
- ✅ Release creada automáticamente.

#### Día 28: Endurecimiento y repaso de la semana 4
- Ejecuta el skill `security-review` y una revisión de código completa.
- Doctor con 0 avisos, cobertura revisada y rutas de error probadas.
- 🧑 Verifica que la documentación no prometa nada que no exista.
- Colchón para terminar lo pendiente.

### Cierre

#### Día 29: Estudio de caso E.E.Q. y v1.0.0
- Ejecución real de mayor alcance, siempre acotada.
- 🧑 Escribe `docs/case-study-eeq.md`: preguntas, método, hallazgos
  **agregados**, limitaciones y avisos (proyecto académico, sin afiliación).
  Sin datos crudos.
- Publica la release `v1.0.0`.

#### Día 30: Preparación para entrevistas
- 🧑 Pitch de 2 minutos: problema, solución, decisiones y resultado.
- 🧑 Recorrido de arquitectura de 10 minutos con un diagrama.
- 🧑 Tres historias en formato STAR (Situación, Tarea, Acción, Resultado):
  una decisión de arquitectura, un bug difícil y cómo usaste IA con control
  humano.
- Simulacro de entrevista conmigo, con preguntas difíciles.
- Retrospectiva del mes.

---

## 8. Preguntas de entrevista que este proyecto te prepara para responder

- ¿Por qué un monolito modular y no microservicios? ¿Qué evidencia te haría
  cambiar de opinión?
- ¿Cómo garantizas que la evidencia cruda no se altera?
- ¿Cómo logras que una ingesta sea idempotente? ¿Y reanudable?
- ¿Cómo pruebas un adaptador HTTP sin depender de la red?
- ¿Qué corre tu CI y por qué en ese orden?
- ¿Cómo trabajaste con agentes de IA sin perder el control del diseño?
  (harny: specs, puertas humanas, hooks y auditoría.)
- ¿Qué harías distinto en la versión 2?

## 9. Verificación de cada sesión

```powershell
node .sdd/doctor/run-doctor.mjs
git status --short
git diff --check
# Desde el Día 4:
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src
# Desde el Día 6:
.venv\Scripts\python.exe -m pytest
```

Los comandos exactos se ajustan cuando se decida D-02 (por ejemplo,
`uv run pytest`). Cuando cambien, se actualizan aquí y en `AGENTS.md`.
