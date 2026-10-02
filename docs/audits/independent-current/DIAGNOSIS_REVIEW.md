# Review independiente del diagnóstico — gate previo a implementación

## VERDICT: PASS_WITH_RESIDUAL_RISK

**Aprobado implementar el alcance mínimo revisado abajo; no aprobado el producto, la activación ni un refactor arquitectónico amplio.** F1–F6 tienen evidencia propia. F5 necesita ampliar el inventario de dependencias; el mapa omite un defecto material de backpressure stderr (R1), que debe incluirse en el paquete TUI. No hay justificación para reducir tests por cuota, sustituir el transporte o modificar autoridad.

Referencia revisada: `docs/audits/independent-current/STAGE1.md`, checkout `/opt/data/plugins/profile-delegate`, HEAD `bebd2335b42934386fbceefc0affe7911db8638c`. Baseline entrante `98e8b10`, `dd15f7e`, `c7bd9b2`, `856b7b8` conservado. Autoridad de esta review: `/opt/data/cache/documents/doc_c29e932e4de7_prompt-auditoria-independiente.txt` y delegación acotada actual. Leídas reglas `AGENTS.md`, `.agents/validation.md`, `.agents/skill-routing.md`, README/BRIEF/STATE/TODO actuales. Las notas históricas de esos documentos no son pruebas de esta tarea ni fundamento de las decisiones.

**Bloqueantes reales para aceptación posterior:** F1/R1 (I/O TUI), F5 (gate CI no ejecutable con sus prerequisitos declarados), y cierre funcional/contractual de F2–F4. F6 debe corregirse en el mismo trabajo por coste trivial y sensibilidad demostrablemente nula. No hay bloqueo que impida iniciar estos paquetes. Review final permanece pendiente.

## Evidencia propia y límites

- Inicio: `git status --short` → solo `?? .artifacts/`; HEAD exacto confirmado. Diff staged/unstaged de código vacío, reconfirmado después de los probes. No código/tests/config/core modificados, no commits, harness de operador, delegación, activación ni eliminación de autoridad.
- Probes ejecutados, exit 0, con scripts fuera del checkout:
  - `/opt/data/profiles/reviewer/cache/scratch/diagnosis_review_probes.py`.
  - `/opt/data/profiles/reviewer/cache/scratch/diagnosis_stderr_probe.py`.
  - `/opt/data/profiles/reviewer/cache/scratch/diagnosis_cli_phase_probe.py`.
  - Comandos: `uv run --frozen python <ruta>`; sus salidas decisivas se transcriben abajo. Son pipes/procesos inocuos y artifacts desechables, no modelo vivo.
- `PYTHONPATH=/opt/hermes uv run --frozen python -m pytest test_reliability_20260927.py::test_strict_origin_rejects_legacy_and_weaker_key_fallback test_native_selection.py test_native_resume_admission.py test_task_approval_selection.py test_runtime_fixture_commands.py -q -o 'addopts=' -W error -p no:cacheprovider` → **43 passed in 1.58s**.
- `PYTHONPATH=/opt/hermes uv run --frozen python -m pytest test_tui_rpc.py -q -o 'addopts=' -W error -p no:cacheprovider --basetemp=/opt/data/profiles/reviewer/cache/scratch/diagnosis-tui-pytest` → **56 passed in 18.29s**. Esto no invalida F1/R1: faltan sus perturbaciones.
- Sin `PYTHONPATH`: collection de `test_runtime_fixture_commands.py` → **exit 2**, `ModuleNotFoundError: tools`, línea 5. Ejecución focal de selección/resume/preview → **15 failed in 0.53s**, imports `hermes_cli`/`agent` ausentes. Es comprobación local de frontera ausente, **no** GitHub Actions ni entorno completamente sin `/opt/hermes`.
- No repetí suite completa: los **651** de STAGE1 son un resultado reportado por Builder, no certificado independiente aquí; faltan logs propios persistidos para esa afirmación.
- `execute_code` fue denegado por política antes de ejecutarse. No cambié guardas. Los scripts inocuos por terminal fueron aceptados por la misma autoridad. No ejecuté el harness de operador.
- Leí y contrasté `.artifacts/task-approval-runtime-e7w8bka6/{receipt,matrix}.json`, el `result.json` y `approval_events.jsonl` del run `pd_20261002_054731_xszmgs`: un caso CLI deny, evento `policy_denied`, terminal real bloqueada exit -1 y resultado fixture recogiendo esa respuesta; `matrix_complete=false`, `complete=false`. No es cuatro modos, TUI, proveedor real ni entrega notificada. `status:ok` del modelo fixture significa que recogió la respuesta, no que la acción bloqueada se ejecutó.

## F1–F6: decisión, evidencia y mínima aceptación

### F1 — ACEPTADO, prioridad P1, ampliado con R1

**Observación:** `tui_rpc.py:40–49` hace select hasta primer byte y después `readline()` bloqueante; `127–135` comprueba longitud cuando ya ha leído todo. `launch_gateway:319–323` usa pipes `bufsize=0`, por lo que esto afecta el cliente productivo, no solo BytesIO de tests.

Probe con pipe real: timeout **0.05 s**, productor emite `{`, newline **0.4 s** después → lectura tarda **0.400234 s** y termina en malformed frame, no timeout. Con **512 bytes sin newline**, cap **64 bytes**, mismo presupuesto → rechazo por tamaño solo tras **0.400220 s**. No probé OOM ni un exploit externo; sí incumplimiento de deadline y límite antes de materialización.

**Cambio mínimo:** buffer owned por `TuiRpcClient` + `select`/`selectors` y `os.read` acotados, deadline monotónico único, conservar fragmentos entre polls y frames concatenados. No reader nuevo por cada timeout, no event loop/framework adicional. `readline(size)` solo limita memoria, no arregla deadline parcial; hilo por llamada puede quedarse leyendo y competir con la siguiente. Para streams sin fd usados por fixtures, adaptador pequeño explícito; no convertirlo en un segundo transporte productivo.

**Aceptación exacta:** pipe sin newline vence dentro de margen documentado pequeño del presupuesto; cap+1 sin newline falla antes de EOF/newline; frames partidos/concatenados y UTF-8 partido se reconstruyen sin perder bytes; timeout con fragmento preserva correlación; EOF parcial falla cerrado; late response integer exacto sigue consumiéndose una sola vez; unknown/duplicate/bool/string ids, hybrids y malformed JSON siguen fallando. Event flood y cancel/close no exceden sus presupuestos; proceso directo reaped y pipes cerrados. Incluir stderr saturation de R1.

### F2 — ACEPTADO, prioridad P2

`core.py:1604,1635,1678,3769` produce `child_running`, `child_stopped`, `cancellation_requested`; `spectator.py:38–43,288–294` las rechaza. Probe validator confirmó las tres; probe **productor real** `run_capped_subprocess(['/bin/true'])` + `inspect_run` durante publicación devolvió `corrupt status.json: unknown phase: exit 4` para `child_running`, pese a exit de proceso 0.

**Mínimo:** admitir exactamente esas fases. La pequeña constante compartida en `event_schema.py` es razonable porque **`event_journal.py:32–37` duplica el mismo vocabulario**, pero no reestructurar lifecycle ni confundir fases de transporte con estados terminales. Otra alternativa válida: añadir las tres al spectator y una prueba producer→consumer que mantenga el contrato; no es obligatorio centralizar por estética.

**Aceptación:** inspección CLI pública de status publicado por proceso real en ejecución, parada y cancelación; unknown phase continúa exit 4; histórico sin journal conserva limited observability; TUI/events siguen validándose y ningún lector escribe artifacts. Incluir cobertura de las fases de journal si se comparte constante.

### F3 — ACEPTADO, prioridad P2

`core.py:2349–2357,2788–2790` ordena JSON siempre. Original `build_prompt:1768–1773` y request `3256–3257` exigen Markdown/text + marker. `normalize_result:2077–2108` ignora envelope JSON en prose. Probe independiente: JSON `status:ok` bajo request Markdown/marker → **`unknown`, `drifted`, `missing_verdict`**. Es contradicción reproducible, no tasa medida de fallo del proveedor.

**Alternativa más pequeña:** sustituir JSON por “preserve the original requested output format and terminal verdict” (sin repetir task). Para aceptación más fuerte, pasar modo resuelto + requirement y emitir instrucción corta Markdown/text/JSON con marker exacto. Ambas evitan recomputar desde texto no confiable o construir otra normalización. No reenviar todo prompt/task ni iniciar una sesión nueva.

**Aceptación:** transitorio reconocido + footer probado, recovery en la misma sesión y envelope frozen idéntico; Markdown/text sin orden JSON, marker `PROFILE_DELEGATE_RESULT: ok|blocked|failed` y resultado normalizado correspondiente; JSON preservado. Mantener no-retry en approval/policy/auth/quota/realm mismatch, timeout/cancel, identidad ausente/malformada, y presupuesto total. Una prueba del string no basta como regresión única: capturar prompt realmente enviado por `_execute_delegate_run` en segundo intento y comprobar parser final. Smoke instalado CLI recovery queda en validación del paquete; padre controla cualquier harness de operador.

### F4 — REVISADO (defectos aceptados; alcance documental, no restaurar APIs), prioridad P2

- Model enum/description `__init__.py:246–250` invita widening que `_read_run_list`, `core.py:3801–3803`, prohíbe. Handler `441–456` pasa esos argumentos realmente. Test independiente exact-origin verde; no hacer que `all` funcione para satisfacer README.
- README `338–342,360–363` contradice `authorize_run:370–403`: origen/home/namespace y continuidad **nativa direccional** comprobada sí son autoridad, no mera provenance.
- README `387–398,421` vende prune inexistente. `register:558–564` registra seis herramientas, ninguna prune; `_prune_handler:459–468` solo devuelve operator_only; `cli.py:91–102` tampoco ofrece prune. `_operator_prune` sigue teniendo pruebas de locks/terminal-only/tombstone/UID (`test_profile_delegate.py:1247–1419`). **Documentar la ausencia de interfaz pública y conservar el helper interno; no añadir una CLI destructiva ni borrar capacidad aquí.** BRIEF:27 debe distinguir superficie disponible de alcance/retención interna.
- README `38,252` promete idempotencia/restart sin pérdida; `/opt/hermes/tools/async_delegation.py:336–350,394–401,472–486` terminalmente marca **dropped** por edad/budget. README:51 y BRIEF:37 ya niegan garantía. Alinear toda la documentación de usuario con persistencia consultable + entrega best effort; no arreglarlo añadiendo outbox.
- README `268–270` describe verdict genérico mientras prompts nuevos exigen marker. Preservar parser histórico conservador para artifacts/requests anteriores y describirlo como compatibilidad, no recomendación nueva.

**Aceptación:** schemas model-facing solo ofrecen scope permitido o identifican inequívocamente refusal de legacy; recomiendo enum `current_session` y conservar rechazo runtime de widening para llamadas antiguas. Seis tools siguen registrados, handler widening sigue `origin_mismatch`, controles same-origin/continuidad positiva siguen funcionando. Ejemplos nuevos de prose terminan en marker y se prueban por handler/parser real. No promesas delivery garantizada ni instrucciones de prune no invocables. Corregir guía Development README:475–480 junto al gate F5, no dejar un comando pip/pytest que ya se demostró incompleto.

### F5 — REVISADO Y AMPLIADO, prioridad P1

Defecto confirmado: `.github/workflows/ci.yml:18–47` instala solo lock plugin. `pyproject.toml:16–22` trae pytest/yaml/ruamel/ruff, **no Hermes ni su closure**. Mi collection sin path fracasa exactamente en `test_runtime_fixture_commands.py:5`.

**La separación no puede basarse en nombres “native” ni en los tres ejemplos de STAGE1.** Consumidores verificados adicionales:

| Archivo/rango | Dependencia efectiva y clasificación |
|---|---|
| `test_native_approval.py:119–140` | 12 parametrizaciones, interpreter `/opt/hermes/.venv/bin/python`, guards reales en fresh child; integración |
| `test_tui_rpc.py:321–332` | contracts Pydantic installed en subprocess; integración, resto de RPC con doubles/pipes no equivale a esta frontera |
| `test_profile_delegate.py:537–610,747–779` | tres guard/schema subprocess (con skipif actual) + `agent.display` directo; integración; command argv:518–534 por sí mismo no necesita Hermes |
| `test_compression_continuity.py:510–614` | SessionDB/publicación nativa y ledger real con proceso/modelo sintéticos; integración, **no unit portable** |
| `test_native_selection.py:7–22` | profiles + resolución nativa readonly/grants reales aunque parchea profile_exists; integración |
| `test_task_approval_selection.py:10–23,59–70` | fixture importa profiles; preflight/resolución usa config/native guards sin sustituir esa frontera; integración mientras eso sea parte de su prueba |
| `test_native_resume_admission.py:29–54` | importa config solo para spy “must not read”; puede ser unit portable con módulo doble estrecho, sin perder assert; no hay que instalar toda Hermes por ese spy |
| `native_resolution.py:75–97` llamado por tests de delegate/preflight | dependency transitive en config/home/approval; buscar todos callers, no basta barrer imports explícitos |

Prueba focal sin path: selección nativa, propagation de task, 12 resume spies y preview → **15 failures**, no portable por estar instalado pytest. Un fixture local no convierte un acceso real a native config/ledger en unit. `test_native_detached_fixture.py` usa shim explícito: eso tampoco demuestra runtime installed; comprobar qué preflight/notification sigue usando antes de clasificar.

**Solución mantenible menor recomendada:**

1. Conservar matrix plugin **3.11/3.12/3.13**, uv.lock frozen, warnings-as-errors, lint/compile/registration/secret scan. Crear una partición simple `tests/integration/` para casos que prueban APIs reales; mover funciones concretas fuera de módulos mixtos evita imports en collection. Alternativa válida marker estricto + import diferido, pero marker solo no evita errores de collection. Nada de inventario de nodeids a mano ni harness nuevo de auditoría.
2. Unit portable debe funcionar con checkout+lock plugin **sin path/binary Hermes**. Mock estrecho únicamente donde el requisito sea lógica plugin; no sustituir guards/session contracts/ledger que una prueba promete integrar. Probar este gate en runner/container realmente sin Hermes, no solo omitir PYTHONPATH en esta máquina.
3. Añadir **un job instalado separado**, dependiente/obligatorio para aceptación de integración: checkout/provisión aislada de revisión Hermes immutable compatible + dependencias de ese runtime; usar su interpreter para integration y variable única para ruta runtime en tests, no hardcode `/opt/hermes` ni copiar host entero. Mantener pytest tooling disponible con instalación reproducible. Prerequisito o import ausente = **fail del job**, nunca `importorskip`, skipif silencioso ni `continue-on-error`. El gate local completo debe seguir ejecutar ambas particiones, no perder tests al cambiar comandos.
4. Reducir skipif de los tres tests antiguos al separar el job: instalado significa instalado; reportar colección/ejecución esperada y cero skips por prerequisitos. No duplicar todos unit tests en la closure Hermes por cada Python: un job runtime compatible basta, además de la matrix portable.
5. No adivinar revisión/runtime. `/opt/hermes/install-stamp.json` identifica build `e8c97320ac8691d4de92af49f98459f9ef9ddb08`; **no** tiene checkout git. Su `pyproject.toml:10–15,40–73` declara compat updater >=3.11,<3.15 pero dependencias runtime nuevas condicionadas a >=3.14. **No** asumir `uv sync` en 3.11 instala este runtime completo. Elegir un pin comprobado y su Python real (posiblemente 3.14 para integration) sin ampliar a la fuerza el contrato Python del plugin ni vender compatibilidad 3.14 sin probarla. El build local no demuestra disponibilidad del mismo commit en GitHub/provisión CI.

**Rechazado como solución:** instalar solo pydantic, ignorar tres archivos, meter source path sin dependencies, skips generales o borrar integración difícil. Provisión completa de Hermes en **todos** jobs es posible pero mayor coste/acoplamiento y no demuestra portabilidad del plugin.

**Aceptación:** matrix portable en checkout limpio sin Hermes; integración explicit instalada y pin verificado, cero omisiones de riesgos anteriores; job falla ante runtime ausente/incompatible; unión de particiones conserva todos casos existentes salvo deslop justificado por requisito/riesgo. Release gate canónico actualizado sin debilitarlo. CI actual no puede llamarse green hasta ejecución sobre SHA final verificable; si push no autorizado, distinguir prueba local equivalente de GitHub pendiente. Scan `ci.yml:72–80`/README:497 debe acotarse a tracked+intended-new (incluir untracked código intencional), no `.venv`/artifacts privados; no reducir patrones.

### F6 — ACEPTADO, prioridad P2 (test, no bug productivo)

`test_runtime_fixture_commands.py:20` evalúa tuple truthiness. Detector real `/opt/hermes/tools/approval_detection.py:1524–1548`: `pwd` → `(False,None,None)` **truthy=True**; fixture command → `(True, 'script execution via -e/-c flag', ...)` **truthy=True**. Aserción insensible confirmada.

**Aceptación:** desempacar y comprobar `dangerous is True`; benign control `dangerous is False`; perturbación controlada del detector a tuple falso debe hacer fallar la aserción positiva (no llamar PASS a un negativo). Conservar exact command, noncompound, exact permanent grant matching, fixture creada y efecto ausente. No ejecutar el comando con efecto como parte de unit ni reemplazar guards por implementación plugin.

## R1 — Omisión material: stderr backpressure TUI (P1)

`TuiRpcClient._drain_stderr`, `tui_rpc.py:87–114`, se llama al pedir diagnóstico o EOF; `read_frame/wait_ready/call:173–247` no drenan stderr mientras esperan stdout. `tui_runner.py:346–349` espera ready por esa ruta y consulta stderr en error/final (`518,570`). Poner fd stderr nonblocking no elimina el pipe que bloquea al escritor. `_drain_stderr` además concatena todo antes de recortar y su while no tiene presupuesto si el productor escribe sin fin.

Probe child Python inocuo escribe **1 MiB stderr antes de ready stdout**. `client.read_event(.15)` → timeout **0.150223 s**, child sigue vivo; drenando explícitamente entre polls aparece `gateway.ready`, tail **100000 chars**. Esto demuestra falso timeout por backpressure, no hang productivo ya observado. Runtime instalado emite stderr (`/opt/hermes/tui_gateway/entry.py:135,175`), así que la frontera es real, no salida imposible.

**Mínimo aprobado dentro F1:** multiplexar stdout/stderr con selectors existente/nativo, descartar exceso conservando tail acotado por chunk y deadline; sin hilo separado por RPC ni cola ilimitada. Aceptación: readiness/call siguen completando con stderr > capacidad de pipe; flood continuo no roba deadline/CPU ilimitado ni memoria; tail respeta límite; EOF parcial/error incluye diagnóstico y todos pipes/proceso se cierran. No montar logger framework ni reescribir runner.

## Mapa integral: suficiente para paquetes, no certificación exhaustiva

Contrastados módulos/consumidores productivos: wrapper `__init__`→core, `child_launch`→bootstrap→Hermes CLI/TUI; aprobación `native_resolution/native_approval`→config/home/guards; core persistencia/publicación/locks→status/control/reconcile; `tui_rpc`→`tui_runner`→journal→spectator/CLI; notificación core→native ledger/process queue. El mapa STAGE1 es útil y la separación de propietarios debe conservarse. Sus rangos amplios no son evidencia de cada negativa ni prueba de performance.

Correcciones al mapa/aceptación:
- Mostrar stderr como canal con backpressure, no solo “diagnóstico limitado”; incluir R1.
- Separar tests portable, unit runtime-coupled, integración nativa determinista, modelo HTTP fixture y proveedor/user delivery real. “instalado” no significa modelo real; “mocked” no significa portable.
- `STATE.md:171–189` aún mezcla “activation-ready”, gateway actualizado y aceptación histórica con candidato/re-review pendiente al inicio; `TODO.md:100` declara no trabajo restante. Para entrega de **esta** auditoría poner un estado actual inequívoco y marcar referencias viejas históricas, sin reescribir receipts como pruebas nuevas. Corregir contradicción operativa, no hacer limpieza masiva del archivo histórico.
- `child_launch.py:60–61` tiene fallback host `/opt/hermes`; no retirarlo durante limpieza de tests sin probar consumidores de launch. CI path parametrizable en tests no equivale a cambio de runtime launcher.

No finding confirmado sobre summary grande: mi probe `normalize_result` con 32769 chars seguido de `inspect_run` fue **accepted**; spectator recorta por `neutralize_terminal` antes del validator (`spectator.py:168–181`). Rechazado fabricar un defecto por leer solo `349–350`. Del mismo modo, no convertir releer journal por append en optimización sin benchmark.

## Deslop autorizado por consumidores, no cuotas

Búsqueda exacta repo Python + `/opt/hermes` + `/opt/data/plugins` (no universo de consumidores externos):

| Candidato | Decisión y justificación |
|---|---|
| `__init__._prune_schema:279`, `_reconcile_schema:295` | **Retirada local aprobada**: privados, ninguna llamada ni registro; no eliminan capacidad. Mantener denial handlers: tests `test_reliability_20260927.py:73–92` los ejercitan como regresión de no autoridad. |
| `core.env_bool:712`, `capped_text:1505` | Sin calls encontrados. Retirada opcional si Builder confirma no export/documentación/uso dinámico; al ser nombres importables sin `_`, ausencia local no prueba ausencia externa. Beneficio bajo: conservar no bloquea. No substituir por helper Hermes que acople gate portable. |
| `core.load_yaml_mapping:1376` | Dos consumidores test reales `test_profile_delegate.py:1695,1792`, ninguno production encontrado. Preferible leer YAML directamente en assertions y retirar helper si no contractual; conservar comprobación del **artifact generado**, no reemplazarla por mock de overlay. Conservación también aceptable por beneficio marginal. |
| `tui_rpc.wait_for_completion:387–408` | Solo `test_tui_rpc.py:336–341`; runner usa su propio flujo de eventos/control y no esta cola. Retirada opcional coherente de helper+test si no API prometida; registrar riesgo que desaparece: un helper sin consumidor no protege completion productivo. **No** portar su lógica simplista al runner: ignora steering/settlement. |
| core→native_resolution / core→child_launch | **Conservar seams**: resolución llamada por ejecución/preflight, monkeypatches reales en tests; módulos importan core y `native_resolution.py:47` vuelve a seam core. Colapsarlos puede cambiar identidad/import/patchability, no hay beneficio medido. |
| `_operator_prune` y tests locks/UID/tombstone | **Conservar**: capacidad interna de retención y pruebas de seguridad comprobadas, docs no autoriza borrar funcionalidad ni añadir CLI destructiva. |
| request/status/envelope/effective/requested, journal, native ledger | **Conservar** snapshots/ejes/observabilidad y propietario nativo. Parecer duplicado no demuestra duplicación semántica. No outbox propio ni recomputar frozen desde config actual. |

Quitar comentarios narrativos solo si se preserva el invariante: discovery no importa run_agent bajo lock (`__init__.py:533–538`), ACK≠delivery, no retry fresh, result-first. Races/publication/control no son redundantes por compartir fixture. Para cada test retirado exigir riesgo→evidencia sustituta o ausencia de consumidor; no contador LOC/tests ni plataforma mutation.

## Paquetes recomendados y ownership

1. **A / P1 — TUI I/O:** `tui_rpc.py`, regresiones propias TUI; F1+R1. Único escritor, sin cambiar contratos RPC/runner/authority. Puede ajustar constante/lógica de lectura, no gran refactor.
2. **B / P2 — Lifecycle y recovery:** core recovery + spectator/event_schema/event_journal si se comparte vocabulario; F2+F3. Tests productores reales y segundo intento prose. Como A/B comparten `test_tui_rpc.py`, serializar ese archivo o separar regresiones en módulo focal, no dos escritores.
3. **C / P1–P2 — Gate y contract/deslop acotado:** CI, tests runtime partition/config de test, `.agents/validation.md`, README/BRIEF/estado; F4+F5+F6 y helpers privados aprobados. Afecta muchos tests: ejecutar solo con fuente estable, no gates durante edits. No reordenar módulos enteros para reducir tamaño.

No condicionar arranque al proveedor real/four-mode matrix si no se modifica permisos. Sí preservar todo paquete baseline de aprobación y exigir cobertura existente más integración afectada; cambios accidentales en bootstrap/resume/native authority expanden la matriz y necesitan revisión específica. Padre ejecuta los probes instalados que requieran autoridad de operador; hijo no elimina guardas para obtenerlos.

### Gate exacto para Builder / review final posterior

- Antes de declarar cada finding cerrado: regresión que falle en baseline y pase con fix; conservar salida/command reproducible, no solo “green”. Para F6 detector falso; F1 partial/cap; R1 saturation; F2 emitted CLI status; F3 prompt segundo intento y marker; F4 actual schema+handler; F5 missing prereq y checkout portable.
- Tras diff coherente: lock/sync frozen, suite completa canónica incluyendo integración explícita, `-W error`, Ruff, compilación, `git diff --check`, scan tracked/intended-new y registration/handler. Después de schema cambios smoke discovery **fresh isolated process** instalado antes de afirmar live; no reinicio productivo autorizado.
- Transport modificado: harmless real subprocess readiness/completion/steer/cancel/cleanup; smoke instalado TUI y CLI recovery cuando disponibles. Registrar separado fixture/modelo simulado/proveedor real. Probe CLI deny entrante se reutiliza solo para lo que demuestra, no como matriz completa.
- Estado actual/contratos actualizados, diffs intencionales, artifacts privados preservados y sin commit automático. Si una integración no puede provisionarse o probarse, reportar **BLOCKED para esa aceptación**, sin skips verdes ni entregar PASS global.
- Independent review final del diff y evidencia queda al padre; este documento **solo autoriza implementación mínima**. Mejoras marginales opcionales no abren rondas infinitas.
