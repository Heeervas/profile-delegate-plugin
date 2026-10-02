# Review final independiente — candidato local

## Veredictos

- **Implementación último delta provenance native503: PASS por inspección focal.** HIGH anterior corregido: streams completos separados de tails legacy, fullmatch/exclusiones native sobre completos; cuatro regresiones caller con captura real añadidas. Sin defectos implementables nuevos demostrados. Esto NO afirma tests ejecutados verdes.
- **F5 código y harness conservan aceptación de implementación anterior.** Receipts históricos completion/steer/cancel/recovery Markdown/text, matrix64 y fresh discovery siguen válidos para sus casos; no repetidos. F3 previo no se reabre.
- **Aceptación ejecutada/global: BLOCKED_INCOMPLETE, motivo BLOCKED_CAPABILITY.** Native Python3.14 sin pytest; cuatro casos caller y demás integration no ejecutados; provisioning limpio/portable sin Hermes/timing gate pendientes. Denegación de instalación no reintentada ni rodeada. No PASS global.
- **Recomendación: consolidar handoff y pedir autorización específica para provisioning aislado locked; después prerequisite, regresión focal y gate completo. No nuevo fix producto ni cadena de review/cosmética.**

## Revisión anterior conservada — histórica, no refleja cierre focal actual

Los apartados siguientes hasta «Re-review focal F5» describen el candidato anterior. Sus estados «matrix en curso» y «F5 código bloqueado» quedan sustituidos por los veredictos de cabecera y el cierre focal final.

Checkout `/opt/data/plugins/profile-delegate`, HEAD/baseline `bebd2335b42934386fbceefc0affe7911db8638c`. Revisados `DIAGNOSIS_REVIEW.md`, `IMPLEMENTATION.md`, todo diff tracked desde baseline y untracked explícitos `pytest.ini`, `scripts/scan_secrets.py`, `test_tui_io.py`, `test_audit_contracts.py`. Único archivo producto escrito por Reviewer: este informe. Sin implementación, delegación, core Hermes/perfiles/config/activación/commit/push. `.artifacts/` preservado. La matriz `.artifacts/task-approval-runtime-hdzu9r09` comunicada por el padre está en curso: **no se contabiliza como éxito**.

## Cierre de ronda — evidencia nueva del padre

Padre comunica ejecución real `/opt/hermes/.venv/bin/python /opt/data/profiles/builder/cache/scratch/audit_operator_discovery.py`, **exit 0**, home aislado `/opt/data/profiles/builder/cache/scratch/pd-discovery-g2g1a7gw`: PluginManager real descubre seis tools, list scope enum `current_session`, status invalid-id devuelve `validation_error`. **Discovery deja de estar pendiente**; es evidencia del padre, no ejecución propia ni activación productiva. Padre también confirma lock/sync/Ruff/release/secret scan incluidos nuevos/diff-check exit 0: esos gates no prueban integración ni provisión limpia.

Matriz instalada lanzada por el padre, proceso `proc_1631652a50d1`, aún sin resultado/receipt. No se espera para cerrar esta ronda ni recibe PASS. Los apartados de evidencia propia conservan sus resultados originales.

**Una corrección coherente al Builder:** F5 workflow + prerequisite + docs, con interpreter/closure/tooling locked correctos. No reabrir los demás fixes aceptables ni introducir mocks/skips. Controles/recovery son aceptación pendiente del padre, no otros defectos implementados demostrados.

## Evidencia independiente y reconciliación de resultados

Logs Builder leídos, no heredados como ejecución propia:

| Archivo bajo `/opt/data/profiles/builder/cache/scratch/` | Resultado literal |
|---|---|
| `audit-closure-full-final.log` | **669 passed in 128.05s** |
| `audit-closure-portable-final.log` | **226 passed, 443 deselected in 8.06s** |
| `audit-closure-gates.log` | lock/sync, Ruff verde, seis tools/CLI/handler FakeContext, `secret_hits=0`; no transcript detallado de cada comando |
| `audit-baseline-sensitivity.log` | baseline rechaza tres fases, recovery impone JSON, scope permite widening, tuple falsa pasa; partial reads .422/.427s y readiness bloqueada por stderr |
| `audit-missing-prereq.log` | runtime `/nonexistent`: **2 errors**, no skips |

Comprobaciones propias sobre el candidato estable:

- `uv run --frozen python -m pytest --collect-only -q -m integration -o 'addopts=' -p no:cacheprovider`: **443/669 collected, 226 deselected**. Confirma selección y cardinalidad, no ejecución native satisfactoria.
- Portable sin `PYTHONPATH`, `-m 'not integration' -W error`: **226 passed, 443 deselected in 6.64s**. Sigue siendo esta máquina con `/opt/hermes` instalado, no prueba de runner totalmente Hermes-free.
- Foco F1/R1/F2/F3/F6 y controles: `PYTHONPATH=/opt/hermes uv run --frozen python -m pytest test_tui_io.py test_audit_contracts.py test_tui_rpc.py test_sync_lifecycle.py test_profile_delegate.py::test_transient_failure_resumes_same_session test_runtime_fixture_commands.py -q -o 'addopts=' -W error -p no:cacheprovider`: **95 passed in 60.84s**.
- Partición native propia completa, mismo entorno instalado: **442 passed, 1 failed, 226 deselected in 118.69s**. Falló solo `test_tui_rpc.py:1103`, límite wall-clock cancel, elapsed **0.817600697017042** vs **<0.8**. Misma prueba aislada con `PYTHONPATH=/opt/hermes`: **1 passed in 2.14s**. Resultado inicial no se convierte en verde por el retry. Ver nota de fiabilidad abajo.
- Ruff, `scripts/validate_release.py`, scan tracked + cuatro untracked explícitos, `uv lock --check`, compilación canónica incluyendo nuevos archivos y `git diff --check`: propios, exit 0. Registration verifica seis herramientas, scope y handler inválido con FakeContext; **no** fresh Hermes discovery.
- `uv run --frozen python --version`: **3.13.5**; `/opt/hermes/.venv/bin/python --version`: **3.14.7**. `.venv/pyvenv.cfg` confirma interpreter 3.13 y sin system-site-packages.

No afirmo “669 verdes propios”: Builder sí conserva ese log; mi ejecución independiente conserva la anomalía temporal. La unión 226+443 está verificada por collection y selección. Basetemps propios: `/opt/data/profiles/reviewer/cache/scratch/final-{portable,focused,native}-pytest` y `final-cancel-retry-with-runtime-pytest`.

## Finding bloqueante — HIGH / F5: job instalado no ejecuta pytest con la closure instalada

**Paths:** `.github/workflows/ci.yml:72–94`, `conftest.py:29–34`, `pyproject.toml:4,16–22`, `.agents/validation.md:12–23`, README Development.

He comprobado el archivo actual: `PYTHONPATH` contiene **solo source** de Hermes. No contiene site-packages 3.14. Corregir cualquier descripción que diga que el candidato ya los incorpora.

El job:

1. instala la closure Hermes en su `.venv` Python **3.14** (`ci.yml:91`);
2. instala tooling del plugin en otra `.venv` Python **3.13** (`:92`);
3. ejecuta `uv run --frozen python -m pytest` desde el proyecto plugin (`:94`), por tanto con **3.13**;
4. `conftest.py:34` importa código Hermes en ese mismo proceso, no en el interpreter instalado.

**Es una separación incompleta, no un entorno de integración nativa con closure verificada.** Source en PYTHONPATH no activa las dependencias de otra venv. La config inicial puede funcionar gracias a ruamel presente en el lock plugin; un import superficial verde no demuestra closure. Muchos consumidores padre son Python puro, mientras los contracts/guards más pesados se prueban en child 3.14: eso explica cómo tests locales pueden pasar y por qué no debo inventar un `ModuleNotFoundError` exacto de GitHub que no he ejecutado.

Evidencia runtime: `/opt/hermes/pyproject.toml:10–15` declara **solo 3.14 como runtime**, 3.11–3.13 son bridge de updater. Dependencias reales (`openai`, `rich`, `pydantic`, etc., :40–73) condicionadas a >=3.14. El lock plugin no las declara. Conftest solo comprueba archivo del interpreter y `hermes_cli.config`; no comprueba que el pytest interpreter sea el runtime provisionado ni la closure representativa. Los 443 casos no son todos end-to-end ni todos ejercitan extensiones en el padre.

**No arreglo válido:** añadir `.venv/lib/python3.14/site-packages` al pytest 3.13. Inspección exacta encontró `/opt/hermes/.venv/lib/python3.14/site-packages/pydantic_core/_pydantic_core.cpython-314-x86_64-linux-gnu.so`; no hay `_pydantic_core` en la venv plugin. Una extensión cp314 no constituye closure compatible cp313; tampoco debe renombrarse ni copiarse. No ejecuté una carga ABI cruzada. Una orden diagnóstica `python -c` fue denegada por guarda; no reintentada ni convertida en script/otra vía. La conclusión está fundada en manifiestos, interpreters y extensión real, no en una ejecución inventada.

### Cambio mínimo real para cerrar F5

- Mantener la matrix portable plugin **3.11/3.12/3.13** y su lock intactos.
- Mantener el pin Hermes inmutable, pero ejecutar **la partición installed con su interpreter 3.14**, no `uv run` del proyecto plugin. Provisionar pytest/tooling bajo **ese mismo 3.14**, de forma locked y explícita. El runtime tiene grupo `dev` con `pytest==9.1.1` (`/opt/hermes/pyproject.toml:540–546`), pero `default-groups=[]` (:611–613): `uv sync --frozen` actual no instala pytest allí. Usar su grupo locked explícito es la variante menor si su closure aporta también los helpers YAML usados por esta suite; de lo contrario, overlay de test tooling separado, locked para 3.14, sin mutar runtime productivo.
- Ejecutar desde cwd plugin con la ruta absoluta `"$PROFILE_DELEGATE_TEST_RUNTIME/.venv/bin/python" -m pytest -m integration ...`; source Hermes en PYTHONPATH es aceptable **con su interpreter/closure**, no como sustituto. Esto prueba source plugin dentro del host soportado sin ampliar por decreto su metadata `<3.14` ni instalar el proyecto plugin como paquete 3.14.
- Prerequisite explícito fail-closed: pytest interpreter/version corresponde al runtime elegido; importar config/approval, SessionDB, display y contracts Pydantic reales antes de declarar installed gate listo. No fixture API falsa, skip, eliminación de casos ni copiar site-packages entre versiones. Que falle si falta tooling o closure.
- Validar esa provisión en entorno limpio autorizado; conservar comandos/resultados del pin, interpreter, imports y **443 casos seleccionados** (o nuevo total explicado si se añaden solo regresiones). Actualizar README/validation para no vender el split 3.13/3.14 actual como solución accepted.

**Regresión mínima de gate:** prerequisito debe rechazar pytest 3.13 + runtime source/venv 3.14, y admitir pytest ejecutado por el runtime 3.14 correctamente provisionado. Runtime ausente sigue fallando, como ya demuestra el negativo Builder. No hace falta reproducir todos imports fallidos uno por uno.

La provisión denegada sigue siendo un **bloqueo de autoridad/entorno separado**. No reintenté extracción ni alternativa. No exijo push para revisar esta corrección ni atribuyo un fallo remoto no observado. Corregir localmente el job es posible sin push; demostrar provisión limpia requiere un contexto autorizado cuando la guarda lo impida.

## Juicio por criterio

| Criterio | Juicio de implementación y evidencia |
|---|---|
| **F1/R1** | **Aceptable localmente.** `tui_rpc.py:55,68–125` mantiene buffer por cliente, cap+1 antes de newline, deadline monotónico y fragmentos entre polls. Stderr se multiplexa con stdout; ocho chunks de 8192 por poll y tail recortado por chunk, EOF deja de vigilarse. Lectura stdout tiene turno aun con flood. BytesIO es adaptador fixture, no hilo nuevo por timeout. `test_tui_io.py` prueba partial deadline/cap, UTF-8 partido, concatenados, EOF parcial, late response, saturation 1 MiB antes de ready y RPC, flood stderr/events y bounds; pasó propio. Validación strict ids/hybrids y close/cancel retenida. Cleanup mata/reap directo y cierra pipes en finally (`:260–325`); installed teardown/control sigue pendiente. Sin evidencia de pérdida de framing o memoria ilimitada en el cambio. |
| **F2** | **Aceptable.** `spectator.py:38–43` y `event_journal.py:32–37` añaden solo las tres fases emitidas. `test_audit_contracts.py:23–43` usa subprocess real y inspect durante running/después stopped; `test_sync_lifecycle.py:93–135` inspecciona publicación real cancellation_requested y conserva reaping grupo. Unknown phase aún rechazado. No se rebaja validación a arbitrary strings. |
| **F3** | **Aceptable localmente.** `core.py:2349–2361,2793–2797` usa modo/requirement persistidos. Regresión parametrizada `test_profile_delegate.py:1465–1503` captura segundo prompt realmente enviado, resume stable_sid, normaliza JSON/Markdown/text y verifica envelope idéntico. No cambios en classifier ni nuevo retry fresh. Instalado CLI transient recovery no está probado por ese double. |
| **F4** | **Aceptable.** `__init__.py:248` solo ofrece current_session; runtime widening refusal permanece intacto. README origin/continuidad, best-effort notification, marker y ausencia de prune público concuerdan; BRIEF conserva helper interno. Seis herramientas aún registradas; denial handlers/privacy/origin y parser legacy sin cambios. Padre ya ejecutó fresh PluginManager discovery en home aislado, scope y handler inválido correctos; no implica activación productiva. |
| **F5** | **Bloqueado** por finding anterior. Partición de 14 módulos conservadora válida como selección inicial: la collection portable ya no rompe por import eager y ningún test se borra. Overclassification no es defecto bloqueante. 443 «native» incluye unit runtime-coupled, fixtures y algunas APIs reales; no vender 443 end-to-end. 226 portable verdes aquí no prueban máquina sin Hermes. |
| **F6** | **Aceptable.** `test_runtime_fixture_commands.py:22–25` desempaca y exige danger True/benign False; `:37–41` perturbación tuple falsa exige AssertionError del positivo. Sensibilidad efectiva, exact grant/noncompound/no-effect retenidos; 2 tests pasaron propio. No cambio en Hermes detector ni claim de bug productivo tuple. |
| **Deslop** | **Aceptable.** Solo dos schemas privados sin consumidores y reader threaded inseguro retirados. Denial handlers, prune safety/helper interno, public helpers, snapshots/ledger/seams y wait_for_completion conservados. Test steer sincroniza publicación del productor antes de polling (`test_tui_rpc.py:998`); no cambia settlement productivo ni sustituye requisito por mock. Sin cuota LOC ni tests borrados. |

## Nota de fiabilidad — MEDIUM, no nuevo bug productivo probado

`test_tui_rpc.py:1103` mide el tiempo completo de `_execute_with_control`, incluido setup del run y arranque Python, contra .8 s, no exclusivamente el presupuesto cleanup .3 s. En mi native suite falló a .8176 s con proceso reaped/SIGKILL y assertions funcionales satisfechas; en foco inicial y retry aislado pasó. Esa aserción **ya existe en baseline** y `tui_runner.py`/close no cambiaron en este candidato. Por tanto: evidencia de gate temporal frágil, no motivo para revertir F1 ni inventar fuga.

Mínimo si se estabiliza: medir cleanup/control desde el punto de cancelación ya preparado y preservar un deadline total separado con margen de scheduler explícito. No borrar test, relajar arbitrariamente .8 ni llamar verde al primer run. Antes de acceptance registrar nueva ejecución final y cualquier fallo recurrente. Es riesgo de reproducibilidad adicional, no el bloqueo arquitectónico F5.

## Gates restantes y autoridad

**Sin permiso externo nuevo:** corrección plugin-local de CI/prerequisite/docs por Builder; lock/lint/compile/registration FakeContext/scan/diff; repetir regresiones y gate final con logs exactos; conservar selección de todos casos y check negativo. Reviewer no implementa esos cambios. La nota histórica `TODO.md:100` no es criterio de aceptación nuevo; STATE y handoff actuales ya niegan global acceptance.

**Contexto autorizado necesario si la guarda lo impide:** provisión aislada Hermes pin y runner realmente sin Hermes; no reintentar extracción denegada por otra herramienta. Discovery ya cerrado por el padre. Mínimo instalado restante: (a) TUI completion válida, steer aceptado con evidencia de follow-up correlacionado — ACK solo no basta — y cancel de un turno activo con estado terminal/proceso reaped/pipes cerrados; pueden ser runs aislados del mismo fixture HTTP, no una nueva matriz de permisos; (b) CLI recuperación tras un fallo transitorio reconocido y footer válido, segundo intento en la misma sesión/envelope, final Markdown y text con marker normalizado, usando parametrización del mismo driver. Los casos JSON/selección/classifier existentes se conservan; no repetirlos por cosmética. Fixture HTTP instalado es válido para la frontera host si se etiqueta; no exige proveedor comercial ni full four-mode matrix nueva porque autoridad no cambió. Una matriz en curso o una ejecución ordinaria resume no prueba recovery forzado. Esta evidencia pendiente no demuestra otro bug productivo.

**Fuera de esta autoridad/no requerido ahora:** push/GitHub remoto, publicación, restart productivo, activación y core/config/perfiles. CI remoto pendiente es una limitación de evidencia, no un defecto ejecutable añadido. No condicionar los fixes locales a publicar.

### Lista mínima de cierre

1. Reemplazar pytest 3.13+source-only por native interpreter 3.14 con tooling/closure locked; prerequisito verificable; docs concordantes.
2. Ejecutar portable sin Hermes y installed partition en provisión limpia autorizada; preservar no-skips y totales/logs, repetir gate final sin ocultar la anomalía cancel.
3. **Discovery cerrado.** Padre aporta únicamente los receipts restantes TUI completion/steer follow-up/cancel/cleanup y CLI recovery forzado Markdown/text, en sesión/envelope conservados. Valorar receipts reales, no una matriz en curso ni solo el documento preparado.
4. Re-review focal del cambio F5 y de esas evidencias. **No PASS global hasta cerrar 1–3; no hace falta otra ronda cosmética.**

## Re-review focal F5 — histórico, sustituido por cierre classifier siguiente

Alcance: stdout/result de `/opt/data/profile_delegate/runs/pd_20261002_071927_xrzs89/`; cambios nuevos CI/conftest/docs, `scripts/native_prerequisite.py`, `scripts/native-test-tooling.txt`, `test_native_prerequisite.py`, timing cancel y `scripts/accept_audit_runtime.py`. Sin provisión ni implementación/delegación. Única escritura este informe. No esperé ni inspeccioné como éxito el harness padre proceso `269408`, pendiente en esta ronda.

### F5 código: PASS_WITH_NOTES, provisión/ejecución no aceptadas todavía

CI ahora usa `uv sync --frozen --group dev --python 3.14` y ruta absoluta del interpreter runtime para prerequisite y pytest. Tooling YAML hash-pinned, binary-only, bajo ese mismo interpreter. Verifiqué hash `c458b6d084f9b935061bc36216e8a69a7e293a2f1e68bf956dcd9e6cbcd143f5` en `/opt/hermes/uv.lock:5590`: wheel PyYAML 6.0.3 **cp314 manylinux x86_64**, coherente con ubuntu-latest x86_64. Plugin matrix/metadata permanecen 3.11–3.13; no mezcla ABI ni resolver abierto nuevo. Un único hash es deliberadamente específico para ese runner, no packaging universal.

`native_prerequisite.py:11–45` comprueba ruta lexical del interpreter, version 3.14, prefix real, imports de pytest/YAML/ruamel/config/approval/SessionDB/display/contracts/Pydantic, procedencia native source y closure venv; validación real Pydantic ejercita la extensión. Conftest lo exige una vez por sesión, sin skip. Negativos no sustituyen APIs nativas; el positivo integration pendiente exige cierre real y missing-contract fail-closed. No nueva producción/core/autoridad. Son prerequisitos creíbles para este slice, no certificación exhaustiva de Hermes.

Evidencia propia nueva: portable `-m 'not integration' -W error -p no:cacheprovider` **228 passed, 444 deselected in 6.77s**; collection **444/672, 228 deselected**, `/opt/data/profiles/reviewer/cache/scratch/f5-focal-collection.log`; Ruff focal y diff-check exit 0. Los tres casos nuevos explican cambio de cardinalidad. `/opt/hermes/.venv/bin/python -m pytest --version` falla **No module named pytest**, igual que `/opt/data/profiles/builder/cache/scratch/f5-final-native.log`. Esto es **prerequisito instalado ausente**, no bug del CI corregido ni evidencia del positivo. `/opt/data/profiles/builder/cache/scratch/f5-foreign-interpreter.log` confirma rechazo del interpreter plugin. Instalación scratch denegada por Tirith metadata/deny no reintentada ni rodeada. No extraigo ni provisiono por otra vía. Closure limpia y portable realmente Hermes-free siguen pendientes, sin exigir push/GitHub remoto fuera autoridad.

### Timing cancel: cambio aceptable, ejecución pendiente

`test_tui_rpc.py:714–720,1107–1121` inicia measurement después de crear proceso y publicar cancel, conserva límite preparado **.8s**, total separado **10s**, SIGKILL/reaped/pipes closed y receipt. Corrige la atribución de startup sin borrar riesgo. Todavía no he podido ejecutar este caso nuevo bajo prerequisite correcto; no declarar fiabilidad estabilizada por código solo.

### HIGH — harness confunde `cancelling` con terminal

`scripts/accept_audit_runtime.py:195–197` retorna status para cualquier valor fuera de running/queued/starting. Productor real `tui_runner.py:268–269` publica **cancelling** antes de interrupt/cleanup. Por ello el waiter :148 puede devolver cancelling mientras `transport_alive` es true y fallar falsamente :150/:157. Es carrera concreta del nuevo harness; no prueba que el runtime cancele mal y no espero su ejecución para señalarla. Verificada por referencias productor/consumer, no por smoke nuevo: un probe aislado del predicate con execute_code fue denegado por single-query, no ejecutó llamadas internas y no lo reintenté ni trasladé a otro ejecutor.

**Fix mínimo único:** predicate de estados terminales positivos explícitos (`completed`, `failed`, `cancelled`, `timed_out`) o, como mínimo, tratar cancelling como no terminal; errores de status/unknown deben fallar diagnosticados, no considerarse completion. Regresión mínima de predicate: running→cancelling→cancelled, solo último cierra; error handler no cierra como éxito. No mockear runtime completo ni tocar productor/control. Luego padre ejecuta el harness válido en su contexto autorizado.

### Harness: assertions/ownership aceptables con límites de evidencia

Opt-in y refusal de ancestry antes de preparar home, loopback server, env allowlist, profiles/config privados bajo `.artifacts`, child deny, handlers/session/control/launch reales, solo modelo HTTP determinista. No cambio a producción/config/perfiles. Recovery exige 503 real, prompt recovery observable, dos intentos/same session y marker/modo; core copia último stdout a canonical (`core.py:2855–2857`), así que assert :179 usa archivo correcto. Comparación envelope provider usa request persistido compartido, **no observación independiente de bind en cada child**; junto a producción frozen intacta y unit equality es útil, no venderla como instrumentación nueva de todos guards.

Steer no se conforma con ACK: exige final token + dos lifecycle start/complete y mismo task; el journal ya filtra UI identity. No exigir que delivery_status unknown se vuelva delivered: receipt funcional y estado delivery siguen independientes. Cleanup prueba PID ausente/transport_alive false, pero comentario :152–153 sobre “no open child pipes” no prueba descriptores del padre; receipt declara `fd_closed_in_parent: not instrumented`. Mantener esa limitación explícita; código close finalmente cierra los streams y test timing comprueba objetos cerrados, ejecución nueva pendiente. No bloquea por cosmética ni requiere logger/probe framework.

### Steer real de Builder: riesgo observado, no false-green

Leídos `result.json` y ACK de `pd_20261002_071927_xrzs89`: execution/status **failed**, error **steer_outcome_uncertain**; ACK `255c255ca4984e1aada807277f507ae6` **accepted**. Stdout útil termina en marker blocked, pero eso no convierte wrapper en éxito. Ruta conservadora `tui_runner.py:463–481` falla cuando falta follow-up completed+settled; receipt demuestra incertidumbre efectiva en una delegación real, **no causa ni pérdida de steer demostrada**. El parse drift del result es otro eje, no excusa para borrar el fallo de transporte.

Implicación mínima de acceptance: no afirmar fiabilidad general de steer por matrix permisos 64/64. Padre necesita follow-up correlacionado del smoke instalado; aun si pasa, conservar este residual real y no llamar esta delegación green. Investigación causal fuera de este slice no autorizada ni necesaria para evaluar el fix F5.

### Evidencia padre cerrada y gaps exactos

Receipt `.artifacts/task-approval-runtime-hdzu9r09/receipt.json` leído: **ok, matrix_complete=true, case_count=64**; agregación 64 pass/0 nonpass comunicada y comprobada por padre, no re-ejecutada aquí. Fresh discovery previamente verde permanece cerrado. La matriz no cubre el nuevo harness de controles/recovery ni native pytest closure.

**Único fix implementable exigido ahora:** waiter terminal del nuevo harness. **Gaps de evidencia:** (1) provisión limpia autorizada native3.14/dev/hash helper + positivo prerequisite + 444 integration y timing receipt; (2) portable en runner sin Hermes; (3) harness instalado corregido, cinco casos completion/steer/cancel/recovery-Markdown/recovery-text y receipts válidos. Proceso269408 en curso no recibe PASS. No full rerun bajo 3.13 para evadir prerequisite, no instalación alternativa a deny, no nueva delegación, no ronda cosmética ni push. F5 defecto de código anterior cerrado por inspección; aceptación global continúa BLOCKED_INCOMPLETE.

## Cierre focal classifier native503 + harness — histórico; sustituido por cierre provenance final

**Alcance y separación:** diff actual `git diff bebd233 -- core.py test_profile_delegate.py` leído; revisados solo nuevo `NATIVE_OVERLOADED_503_PATTERN`/branch classifier y regressions, y delta harness. El recovery prompt mode-aware/marker es **F3 anterior** ya aceptado, no un cambio nuevo al classifier ni nueva auditoría. Única escritura este informe; sin implementación/delegación/install/core Hermes/config/perfiles/commit/push.

### Evidencia de necesidad y compatibilidad real

Leídos stdout/stderr/result de `.artifacts/audit-runtime-5avgd_3s/runs/pd_20261002_075602_e8z5lh/`: exit1, no timeout, duración11.467s, session `20261002_075608_f63a8e`, history transient_reason null. Stdout contiene native exhausted overloaded + `Provider said: HTTP 503: HTTP 503: Service Unavailable upstream temporarily unavailable`. Es fallo real de reconocimiento previo, no inventado del provider ni F3 serialization.

Source Hermes solo leído: `/opt/hermes/agent/turn_failure_copy.py:165,175,363–375` construye exactamente lead overloaded, em dash, instrucciones y Provider said; `/opt/hermes/agent/turn_recovery.py:1201–1203` lo usa con label/attempts/summary real. Regex nuevo coincide con este native copy, duplicación opcional HTTP503 y legacy separado. Provider label1–200 y carácter conservador, count positivo, línea única y case-sensitive copy son restricciones fail-closed aceptables para pin actual; no claim de compat universal. Gates exit/interrupt/timeout/parsed terminal/realm mismatch/exclusions quedan antes del match. No toca sesión/approval/fresh retry/max resumes/shared deadline.

### HIGH — fullmatch recibe un tail, no el bloque completo original

**Evidencia exacta:** `core.py:1669` mantiene `diagnostic_tails = (... + chunk)[-DIAGNOSTIC_TAIL_CHARS:]`; límite4000 definido :71. `core.py:2842–2848` entrega esos tails a `classify_transient_failure`, aunque los artefactos retenidos no hayan truncado. `stdout_truncated`/`stderr_truncated` reportan cap del archivo, **no clipping del tail** (:1671–1674). Branch nuevo :2353–2358 dice que no tail-slice y hace fullmatch, pero el prefijo ya desapareció antes de entrar.

Por tanto puede promover un bloque nativo que era solo suffix de output contradictorio: output sin JSON-terminal con texto previo de acciones completadas o exclusión policy/approval, seguido de más de4000 chars de líneas vacías y luego bloque nativo completo corto. El tail queda whitespace + bloque; strip lo reduce al bloque exacto; flags de artifact cap permanecen false y las exclusiones previas desaparecen. caller autoriza provider_503 y resume aun cuando direct classifier con todo stdout lo rechazaba. **Escenario derivado del código, no smoke malicioso ejecutado ni replay observado.** Con default artifact cap200000 no requiere overflow ni permisos nuevos. Desmiente garantía de rechazo de surrounding prose en ruta real. El daño posible es continuación inapropiada/repetición de acciones, no falsa wrapper success inmediata.

**Fix mínimo:** alimentar el nuevo reconocimiento con stdout/stderr retenidos completos cuando no truncados (ya disponibles como stdout_attempt/stderr_attempt), conservando tail/legacy y exclusions intactos; o verificar explícitamente provenance/completeness antes del branch native con flag de clipping del diagnostic tail. No marcar todo legacy como truncado ni introducir router/general retry. Regresión de caller real o seam `run_capped_subprocess→classifier`: prefix contradictorio + >4000 whitespace + bloque, sin artifact truncation, exige no provider_503/no resume. Mantener positivo native puro. No exigir nueva matriz ni re-ejecutar smokes ya cerrados por cosmética.

### Calidad de tests y gates

Nuevos tests en `test_profile_delegate.py:1466–1523` fijan copy literal independiente del import Hermes: buena sensibilidad a drift. Positivos native simple/doble503 y legacy; negativos exits/interrupt/timeout/truncation/parsed status/4xx/realm/billing/credential/wrapper/fence/suffix/other5xx/count0/lead/permanent cubren riesgos locales. Todos prueban classifier directamente, **no tail-provenance del caller**; de ahí gap concreto, no razón para borrar tests. Regressions nuevas están en módulo integration conservador; **no ejecutadas** por falta native pytest. No modificar markers para false-green.

Ejecución propia portable `-m 'not integration' -W error -p no:cacheprovider`: **228 passed, 477 deselected in 7.71s**. Ruff focal (`core.py`, tests, harness) y diff-check exit0. El comando combinado acaba exit1 solo por `/opt/hermes/.venv/bin/python -m pytest --version`: **No module named pytest**. Portable verde no ejecuta los nuevos negativos, y direct probe comunicado no sustituye esa suite. No instalé ni rodeé denegación previa; no hice probe por executor alternativo.

### Harness corregido y bounds/ownership

`accept_audit_runtime.py:170` usa `ui_child_session_id`, productor/receipt correcto. :200 incluye cancelling no terminal; fallo anterior cerrado. Unknown/error aún devuelve rápido pero asserts posteriores fallan, nunca receipt ok; whitelist terminal sería mejora no bloqueante y no cosmética exigida ahora. `--cases` usa choices y receipt enumera solo casos efectivamente ejecutados, permite cerrar recuperación sin repetir controles; no vender subset como cinco casos ni matrix.

Source `/opt/hermes/agent/agent_init.py:1448–1459` confirma api_max_retries minimum1/default3 y auto_recovery_cycles minimum0/default5. Harness :238–241 cambia esos valores **solo nuevo target home bajo root .artifacts**, no config productivo. Reduce ladder para que el fallo/footer alcance al plugin antes del timeout180, manteniendo HTTP503 real, delay/recovery/session/control reales. Opt-in/refusal ancestry/env privado permanecen. Válido fixture acotado de frontera, no prueba defaults/latencia proveedor comercial ni autorización de retry de comando denegado.

### Receipts instalados cerrados (sin repetir smokes)

- `.artifacts/audit-runtime-2yxstbtt/calls/completion.response.json`: completed/success true/exit0. Steer response idem, stdout token `AUDIT_FOLLOWUP_CORRELATED`; followup receipt tiene ACK accepted, dos starts/completes mismo task `pd_20261002_074606_o3viov`, UI `a7af88a9`, child `20261002_074612_afbaf4`. Cancel response terminal cancelled. Tres cleanup receipts proc_absent=true/transport_alive=false; fd.closed padre sigue **not instrumented**, no ampliar claim. Los tres casos válidos, no convierte receipt de harness completo que falló después en global verde.
- Evidencia recovery entregada mid-turn y leída exacta: `.artifacts/audit-runtime-j9k2fb22/receipt.json` ok con **solo recovery-markdown y recovery-text**; ambos response success true/completed/result ok/contract recovered. Markdown task `pd_20261002_080449_1t6j5z`, sesión `20261002_080455_b29ccd`; text task `pd_20261002_080529_12ulv8`, sesión `20261002_080536_e2035f`. Cada history intento1 exit1/provider_503 y intento2 exit0/null con misma sesión. `.recovery.json` deny/bypass false y prompt formato correspondiente+marker+no repetir acciones; canonical stdout tiene marker ok. **Recovery ya no pendiente**; proceso padre deja de ser evidencia provisional por estos receipts, no ejecutado por Reviewer.
- Solo MODEL HTTP determinista; handlers/CLI/session/control reales. Envelope en provider sigue request compartido, no instrumentación independiente de todos child binds. Native same-session receipt no demuestra idempotencia de tools (estos casos no ejecutan tools).
- Matrix64 y fresh discovery permanecen cerrados de ronda previa. Steer real Builder `steer_outcome_uncertain` permanece riesgo residual genuino, no invalidado por smoke correlacionado ni causa investigada arbitrariamente.

## Recomendación final de ronda anterior — histórica

**BLOCKED_NEEDS_FIXES para nuevo classifier**, único finding tail-provenance anterior. Harness/controles/recovery acotados aceptables y verificados, sin repetirlos. **BLOCKED_INCOMPLETE global** por native pytest/deps/provisión limpia, nuevos integration negativos/timing receipt y portable realmente Hermes-free. Cerrados los smokes no son gates completos; implementación del fix mínimo y prueba focal no requieren reauditar F1–F6 ni publicar/restart/provisionar bajo deny.

## Cierre FINAL focal provenance — vigente

**Implementación PASS (inspección), aceptación BLOCKED_CAPABILITY / BLOCKED_INCOMPLETE.** Leídos delta `core.py`/`test_profile_delegate.py` y stdout Builder `/opt/data/profile_delegate/runs/pd_20261002_081218_0lxil8/stdout.txt`. HIGH tail-provenance cerrado como defecto de implementación. Ningún fix producto adicional exigido; no otra cadena de review ni cosmética. Solo este informe editado.

**Provenance y bounds:** `core.py:2832–2836,2853–2861` obtiene archivos retenidos completos con `tail_text(path,0)` y pasa `native_stdout/native_stderr`; tails legacy permanecen separados. `tail_text:714–719` ya leía el archivo entero antes de recortar: este cambio elimina slicing, no introduce nueva lectura ilimitada de stdout vivo. `append_capped:1529–1536` limita por caracteres decodificados, output_limits :1523–1525 impone máximo configurado10_000_000 por stream. Por tanto leer entero el archivo retenido es coherente con su cap en caracteres, no bytes ni tail4000; flag de artifact truncation sigue deshabilitando native. Exclusions native :2361–2363 escanean completos de ambos streams y fullmatch :2364 rechaza prefix original. Helper realm conserva semántica previa bounded; no se ha ampliado el scope del classifier legacy. No modificación de sesiones/approval/maxresumes/deadline.

**Cuatro regresiones caller :1523–1585:** real `delegate_profile→run_capped_subprocess` con emisor child local; capture/caps/tails/files reales, solo admission/rename/wait fixtures acotadas. Native limpio y legacy tail esperan dos intentos/same resume; prefix contradictorio perdido y exclusion en otro stream esperan uno/no transient/nonzero_exit. Asserts comprueban archivos exactos/no truncation/longitud mayor que4000/pérdida real del prefix en tail y resultado caller. Cobertura pertinente al HIGH, no mock que devuelve classifier verde; no prueba Hermes end-to-end, eso ya tiene receipts normales históricos. No ejecución de estos cuatro casos ni de nuevos integration negativos: pytest nativo ausente. No false-green por revisión.

**Checks propios esta ronda:** Ruff focal core/tests y `git diff --check` exit0; `/opt/hermes/.venv/bin/python -m pytest --version` nuevamente falla `No module named pytest` (comando combinado exit1, no gate verde). Portable228/481 y static gates del stdout Builder son resultados reportados, no ejecución propia en esta ronda. Sin installs/executor alternativo ni smokes repetidos.

**Evidencia histórica conservada:** `.artifacts/audit-runtime-j9k2fb22/` recovery Markdown/text y `.artifacts/audit-runtime-2yxstbtt/calls/` completion/steer/cancel aceptados para caso normal anterior; no denominarlos prueba de regresiones actuales. Matrix64 y discovery cerrados. Riesgos fd.closed no instrumentado/real steer uncertain/envelope compartido ya explicitados, no nueva investigación ni blocker código en este delta.

### Handoff de capability: comandos mínimos pendientes, NO ejecutados

Desde repo root, después de **autorización específica y aprovisionamiento aislado** del pin Hermes `e8c97320ac8691d4de92af49f98459f9ef9ddb08` (no modificar `/opt/hermes` instalado). `$PROFILE_DELEGATE_TEST_RUNTIME` debe apuntar a ese checkout privado autorizado. Las dos órdenes de instalación siguientes son propuesta para autorización nueva, no reintento ni workaround de deny vigente:

```bash
uv sync --frozen --group dev --python 3.14 --project "$PROFILE_DELEGATE_TEST_RUNTIME"
uv pip install --python "$PROFILE_DELEGATE_TEST_RUNTIME/.venv/bin/python" --require-hashes --only-binary :all: -r scripts/native-test-tooling.txt
export PYTHONPATH="$PROFILE_DELEGATE_TEST_RUNTIME"
"$PROFILE_DELEGATE_TEST_RUNTIME/.venv/bin/python" scripts/native_prerequisite.py
"$PROFILE_DELEGATE_TEST_RUNTIME/.venv/bin/python" -m pytest test_profile_delegate.py::test_native_503_recovery_caller_preserves_complete_output -q -o 'addopts=' -W error
"$PROFILE_DELEGATE_TEST_RUNTIME/.venv/bin/python" -m pytest -q -o 'addopts=' -W error
```

El full gate incluye los nuevos negativos integration y timing cancel; conservar totales/logs/receipt real, no llamar los cuatro casos ejecutados hasta obtener salida. Para evidencia portable realmente Hermes-free, en runner separado sin runtime y sin PYTHONPATH:

```bash
uv sync --frozen
uv run --frozen python -m pytest -m 'not integration' -q -o 'addopts=' -W error
```

Resto de release gate exacto en `.agents/validation.md` (Ruff/compilación/validate_release/secrets/diff), sin push/restart requeridos por esta revisión. Si autorización/provisión sigue denegada, handoff conserva **implementación PASS, aceptación BLOCKED_CAPABILITY**; no reabrir fixes aceptados ni buscar otro instalador/ejecutor.
