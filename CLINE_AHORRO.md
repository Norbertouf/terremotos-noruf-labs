# Política transversal de ahorro de trabajo

Aplicar antes de cualquier tarea en Terremoto_NorUF_Labs. Ahorrar lecturas,
análisis, ejecuciones y comunicación redundantes, sin sacrificar calidad,
seguridad, cumplimiento del alcance, corrección de datos ni trazabilidad.

## Contexto y archivos

- Partir del estado Git, del último checkpoint y de la continuidad pertinente.
  Distinguir decisiones vigentes de notas históricas.
- No releer todo el proyecto. Buscar primero lo necesario y abrir solo los
  archivos o fragmentos relacionados con la unidad autorizada.
- Antes de abrir más de cinco archivos en una tarea, justificar brevemente
  por qué es necesario y qué se pretende resolver. Contar el alcance total,
  no fragmentar lecturas para evitar la justificación.
- No repetir análisis cerrados. Reabrirlos solo ante cambios, evidencia nueva,
  contradicción demostrable o petición explícita del usuario.
- Al retomar tras una interrupción, comprobar qué se completó; no rehacer ni
  revertir trabajo válido. Reutilizar checkpoints y resultados ya validados
  cuando correspondan al mismo código, configuración, datos y alcance.
- Mantener como referencia las decisiones ya cerradas del proyecto:
  fuentes oficiales, criterios de inclusión, alcance geográfico, comportamiento
  de la interfaz y límites expresamente aplazados.

## Desarrollo y pruebas

- Trabajar en unidades pequeñas y dentro del alcance autorizado. Durante el
  desarrollo, ejecutar pruebas focales sobre el comportamiento cambiado.
- Reservar la regresión completa para hitos: cierre de unidad, integración,
  checkpoint que la requiera o petición explícita. Un fallo o riesgo nuevo que
  afecte a varios componentes también puede justificar ampliarla.
- Antes de ejecutar cualquier batería completa, justificar brevemente por qué
  es necesaria en ese punto. La justificación no exige pedir permiso adicional
  si el trabajo ya está autorizado.
- No repetir una batería ya válida sin cambios relevantes, fallos pendientes o
  exigencia expresa.
- Los cambios solo documentales requieren comprobaciones documentales, salvo
  que alteren instrucciones, configuración o datos ejecutables.
- Los cambios exclusivamente visuales deben verificarse con las comprobaciones
  técnicas necesarias y, cuando corresponda, quedar pendientes de revisión
  visual humana sin simular que esta se ha realizado.
- Nunca presentar un resultado reutilizado como recién ejecutado. Identificar
  checkpoint y alcance de la evidencia; distinguir PASS, FAIL, BLOCKED y ERROR.
- No rebajar filtros, criterios geográficos, validaciones, aserciones ni
  controles para ahorrar trabajo o conseguir verde.
- Ante contradicción con una decisión congelada, dato oficial, prueba previa o
  material validado, detener y notificar antes de cambiarlo.
- No ampliar el alcance funcional por iniciativa propia. Las mejoras aplazadas
  o futuras se mantienen fuera hasta autorización expresa.

## Fuentes y datos

- Priorizar las fuentes oficiales ya definidas para el proyecto.
- No sustituir una fuente oficial por una inferencia, aproximación o fuente
  secundaria sin necesidad justificada y autorización cuando cambie el
  comportamiento del producto.
- Distinguir claramente:
  - dato recibido de la fuente;
  - dato transformado por la aplicación;
  - inferencia o clasificación propia.
- No afirmar que falta un evento, que no fue sentido o que está fuera de
  cobertura cuando la fuente solo indique ausencia, indisponibilidad o error.
- No ocultar contradicciones entre fuentes o entre señales de clasificación.
  Registrarlas y conservar el comportamiento acordado.

## Comunicación y cierre

- Respuestas y actualizaciones breves: resultado, cambios, evidencia,
  pendientes y decisiones necesarias.
- Evitar repetir planes, listados o explicaciones ya cerradas.
- Agrupar comprobaciones independientes cuando sea seguro y útil, sin perder
  sus resultados ni ejecutar trabajo innecesario.
- Registrar continuidad suficiente para retomar sin reconstruir todo el
  historial: rama, HEAD, relación con remoto, árbol de trabajo, pruebas
  relevantes, bloqueos y siguiente unidad.
- Mantener las autorizaciones de commit, push, merge, red y secretos.
  Esta política no amplía permisos ni sustituye requisitos de seguridad o
  instrucciones superiores.
- Antes de una integración o publicación, verificar solo lo necesario para ese
  hito y detenerse ante cualquier divergencia, conflicto o decisión de producto
  no resuelta.

## Principio

Mínima repetición necesaria, con evidencia suficiente y trabajo completo.

En este proyecto:

**Que lo que esté, sirva; y que lo que diga, sea verdad.**