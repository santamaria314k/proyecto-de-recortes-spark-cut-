# Modelo de IA

## Purpose

RNN propia (BiGRU con atención en PyTorch, tokenizador SentencePiece propio) que puntúa el texto de un
fragmento entre 10 y 100 para ordenar los momentos que sobresalen dentro del video. El resultado no es
una predicción de viralidad futura.
Incluye la página pública «Cómo funciona el modelo» con métricas y limitaciones, un probador de textos y el
contrato de los artefactos del modelo entregados por el entrenamiento en Colab.
Satisface RF-08, RF-10, RF-19, RF-21, RNF-11.

## Requirements

### Requirement: Puntaje de potencial viral 10-100
El modelo SHALL devolver, para cada texto de fragmento, un puntaje entre 10 y 100. La versión v6 combina
las salidas `adj` y `pk` de la RNN según `score_weights` y su calibración por cuantiles en `config.json`.
Cuando se puntúa un video completo, el ranker contextual v6 mezcla la RNN, TF-IDF y cambio textual entre
ventanas según `context_rank_blend`.

#### Scenario: Puntaje de una ventana
- **WHEN** `score_segments` recibe el texto en inglés de una ventana
- **THEN** devuelve un puntaje entre 10.0 y 100.0; un fragmento es seleccionable si puntúa mayor a 70

#### Scenario: Puntaje detallado
- **WHEN** la vista llama a `score_segments_detailed`
- **THEN** recibe `{score, dims: {hook, emotion, surprise, conflict, story}, top_emotions: [(nombre, prob)]}` con las emociones ordenadas de mayor a menor probabilidad

### Requirement: Modelo de solo texto
El modelo SHALL puntuar solo con el texto del fragmento. El ranker contextual puede recibir la lista de
ventanas para medir diferencias textuales entre candidatos, pero no usa imágenes ni audio.

#### Scenario: Determinismo
- **WHEN** se puntúa dos veces el mismo texto con los mismos artefactos
- **THEN** el puntaje es idéntico

#### Scenario: Independencia de posición
- **WHEN** se ejecuta el protocolo de evaluación sobre ventanas en distintas posiciones del video
- **THEN** la correlación puntaje-posición reportada en `metrics.json` es cercana a 0 (umbral aceptable por definir en la evaluación)

### Requirement: Carga de artefactos del modelo
El worker SHALL cargar al iniciar la carpeta `ml_artifacts/` (modelos `model_0.pt..model_N.pt`,
`tokenizer.model`, `config.json`, `metrics.json`, `golden_tests.json`) y SHALL NOT iniciar si falta un
archivo, indicando en el mensaje cuál falta. La web SHALL poder leer los mismos artefactos para servir
`/modelo/` y `/modelo/probar/`.

#### Scenario: Artefactos completos
- **WHEN** el worker arranca con `ml_artifacts/` completa
- **THEN** carga el ensamble (3 modelos con semillas distintas, salidas promediadas) y el tokenizador una sola vez por proceso

#### Scenario: Artefacto faltante
- **WHEN** falta un archivo en `ml_artifacts/`
- **THEN** el worker no inicia y el mensaje de error indica el archivo faltante

#### Scenario: Cantidad de modelos incoherente
- **WHEN** el número de archivos `model_*.pt` no coincide con el ensamble declarado en `config.json`
- **THEN** el worker no inicia y el mensaje indica la discrepancia

### Requirement: Modo simulado para desarrollo
El sistema SHALL soportar la variable `MOCK_SCORER=1` con un puntaje simulado determinista para
desarrollar sin esperar al modelo (hito H3 del plan), y SHALL NOT habilitarlo por defecto en el despliegue.

#### Scenario: Desarrollo sin modelo
- **WHEN** el entorno define `MOCK_SCORER=1`
- **THEN** el pipeline completo funciona con puntajes simulados reproducibles y el log lo advierte al iniciar

### Requirement: Página pública del modelo
El sistema SHALL publicar en `/modelo/` la versión, la arquitectura, los datasets, los resultados de
evaluación (contenidos en `metrics.json`) y las limitaciones declaradas, sin requerir sesión (MoSCoW: Should — RF-21).

#### Scenario: Consulta del modelo
- **WHEN** un visitante abre `/modelo/`
- **THEN** ve versión, arquitectura, datasets de entrenamiento, métricas con intervalos de confianza y las limitaciones (solo texto en inglés, el puntaje es una estimación sin garantía de resultados)

#### Scenario: Probador de puntaje
- **WHEN** un visitante envía `POST /modelo/probar/` con un texto de hasta 500 caracteres
- **THEN** recibe el puntaje y las emociones dominantes en JSON

#### Scenario: Texto inválido en el probador
- **WHEN** el texto está vacío o supera 500 caracteres
- **THEN** la respuesta es 400 con JSON `{error, code}` en español

### Requirement: Entrenamiento reproducible
El entrenamiento SHALL ser reproducible: semillas fijas, configuración versionada y métricas guardadas
(RNF-11), evaluado contra líneas base con intervalos de confianza del 95 % por bootstrap.

#### Scenario: Verificación golden
- **WHEN** se ejecutan los textos de `golden_tests.json` por la app
- **THEN** la app reproduce el puntaje esperado del entrenamiento dentro de la tolerancia indicada en ese archivo
