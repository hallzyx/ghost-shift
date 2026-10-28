# GhostShift — Product Requirements Document (PRD)

**Versión:** 1.0 — 28 de octubre de 2026  
**Estado:** Propuesta para validación; capacidades no demostradas todavía  
**Contexto:** Meta Global AI Developer Hackathon 2026  
**Track previsto:** Indie Developer  
**Problem statement:** Push the Frontier (preferente; encaje también posible con Build for Your World)  
**Premio complementario potencial:** Best Agentic Use-Case, sujeto a elegibilidad y reglas oficiales  
**Fecha límite de envío:** 4 de noviembre de 2026, 9:00 p. m. hora de Lima

## 1. Resumen ejecutivo

**GhostShift convierte una demostración en video en un verificador visual reutilizable de procedimientos físicos.** Una persona graba cómo se realiza una tarea estructurada; el sistema identifica objetos y eventos observables, propone reglas (presencia, colocación y orden), solicita una confirmación breve y luego analiza una nueva ejecución. El resultado es **PASS**, **FAIL** o **REVIEW**, acompañado de evidencias visuales y explicaciones.

**Promesa del MVP:** «Enséñale una tarea una vez. Comprueba la siguiente ejecución».

**Hipótesis que debemos validar:** es posible obtener reglas verificables de un procedimiento físico *nuevo*, sin entrenar modelos especializados ni programar una lógica exclusiva para ese procedimiento. Una demostración por sí sola no establece qué es normativamente obligatorio; por eso el usuario debe aprobar las reglas propuestas.

GhostShift **no** pretende certificar procesos industriales, evaluar seguridad humana ni comprender cualquier tarea. Su alcance inicial es un entorno de mesa, cámara fija, pocos objetos claramente diferenciables y transiciones visuales observables.

## 2. Problema y oportunidad

En tareas manuales cortas y repetitivas (p. ej., preparar kits o montar componentes sencillos), convertir una demostración en comprobaciones digitales puede requerir configuración, etiquetado o ingeniería especializada. Esto dificulta probar controles de calidad visuales en procesos pequeños o cambiantes.

**Problema concreto:** un responsable conoce el orden correcto, pero carece de una forma rápida de convertirlo en verificaciones observables y explicar exactamente dónde una nueva ejecución se apartó de lo esperado.

**Alternativas existentes:** plataformas de inspección visual industrial, checklists, procedimientos escritos y herramientas que generan instrucciones a partir de videos. GhostShift no afirmará inventar la inspección visual; su diferenciación aspiracional es **la configuración rápida desde un ejemplo, con reglas transparentes y evidencias auditables**.

## 3. Usuarios y casos de uso

**Usuario primario:** persona responsable de preparar o revisar un proceso repetitivo de ensamblaje ligero, empaquetado o preparación de kits en un entorno controlado.

**Usuario secundario:** operador o evaluador que ejecuta el procedimiento y necesita saber qué condición se incumplió.

**Caso principal:** montar un kit de tres componentes A, B y C sobre una superficie, ubicarlos en sus zonas y respetar un orden definido.

**Casos similares admitidos para comprobar generalización:** otro kit con objetos distintos y una secuencia diferente; una tarea de clasificación simple con 2–4 elementos visibles.

## 4. Objetivos, métricas y límites

### 4.1 Objetivos de producto

1. Convertir un video de referencia en **reglas comprensibles y editables**, no solo en un resumen narrativo.
2. Reutilizar esas reglas sobre una ejecución independiente sin cambiar el código.
3. Informar el resultado con evidencia visual, eventos observados y causa concreta.
4. Reconocer incertidumbre y solicitar revisión cuando los objetos no sean observables de forma suficiente.
5. Hacer visible el uso sustancial de Muse Spark y SAM 3.1 en una demo auténtica de tres minutos.

### 4.2 Métricas de aceptación del prototipo (objetivos, no resultados)

- **Generalización mínima:** dos procedimientos diferentes creados desde videos de referencia distintos; el segundo no requiere cambios de código ni reglas específicas precargadas.
- **Exactitud sobre conjunto de demostración controlado:** cuatro de cuatro ejecuciones correctas aceptadas; al menos cinco de seis ejecuciones deliberadamente incorrectas rechazadas; dos clips visualmente ambiguos enviados a **REVIEW**.
- **Trazabilidad:** cada FAIL identifica regla, objeto, instante/fotograma y evidencia asociada; nunca se muestra un error sin una condición observable.
- **Configurable por usuario:** los pasos esenciales se confirman desde la interfaz sin etiquetado manual fotograma por fotograma.
- **Operación real:** la demo emplea las llamadas auténticas a modelos y el mismo verificador que el producto; no se precalculan los resultados presentados como inferencia en vivo.
- **Usabilidad objetivo:** desde subir un video válido hasta confirmar reglas, un usuario primerizo puede completar el recorrido guiado sin editar archivos ni código.

Estas cifras son criterios de *go/no-go* para hackathon, **no** métricas suficientes para un despliegue industrial.

## 5. Alcance de la versión MVP

### Incluido (P0: imprescindible)

- Subida de un **video de referencia** y de un **video de ejecución**.
- Formatos MP4/WebM compatibles y validación de archivo, duración y orientación antes de procesar.
- Entorno con cámara fija y visión completa de una mesa o superficie delimitada.
- **2–4 objetos visualmente diferenciables**, con nombres o descripciones cortas confirmables.
- Análisis con Muse Spark para proponer objetos, pasos y orden lógico observables.
- Segmentación/seguimiento con SAM 3.1 para obtener evidencia espacial y temporal.
- Reglas de **presencia de objeto**, **entrada/posición en zona** y **precedencia A antes de B**.
- Pantalla de revisión donde el usuario acepta, desactiva o modifica reglas propuestas (incluyendo el orden), con validaciones simples.
- Compilación de reglas aprobadas a una representación estructurada y ejecutable.
- Verificación de otra ejecución y resultados **PASS / FAIL / REVIEW** por regla y globales.
- Línea de tiempo con fotogramas de evidencia, máscaras o cuadros resaltados y explicación comprensible.
- Registro de llamadas, versiones de modelo, reglas aprobadas y resultados para auditar la demo.
- Ejemplo de un segundo procedimiento distinto para demostrar que no existe una secuencia codificada manualmente.

### Deseable (P1: solo si P0 funciona)

- Captura desde cámara del navegador, además de subir clips.
- Comparador lado a lado entre video de referencia y ejecución.
- Exportar reporte JSON o PDF con reglas y evidencias.
- Editor visual de zonas de interés para corregir una zona propuesta automáticamente.
- Métricas simples de tiempo por paso.

### Fuera de alcance (P2 / futuro)

- Video en directo con alertas de baja latencia.
- Múltiples cámaras, cámaras móviles o reconstrucción 3D.
- Seguimiento de manos preciso, estimación de fuerzas o comprobación de acciones invisibles.
- Integración con PLC, robots, sistemas MES/ERP o cámaras industriales.
- Certificación de seguridad, control de riesgos para personas, vigilancia de empleados o evaluación de productividad individual.
- Entrenamiento/fine-tuning de modelos y reconocimiento universal de objetos arbitrariamente similares.
- Detección de fallas en procedimientos largos, superpuestos o con muchos objetos oclusos.

## 6. Recorrido principal del usuario

**Paso 1 — Crear procedimiento.** La persona abre GhostShift, elige «Enseñar nuevo procedimiento», ve requisitos del video y sube una grabación de referencia.

**Paso 2 — Analizar.** GhostShift identifica los elementos relevantes y propone una línea de tiempo: qué objeto entra en qué zona y en qué orden. El usuario ve el estado del análisis y las partes que no pudieron interpretarse.

**Paso 3 — Aprobar reglas.** La persona revisa una lista comprensible (p. ej., «El componente azul debe estar en la zona A al finalizar» y «A debe colocarse antes que B»), corrige lo necesario y hace clic en «Guardar procedimiento». Ninguna inferencia ambigua se convierte silenciosamente en obligación.

**Paso 4 — Verificar.** La persona sube una nueva ejecución del mismo procedimiento. GhostShift reutiliza las reglas guardadas, vuelve a observar objetos y eventos y calcula el resultado.

**Paso 5 — Comprender el veredicto.** Se muestra un estado global y una lista de reglas; las incumplidas contienen evidencia temporal y visual. Si la observación es insuficiente, se indica REVIEW, no FAIL automático.

**Paso 6 — Probar transferencia.** El usuario enseña un procedimiento diferente con nuevos objetos y orden; GhostShift genera reglas nuevas utilizando la misma arquitectura.

## 7. Requisitos funcionales y criterios de aceptación

### EP-01 — Crear un procedimiento

**US-01.** Como responsable, quiero subir una demostración para iniciar una especificación visual sin escribir código.

**Aceptación:** se puede cargar un MP4/WebM compatible; aparecen vista previa, duración y estado de procesamiento; archivos ilegibles muestran error accionable; el usuario no puede iniciar verificación antes de guardar reglas.

### EP-02 — Proponer reglas visuales

**US-02.** Como responsable, quiero que la IA identifique objetos, eventos y dependencias para reducir la configuración manual.

**Aceptación:** el sistema propone una lista estructurada de objetos/zonas/eventos/reglas; cada regla tiene texto comprensible; si una acción no es visible o no puede inferirse, se marca como hipótesis o incertidumbre; las propuestas no se confunden con hechos confirmados.

### EP-03 — Confirmar y editar

**US-03.** Como responsable, quiero aprobar o corregir las reglas para decidir qué se considera correcto.

**Aceptación:** puedo activar/desactivar una regla, cambiar el orden previsto y confirmar identificadores de objetos; los cambios se guardan en un procedimiento versionado; ninguna verificación utiliza versiones de borrador no aprobadas.

### EP-04 — Inspeccionar una nueva ejecución

**US-04.** Como evaluador, quiero subir otro video y ver el cumplimiento de reglas específicas.

**Aceptación:** el sistema utiliza las reglas aprobadas; calcula eventos observables del nuevo clip; distingue entre «objeto presente» y «orden correcto», de modo que dos ejecuciones con el mismo estado final puedan producir resultados diferentes.

### EP-05 — Evidencia y veredictos

**US-05.** Como evaluador, quiero entender por qué el sistema aprobó, rechazó o no pudo decidir.

**Aceptación:** cada regla expone PASS, FAIL o REVIEW, junto con evidencia temporal; un FAIL contiene la regla incumplida y un evento que la contradice; REVIEW explica el dato faltante; el estado global es FAIL si existe algún fallo confirmado, REVIEW si no hay fallos pero al menos una regla es incierta y PASS solo si todas las reglas son verificadas.

### EP-06 — Generalización demostrable

**US-06.** Como juez o evaluador, quiero enseñar una tarea distinta para comprobar que el producto no está codificado para un solo ejemplo.

**Aceptación:** el segundo procedimiento puede darse de alta desde cero, con objetos y reglas propias; la verificación utiliza un motor genérico; no se despliegan nuevas versiones de código ni se modifican configuraciones ocultas para aceptarlo.

### EP-07 — Robustez básica

**US-07.** Como usuario, quiero saber qué falló y cómo reintentarlo.

**Aceptación:** los errores de red/modelo tienen un mensaje visible y opción de reintento; los clips con cámara móvil, objetos fuera de plano o baja visibilidad se advierten; una segmentación vacía no provoca un PASS ni un FAIL artificial.

## 8. Reglas de evaluación del producto

- **Presencia:** un objeto confirmado debe existir y poder identificarse en un estado temporal relevante.
- **Posición:** un objeto debe ocupar una zona definida; la zona se representa en coordenadas relativas a la escena.
- **Orden:** el evento de colocación A debe ocurrir antes del evento B; si el sistema solo ve los estados finales, no puede afirmar que verificó la secuencia.
- **Persistencia mínima:** para evitar falsos eventos, una colocación puede requerir estabilidad durante un número configurable de fotogramas.
- **Incertidumbre:** oclusión, identidad dudosa, ausencia temporal de detección o desplazamiento de cámara significativo llevan a REVIEW cuando impidan comprobar una condición.
- **Identidad entre videos:** no se asume que los IDs de objetos devueltos por SAM se mantengan entre clips; se realiza correspondencia por descripción visual/semántica y verificación de zona, y se pide confirmación si es ambiguo.

**Contrato de reglas (ilustrativo):**

```json
{
  "procedure_id": "kit-001",
  "version": 1,
  "objects": [
    {"id":"A","description":"componente azul"},
    {"id":"B","description":"componente amarillo"}
  ],
  "rules": [
    {"id":"R1","type":"present_in_zone","object":"A","zone":"left","at":"end"},
    {"id":"R2","type":"before","first":"place:A","second":"place:B"}
  ],
  "approved_by_user": true
}
```

## 9. Estados y casos límite

- **Sin archivo:** pantalla de inicio con instrucciones, ejemplo y restricciones de grabación.
- **Video sin objetos detectables:** explicación + recomendación para repetir grabación; sin veredicto.
- **Manos tapan un objeto:** REVIEW para reglas afectadas; no asumir automáticamente que el objeto falta.
- **Mismos componentes, orden incorrecto:** FAIL de precedencia aunque el estado final sea válido.
- **Orden correcto, objeto fuera de zona:** FAIL de posición, no de orden.
- **Dos objetos casi idénticos:** solicitar identificación/corrección humana; no afirmar correspondencia segura.
- **Solo se ve el final de la tarea:** las reglas de orden deben quedar en REVIEW.
- **Cambio fuerte de cámara o encuadre:** mostrar incompatibilidad o solicitar recalibración.
- **Edición posterior de reglas:** crear nueva versión y señalar que resultados anteriores corresponden a la versión usada.
- **Caída de API o timeout:** ofrecer reintento y conservar los datos de la sesión si es posible.

## 10. Experiencia e interfaz

**Pantalla A: Inicio.** CTA «Enseñar procedimiento», ejemplo visual, requisitos de grabación.

**Pantalla B: Análisis.** Video original, progreso por etapas (interpretación, segmentación, propuesta de reglas), incidencias.

**Pantalla C: Rule Studio.** Lista editable de reglas, miniaturas o marcas temporales, botones de aprobación y guardado; señalar explícitamente que la IA propone y el usuario define la norma.

**Pantalla D: Verificación.** Subida del segundo video y selección del procedimiento versionado.

**Pantalla E: Resultado.** Encabezado PASS/FAIL/REVIEW, tabla de reglas, línea de tiempo y fotogramas resaltados; clic en evidencia lleva al instante del clip.

**Principios UX:** explicación antes que puntuaciones opacas; una acción principal por pantalla; mostrar incertidumbre; etiquetas visibles, no solo colores; demo accesible en desktop moderno.

## 11. Integración de Meta AI (límites funcionales)

**Muse Spark (preferencia: `muse-spark-1.3`):** comprender el video de referencia, proponer objetos y pasos, producir reglas estructuradas candidatas y ayudar a resolver correspondencias semánticas. Sus propuestas requieren validación por observación y aprobación humana. Puede funcionar como coordinador de llamadas y acciones con herramientas, sin afirmar autonomía irrestricta.

**SAM 3.1 (`sam-3-1`):** localizar, segmentar y seguir objetos dentro de un clip. Las máscaras y trayectorias alimentan el detector de eventos del verificador.

**Motor determinista propio:** convertir geometría y tiempo a eventos; ejecutar reglas de presencia/posición/orden; calcular PASS/FAIL/REVIEW con evidencias y registrar incertidumbre. No delegar el veredicto final exclusivamente a una respuesta libre del LLM.

**Condición operativa:** comprobar antes de implementar los límites actuales del servicio para tamaño de video, duración, fps, costos, formatos y latencias. Mantener parámetros de modelo configurables y no prometer cifras no medidas.

Referencias técnicas oficiales:
- https://dev.meta.ai/docs/models
- https://dev.meta.ai/docs/sam/overview
- https://dev.meta.ai/docs/media-segmentation

## 12. Restricciones no funcionales, seguridad y privacidad

- **Seguridad de credenciales:** claves API solo en backend; nunca embebidas en frontend.
- **Consentimiento:** no subir grabaciones con personas identificables o información privada sin permiso; informar que se enviarán a un proveedor de inferencia.
- **Retención:** borrar archivos temporales tras sesión o permitir eliminación explícita; cualquier retención persistente debe ser consentida y documentada.
- **Aislamiento:** cada procedimiento y sus videos pertenecen a una sesión; no exposición pública automática.
- **Observabilidad:** conservar en logs técnicos los IDs de petición, estado, errores, versión de modelo y tiempos, evitando datos personales innecesarios.
- **Limitación declarada:** prototipo experimental; no apto para controles críticos de seguridad, cumplimiento legal o decisiones laborales automatizadas.
- **Compatibilidad objetivo:** navegador moderno en escritorio; móvil no es requisito P0.

## 13. Plan de validación y decisión go/no-go

**Dataset controlado mínimo:**

- Dos procedimientos independientes, cada uno con su referencia y reglas aprobadas.
- Doce videos de ejecución en total: cuatro correctos, seis con errores reales distintos y dos con evidencia deliberadamente insuficiente.
- Cambios de ritmo y gestos entre ejemplos correctos; al menos un par con idéntico estado final pero diferente orden.

**Go:** se demuestra generalización a dos procesos sin ajustes ocultos, 4/4 PASS correctos, 5/6 FAIL detectados, 2/2 REVIEW ambiguos y evidencias razonablemente precisas.

**Conditional go:** si presencia y posición funcionan pero orden no, mantener un MVP honesto limitado a estados y reducir la ambición de la propuesta; evitar describirlo como verificador de secuencias.

**No-go:** si los veredictos requieren valores fijos para cada video, si se inventan eventos no observados o si no puede funcionar sobre una tarea nueva. En ese caso, replantear el producto antes de dedicar tiempo a acabados visuales.

## 14. Cronograma orientativo hasta la entrega

| Fecha | Resultado requerido |
|---|---|
| 28 oct | Validar acceso a Muse Spark/SAM y procesar un clip de referencia |
| 29 oct | Obtener objetos, máscaras y eventos; decidir go/no-go inicial |
| 30 oct | Generación y aprobación de reglas + contrato JSON |
| 31 oct | Verificador de presencia, posición y orden + evidencias |
| 1 nov | Segunda tarea nueva y pruebas de generalización |
| 2 nov | Interfaz completa y gestión de estados/errores |
| 3 nov | Pruebas de 12 ejecuciones, correcciones, repositorio y video |
| 4 nov | Congelar versión, verificar envío y presentar antes de las 9:00 p. m. de Lima |

El plan requiere priorizar las pruebas de viabilidad. Si la interpretación de eventos temporales falla el 29–30 de octubre, no continuar como si la secuencia estuviera solucionada.

## 15. Demostración final (máximo 3 minutos)

1. **0:00–0:20 — Problema:** mostrar tarea manual y ausencia de control verificable rápido.
2. **0:20–0:55 — Enseñar:** cargar una demostración nueva; mostrar análisis real con Muse Spark y SAM.
3. **0:55–1:20 — Convertir:** aprobar reglas que el sistema propone, no una secuencia hardcodeada.
4. **1:20–1:55 — Verificar:** cargar ejecución con orden incorrecto, aunque termine con piezas correctamente ubicadas.
5. **1:55–2:20 — Evidencia:** enseñar FAIL con instante exacto y regla incumplida.
6. **2:20–2:45 — Transferencia:** procedimiento con nuevos objetos y distinta secuencia; mostrar reglas creadas sin editar código.
7. **2:45–3:00 — Cierre:** explicar utilidad, límites y el diferenciador del «video a verificador».

**Honestidad de la demo:** grabar la experiencia real, acortar esperas en edición de forma transparente si se explica, pero no representar respuestas grabadas como inferencia en vivo ni ocultar cambios de código por procedimiento.

## 16. Entregables y definición de terminado

- [ ] Aplicación funcional con flujo completo enseñanza → confirmación → verificación → evidencia.
- [ ] Al menos dos procedimientos diferentes verificados con el mismo código.
- [ ] Conjunto de pruebas y resultados medidos documentados; registrar fallos reales y límites.
- [ ] Repositorio público con README, arquitectura, instrucciones de ejecución, variables de entorno y advertencias.
- [ ] Evidencia explícita de uso de modelos Meta y contribuciones realizadas durante la hackathon.
- [ ] Video de demo de tres minutos, enlace accesible y producto accesible para revisión.
- [ ] Formulario de envío antes del plazo y miembros del equipo correctamente identificados.

**Criterio de «terminado»:** una persona puede enseñar un proceso compatible, aceptar reglas, analizar otra ejecución y rastrear la evidencia del veredicto sin que un desarrollador modifique la lógica para ese proceso.

## 17. Riesgos y decisiones abiertas

| Riesgo | Severidad | Mitigación |
|---|---|---|
| No inferir de forma fiable eventos temporales | Crítica | Pruebas día 1–2; restringir acciones a entradas estables en zonas |
| Una sola ejecución no define obligatoriedad | Alta | Aprobación explícita de reglas y su versionado |
| Confusión de objetos entre clips | Alta | Objetos diferenciables, descripciones confirmadas, REVIEW ante incertidumbre |
| Oclusión o mala cámara | Alta | Guía de grabación y estado REVIEW |
| Competencia con soluciones industriales | Alta | Demostrar configuración desde procedimiento desconocido y sin entrenamiento específico |
| APIs, latencia y costo | Media-alta | Preflight de formatos/límites y presupuestos; carga de video optimizada |
| Resultados atractivos pero hardcodeados | Crítica | Segundo procedimiento elegido al final, logs y repositorio auditable |

**Decisiones que quedan para la fase técnica:** encuadre mínimo recomendado, duración y fps exactos, método de definición de zonas, esquema final de eventos, umbrales geométricos y stack de frontend/backend. Se seleccionarán tras probar datos reales, no por suposición.

---

**Estado del PRD:** listo para iniciar validación técnica. No equivale a evidencia de que el modelo ya alcanza estos criterios.
