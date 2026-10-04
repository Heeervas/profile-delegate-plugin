# Terminar la simplificación y reducir tests

Cerrar el refactor de Profile Delegate conservando su funcionamiento. **`/goal` de Hermes queda fuera del alcance.** Se descarta la importación de skills de Builder.

El punto de partida es `3f82526`, con worktree limpio y última suite completa de 715 casos aprobada. Los TODO históricos no se tomarán como pendientes cuando los commits y la evidencia posterior demuestren que ya están resueltos.

## Trabajo cerrado que no se repetirá

- Contratos y publicación terminal compartidos; preparación y comandos del hijo consolidados.
- Worker como productor de completion y watcher como consumidor.
- Correcciones de identidad del supervisor, lectura coherente de resultados y steering.
- Consolidaciones de fixtures y retiradas ya documentadas.
- Investigación de las sustituciones rechazadas de reasoning y async: se conserva la implementación actual.

## Implementación mediante subagentes

- Todas las implementaciones las harán subagentes **`gpt-6.1-sol`, razonamiento `medium`**.
- Yo dirigiré el trabajo, asignaré porciones pequeñas y revisaré los diffs y sus pruebas.
- Cada encargo tendrá archivos delimitados, duplicación concreta que eliminar, contratos que conservar y comprobación focalizada. Sin encargos abiertos de «seguir optimizando».
- Solo habrá trabajo paralelo cuando los archivos sean independientes. Cada lote terminará revisado, comprometido localmente y con worktree limpio.

## Trabajo restante

- Consolidar el setup repetido que todavía quede usando los helpers existentes.
- Retirar tests equivalentes únicamente cuando otro test conserve la detección del mismo defecto; mantener escenarios distintos de seguridad, transporte y recuperación.
- Eliminar código de producción sin consumidores o duplicado que estas consolidaciones permitan retirar.
- Contar helpers y auxiliares en la reducción neta. Sin ocultar casos en bucles ni reducir líneas mediante formato.

## Validación y cierre

Reutilizar evidencia válida; ejecutar checks focalizados por lote y la validación completa sobre el candidato final. Si cambia ejecución, comprobar el recorrido afectado con Hermes real.

Entregar commits, worktree limpio y cifras finales frente al histórico y al estado actual. Sin modificar core, YAML o perfiles, publicar ni reiniciar el gateway. Distinguir funcionamiento probado en procesos nuevos de activación en el gateway.
