# Profile Delegate vs Hermes Herald — comparación y plan de implementación

Estado: propuesta completa; no autoriza implementación, activación, credenciales ni publicación.
Fecha: 2026-09-09.
Destinatario/resultado: Alberto debe poder decidir qué incorporar y encargar una implementación sin reabrir decisiones arquitectónicas básicas. Medio: informe y plan Markdown; no dashboard.

## Decisión

Mantener Profile Delegate como ejecutor local entre perfiles. Incorporar descubrimiento verificable, continuidad explícita y observabilidad de Herald; no sustituir el transporte por HTTP ni importar su ledger. Inferencia sin agente y delegación entre hosts son capacidades adyacentes, no requisitos del ejecutor local.

El argumento más fuerte a favor de Herald es su frontera HTTP pública: sirve para hosts distintos y desacopla al originador del arranque local/TUI del especialista. El argumento más fuerte contra nuestra solución es el acoplamiento al bootstrap, RPC TUI y APIs nativas de Hermes. Cambiaría la recomendación si aparece un destino remoto real o si una comparación controlada demuestra que la alternativa reduce fallos/latencia sin perder controles ni entrega persistente.

## Evidencia y límites

- Profile Delegate: versión declarada 1.10.0, commit `c8a0244f79c443cfc04f1fdb82594049c53bcab5`. Árbol limpio al comenzar.
- Herald: commit `a033d52002a4c808ad89c1713a188449b27465de`, mensaje v1.1.0; copia de lectura en `/opt/data/workspace/projects/herald-comparison/source/hermes-herald`.
- Prueba actual nuestra: `PYTHONPATH=/opt/hermes .venv-ci-313/bin/python -m pytest -q -o 'addopts=' -W error -p no:cacheprovider` → **389 passed in 38.25s**.
- `profile_delegate_policy` actual: native async ledger compatible, apertura read-only, sin APIs/columnas incompatibles. Esto valida integración de lectura, no un nuevo ciclo de ejecución/entrega.
- Últimos 30 registros del originador default, fechados entre 2026-08-28 y 2026-09-09: 28 completed, 1 timed_out, 1 cancelled; todos TUI. Los resultados desglosan: 6 ok, 8 blocked, 12 unknown/drifted y 4 failed (incluidos timeout/cancel). No confundir completed con tarea resuelta; blocked puede ser una respuesta correcta. Los 12 unknown tienen parse_method=none y requieren inspección funcional antes de llamarlos fallos.
- Inspección adicional de registros de perfiles nombrados: existen fallos históricos y alguno reciente; no se mezclan con el default ni se atribuyen automáticamente al release actual. No hay benchmark comparable CLI/TUI en esta revisión.
- No se arrancó Herald, no se crearon tokens/rutas, no se lanzó una nueva prueba LLM de Profile Delegate ni se reinició ningún gateway. La evidencia histórica del STATE no equivale a certificación nueva.
- STATE conserva notas de push/restart pendientes; no se ha certificado publicación remota ni igualdad del código cargado por todos los gateways.

## A. Qué mejorar

### 1. Resultado útil sin relajar la veracidad

La separación execution/task/contract/notification/transport es una ventaja. Sin embargo, 12 unknown/drifted en la muestra justifican revisar fricción de contratos antes de añadir transporte distribuido. Separar el modo elegido por el llamador de la exigencia de un sobre de estado. Un informe válido sin `status` debe conservarse como respuesta útil con task_status desconocido, nunca convertirse por heurística en éxito. Explicar concretamente qué falta y cómo continuar.

### 2. Modelo solicitado, resuelto y observado

`core.py:736–830` valida permisos/forma, no un catálogo real de pares proveedor-modelo. `resolve_capability_preset` copia requested_execution y ajusta capacidades; el campo effective_execution no prueba qué backend ejecutó la petición. `tui_runner.py:285–304` envía el override y registra identidades, sin demostrar el modelo efectivo.

Añadir preflight contra las superficies nativas disponibles del perfil destino y procedencia con tres estados: requested, resolved, observed. Credenciales nunca salen del destino. Si no existe evidencia del modelo usado, `observed=unknown`, no rellenarlo con lo solicitado. El razonamiento solicitado tampoco demuestra el razonamiento aplicado por proveedor/proxy.

### 3. Salud y plazos

Tenemos journal, spectator, limpieza, cancelación y estados. Falta una vista compacta que explique dónde está detenido un run, última actividad significativa, calidad del contrato y estado de entrega. Separar deadline total, timeout de arranque y actividad-estancamiento. Un keepalive no debe perpetuar un proceso bloqueado ni una herramienta larga parecer muerta sin prueba.

### 4. Política realmente operable

La política live permite overrides de modelo/proveedor/razonamiento, pero las allowlists de toolsets y skills están vacías: los overrides correspondientes están bloqueados; no implica que los perfiles carezcan de sus herramientas/skills heredadas. Los límites live de concurrencia y duración difieren del README. Hacer esas diferencias visibles y basar cualquier ajuste en consumo/fallos observados. No cambiarlos a ciegas ni tratar límites por HERMES_HOME como un presupuesto global del contenedor.

### 5. Continuidad y transporte sin sorpresas

Ya existe `session_mode=resume` con session_id. Incorporar `continue_from_task_id` autorizado por origen reduce errores y descubrimiento manual. Mantener nuevas sesiones por defecto. Exponer posteriormente `transport_mode=auto|simple|interactive` sin alterar silenciosamente el TUI predeterminado actual.

## B. Qué incorporar de Herald

**Incorporar al núcleo local:**
- Descubrimiento/preflight con error reparable antes del lanzamiento.
- Registro de procedencia del modelo/ruta, diferenciado de la ejecución observada.
- Temporizador de estancamiento por actividad junto con deadline absoluto.
- Continuidad fácil, pero ligada a origen + tarea + perfil, no a un único último chat global por perfil.
- Consultas compactas de runs relacionados y salud, reutilizando los artefactos actuales.

**Capacidades adyacentes, con límites:**
- Inferencia sin agente: útil para extracción/clasificación/resumen corto; investigar primero el helper público host-owned y herramientas existentes. Mantenerla fuera del ciclo de procesos de Profile Delegate.
- HTTP/SSE entre hosts: buen diseño para destinos realmente remotos; extensión opt-in separada con su propio gate de integración.
- Notificación de aprobación pendiente y denegación: interesante para trabajo atendido, pero no introducir autorización positiva remota hasta disponer de ID inmutable ligado al comando exacto.

**No copiar:**
- Un segundo SQLite/outbox propietario para entregar notificaciones: Hermes ya es nuestro dueño de entrega.
- Sesión persistente global por nombre de perfil: mezcla conversaciones independientes del mismo originador.
- `llm_direct` como bypass de políticas/credenciales/model routing del host.
- Otro delegate_subagent paralelo al nativo sin carencia y consumidor concreto.
- Reintentar tareas completas tras un fallo de transporte ambiguo.
- Etiquetas de seguridad excesivas: perfiles no son sandboxes; hop/depth limits no son barreras criptográficas.

## C. Estado comparado

- **Trabajo local entre perfiles:** ambos; nosotros sin necesidad de mantener API/gateway de cada destino.
- **Hosts distintos:** Herald sí; nosotros no.
- **Override modelo/proveedor/razonamiento:** ambos; no es una novedad que nos falte. Herald añade descubrimiento y verificación explícita de alias remotos.
- **Continuidad:** ambos; Herald automatiza último chat por perfil, nosotros requerimos session_id explícito.
- **Entrega después de restart del originador:** nuestra integración usa ledger/cola durable nativos con semántica al menos una vez. Herald documenta listeners ligados al proceso y recuperación manual por status/check; SQLite no equivale a una cola durable.
- **Steer/cancel:** nosotros TUI y ACKs de control; Herald expone `cancel_dispatch`, pero no herramienta de steer en sus 12 registros públicos (`__init__.py:64–76`), aunque el API host dispone de un endpoint steer.
- **Control de aprobaciones:** nosotros deny predeterminado y approve_yolo explícito; no broker. Herald relay deny-only; no aprobación positiva segura.
- **Resultado y contratos:** nosotros separación explícita y defensiva, con fricción observable en resultados unknown. Herald devuelve respuestas y estados de red/ejecución; no es una certificación del trabajo.
- **Auditoría:** nosotros artefactos privados, journal, spectator y descendencia directa. Herald ledger de llamadas y grafo/hops de red.
- **Inferencia sin herramientas:** Herald llm_call y llm_direct opt-in; fuera del alcance actual nuestro.
- **Madurez:** no usar 1.10 vs 1.1 ni número de tests como ranking. Nuestra evidencia local actual es más fuerte para nuestro flujo; no se certifica superioridad global ni rendimiento comparativo.

## Alternativas consideradas

1. **Reemplazar por Herald:** ganamos red e inferencia; perdemos integración local, garantías/UX actuales y asumimos despliegue/credenciales/listeners. Rechazada para la necesidad actual.
2. **Instalar ambos y enrutar según tarea:** reduce desarrollo remoto pero duplica herramientas y políticas. Reservada a un consumidor remoto concreto; no habilitar por defecto.
3. **Evolucionar local-first con contratos nativos:** recomendada. Menor migración, conserva estado y añade las mejoras útiles.
4. **Reescribir Profile Delegate sobre HTTP:** solo reconsiderar si la API nativa ofrece paridad demostrada y un destino real; no crear gateways por estética arquitectónica.

## D. Plan ejecutable completo

Versiones siguientes son hitos funcionales propuestos, no releases publicadas ni permiso para desplegar. Mantener compatibilidad del 1.x; cualquier ruptura requiere decisión versionada.

Grafo: `T0 → T1 → [T2 || T3] → T4 → T5 → T6`.
Ramas adicionales: `T0 → I1 → I2` (inferencia); `T0 → R1 → R2 → R3` (remoto, condicionado a consumidor/autoridad). La implementación del núcleo no depende de estas ramas.

### T0 — Baseline y contrato de compatibilidad

Objetivo: fijar lo que existe y el host que realmente lo ejecuta; no reabrir bugs cerrados por notas antiguas.
- Dependencias: ninguna. Modo: secuencial.
- Superficie: `plans/2026-09-09-herald-comparison-and-roadmap.md`, pruebas existentes; `/opt/hermes` y estados de perfiles son solo lectura.
- Produce: matriz de capacidades host/plugin, diferencias de código cargado, muestra de resultados por perfil/transporte/fecha/revisión cuando esa revisión esté disponible. No asumir revisión histórica si no se registró.
- Aceptación: suite actual, `profile_delegate_policy`, inventario sanitizado; preflight no muta state.db ni arranca procesos. Revisar causas de los 12 unknown con autorización de lectura, sin publicar contenido de tareas.
- Gate real antes de implementación de integración: prueba local inocua new → resultado → resume → resultado, más steer/cancel del transporte vigente y lectura de su entrega. Sin reinicio de producción para probar recovery: entorno aislado o ventana autorizada.
- Recuperación: ninguna migración; preservar artefactos originales.

### T1 — Hito: resultados comprensibles y diagnóstico útil

Objetivo: distinguir respuesta útil, éxito declarado, contrato y ejecución sin falsos verdes.
- Depende: T0. Modo: secuencial.
- Escritura: `core.py` (normalización/proyección), `__init__.py` (descripciones/esquemas), `test_reliability_reset.py`, fixtures sanitizadas bajo `tests/fixtures/profile_delegate/`.
- Produce: `result_availability`/diagnóstico equivalente aditivo, instrucciones inequívocas por output_mode y mensajes de corrección que no exigen reejecutar trabajo.
- No hacer: parsear palabras positivas para convertir unknown en ok; inventar éxito por exit=0; envolver a la fuerza todo JSON custom; reparar con otra llamada LLM automática.
- Aceptación: todos los históricos y adversariales conservan sus outcomes; texto/Markdown/JSON custom se recuperan completos según contrato; missing status sigue unknown. Prueba real de cada modo sin efectos externos. Gate completo del proyecto.
- Rollback: campos aditivos, lectores antiguos siguen válidos; revertir código sin tocar runs.

### T2 — Hito: elegir el modelo con evidencia

Objetivo: descubrir y validar rutas del perfil destino, sin exponer secretos ni recrear el router.
- Depende: T1. Paralelizable con T3; evitar escritura concurrente de `core.py`/`__init__.py`: implementación nueva aislada y wiring en T4.
- Escritura: nuevo `model_preflight.py`, `test_model_preflight.py`; wiring posterior en core/bootstrap/TUI/wrapper.
- Produce: consulta opcional desde policy/preflight con provider+model válidos, ruta heredada, motivos de indisponibilidad y requested/resolved/observed.
- Diseño: usar API pública host-owned si existe; si no hay seam estable, reportar unsupported en modo estricto, no importar funciones privadas arbitrarias ni probar credenciales haciendo llamadas LLM. Catálogo puede no ser exhaustivo; hacer explícita esa limitación. Preservar overrides heredados con advertencia hasta aprobar un cambio de semántica estricta.
- Aceptación: modelo inexistente, proveedor incongruente y alias ambiguo fallan antes de crear run bajo modo estricto; herencia no muta config; ninguna credencial en JSON/logs; una llamada inocua valida procedencia disponible y marca unknown donde no pueda observarse.
- Rollback: desactivar preflight estricto sin borrar procedencia ni cambiar configuraciones de destino.

### T3 — Hito: salud observable y plazos correctos

Objetivo: saber si el run trabaja, espera o está atascado sin confundir silencio con fallo.
- Depende: T1. Paralelizable con T2, con ownership separado.
- Escritura: `event_schema.py`, `event_journal.py`, `spectator.py`, `test_event_journal.py`, `test_spectator.py`; wiring posterior en T4.
- Produce: proyección compacta de fases, última actividad significativa, tiempos de arranque/primera actividad, deadline restante, contrato y entrega. Consumo/API calls/coste solo si la fuente los ofrece; ausente = unknown, nunca cero ficticio.
- Presupuestos: medir latencias, silencios legítimos y RSS antes de elegir valores. Conservar deadline duro. Clasificar activity vs keepalive y documentar límites por perfil frente a recursos compartidos.
- Aceptación: eventos continuos no vencen el deadline; keepalives no ocultan estancamiento; herramienta larga no es eliminada sin política explícita; lector no muta runs; resumen bounded señala qué omite y cómo recuperar el detalle.
- Rollback: proyección aditiva, journal v1 legible; no convertir ni borrar eventos históricos.

### T4 — Hito: integración local y continuación segura

Objetivo: unir modelos/salud y continuar una tarea sin buscar sesiones manualmente.
- Depende: T2 y T3. Modo: secuencial; dueño único del wiring.
- Escritura: `core.py`, `__init__.py`, `child_bootstrap.py`, `tui_runner.py`, `test_profile_delegate.py`, `test_tui_rpc.py`, README.
- API: argumento aditivo `continue_from_task_id`, incompatible con session_id/profile discordantes; resolver desde artefacto autorizado del origen. Nunca “último chat de reviewer” global. Sesión nueva sigue predeterminada.
- Reanudar requiere prueba de perfil/session_id y política vigente, no los permisos viejos. Dos continuaciones simultáneas de la misma sesión se serializan o rechazan con error reparable; no fusionan prompts.
- Aceptación: new → continue recuerda un marcador inocuo; otro origen no accede; sesión ausente/perfil distinto falla cerrado; nested results se conservan; native delivery sigue con identidad task-id y separación de estados.
- Rollback: retirar parámetro nuevo conserva `session_mode=resume`; sin migración de sesiones ni DB.

### T5 — Hito: transporte adecuado sin degradar controles

Objetivo: conservar steer como capacidad central, habilitar simple/interactive explícitos y decidir los fallbacks de auto con mediciones.
- Depende: T4. Modo: secuencial.
- Escritura: `core.py`, `__init__.py`, `tui_runner.py`, `tui_rpc.py` solo si necesario, `test_sync_lifecycle.py`, `test_tui_rpc.py`, README.
- API propuesta: `transport_mode=auto|simple|interactive`. En primera compatibilidad, omitirlo conserva comportamiento actual; interactive/TUI sigue siendo el camino normal de background porque mantiene steer. Auto elige interactive para runs background o live-steerable y solo puede degradar a simple antes de que el prompt sea aceptado; modo simple usa el camino CLI existente como fire-and-forget explícito.
- Contrato steer tomado del harness nativo de subagentes: ownership exacto de sesión/transporte/generación, `accepting_steer` cerrado atómicamente antes de completar, ACK `queued` distinto de entrega, entrega en el siguiente boundary seguro y `missed_steer` terminal si el run acaba antes. Persistir request/accept/deliver/miss sin guardar texto sensible fuera de la política existente.
- No construir una jerarquía genérica de adapters para dos caminos existentes. No reintentar por el otro transporte después de una aceptación ambigua: antes de lanzar puede elegirse otro, después solo reconciliar o reanudar la misma sesión bajo contrato existente.
- Simple declara antes del lanzamiento que no soporta steer; cancellation sigue limpiando/reaping el proceso y no debe reportar ACK interactivo inexistente. Nunca cambiar de transporte tras aceptación o aceptación ambigua.
- Aceptación: mismos prompts inocuos/perfil/modelo comparados por arranque, éxito técnico, calidad de resultado, RSS y cancelación; repeticiones acordes con variabilidad observada, sin número de conveniencia. Native notifications comprobadas en ambos. Test real detached: originador termina, resultado persiste y entrega se recupera por Hermes en entorno autorizado.
- Gate: interactive sigue predeterminado mientras steer sea requisito clave. Las mediciones deciden si simple merece fallback pre-aceptación u opt-in, no si se elimina steer del camino normal.
- Rollback: restaurar selector previo; no migrar ni reejecutar runs activos; activar solo para runs nuevos.

### T6 — Release/rollout del núcleo completo

Objetivo: entregar T1–T5 como capacidad compatible comprobada, no solo código y tests.
- Depende: T5. Modo: secuencial.
- Escritura: README, CHANGELOG, plugin.yaml, pyproject.toml y lock solo si cambia versión/dependencias, STATE, TODO, handoff; `scripts/validate_release.py` si cambia registro.
- Aceptación: gate `.agents/validation.md`, suite Python soportada, Ruff, registro, diff, revisión independiente centrada en origins/concurrencia/model routing/limpieza. Cerrar hallazgos y repetir su cono de pruebas, no toda la historia.
- Seguridad: fixture de denegación real sin ejecutar comando peligroso; permisos y secretos no se amplían. Retención solo diagnóstico/dry-run; prune y reconciliación mutante quedan separados y requieren aprobación.
- Activación: aprobación única para publicación/restart/cambios de política de perfiles; comprobar versión cargada y workflow real desde el canal. No marcar live por existir un commit.
- Rollback: versión previa y configuración preservadas; ninguna migración destructiva ni eliminación de artefactos. No matar runs en curso para activar.

## Rama I — Inferencia ligera (adyacente, no inflar Profile Delegate)

### I1 — Gate de utilidad y API host
- Depende T0. El seam público ya existe en el host inspeccionado: `hermes_cli/plugins.py:1564–1579`, `PluginContext.llm` → `agent.plugin_llm.PluginLlm`, con permisos fail-closed por plugin. Herald lo recibe en `__init__.py:82–90`. Falta validar contrato completo y llamada real, no descubrir/inventar un router. También existe `ctx.subagent_lifecycle` (`plugins.py:1581–1597`): antes de copiar el subagent wrapper de Herald, comparar esa API nativa.
- Produce contrato de inferencia sin agente: mensajes, provider/model, salida estructurada, límites, uso y cancelación según soporte host. Comparar con herramientas ya existentes; eliminar duplicados antes de añadir otra.
- Gate: consumidor real de clasificación/extracción y prueba inocua por ruta existente. No inventar un router privado ni un fallback llm_direct.

### I2 — Implementación separada si I1 pasa
- Superficie propuesta: plugin hermano `profile-inference/`, no autorizado para crear en este turno; no toca estado/runs de Profile Delegate.
- Una herramienta pequeña sobre API pública con allowlist, sin terminal/browser/skills/memoria y sin credentials en argumentos.
- Aceptación: salida estructurada inválida explícita, proveedor no permitido bloqueado antes de llamada, timeout y usage honestos; prueba real del consumidor y comparación con agente completo.
- Rollback: deshabilitar plugin; ningún estado de delegación depende de él.
- Si no hay API pública compatible o consumidor, cerrar como no necesario/bloqueado, sin stub publicado.

## Rama R — Delegación remota completa, solo con destino real

### R1 — Gate de frontera real
- Depende T0 y aprobación para endpoint/credencial/transmisión de datos. Perfil remoto explícito; TLS o red privada; token dedicado fuera del repositorio.
- Leer `/v1/models` y capacidades actuales; comprobar soporte de runs/status/events/stop y restricciones de modelo. No asumir que el comentario de Herald sobre aliases describe todas las versiones del host: nuestro api_server ya distingue overrides por endpoint/proveedor.
- Ejecutar tarea inocua → observar SSE/status → recuperar tras corte del listener → stop otra tarea inocua. Si no existe destino/autoridad, detener aquí; ningún despliegue especulativo.

### R2 — Extensión remota opt-in
- Depende R1. Superficie propuesta separada `profile-delegate-remote/` o módulo único solo si ambos consumidores justifican seam compartido; decisión con evidencia de R1 antes de crear abstracción.
- Configuración por target: endpoint fijo, referencia de credencial, capacidades permitidas y aliases/rutas. Rechazar redirects autenticados, destinos suministrados libremente por modelo y mismatches de ruta.
- Persistir handle remoto y correlación en artefactos; usar entrega nativa del originador, no otro outbox. SSE con reconexión/polling de status; nunca repetir POST de trabajo tras resultado ambiguo sin idempotencia nativa probada.
- Propiedad de sesión: origin + target + task/session exactos. Sin memoria de chat global por target.
- Aprobaciones: solo mostrar petición sanitizada y permitir denegación. Aprobar requiere ID inmutable verificable; FIFO no basta. Ausencia de esa capacidad bloquea aprobación positiva, no se sortea con yolo.

### R3 — Verificación y activación remota
- Depende R2. Pruebas de 401, redirect, SSE caído, target reiniciado, resultado duplicado, origin distinto, cancelación ambigua y offline.
- Evidencia real en destino autorizado, entrega nativa recuperable y secretos ausentes de artefactos. Target restart no implica trabajo durable; reflejar lost/unknown si el host no lo garantiza.
- Rollback: deshabilitar nuevas llamadas, conservar handles/resultados y consultar/cancelar trabajos existentes bajo autoridad; no borrar el ledger nativo.

## Riesgos y controles decisivos

- Compatibilidad Hermes: APIs privadas cambian → feature detection y gate previo; no core patches.
- Mezcla de contexto: continuación global → ownership exacto y pruebas multi-origin.
- Coste/modelo inesperado: requested confundido con observado → procedencia explícita y strict opt-in.
- Tarea duplicada con efectos: retry tras aceptación ambigua → nunca nuevo run automático; status/resume del mismo.
- Runtime sin recursos: concurrencia alta por perfil → medir RSS/cgroup y suma real; no aumentar límites por intuición.
- Estado perdido: migración innecesaria → campos aditivos y lectores legacy; si alguna migración futura resulta necesaria, backup inspeccionado/restauración probada y aprobación antes de tocarla.
- Privacidad: logs/fixtures con tareas reales → extracción sanitizada y no publicar resultados internos.

## Referencias de código

Nuestro repositorio: https://github.com/Heeervas/profile-delegate-plugin
- `core.py:736–863`: ejecución solicitada, preflight y preset.
- `core.py:1799–1888`: normalización conservadora de resultado.
- `core.py:2207–2273`: gate read-only de ledger nativo.
- `core.py:2277–2400`: identidad y entrega de completion.
- `core.py:2727–2860`: dispatch, dedupe, artefactos, selector actual.
- `tui_runner.py:252–354`: arranque, sesión, overrides, deadline y final.
- `TODO.md:30–56`: transporte y observabilidad pendientes, non-goals.

Herald: https://github.com/bennybuoy/hermes-herald/tree/a033d52002a4c808ad89c1713a188449b27465de
- `tools.py:1812–1903`: verificación de rutas anunciadas.
- `tools.py:2430–2518`: chat persistente.
- `callback.py:1374–1418`: sesión guardada por perfil.
- `README.md:338–356`: auto-delivery y límites tras restart.
- `README.md:395–411`: límites de subagent por contexto host y razonamiento.
- `README.md:463+`: llm_direct opt-in y bypass de routing host.
- Documentación host consultada: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation/

Cierre: priorizar resultado útil, procedencia, salud y continuidad; después transporte medido. Red e inferencia son ramas completas con gates, no excusas para reescribir el ejecutor local.
