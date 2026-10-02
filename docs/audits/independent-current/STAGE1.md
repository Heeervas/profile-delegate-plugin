# Etapa 1 independiente — baseline terminado y diagnóstico para Reviewer

## Conclusión / límite de etapa

**READY_FOR_REVIEW del diagnóstico, no aceptación del producto ni implementación de findings.** Baseline entrante revisado y conservado en cuatro commits locales de rutas explícitas. Auditoría transversal terminada: API, configuración/admisión, permisos, launch/bootstrap, CLI/TUI, sesión/resume, publicación/control, notificación, artifacts/spectator, scripts, documentación y pruebas. No hay base para una reescritura amplia ni una cuota de reducción de tests. Hay defectos pequeños reproducibles y contratos desalineados que justifican paquetes posteriores, sujetos al Reviewer del padre.

Checkout `/opt/data/plugins/profile-delegate`; punto inicial `17fdf80612895c0a2cf5474b282b0cdbac8fe64e`. Fuente de alcance `/opt/data/cache/documents/doc_c29e932e4de7_prompt-auditoria-independiente.txt`; delegación actual autoriza los commits locales y limita esta etapa a baseline + diagnóstico. No refactors/correcciones, delegación, core/perfiles/config productiva/credenciales/restart/activación/publicación/push. Los mensajes históricos de documentos entrantes se preservan como datos, **no se adoptan como validación**.

## Baseline / evidencia propia

Gates ejecutados en esta misma etapa antes de los commits, sin cambios posteriores de código:

| Check | Resultado y frontera |
|---|---|
| `uv lock --check && uv sync --frozen` | exit 0 |
| `PYTHONPATH=/opt/hermes uv run --frozen python -m pytest -q -o 'addopts=' -W error` | **651 passed in 99.34s**, exit 0; no matriz end-to-end |
| `uv run --frozen ruff check .` | All checks passed |
| `uv run --frozen python -m py_compile` lista canónica `.agents/validation.md:25-30` | exit 0 |
| `uv run --frozen python scripts/validate_release.py` | success true; 1.10.0, seis tools, CLI, validation_error_ok; FakeContext, no discovery real |
| `git diff --check`; `git diff --cached --check` | exit 0 antes y después de baseline |
| Scan explícito tracked/intended-new | cero coincidencias private-key/provider-token/AWS-key; sin valores impresos |

Scan: `/opt/data/profiles/builder/cache/scratch/independent-current/scan.py`, ejecutado `uv run --frozen python <ruta>`. Alcance `git ls-files` + `test_runtime_fixture_commands.py` + este documento; `.artifacts` fuera. No es garantía de ausencia de secretos arbitrarios/alta entropía. Diff entrante revisado; no se trackean `.venv`, caches, credenciales ni artifacts privados. No se repiten gates verdes porque solo se organiza el mismo contenido y se redacta este informe.

### Integración nueva del padre: verificación exacta, limitada

Leídos `receipt.json` y `matrix.json` en `.artifacts/task-approval-runtime-e7w8bka6/`. Receipt `status=ok`, `phase=probe`, `case_count=1`, `matrix_complete=false`; matrix `complete=false`. Caso `probe-cli-deny-fresh`, run `pd_20261002_054731_xszmgs`, verdict pass, expected/observed effect false. Tool REAL terminal: exit_code -1, status blocked, razón script execution via -e/-c, approval event policy_denied. Es integración instalada del handler/launch/bootstrap/guards/tools con **modelo HTTP determinista simulado**, no proveedor real ni matriz completa ni TUI discovery verificado en esta ejecución. No se utilizó ninguna matriz de otra sesión para validar.

Intento anterior de este hijo: harness exit 2 por frozen delegated authority; log `/opt/data/profiles/builder/cache/scratch/independent-current/installed-probe.log`. Ya no es bloqueo del baseline; queda como provenance. No se eliminó ninguna variable/guarda y no se volvió a ejecutar harness desde el hijo. El padre puede aportar pruebas adicionales decisivas listadas abajo, sin detener inspección independiente.

## Entrantes, ownership y commits

Se revisó HEAD→working tree, además de staged/unstaged en el arranque. Mixto entrante incluía STATE/handoff/native_resolution/pyproject/harness/tests/docs; intended-new `test_runtime_fixture_commands.py`. Se conservó el contenido final de ambos lados del índice: sin reset/stash/clean/stage masivo. Solo `git add -- test_runtime_fixture_commands.py` para admitir el archivo nuevo; todos los commits de baseline mediante `git commit --only` con las rutas siguientes. Identidad local autorizada eve-ai-dev / eve.ai.ahh@gmail.com. Un único escritor de esta etapa; inspección de procesos muestra runtime Hermes/gateway y worker de esta delegación, no permite garantizar ausencia de escritores latentes. No se activó código cargado ni se confundió proceso vivo con editor concurrente.

1. **`98e8b10091096acb263a9d5ea4264b87f714d2ed`** — baseline coherente imports + autoridad frozen + fixtures dependientes: `__init__.py`, `child_launch.py`, `core.py`, `native_approval.py`, `native_resolution.py`, `child_bootstrap.py`, `conftest.py`, `test_package_loading.py`, `test_preflight_contract.py`, `test_reliability_20260927.py`, `test_task_approval_selection.py`, `test_native_approval.py`, `test_native_resume_admission.py`, `test_compression_continuity.py`, `test_profile_delegate.py`.
2. **`dd15f7eb66abc7b051e850e96edf400ddd40c300`** — contrato TUI resume y regresión instalada: `tui_rpc.py`, `test_tui_rpc.py`.
3. **`c7bd9b2c1f9c69ed1dbb42cd1dca6b1c153e3a41`** — preparación harness/fixture y dependencias: `scripts/accept_task_approval_runtime.py`, `test_runtime_fixture_commands.py`, `pyproject.toml`, `uv.lock`. El defecto de aserción se conserva para diagnosis, no se corrige aquí.
4. **`856b7b81588ebf6cec79d5f4471ae2f99ef88aec`** — documentación entrante sin reinterpretar sus receipts: `README.md`, `STATE.md`, `.hermes/handoff.md`, `docs/plans/2026-10-01-native-approval-modes/{ACCEPTANCE,DRIFT,OPERATOR,PER_TASK_REPAIR,REVIEWS,RUNTIME_HARNESS,STATE}.md`.

Estos commits fijan un baseline **con findings**, no afirman aprobación de cada contrato/documento. Ningún archivo runtime ajeno se incluyó. El informe propio va en commit separado para no confundirlo con los entrantes; SHA de ese commit se entrega fuera de sí mismo.

## Mapa módulos → contratos → consumidores reales

| Superficie | Propietario / flujo / consumidor |
|---|---|
| Manifest/registro/import | `plugin.yaml`, `__init__.py:register`; seis tools OpenAI `parameters`, CLI; consumidor Hermes `hermes_cli/plugins.py:discover_plugins`; `scripts/validate_release.py` es consumidor falso separado |
| Wrapper/origin | `__init__.py:_handler/_current_origin` obtiene contexto Hermes concurrency-safe, no acepta origin del modelo; handlers devuelven JSON-safe errores; core `authorize_run` exige origin/home y prueba nativa direccional de compresión |
| Config/preflight/admisión | `core.py:737-1494,3097-3336`; YAML/env/default + caller grant; profile/depth/workdir/overrides; resolución solicitada distinta de observada; dedupe con fingerprint y locks, no mantenimiento de runs ajenos |
| Aprobación | `native_approval.py` fuentes/envelope v2, fingerprint no firma ni sandbox; `native_resolution.py` config readonly/frozen resume; `core.resolve_request_approval`; consumidor instalado `tools.approval` / floors/detection |
| Launch/bootstrap | `child_launch.py` argv @file/resume/overrides; `child_bootstrap.py` instala binding y aliases antes del agente; `hermes_cli.main` o `tui_gateway.entry`; capability filter modifica schemas, no aislamiento OS |
| CLI ejecución | `core.run_capped_subprocess/_execute_delegate_run`; deadlines, actividad/interrupción, grupo propio, stdout caps, footer observado, recuperación limitada; `cli_smoke.py` consumidor directo de core, no prueba pública completa |
| TUI ejecución | `tui_rpc.py` JSON-RPC newline/correlación; `tui_runner.py` readiness/session/prompt/controls/follow-up/teardown; consumidores installed contracts sessions y gateway methods/session lifecycle |
| Persistencia | request/status artifact v3, result v1; `publish_terminal_run`, `_locked_run_status`, `_validated_terminal_result`; result-first + status no crash-atomic, reparación operator explícita; status/task/contract independientes |
| Control | private commands/acks secuenciados + control/status locks; TUI steer queued≠delivered, interrupt/cancel limpieza; CLI grupo identity verificado; handlers status/list/control autorizados |
| Notificación | core `_register_durable_notification/_persist_profile_delegate_completion/_push_profile_delegate_completion`; consumidor `/opt/hermes/tools/async_delegation.py` y process_registry; ledger nativo, no outbox propio; native replay puede dropped |
| Eventos/spectator/operador | `event_schema.py`, `event_journal.py` derived allowlist/text opt-in/limites/locks; `spectator.py` sanitize + bounded reader; `cli.py` watch/inspect/operator-status/list/reconcile; root explícito UID/private para operador |
| Scripts/CI/docs | harness opt-in instalado con proveedor fixture, validate_release fake, `.github/workflows/ci.yml`, lock; README/BRIEF/AGENTS/.agents contratos actuales. Planes entrantes leídos para conservar diff, no autoridad del diagnóstico |

Tests mapeados por riesgos y búsquedas de consumidores, no por cuota: `test_profile_delegate` parser/policy/admission/locks/prune/overrides; reliability_reset/prose_verdict/read_completion_safety resultado honesto; publication_seam/operator_repair_races/run_reconciliation transacciones/races; sync_lifecycle procesos/interrupción; tui_rpc/transport_d evento/protocolo/controls; event_journal/spectator privacidad/reader; compression_continuity identidad/admisión; native_approval/native_selection/native_resume_admission/native_history_evidence/task_approval_selection permisos; preflight_contract errores sin run; package_loading namespace; native_detached_fixture/recursion_integration/private harness fronteras diferentes. Mocks de client/launch prueban lógica, **no equivalen a runtime**. Sleeps de pruebas de procesos/follow-up tienen un riesgo temporal distinto; no borrar como duplicados sin reemplazo sensible.

## Hallazgos priorizados (mínimos, no corregidos)

### F1 — Alta: deadline/frame bound TUI no efectivo con línea parcial

`tui_rpc.py:40-49,127-135`: select espera primer byte; después `stream.readline()` bloqueante sin deadline ni límite previo. Reproducción propia `/opt/data/profiles/builder/cache/scratch/independent-current/diagnostic_probes.py`: pipe real emite `{`, espera 1s, lector timeout .05 tarda **1.017s**, exit 0. La longitud se valida solo tras materializar toda línea. Un gateway atascado en frame parcial puede impedir timeout/cancel del owner, y frame enorme puede consumir memoria antes de rechazarlo. No se demuestra exploit externo ni crash productivo.

Propuesta mínima: lector incremental bounded con deadline único y buffer entre frames; conservar single-owner y correlación estricta, sin framework nuevo. Beneficio alto; esfuerzo medio; riesgo medio en lectura interleaved. Aceptación: partial frame sin newline vence cerca de presupuesto, oversized sin newline falla antes de materializar ilimitado, múltiples frames en un read no se pierden, stderr flooding/EOF/cancel siguen limpiando. No usar newline mock como única evidencia.

### F2 — Media: spectator rechaza fases producidas por CLI real

`core.py:1604,1678,3769` publica `child_running`, `child_stopped`, `cancellation_requested`; `spectator.py:38-43,288-294` no las acepta. Probe propio llama validator con status legítimo y cada fase: **corrupt status.json: unknown phase**. Watch/inspect anunciado también para legacy/CLI puede salir 4 durante ejecución o cancelación normal.

Propuesta: vocabulario compartido de fases o admitir exactamente las fases emitidas; no relajar validator a cualquier string. Beneficio medio, esfuerzo pequeño, riesgo bajo. Aceptación: fixture publicado por run_capped_subprocess inspeccionable durante proceso/cleanup/cancel, fase desconocida todavía falla. `core.py` seguirá dueño lifecycle; no hacer al spectator escritor.

### F3 — Media: recuperación automática impone JSON a contrato prose

`core.py:2349-2357,2788-2790` genera siempre “return ... final JSON result”; el request original conserva markdown/text + require_terminal_verdict (`3256-3257`, normalización `2872-2879`). Probe propio confirma prompt JSON incondicional. En recovery CLI una sesión solicitada Markdown recibe instrucciones contradictorias y puede terminar unknown aunque el trabajo termine. Es defecto observable del prompt; no se afirma tasa real de fallo proveedor.

Propuesta: recovery prompt usa resolved_output_mode/verdict del request sin repetir task ni cambiar sesión/autoridad; mantener retry allowlist/deadline. Beneficio medio, esfuerzo pequeño, riesgo bajo. Aceptación: transitorio con footer probado → recovery Markdown/text no solicita JSON y conserva marker; JSON sin regresión, incompatible provider no retry. Padre solo necesita runtime adicional si el Reviewer requiere comportamiento end-to-end, no para confirmar contradicción literal.

### F4 — Media: contratos públicos se contradicen con acceso y entrega

- `__init__.py:246-250` enum/model description invita current_lane/all, pero `core.py:3801-3803` los rechaza salvo operador.
- `README.md:338-342,360-363` afirma provenance no access control/global lookup y widening model; core `authorize_run` y tests explícitos lo contradicen.
- `README.md:387-398` anuncia prune tool, pero register no lo incluye, handler operator_only y `cli.py` tampoco expone prune. Core `_operator_prune` solo tiene consumidores test encontrados en checkout.
- `README.md:252` promete no descarte tras restart; BRIEF:37 lo excluye; consumidor nativo `/opt/hermes/tools/async_delegation.py:314-347,372-400` permite dropped por edad/budget. Persistencia consultable no equivale entrega garantizada.
- `README.md:268-270` describe verdicts antiguos como contrato prose nuevo; prompts requieren marker exacto.

Propuesta: alinear documentación/schema con autoridad vigente y separar historial; si se pretende restaurar widening/prune o garantía es decisión de contrato, NO cosmética ni eliminación unilateral. Beneficio alto para uso correcto, esfuerzo pequeño/medio, riesgo bajo documental y alto si cambia authority. Aceptación: public schemas/examples probados vía handler; operador sigue separado; ninguna promesa exactamente-once/restart. Preservar helper prune/tests hasta revisar consumidores externos, no inferir obsolescencia de solo búsqueda local.

### F5 — Media: CI no provisiona frontera instalada que nuevos tests requieren

`.github/workflows/ci.yml:18-47` instala solo deps plugin y ejecuta todos tests en ubuntu, sin checkout/install Hermes ni `/opt/hermes`. `test_runtime_fixture_commands.py:5-6` importa tools instalado en collection; `test_native_approval.py:136`, `test_tui_rpc.py:322` invocan `/opt/hermes/.venv/bin/python`. El gate local con PYTHONPATH/runtime presente no prueba portabilidad CI. Defecto de prerequisitos estático confirmado; **no se ejecutó GitHub CI**.

Propuesta: split explícito portable unit vs installed integration con provisión Hermes reproducible/versionada para esta última. No skip silencioso general para fabricar verde. Beneficio alto release, esfuerzo medio, riesgo medio dependency. Aceptación: checkout limpio CI sin /opt/hermes pasa portable gate y un job provisionado ejercita integración; missing prereq se declara, no convierte integración en PASS. Scan CI también recorre `.venv` y artifacts por os.walk: revisar alcance tracked/intended-new sin debilitar detección.

### F6 — Baja/media: aserción del detector insensible

`test_runtime_fixture_commands.py:20` comprueba tupla completa. Probe detector REAL: `pwd` → dangerous false pero tuple truthy true; comando fixture actual dangerous true. El test permite detector falso. Propuesta: comprobar primer booleano y perturbación benigna. Beneficio de sensibilidad alto, esfuerzo trivial, riesgo bajo. Conservar matching exact grant/no-compound/effect absent; no afirmar defecto de guard productivo.

## Conservaciones y oportunidades acotadas

Conservar wrapper_success y ejes independientes; terminal result-first/lock/repair explícita; read-only status/list/capacity; frozen envelope/resume no recompute y v1-deny refusal con error actionable; deny permanent grants/floors y caller grant separados; target admission/depth/same-home; capability review schema filter sin promesa sandbox; startup discovery serial y no import run_agent en register; RPC late-response id strict; steer ACK unknown/no silence proof; cancel grupo propio/reap; private artifacts y text opt-in. Tests de adversarios y carreras no son duplicados por compartir fixtures.

Simplificaciones candidatas, **no eliminación aprobada**: wrappers core→native_resolution son seams de import/monkeypatch y tienen consumidores; mantener salvo beneficio probado. `env_bool`, `capped_text`, `_prune_schema`, `_reconcile_schema` no tuvieron consumidores de producción en búsqueda local; `load_yaml_mapping` y wait_for_completion tienen consumidores test. Reviewer puede retirar solo helpers realmente internos sin usuarios externos; beneficio bajo, no justifica reordenar etapa. Estado/request/policy duplicados preservan snapshots y observación; no deduplicar automáticamente. Comentarios narrativos de incidentes en tui_rpc/tui_runner/docs pueden convertirse a invariantes, sin borrar justificación de seguridad. EventJournal `_recover_locked` relee/parsea journal completo por append; es oportunidad de medida, **no performance finding ni optimización propuesta sin benchmark**.

## Riesgos / pruebas decisivas / residual

1. Padre: matriz **nueva** cuatro modos en CLI/TUI, grant caller/target disjunto, floors, nesting, alias/omission/unauthorized y resume frozen. Reutilizar probe nuevo; otras sesiones no validan esta auditoría. No es condición para terminar este diagnóstico estático, sí para aceptación de cambio permisos.
2. Runtime adicional mínimo tras correcciones: CLI transient prose recovery; TUI partial frame/oversize real pipe; stored-workspace resume contrastando cwd (request workdir admitido y restored cwd son conceptos distintos); notification failure/ledger dropped sin afirmar entrega humana.
3. Coverage restante: proveedor real, restart delivery, named profiles parity/UI rendering, correlated steer receipt no validados; no activar/reiniciar para probarlos sin autoridad.
4. Privacidad: scan patrones no excluye cualquier secreto arbitrario; request/result crudos son privados, journal sanitizado no scrubber universal. Process/PID liveness advisory no seguridad OS. Lecturas modelo tail_text materializan archivo completo antes de tail, mientras operador es bounded fd; endurecimiento requiere revisar amenaza y seam, no afirmar exploit cross-origin no probado.
5. Stage completo NO cierra el objetivo global de implementación/deslop/review final: padre hace Reviewer diagnóstico y decide paquetes F1–F6. No reviewer independiente aún, no métricas de aceptación inventadas.

Residual tras cuatro baseline commits: `?? .artifacts/` y documento propio aún untracked antes del commit informe. Ningún staged/unstaged de producción residual. `.artifacts/` ajeno intacto/no track; sin cambios TODO/CHANGELOG porque no se implementó ni publicó mejora de producto ni cambió prioridades del backlog. Este registro es handoff actual; no se reescribieron receipts históricos entrantes para convertirlos en evidencia propia.
