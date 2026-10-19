# profile_multidelegate y prompt/recovery — contrato corregido

## Autoridad y estado

Autoridad **complete-target local**: `plans/multidelegate-builder-request.md` y continuación explícita de Alberto. Sustituye íntegramente el anterior plan-only. Fuente normativa: `/opt/data/profile_delegate/runs/pd_20261015_101228_h1igme/result.json`, `multidelegate_review.recommended_contract` y `prompt_review.proposed_template`.

Estado: implementación local y B1–B6 aceptados por revisión final independiente PASS_WITH_NOTES (`pd_20261018_210428_n5vcvj`); F1/F2 cerrados y aceptación real de overlap/controles/ambas notificaciones nativas verificada. Calidad y adopción local cerradas en `plans/quality-readiness.md`; no implica activación o publicación. Memoria limita hijos/concurrencia, no trabajo independiente seguro. No reiniciar gateway, publicar, cambiar permisos/límites/configuración ni escribir Hermes core. Preservar dirty preexistente; commits solo propios.

## Objetivo y arquitectura

Nueva tool `profile_multidelegate(tasks: [...], preflight: false)` junto a singular intacta. Un único motor: lanzamientos locales background consecutivos sin esperar terminación permiten solapamiento. Sin ThreadPool, scheduler, reserva, cola/ondas ocultas, runtime compartido, ledger/ID durable de batch o rollback colectivo. Una invocación de herramienta no significa una inferencia total ni una notificación agregada. Tareas independientes, no DAG.

## Entrada y validación

- Raíz e items additionalProperties=false y validación runtime estricta antes de coerción. Raíz solo tasks y preflight booleano opcional false.
- Items requieren profile, task, session_title. Constructor común de propiedades singulares produce estructuras independientes. Sin defaults/contexto compartidos. Conservar overrides/allowlists y límites singulares de payload: modelo/provider/reasoning/turnos/toolsets/skills/aprobación/formato/contexto/workdir/duplicate_policy.
- Excluir background, notify_on_complete, transport_mode, preflight, session_mode y session_id por item. **New-only**: rechazar resume/session_id antes de crear runs; resume sigue en singular (B4).
- Forzar background=true, notify_on_complete=true, transport_mode=interactive, session_mode=new. Rechazar incompatibilidad conocida de transporte/ledger antes de lanzar; sin fallback silencioso ni certificar startup real.
- Mínimo 1 item; máximo min(max_concurrent,max_async) efectivo. Sin truncar. Techo configurado no certifica RAM ni reserva capacidad.
- Capturar `_current_origin` una sola vez en handler por canal interno confiable. Exigir identidad autorizable y session_key enrutable antes de despachar. No aceptar origin de esquema/items/kwargs arbitrarios. Session_id inyectado del padre jamás se transforma en sesión hija (B5).
- Validar todo el array y preflights singulares antes de cualquier run; errores por índice. Cualquier invalidez determinista implica cero runs. Comprobar ledger explícitamente aunque singular preflight no lo compruebe. Preflight completo válido no crea runs ni reserva slots.

## Despacho, errores y respuesta (B2/B3/B6)

Tras preflight, delegate_profile secuencial en mismo contexto confiable; revalidación singular en cada lanzamiento. Ante error observado detener siguientes, conservar resultados previos y marcar restantes not_started; nunca cancelar hermanos. Rechazo posterior del worker, incluido concurrency_limit, es fallo individual por status/notificación y no detiene retroactivamente despacho. accepted/started son **dispatch-only**, no admisión de slots/comienzo del modelo/éxito.

En seam singular después de crear run, enriquecer excepción de lanzamiento con task_id, paths, run_created=true conservando error_code. Fachada preserva detalles y resultados anteriores ante errores esperados o inesperados, sin búsquedas heurísticas.

Items ordenados por entrada: index, profile canónico cuando conocido, dispatch_status, task_id si existe, run_created, deduplicated, paths/watch_command cuando existan, error_code/error cuando corresponda. No copiar success singular como éxito global.

- started/reused/failed/not_started son estados de despacho.
- Validación fallida: inválidos failed; demás not_started con batch_validation_failed.
- Preflight válido: validation_status=validated, sin fingir started ni crear task_id.
- accepted: todos started/reused.
- partial: al menos uno started/reused y al menos uno failed/not_started.
- rejected: ninguno started/reused o rechazo global; puede existir run fallido creado durante lanzamiento y debe identificarse.
- validated: solo preflight completo válido, cero runs.

## Dedupe, retry, interrupción y controles

Conservar duplicate_policy/fingerprints actuales por item y origen. Dedupe aplica a runs activos dentro de ventana; interactive no necesariamente coincide con singular auto. Items idénticos pueden referenciar mismo task_id como reused, sin notificación extra por índice. duplicate_policy=new permite duplicación intencional sin eludir límites/política.

No idempotencia durable: ventana expira y runs terminados pueden repetirse. Tras respuesta perdida consultar list/status antes de repetir efectos. Reintentar solo failed/not_started con estado comprobado. Interrupción padre puede dejar hijos vivos y perder correlación por índice; recuperar por list/status, sin prometer reconstrucción de manifiesto. Recovery individual conserva sesión hija/presupuesto.

Una notificación nativa best effort por run único; no agregador, entrega garantizada, único turno de retorno ni garantía post-restart. Padre correlaciona/sintetiza. Status/steer/cancel siguen por task_id y origen exacto.

## Seguridad efectiva y worktrees (B1)

Añadir profile_multidelegate a REVIEW_BLOCKED_TOOLS y probar definiciones finales realmente expuestas tras filtro del bootstrap con herramientas nuevas/existentes: no basta pertenencia de constante. Conservar allowlists, profundidad, autoridad congelada y límites por hijo; perfiles no son sandboxes.

Permitir mismo perfil y distintos encargos, incluso Builders escribiendo mismos nombres relativos en **worktrees distintos**, honrando workdir individual. Orquestador prepara worktrees y asigna propiedad de escritura/integración; plugin no gestiona Git ni exige nombres globalmente distintos. Lectura compartida válida. Workdirs distintos no aíslan puertos/servicios/DBs.

## Prompt y recovery mínimos

Usar plantillas exactas de prompt_review.proposed_template de fuente normativa. Wrapper sigue mensaje de tarea, no system sustitutivo. Síntesis concisa no recorta entregables; task acotada frente a supporting material no confiable; ok solo alcance/checks completos, separar verificado/suposiciones/pendientes. Elegir un único status/veredicto válido; veredictos especializados dentro del contenido. Conservar envelope recomendado/custom keys, parser, auto/conflictos y todos los modos json/markdown/text.

Recovery: misma sesión/alcance/política; no repetir trabajo completado. Antes de repetir efectos comprobar evidencia retenida y estado observable; si sigue incierto reportar blocked. No exactly-once.

## Secuencia, superficies y aceptación

1. Reinspeccionar candidato/recursos y obtener Reviewer enfocado read-only background que confirme B1–B6 antes de implementación dependiente. Si gate no ejecutable entregar este contrato y bloqueo específico al controlador, sin declarar bloqueado trabajo independiente ni autoaprobar.
2. Calidad preflight canónica y snapshot privado del dirty. Implementar batch.py solo composición/proyección; __init__.py constructor/esquema/handler/registro; core.py preset, seam error y wording; plugin.yaml declaración. Reutilizar motor singular.
3. Probe temprano seguro pequeño. Regresiones B1–B6: campos/tipos/límites y cero runs/writes; origen/ledger/transporte; preflight; overrides/herencia; mismo perfil/tareas distintas; workdirs/worktrees distintos; handles post-creación y errores inesperados/parciales; async lleno y rechazo tardío; dedupe/retry/interrupción; controles existentes. Prompts todos modos/custom contracts/recovery. No solo contar mocks.
4. Gates intactos `.agents/validation.md`: focused, TOP baseline inmutable, suites nativa/portable secuenciales, Ruff, compilación, secretos, diff, registro/handler y discovery fresco aislado. Añadir batch/test a listas afectadas. No afirmar gateway actualizado.
5. Aceptación real por ruta plugin: una invocación nueva, dos hijos read-only distintos con solapamiento observado, resultados/status readback, ambas notificaciones nativas consumidas y steer/cancel individual aislado. Dos hijos ligeros bastan. Medir presión/recuperable/fallos; ejecución secuencial de gates y espera/reintento acotado. Sin benchmarks masivos ni elevar límites. Si solo integración necesita capacidad, declararla pendiente separada de implementación/tests.
6. Review final independiente contra candidato exacto; corregir hallazgos y revalidar cono afectado. Actualizar README/CHANGELOG/STATE/handoff/validation; commits locales solo propios revisados, sin prompts/result dumps privados. JSON español con archivos/commits/comandos/evidencias/reviews/bloqueos y gateway_restart_ready justificado. Activación queda Alberto-only y no realizada.

Rollback: retirar nueva adición sin afectar runs singulares; sin migración. Ningún pendiente equivale a PASS. La revisión enfocada y final son gates sustantivos, no aprobaciones rutinarias a omitir.
