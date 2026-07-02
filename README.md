# Interface Tester

Aplicacion de escritorio en Python para probar paneles mediante una conexion serial y definiciones de interfaz `.dat` cargadas por el usuario.

Version actual: `0.2.39`.

## Cambios recientes

### Version 0.2.39

- La pestana `Report` permanece oculta al iniciar y se puede mostrar u ocultar desde `View > Show Report`.
- Se agrego la pestana opcional `Help`, disponible desde `View > Show Help`.
- Ocultar `Report` o `Help` no elimina sus controles, resultados ni estado actual.
- `Help` incluye los comandos transmitidos con mayor frecuencia, ejemplos de uso, formatos de respuesta y advertencias para comandos que modifican configuracion persistente o mueven hardware.
- La release publica no contiene definiciones de panel `.dat`; deben cargarse externamente desde la GUI.

### Version 0.2.38

- Se agrego el test automatico de displays basado en campos `BIT-FLD` de 7 u 8 bits detectados en el `.dat`.
- Cada word de display recibe dos caracteres para evitar que el comando `S` se extienda sobre words siguientes.
- Para ATCTCAS se detectan `w30`, `w31` y `w32`; el mapa inicial `12 34 56` permite identificar la posicion fisica de los seis digitos.
- La secuencia configurable recorre valores alfanumericos, permite ajustar el tiempo por paso, detener el barrido y restaurar `00` al finalizar.

## Ejecutar en desarrollo

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Smoke sin hardware

Antes de empaquetar o probar con paneles reales puedes correr un smoke de GUI sin abrir conexion serial:

```powershell
python tools\gui_smoke.py
```

El smoke requiere que el `.dat` A320 este disponible localmente. Valida comandos de luces, planes de entradas/salidas, reporte, estado operativo, pestanas opcionales y round-trip de sesion.

## Flujo actual

1. Presiona `Cargar .dat` y selecciona una definicion de interfaz.
2. Revisa la tabla de paneles disponibles para test. La tabla muestra familias con luces, entradas o salidas `CO` no-luz detectadas.
3. Refresca y selecciona el puerto serial.
4. Escribe los baudios.
5. Conecta.
6. Presiona `Info` para enviar `i` y detectar la direccion de la motherboard.
   - Si la direccion existe en varios paneles y la tarjeta no reporta canal suficiente para distinguirlos, selecciona el panel correcto en la ventana de candidatos.
   - El panel y la tarjeta detectados permanecen visibles en la cabecera, sin importar la pestana activa.
   - `Cambiar direccion` permite buscar un panel del `.dat`, revisar lado/variante, canal y direccion, y confirmar la secuencia `A <direccion>`, `SAVE`, `i`.
7. Opcionalmente presiona `?` para consultar comandos soportados por la tarjeta.
8. Selecciona o confirma el panel.
   - Si `Info` detecto un panel distinto al seleccionado, la app pide confirmacion antes de enviar luces.
   - Usa `Definir detectado` si necesitas escoger manualmente la variante conectada dentro de una familia agrupada.
   - Usa `Detalle panel` para revisar variantes, direcciones, luces, entradas y salidas `CO` no-luz interpretadas desde el `.dat`.
9. Abre la pestana `Luces` y revisa `Comandos generados` para validar los `word`, mascaras y comandos ON/OFF antes de enviar.
   - Usa `Copiar ON`, `Copiar OFF`, `Copiar detalle` o `Exportar comandos` si necesitas preparar evidencia sin enviar comandos al panel.
   - Selecciona una fila y usa `Encender word` o `Apagar word` para probar solo ese `word`.
   - Selecciona una senal dentro del `word` y usa `Encender senal` o `Apagar senal` para aislar una luz/campo especifico.
   - Si el panel no tiene luces con el filtro actual, esa seccion lo indica y no permite copiar/exportar comandos vacios.
10. Elige el tipo de luces:
   - `Todas`: backlights, lights y annunciators.
   - `Backlight`: solo senales de backlighting.
   - `Lights / Ann`: luces y annunciators, excluyendo backlighting.
11. Elige el perfil de intensidad:
   - `Raw FF`: enciende cada campo con todos sus bits en `1`.
   - `Percent 100`: en campos `FLOAT-FLD`, escribe `100` decimal (`64` hex).
12. Usa `Encender luces`, `Apagar luces` o `Test automatico`.
13. Manten `Apagar al finalizar` activo si quieres que el test automatico mande OFF al terminar.
14. Usa `Detener y apagar` para interrumpir una secuencia automatica y mandar OFF al panel seleccionado.
15. Usa `Iniciar checklist` para saltar al primer panel pendiente y los botones `OK y siguiente`, `FAIL y siguiente` o `N/A y siguiente` para registrar y avanzar rapido.
16. Usa `Estado operativo` para revisar o exportar una foto rapida de la prueba antes de enviar comandos.
17. Usa `Checklist pre-HW` antes de conectar panel real para revisar pasos y evidencia minima.

## Configuracion recordada

La app guarda automaticamente la configuracion operativa de la ultima sesion:

- Ultimo `.dat` cargado y carpeta de definiciones.
- Puerto serial seleccionado, baudios y fin de linea.
- Tipo de luces, perfil de intensidad, duracion del test y `Apagar al finalizar`.
- Categoria de salidas `CO` no-luz usada en `Detalle salidas` y `Exportar salidas`.
- Tiempos seriales: espera de respuesta, silencio para cerrar lectura, pausa entre comandos y ventana de lectura cruda.
- Valores usados en la seccion de displays.

En Windows se guarda en:

```text
%LOCALAPPDATA%\InterfaceTester\settings.json
```

Si el ultimo `.dat` sigue existiendo, la app lo carga automaticamente al iniciar.

## Diagnostico serial

La pestana `Terminal` contiene el diagnostico serial, el registro general y un campo para enviar comandos libres.

- `Leer crudo`: lee bytes disponibles durante la cantidad de segundos indicada.
- `Guardar log serial`: guarda la traza TX/RX en `Diagnostics`.
- `Limpiar log serial`: borra la traza serial de la sesion actual.
- `Resp. s`: tiempo maximo para esperar respuesta despues de enviar un comando.
- `Silencio s`: tiempo sin bytes recibidos para considerar cerrada una respuesta.
- `Pausa cmd s`: pausa entre enviar un comando y empezar a leer su respuesta.

El log serial incluye timestamp, origen, direccion (`TX`/`RX`), texto con caracteres de control escapados y bytes en hexadecimal.

La app registra automaticamente en esta traza los comandos enviados desde la GUI y las respuestas recibidas.
Para evitar sesiones demasiado grandes, la app conserva en memoria los ultimos 5000 eventos TX/RX y cuenta cuantos eventos antiguos se descartaron.

## Estado operativo

El boton `Estado operativo` abre una vista Markdown con:

- Version de la app, `.dat`, avion/proyecto y metadata serial.
- Estado de carga del `.dat`, validacion, puerto, conexion, baudios y panel seleccionado.
- Panel detectado por `Info` o manualmente, y advertencia si no coincide con el panel seleccionado.
- Conteo de capacidades mapeadas, comandos ON/OFF, words, avance del checklist, historial de comandos y traza serial.
- Recordatorio de Direct Mode: la app asume que Sim Host ya esta descargado y no intenta controlarlo.

Desde esa ventana puedes copiar el texto o exportarlo en `StatusSnapshots`.

El boton `Checklist pre-HW` abre una lista Markdown para preparar pruebas con hardware real. Incluye contexto del `.dat`, puerto, panel seleccionado/detectado, pasos de conexion, Direct Mode, luces, entradas, salidas y evidencia minima. Desde esa ventana puedes copiar el texto o exportarlo en `PreHardwareChecklists`.

## Entradas en Direct Mode

La seccion `Entradas` permite probar switches, knobs, levers y otros inputs desde la tarjeta conectada:

1. Conecta el puerto serial.
2. Confirma que el Sim Host esta descargado.
3. Presiona `Monitorear VER 3`.
4. Mueve el elemento fisico del panel.
5. Revisa en la pestana `Entradas` la tabla de cambios decodificados y la consola `VER 3` con el flujo crudo recibido.
6. Presiona `Detener monitor` para finalizar la lectura.
7. Usa `Reset panel` si necesitas reiniciar la tarjeta/panel.
8. Usa `Detalle entradas` o `Exportar entradas` para revisar el mapa de senales `CI` del panel/familia seleccionada.

Cuando la respuesta de `VER 3` contiene pares `word/hex`, la app intenta decodificarlos contra las senales `CI` del `.dat`.
El primer valor visto de cada word se registra como `baseline`: establece el estado inicial, pero todavia no hay una lectura anterior con la cual calcular un cambio. `baseline_signal` identifica senales activas dentro de esa primera lectura. Cada lectura posterior se compara con la lectura inmediatamente anterior; si coincide con una senal `CI` se registra como `changed`.
`unmapped_change` significa que el firmware reporto un cambio real, pero la mascara modificada no corresponde a ninguna senal `CI` del panel seleccionado en el `.dat`. La tabla conserva la mascara como `Sin CI para mask xxxx` para facilitar la correccion de la definicion.
Si el cambio no coincide en orden normal pero si coincide exactamente al reflejar los 16 bits, se registra como `changed_mirrored`. Es una inferencia visible para drivers que publican algunos words con el orden opuesto; el archivo `.dat` no se modifica automaticamente.
Si la senal tiene `FLIP`, la consola muestra valor `raw` y valor `logico`.
La recepcion reconstruye lineas aunque los bytes lleguen fragmentados en varias lecturas seriales. Los cambios que no coinciden con una mascara del `.dat` se resaltan y muestran las senales y mascaras esperadas para ese word.

Las entradas analogicas `FLOAT-FLD` dependen de que el firmware las publique en modo verbose. Si no aparecen, usa el comando libre `ANALOG` para consultar la sensibilidad configurada; la app no modifica esa sensibilidad automaticamente.
Al detener el monitor se detiene la lectura de la aplicacion, pero por ahora no se envia `VER 0`, ya que ese comportamiento queda pendiente de validar con hardware.

Para filtrar el mapa de entradas, la app usa primero el panel detectado por `Info` o manualmente. Si no hay panel detectado, usa el panel/familia seleccionado. Si no hay seleccion clara, intenta usar todas las entradas `CI` del `.dat`.
`Detalle entradas` abre un plan Markdown con resumen por word, senales `CI`, tipo, bits, flags como `FLIP` y comentarios del `.dat`.
`Exportar entradas` guarda ese plan en `InputPlans`.

## Displays e indicadores

La pestana `Salidas` permite enviar comandos directos adicionales:

- `Enviar display`: manda `S word texto`, por ejemplo `S 38 105435`.
- `Test automatico display`: detecta los words con campos `BIT-FLD` de display de 7 u 8 bits y ejecuta un mapa de posiciones seguido por la secuencia configurada, normalmente `0..9`.
- El barrido envia exactamente dos caracteres por word (`S <word> 11`, etc.) para impedir que el comando `S` continue escribiendo sobre los words siguientes. En ATCTCAS usa `w30`, `w31` y `w32`, primero con el mapa `12 34 56` y luego con cada digito repetido.
- `Paso s` controla el tiempo visible de cada patron, `Detener` interrumpe el barrido y `Restaurar 00` deja todos los words probados en cero al finalizar.
- `demo`: inicia demo/self-test del indicador si el firmware lo soporta.
- `ST`: inicia self-test del indicador si el firmware lo soporta.
- `ST_Brushless`: inicia self-test para brushless repeater si aplica.
- `Detalle salidas`: abre un plan Markdown con salidas `CO` no-luz detectadas en el `.dat`: displays, indicadores, matrices, enables, discretas/CB, valvulas y solenoides.
- `Exportar salidas`: guarda ese plan en `OutputPlans`.
- `Categoria`: filtra el plan de salidas por `Display`, `Indicator`, `Enable`, `Matrix/Sign`, `Actuator` o `Discrete/CB`.

El test automatico de display exige un panel exacto detectado o una familia con una sola variante y no se inicia mientras `VER 3` o un test de luces esten activos.
El plan de salidas no genera comandos raw automaticos para actuadores, indicadores o discretas; se usa como mapa antes de decidir si conviene enviar `demo`, `ST`, `ST_Brushless` o un comando `w` manual.

## Pestanas opcionales

El menu `View` permite mostrar u ocultar dos pestanas que no aparecen al iniciar:

- `Show Report`: muestra la pestana `Report`, que conserva resultados, comentarios y controles aunque vuelva a ocultarse.
- `Show Help`: muestra la pestana `Help`, con una referencia de comandos y respuestas seriales.

La ayuda integrada documenta, entre otros:

- `i` para solicitar informacion de tarjeta.
- `?` para pedir la ayuda soportada por el firmware.
- `VER 3` para monitorear entradas.
- `w <word> <hex>` con ejemplos `00ff`, `ff00`, `ffff` y `0000`.
- `S <word> <text>` para displays compatibles.
- `A <address>` y `SAVE` para asignacion persistente de direccion.
- Formatos comunes recibidos por `Info` y `VER 3`.
- Significado de `baseline`, `baseline_signal`, `changed` y `unmapped_change`.

## Reportes

La pestana `Report` guarda resultados por panel durante la sesion y exporta archivos en `Reports`. Esta pestana inicia oculta y se activa desde `View > Show Report`.

Flujo recomendado:

1. Selecciona o detecta el panel.
2. Ejecuta el test necesario.
3. Marca `OK`, `FAIL`, `N/A` o `Not tested`.
4. Escribe un comentario si aplica.
5. Presiona `Guardar panel`.
6. Repite con los demas paneles.
7. Presiona `Guardar reporte`.

Al guardar reporte se generan cuatro archivos con el mismo timestamp:

- `interface_test_YYYYMMDD_HHMMSS.md`: reporte completo en Markdown.
- `interface_test_YYYYMMDD_HHMMSS_results.csv`: matriz de resultados por panel para abrir en Excel.
- `interface_test_YYYYMMDD_HHMMSS_commands.csv`: historial de comandos y respuestas para abrir en Excel.
- `interface_test_YYYYMMDD_HHMMSS_inputs.csv`: historial de entradas `VER3 decode` para abrir en Excel.

Los CSV incluyen contexto de la prueba en cada fila: archivo `.dat`, puerto, baudios, fin de linea, tarjeta detectada, panel detectado, panel seleccionado, filtro de luces, intensidad y tiempos seriales.
El CSV de resultados incluye ademas los contadores de luces, words de luces, entradas, words de entradas, salidas `CO` no-luz y words de salidas por familia.
El CSV de comandos tambien incluye `status` para diferenciar respuestas `OK`, comandos iniciados y comandos sin respuesta.
El CSV de entradas incluye word, valor anterior/actual, mascara cambiada, panel, senal, tipo, bits, flags, valor raw, valor logico, comentario y linea cruda recibida.

Para avanzar mas rapido:

- Usa el filtro `Estado` para ver `Todos`, `Pendientes`, `Con estado`, `OK`, `FAIL`, `N/A` o `Mixed`.
- Usa `Siguiente pendiente` para saltar al proximo panel sin resultado.
- Usa `Guardar y siguiente` para guardar el resultado del panel actual y avanzar al siguiente pendiente.
- Usa `Iniciar checklist` y los botones rapidos `OK/FAIL/N/A y siguiente` para recorrer todos los paneles pendientes.

El reporte incluye:

- Fecha y resumen de resultados.
- Matriz de resultados por panel/familia.
- Comentarios del tecnico por panel.
- Archivo `.dat` cargado.
- Estado de conexion serial.
- Informacion detectada con `i`.
- Panel detectado y seleccionado.
- Tipo de luces e intensidad.
- Tiempos seriales usados para esperar respuestas.
- Historial de comandos enviados y respuestas recibidas.
- Estado de cada comando (`OK`, `Iniciado` o `Sin respuesta`).
- Historial de entradas decodificadas desde `VER 3`.

Usa `Limpiar historial` para empezar un nuevo registro dentro de la misma sesion de app.
Usa `Limpiar resultados` para reiniciar la matriz de resultados sin borrar el historial de comandos.
Cuando `Info` detecta una direccion distinta, la app inicia automaticamente un contexto nuevo y limpia comandos, entradas, resultados y traza del panel anterior. El comando `i` y la traza de la tarjeta nueva se conservan.

## Sesiones de prueba

Usa `Guardar sesion` para pausar una prueba y continuarla despues. La sesion se guarda en formato JSON dentro de `Sessions`.

La sesion incluye:

- `.dat` usado.
- Resultados por panel.
- Historial de comandos.
- Traza serial TX/RX.
- Historial de entradas decodificadas.
- Ultimo baseline conocido de entradas `VER 3`.
- Panel detectado, comentario actual, tipo de luces, categoria de salidas, configuracion de test y tiempos seriales.

Usa `Cargar sesion` para restaurar una sesion guardada. Si el `.dat` original no existe en la ruta guardada, la app muestra un error y no modifica la sesion actual.
Al restaurar, la app intenta volver al panel/familia que estaba seleccionado; si un filtro de la tabla lo oculta, limpia esos filtros y reintenta la seleccion.

La app trabaja en Direct Mode y asume que el Sim Host ya esta descargado. No intenta controlar, detener, iniciar ni verificar el Sim Host.

Los paneles indexados se agrupan por familia. Por ejemplo, si el `.dat` contiene `RMP[0]`, `RMP[1]` y `RMP[2]`, la lista muestra un solo `RMP`.
`Detalle panel` abre una vista Markdown con variantes, canal, direccion, resumen de capacidades, comandos de luces, senales `CI` y salidas `CO` no-luz. Desde esa ventana puedes copiar el detalle o exportarlo en `PanelDetails`.

La tabla de comandos muestra cada `word`, la mascara calculada y las senales agrupadas. Por ejemplo, si un panel tiene luces en bits `0..7` y `8..15` del mismo word, la mascara resultante es `ffff`. Los comandos transmitidos usan siempre tokens separados, por ejemplo `w 38 ffff`.
Para escritura RAW de luces, bits `0..7` generan el byte bajo (`00ff`) y bits `8..15` generan el byte alto (`ff00`). Esta mascara de escritura es independiente de la representacion usada para decodificar entradas `VER 3`.

Desde esa tabla puedes copiar solo comandos ON, solo comandos OFF o el detalle completo. `Exportar comandos` guarda un Markdown en `CommandPlans` con panel, `.dat`, modo de luces, intensidad, puerto configurado y la tabla de words.
Tambien puedes seleccionar un `word` de la tabla y enviar solo su comando ON u OFF; la app conserva las mismas validaciones de conexion, Direct Mode y panel detectado antes de transmitir.
Debajo de cada `word`, la app lista las senales individuales incluidas y permite enviar ON/OFF solo para la senal seleccionada. El OFF individual usa `w <word> 0000`, por lo que limpia el word completo igual que la prueba por word.

## Validacion del .dat

Al cargar un archivo `.dat`, la app muestra un resumen de validacion y escribe detalles en la consola.

Actualmente valida:

- Paneles usados en senales pero sin `define` activo.
- Direcciones repetidas que pueden ser ambiguas si la tarjeta solo reporta address.
- Direcciones `channel.address` completamente duplicadas.
- Luces `FLOAT-FLD` con anchos distintos de 8 o 16 bits.
- Paneles definidos que no tienen pruebas testeables.

La validacion es informativa: no modifica el `.dat` ni bloquea el uso de la app.
Cuando una direccion ambigua aparece durante `Info`, la app permite escoger manualmente el panel detectado desde una lista de candidatos.
Tambien puedes usar `Definir detectado` para fijar manualmente el panel/variante conectada cuando `Info` no devuelve una direccion parseable.

## Empaquetado Windows

```powershell
.\build_windows.ps1
```

El script:

1. Crea `.venv` si no existe.
2. Instala dependencias desde `requirements.txt`.
3. Corre las pruebas.
4. Limpia `build` y `dist\InterfaceTester`.
5. Genera `dist\InterfaceTester\InterfaceTester.exe` usando `setup.py` y cx_Freeze.

Para reconstruir mas rapido cuando ya instalaste dependencias:

```powershell
.\build_windows.ps1 -SkipInstall
```

Para saltar pruebas durante una iteracion local:

```powershell
.\build_windows.ps1 -SkipTests
```

Se recomienda distribuir la carpeta completa `dist\InterfaceTester`, no un ejecutable comprimido de un solo archivo.

Antes de crear el ZIP de entrega, valida el build actual:

```powershell
python tools\pre_release_check.py
```

Si necesitas correr pasos individuales, usa `python tools\gui_smoke.py`, `python tools\release_check.py` o `python tools\exe_smoke.py`.

## Paquete de entrega

Para generar una carpeta versionada, un ZIP y un checksum SHA256 desde el build actual:

```powershell
.\package_release.ps1 -SkipBuild
```

Para reconstruir y empaquetar en un solo paso:

```powershell
.\package_release.ps1 -SkipInstall
```

El paquete queda en `Releases\InterfaceTester-vX.Y.Z-win` y `Releases\InterfaceTester-vX.Y.Z-win.zip`.
Dentro de la carpeta se incluyen `RELEASE_NOTES.txt`, `release_manifest.json` y `SHA256SUMS.txt`.

Para reducir alertas de Windows Defender/SmartScreen:

- Firmar el ejecutable con un certificado de firma de codigo.
- Evitar compresores tipo UPX.
- Distribuir en formato carpeta o instalador firmado.
- Mantener nombre, version y publisher consistentes en cada release.

Sin firma, Windows puede mostrar "publicador desconocido" aunque la app no sea maliciosa.

La configuracion del ejecutable vive en `setup.py`, incluyendo version, nombre, descripcion e inclusion opcional de `InterfaceDefinition` cuando existen definiciones locales durante el build.

La release publica `0.2.39` no incluye los `.dat` de A320 ni ATR. El operador debe seleccionar la definicion correspondiente mediante `Load .dat`. Esta separacion permite mantener las definiciones fuera de la rama publica `main`.
