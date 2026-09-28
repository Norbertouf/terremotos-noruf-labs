# Estrella Polar — Terremoto_NorUF_Labs

Este proyecto existe para ofrecer información sísmica de Granada y provincia de forma clara, rápida, fiable y útil.

## Principios

- Primero la necesidad real del usuario; después la solución técnica.
- Priorizar datos oficiales y verificables, con el IGN como fuente principal.
- No presentar como cierto lo que no esté demostrado.
- Calidad funcional antes que cantidad de funciones.
- Rapidez, claridad y sencillez de uso.
- Mantener el proyecto ligero, comprensible y fácil de mantener.
- Arquitectura y modularidad son medios, no fines.
- Evitar complejidad que no aporte utilidad real.
- Conservar los nombres oficiales y datos originales cuando la fuente ya los proporciona correctamente.
- Diferenciar claramente entre magnitud, intensidad, ubicación del epicentro y lugar donde fue sentido.
- No alarmar ni exagerar la información sísmica.
- Si existe una opción más simple, fiable y mantenible que logra el mismo objetivo, preferirla.
- Antes de añadir una función, preguntar: ¿aporta utilidad real al usuario?

## Fuentes, datos e incertidumbre

- Distinguir siempre entre:
  - dato proporcionado directamente por una fuente oficial;
  - dato transformado o calculado por la aplicación;
  - inferencia o clasificación realizada por nuestra lógica.
- No convertir ausencia de información en una afirmación negativa.
  Que una fuente no proporcione un dato no significa necesariamente que el hecho no exista.
- No interpretar un error, indisponibilidad, respuesta vacía o recurso no encontrado como prueba de que un terremoto no fue sentido o no ocurrió.
- Cuando existan varias señales o fuentes, no ocultar contradicciones. Mantenerlas visibles en la lógica y tratarlas de forma conservadora.
- No sustituir un dato oficial por una aproximación propia cuando el dato oficial esté disponible.
- No inferir que un terremoto pertenece a Granada únicamente por proximidad si existe un criterio oficial o geográfico más sólido.
- Toda transformación de datos debe conservar su significado original y poder explicarse.
- Si el grado de certeza es insuficiente, mostrar la limitación o no presentar el dato como confirmado.
- Las fuentes secundarias pueden complementar información, pero no deben modificar silenciosamente el significado de los datos oficiales.
- La aplicación debe reflejar correctamente los límites de cobertura de sus fuentes. No debe dar sensación de exhaustividad cuando la fuente utilizada no la garantiza.

## Regla de trabajo

**Calidad alta, alcance contenido.**

Toda modificación futura debe revisarse contra esta Estrella Polar antes de implementarse.

No ampliar el alcance funcional por iniciativa propia cuando una mejora pueda introducir complejidad, nuevas fuentes, nuevas dependencias o cambios de criterio. Las mejoras aplazadas se mantienen fuera hasta una decisión expresa.

## Regla de utilidad y verdad

**Que lo que esté, sirva; y que lo que diga, sea verdad.**

Cada elemento del proyecto debe aportar utilidad real al usuario.

Cada texto, dato, etiqueta, cálculo o interpretación debe ser correcto, claro y estar respaldado por la información disponible.

Si algo no aporta utilidad real, debe cuestionarse su permanencia.

Si algo no puede afirmarse con suficiente certeza, no debe presentarse como si estuviera demostrado.

La aplicación debe preferir reconocer una limitación antes que rellenar una ausencia con una suposición.