---
plan_id: profile-delegate-worktree-mvp
status: done
updated_at: 2026-10-18
superseded_by: null
---

# Worktrees opcionales — plan de integración mínimo viable

**Autoridad actual: complete-target local.** Alberto aprobó este plan y pidió «Implementa con builder» y «Avísame para reiniciar gateway». Se autoriza la implementación acotada, pruebas y journeys desechables previstos, documentación y commits locales propios verificados. Builder es el único escritor del candidato; Adán coordina y verifica con Reviewer. No se autoriza reiniciar gateway, editar Hermes core/perfiles/configuración global, push/publicación ni reparar deuda ajena por inercia. La aceptación plan-only anterior queda como antecedente; no demuestra aceptación runtime.

**Estado efectivo:** F1–F5 cerrados en revisión focal y responsabilidades F6 aceptadas; excepción firma máximo29 hasta2026-11-17 decidida por Adán (ADR0002). F7 corregido plugin-only mediante --in/source cli y scope terminal nativo, sin DB patch. Adán completó CLI real new/resume con el mismo SID sin workdir en resume; verificó cwd nativo read-only, archivos y terminal. TUI real previo new/resume sigue aplicando a su camino intacto. Dos hijos empty, mismo SHA y checkouts distintos, producen alpha10/beta20; integración posterior por único escritor en tercer worktree ejecuta y verifica suma30. Fuente intacta y configs sin cambios. No claim de overlap, batch notificaciones ni gateway activo. `.artifacts/worktree-mvp/real-acceptance/acceptance-summary.json` contiene evidencia exacta; F7 tests/identidad en `.artifacts/worktree-mvp/f7/`. Revisión independiente consolidada completada (`f7-review/review.md`): PASS_WITH_NOTES funcional, F7 cerrado y excepción exacta PASS local; código/tests/policy/ADR verificados. Alberto autorizó después cerrar calidad y dejarlo listo; los gates globales y readiness se ejecutan bajo `plans/quality-readiness.md`, sin rebajarlos. La aceptación funcional worktree permanece cerrada. Sólo estado/docs cambiaron tras fingerprint F7; código permanece estable. Calidad posterior y adopción local completadas con review independiente y aceptación real batch, bajo `plans/quality-readiness.md`. El cierre local está listo para la decisión de restart de Alberto; no se ejecutó restart, ni cambios core/perfiles/global config o publicación. No confundir esta aceptación local con gateway activado.

## Resultado y elección

Una sola mejora opt-in del motor singular: crear un worktree para una sesión nueva y dejar que batch componga esa misma operación. Conservar el uso universal de `workdir`, incluso sin Git. El coordinador sigue decidiendo reparto, SHA común, revisión, integración y limpieza autorizada.

**Aceptación funcional:** dos encargos independientes del mismo perfil parten de un SHA local común en ramas/checkouts distintos; sus handles exponen los hechos reales de creación; el padre puede continuar cada sesión sin cambiar de checkout; un candidato integrado se comprueba con comportamiento real. Preflight, dedupe, fallos y cancelación no pierden trabajo ni inventan éxito.

**Alternativa conservada:** worktrees o copias preparados expresamente y pasados como `workdir`. Automatizar preparación recurrente justifica esta mejora, no crear un gestor de proyectos. No dependencias nuevas ni proveedores de workspace.

## Contrato mínimo

- `worktree: boolean = false`, estricto. Omitido/false no consulta ni exige Git y conserva el comportamiento/fingerprint histórico.
- `base_ref: string`, opcional sólo con creación. Default `HEAD`, referencia local a commit o SHA ya disponible; sin fetch/fallback. Rechazar vacío y entradas que Git interprete como opciones; no corregirlas en silencio.
- `branch: string`, opcional sólo con creación. Rama **nueva**, default `pd/<task_id>`. Validar con Git; colisión falla sin force/reset ni reutilización.
- `worktree:true` sólo con sesión nueva, `workdir` explícito igual a la raíz resuelta de un checkout no bare y preset que admita escritura. El preset `review` no puede provocar creación del padre: recibe un workspace existente si lo necesita. No alterar ni eludir autorización/política de aprobación. La preparación Git es una mutación del padre, anterior al hijo: admitirla bajo la autoridad del llamador y las políticas aplicables. El snapshot `native_approval` gobierna al hijo y no autoriza por sí solo esa mutación. No usar `native_approval.bind` en el padre ni añadir aprobación delegada; si falta autoridad aplicable, rechazar antes de Git y ofrecer preparación manual.
- No inferir proyecto por texto/hilo ni ascender desde una carpeta hasta `/opt/data`. Un monorepo se elige pasando conscientemente su raíz. Sin Git: salidas separadas, escritores por turnos o copias controladas fuera del plugin.
- Destino mecánico: `<repo-parent>/.profile-delegate-worktrees/<repo-name>/<task_id>`. Validar fuente, destino resuelto y directorios creados contra la política de workdirs existente. No ampliar allowlists. Si sólo está permitido el checkout fuente, explicar alternativa manual.
- Fuente dirty permitida e intacta. Sólo se materializa el commit: staged/unstaged/untracked/ignored quedan excluidos, con aviso visible. No stash, reset, auto-commit, copia de `.env` ni hooks/setup implícitos.
- Batch: el coordinador resuelve una sola vez el SHA y lo envía en cada item. El default HEAD por llamada no garantiza una base común.
- Resume: no crear, cambiar base/rama ni aceptar opciones de creación. `worktree:false` no significa abandonar un worktree anterior. Las continuaciones históricas sin metadata no adquieren requisito Git.
- Conservar workspace/rama tras éxito, fallo, timeout o cancelación; retención de artefactos no los borra. Ningún commit limpio obligatorio para `ok`. Sin auto-merge/cleanup, scheduler/DAG, IDs lógicos, mensajería, sandbox ni garantía exactamente una vez.

## Integración real, no otro subsistema

Repo: `/opt/data/plugins/profile-delegate`. Se inspecciona el candidato dirty, no se reconstruye desde HEAD. Los cambios existentes de batch, reasoning y calidad son ajenos a esta tarea.

- **`__init__.py:_schema/_handler`**: añadir/transmitir tres argumentos opcionales; no convertir `worktree` con `bool(...)`. Añadir al final de la firma singular para compatibilidad posicional. `_multischema` deriva del singular; no duplicar definición.
- **`core.py:delegate_profile`**: inspección opt-in, preflight sin asignación y preparación después de dedupe dentro de los locks actuales. `resolve_workdir/enforce_workdir_policy` siguen sirviendo el camino genérico.
- **Nuevo `worktrees.py`**: helpers pequeños de inspección/creación/verificación con Git por argv sin shell; sin clases proveedoras, configuración, dependencias ni framework. Reutilizar errores/política del plugin. Entorno Git controlado para no heredar redirecciones `GIT_*`; hooks deshabilitados por invocación, no mediante cambios persistentes.
- **`request_fingerprint`, `_active_matching_run`, `FingerprintLock`**: incluir opciones sólo en opt-in, ruta fuente y referencia solicitada; no destino único ni SHA de HEAD móvil. Preservar payload histórico sin opt-in. Reusar antes de comprobar si la rama creada por ese mismo run ya existe. El preflight que batch ejecuta antes de dispatch tampoco debe rechazar una reutilización válida por encontrar esa rama. Puede informar ocupación observada sin reservar recursos; decidir si la creación está libre ocurre después del matching autorizado.
- **Artefactos/retornos de `core.py`**: `request.workdir` sigue siendo cwd efectivo para consumidores existentes. Guardar metadata sólo cuando corresponde y proyectarla en preflight/launch/reuse/status/final/fallo con run creado; `_read_run_status` filtra campos y requiere extensión. No introducir `delivery` ni validador Git de resultados del modelo.
- **`batch.py:_validate_tasks/_dispatch/error_item`**: seguir validación de todos antes de lanzar; no crear por separado. Proyectar el mismo bloque workspace desde `_validate_tasks` en preflight, `_dispatch` y los details de `error_item`; ambos caminos filtran campos. Mantener partial/stop-later y hermanos vivos. No limitar la comprobación a request.json ni a los items lanzados.
- **`execution.py:build_child_command`, `core.py:_execute_delegate_run`, `tui_runner.py`, `tui_rpc.py:launch_gateway/start_session`**: consumidores a verificar; no obligar a modificarlos si `request.workdir` efectivo basta. No usar flag worktree del CLI ni pasar cwd a un RPC resume que no lo admite.

### Hechos mínimos de workspace y recuperación

Un único bloque opcional en los artefactos existentes registra fuente raíz, referencia solicitada, SHA inicial observada cuando esté disponible, rama inicial, destino y estado de preparación. No duplicar fuente/repo ni destino/cwd cuando expresen el mismo hecho. `request.workdir` conserva su contrato de cwd efectivo y sólo pasa al destino tras verificar la creación. `planned`, `created` y `unknown` distinguen intención de preparación observada; no forman otro registro ni se mezclan con los estados de ejecución, tarea, contrato, notificación o transporte.

Preflight devuelve hechos inspeccionados y patrón de destino, sin inventar task_id/cwd creado ni reservar capacidad. El lanzamiento revalida hechos mutables. Tras dedupe: task_id → persistir intención → resolver base exacta → `git worktree add` → verificar ruta/rama/base → persistir cwd efectivo → arrancar hijo. Si la creación falla o persistir después falla, conservar recursos y handle, inspeccionar efecto real y no arrancar en una carpeta alternativa. Error/estado no pueden afirmar «no creado» por un exit code solo.

### Continuidad: cerrar una desviación concreta, no rehacer resume

La fuente instalada confirma que CLI restaura cwd de metadata nativa y TUI resume restaura la sesión; el cwd del proceso lanzador no basta. `core.resume_native_approval/_resume_record_matches` ya asocia perfil/sesión a artefactos, pero el matching no equivale a autorización de origen.

Para sesiones creadas con worktree: recuperar una asociación no contradictoria y autorizada usando artefactos existentes. Si el caller omite `workdir`, usar el cwd efectivo registrado; si lo incluye, exigir el mismo. Revalidar política, existencia y asociación al mismo repo/worktree. La rama y SHA registradas describen la creación: no exigir que HEAD siga en el commit inicial ni que conserve el nombre original de rama; renombrarla o dejar HEAD detached no cambia por sí mismo el checkout. Antes de cada continuación nativa, incluidos los reintentos internos, leer en modo read-only el cwd de la sesión efectiva y exigir coincidencia; conservar `request.workdir` por sí solo no la demuestra. Si no se puede verificar, bloquear con recuperación manual; nunca regenerar. Reusar `SessionDB(..., read_only=True)` y APIs públicas nativas, patrón ya presente en `native.py:steer_snapshot`, sin escribir DB ni cambiar Hermes core.

La instalación inspeccionada expone `SessionDB.resolve_resume_session_id` y `get_session`, utilizados por CLI y TUI para resolver la sesión efectiva y leer su metadata. Verificar ese uso con `SessionDB(..., read_only=True)` en el runtime soportado; no reproducir linaje ni cargar conversaciones para consultar cwd. No crear un router de linaje o registro alternativo. Los reintentos internos usan el request efectivo existente sin asignar de nuevo y aplican la misma comprobación previa a continuar. Si esa continuidad no cabe en un ajuste acotado, detener y reconsiderar el contrato antes de ampliar alcance.

## Ejecución autorizada: tres pasos, un candidato

`[1] Contrato e inspección → [2] Preparación y continuidad → [3] Composición y aceptación`

Un Builder posee el candidato completo; no paralelizar ediciones del core ni hacer tres entregas incompletas. Reviewer revisa el candidato coherente; Adán conserva integración, autoridad y comunicación.

### 1. Contrato e inspección

**Depende de:** aceptación del plan y autorización de implementación. Inspeccionar snapshot entrante y prerrequisitos de calidad ya exigidos antes de editar producción.

**Escritura:** `__init__.py`, admisión de `core.py`, nuevo `worktrees.py`; tests focales nuevos/existentes.

**Produce:** argumentos compatibles e inspección sin efectos.

**Evidencia:** control positivo con repo local; ruta genérica funciona sin Git instalado; preflight singular/batch no crea run/rama/directorio; rechazos de tipos/opciones huérfanas, bare/subcarpeta/raíces no permitidas, base y rama inválidas. Probar escapes de ruta/symlink sin inventar matriz redundante.

### 2. Preparación y continuidad

**Depende de 1. Escritura:** preparación/retornos/resume en `core.py`, helpers de `worktrees.py` y sólo las superficies nativas/transportes del plugin que la evidencia exija.

**Produce:** workspace verificable y recuperable antes del hijo, continuidad sin reasignación.

**Evidencia:** repos temporales Git reales para SHA/rama/ruta, exclusión dirty y fuente intacta; dedupe no asigna segunda vez aunque rama exista; colisiones nunca fuerzan; fallo tras Git o persistencia/arranque deja handle y estado honesto. Resume/reintento conserva cwd sin create; discrepancia/ausencia/otra asociación bloquea, commits nuevos y cambios legítimos de rama no. El preflight de batch no rechaza una reutilización válida por la rama ya creada. Autorización de origen y frozen approvals preservadas.

### 3. Composición, documentación y aceptación

**Depende de 2. Escritura:** `batch.py`, tests focales, receta en `README.md`; actualizar `STATE.md`, `CHANGELOG.md`, `.hermes/handoff.md` con resultados reales. `.agents/validation.md` sólo para incluir módulos nuevos en compilación/comandos aplicables; sin bajar gates.

**Produce:** un único candidato revisable y utilizable con singular/batch y fallback manual/sin Git.

**Evidencia:** mismo perfil+SHA en dos worktrees distintos, metadata por item, partial dispatch conserva handles/hermanos y no lanza siguientes; preflight sin reserva. Verificar proyecciones launch/reuse/status/final y errores, no sólo request.json. Gates vigentes y aceptación real descrita abajo. No activar ni publicar por inferencia.

## Verificación proporcional

**Tests:** `test_worktrees.py` para Git local real sin proveedor; ampliar sólo casos necesarios en `test_preflight_contract.py`, `test_multidelegate.py`, `test_native_resume_admission.py` y `test_tui_rpc.py`. Reutilizar fixtures y clasificar portable/native según `conftest.py`. Testear fallos distintos, no número de tests ni texto de implementación.

**Comandos:** la única autoridad es `.agents/validation.md`, inspeccionada en esta planificación. Incluye lock/frozen setup, política/baseline calidad `e46c84910ea00e0f4b8795cd2bfcc35378ce1cee`, portable/native con prerrequisito, Ruff, compilación, `git diff --check`, secrets/alineación y `scripts/validate_release.py` para registro/handler. No copiar aquí un segundo bloque de comandos que pueda divergir. Añadir módulos nuevos al listado explícito de compilación. Usar checks focales durante trabajo y los gates obligatorios una vez sobre el candidato final, no suites completas por paso.

**Aceptación real posterior:** en repo desechable y mediante entrada pública del plugin, observar cwd/archivo de un hijo CLI y uno TUI nuevos y su continuación viendo el mismo archivo en el mismo workspace. Para coordinación, dos cambios pequeños independientes desde SHA común y un único integrador comprueban comportamiento combinado. No usar mocks ni resumen `ok` como prueba de estas fronteras. La aprobación de implementar no autoriza tocar código/core/config ajenos, restart de gateway, push o deploy. Fresh discovery en proceso aislado prueba registro; carga del gateway vivo sigue pendiente hasta activación autorizada.

**Recuperación:** sin reset del candidato dirty. Revertir sólo los cambios propios identificados si hace falta, conservando trabajo ajeno. Volver a llamadas genéricas con workdirs preparados es fallback funcional; retirar código no borra worktrees. Ante respuesta perdida, list/status antes de repetir. No hay promesa de exactly-once.

## Esfuerzo, incertidumbre y deuda previa

Estimación provisional de Builder: **1–2 jornadas de trabajo concentrado** para integración/regresiones/docs. Builder contempla **media a una jornada adicional** de revisión/correcciones sólo si hace falta; no es una fase obligatoria ni un plazo fijo. Reviewer considera plausible el rango bajo los supuestos declarados, pero se abstiene de inventar una estimación independiente sin mediciones. La creación Git es pequeña; el trabajo sustancial está en continuidad, fallos parciales y proyecciones públicas. Los recortes eliminan trabajo innecesario, sin justificar un ahorro numérico. No incluye esperas de suites/proveedores, deuda heredada ni activación. Es juicio, no medición ni compromiso de calendario.

Supuestos: Git normal, fixtures existentes, APIs read-only de sesión utilizables, sin dependencia nueva. El principal riesgo restante es ejercer el uso read-only del resolver nativo y confirmar el cwd efectivo en resume; la API existente ya está identificada. Resolverlo primero con una comprobación acotada cuando se autorice implementar, no construir una capa genérica. Autoridad/proveedor/RAM condicionan smokes posteriores.

**Heredado, no reevaluado como gate aquí:** STATE cabecera registra multidelegate local no activado, aceptación real de solapamiento/notificación/control pendiente, errores vendor Ruff, discrepancia de gate de Python y quality FAIL sobre candidato entrante. No inventar que están resueltos ni arrastrar su reparación al alcance. Si siguen bloqueando el gate global, reportar worktree comprobado por separado y release/activación bloqueados; no declarar release completo ni debilitar validación.

## Trazabilidad de esta planificación

- Builder: `pd_20261018_110350_62bj5o`, sesión `20261018_110405_339b0e`; plan original y hallazgos en `/opt/data/profile_delegate/runs/pd_20261018_110350_62bj5o/result.json`.
- Adán confirmó en fuente admisión/dedupe/request en `core.py:2695–2919`, matching/resume/policy en `1268–1385`, filtros de batch, patrón read-only de `native.py:111–123` y restauración de cwd CLI/TUI. No ejecutó Git-worktree ni tests del cambio.
- Reviewer: `pd_20261018_111015_vm8j89`, sesión `20261018_111028_87aa3b`; resultado en `/opt/data/profile_delegate/runs/pd_20261018_111015_vm8j89/result.json`. Veredicto estático `PASS_WITH_NOTES`, sin hallazgos materiales ni rediseño requerido. Se incorporaron sus seis precisiones: dedupe/preflight, metadata mínima, rama no inmutable en resume, API nativa existente, autoridad de preparación del padre y proyección completa en batch.
- Adán contrastó las APIs citadas en `hermes_state_messages.py:1559–1598` y `hermes_state_sessions.py:826–834`, y el contrato de validación. La revisión del plan no demuestra funcionamiento, gates pasados ni activación. No se ejecutaron pruebas ni se modificaron código/configuración; el único entregable de esta consolidación es este plan.
