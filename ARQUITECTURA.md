# Arquitectura del Orientador USIL por WhatsApp

## Descripción

Este proyecto recibe y envía mensajes reales mediante una sesión persistente de
WhatsApp Web. FastAPI procesa cada mensaje, clasifica su intención con un motor
semántico puro en Python, genera respuestas desde datos institucionales
controlados y guarda toda la conversación en PostgreSQL.

No depende de APIs LLM ni servicios externos de inteligencia artificial.

## Stack

| Componente | Tecnología |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| Motor semántico | scikit-learn TF-IDF, python-Levenshtein |
| Persistencia | PostgreSQL local, Supabase u otro PostgreSQL remoto |
| ORM | SQLAlchemy |
| WhatsApp | Node.js, whatsapp-web.js |
| Envío saliente | BridgeProvider |
| Pruebas | Pytest |

## Flujo principal

```text
Usuario de WhatsApp
        |
        v
bridge/index.js
        |
        | POST /webhooks/whatsapp/inbound
        v
FastAPI
        |
        v
ConversationService
        |
        +--> verifica stop_bot
        +--> IntentClassifier
        |       |
        |       +--> SemanticEngine singleton
        |               +--> reglas exactas
        |               +--> alias de carreras
        |               +--> TF-IDF
        |               +--> Levenshtein
        |
        +--> ChatbotService
        |       +--> plantillas
        |       +--> carreras.json
        |       +--> institucion.json
        |
        +--> PostgreSQL
        |
        v
Respuesta JSON al bridge
        |
        v
Respuesta enviada al chat
```

## Bridge bidireccional

`bridge/index.js` mantiene la sesión autenticada mediante `LocalAuth` en
`bridge/.wwebjs_auth/`.

Funciones:

- Recibe mensajes de chats individuales.
- Ignora grupos, estados y mensajes propios.
- Resuelve identificadores `@lid` al teléfono real.
- Mantiene una cola por contacto para preservar el orden.
- Envía mensajes salientes mediante la misma sesión.
- Expone `GET /health` y `POST /send` en `127.0.0.1:3001`.

`BridgeProvider` llama a `POST /send` desde FastAPI y scripts de campaña.

## Concurrencia

Existen dos niveles de protección:

1. El bridge serializa mensajes por contacto mediante colas de promesas.
2. `ConversationService` utiliza un `asyncio.Lock` por teléfono normalizado.

Contactos distintos pueden procesarse concurrentemente, pero dos mensajes del
mismo contacto mantienen su orden.

`ContactRepository.get_or_create` usa una transacción anidada para tolerar
creaciones simultáneas del mismo teléfono.

## Motor semántico

`app/services/semantic_engine.py` implementa un pipeline en cascada.

### Nivel 1: reglas exactas

Se ejecuta siempre primero:

- Bajas explícitas.
- Ruido conversacional.
- Saludos.
- Agradecimientos.
- Presentación de nombre.

Una baja solo se activa con frases explícitas como `basta`, `stop`,
`ya no me escriban` o `quiero darme de baja`.

Mensajes como `JAJAJA`, `XD`, `OK`, `YA`, `AJA` y `no gracias` nunca activan
`stop_bot`.

### Nivel 2: carreras y temas

El motor carga `app/data/carreras.json` una sola vez. Detecta nombres canónicos
y alias, incluyendo errores frecuentes:

```text
adminsitracion -> Administración
sitemas        -> Ingeniería de Sistemas
derehco        -> Derecho
big data       -> Ciencia de Datos
```

Si encuentra una carrera y un tema, produce una intención compuesta como
`consulta_campo_laboral`, `consulta_costos`, `consulta_malla` o
`consulta_modalidad`.

### Nivel 3: TF-IDF

El corpus vive en `app/data/intent_corpus.json`. Contiene ocho intenciones y al
menos veinte ejemplos por intención.

Configuración:

```python
TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
```

El uso de n-gramas de caracteres permite tolerar errores ortográficos.

Si la similitud máxima es menor a `0.25`, retorna `fuera_de_alcance`.

### Nivel 4: Levenshtein

Cuando la similitud coseno está entre `0.25` y `0.40`, se combina con distancia
Levenshtein:

```text
score_final = 0.7 * score_coseno + 0.3 * (1 - levenshtein_normalizado)
```

### Singleton

`get_semantic_engine()` crea el índice una sola vez y lo reutiliza durante toda
la vida de la aplicación.

## Clasificador

`IntentClassifier` mantiene la interfaz:

```python
intent, entities = classifier.classify(message, conversation_context)
```

Internamente delega en `SemanticEngine` y conserva una segunda verificación para
impedir bajas falsas.

## Generación de respuestas

`ChatbotService` no genera texto libre. Selecciona variantes aleatorias desde
`app/data/respuestas_base.json` e interpola:

- Carrera.
- Descripción controlada.
- Campo laboral controlado.
- Portal oficial.
- Portal de admisión.
- Lista de campus.

Las respuestas:

- Se limitan a 800 caracteres.
- Eliminan emojis cuando el usuario no usó emojis.
- Usan fallback estático si falla una interpolación.
- No inventan costos, fechas, vacantes ni requisitos.

Antes de elegir una plantilla, `KnowledgeBase` consulta
`app/data/conocimiento_institucional.json`. Ese archivo puede crecer con
respuestas revisadas, palabras clave, fecha de verificación y una fuente
oficial. Si encuentra contexto coincidente, la respuesta verificada tiene
prioridad.

El sistema no registra solicitudes humanas ni promete llamadas. Las consultas
de contacto reciben únicamente teléfonos, correo y enlaces oficiales definidos
en `app/data/institucion.json`.

## Persistencia

### `contacts`

Estado actual del contacto, teléfono, carrera de interés, última intención,
`opt_out` y `stop_bot`.

### `messages`

Historial completo inbound y outbound con intención, entidades y payload.

### `conversations`

Último estado y contexto resumido de la conversación.

### `campaign_messages`

Resultado de cada envío de campaña.

## Baja persistente

Cuando `stop_bot=true`:

- El mensaje entrante se guarda.
- No se genera mensaje saliente.
- El bridge no responde.
- El contacto queda excluido de campañas futuras.

## Campañas

El proveedor recomendado es `BridgeProvider`, que reutiliza la sesión de
WhatsApp Web.

```powershell
python scripts/send_campaign.py --limit 1
python scripts/send_campaign.py --delay 10
```

Cada resultado se guarda y confirma antes de procesar el siguiente contacto.

## Base de datos local o cloud

### Local con Docker

```powershell
docker compose up -d
python scripts/init_db.py
```

Configuración:

```dotenv
DB_MODE=local
DATABASE_URL=postgresql+psycopg2://usil:usil@localhost:5432/usil_db
```

### Cloud

Para Supabase u otro PostgreSQL remoto:

```dotenv
DB_MODE=cloud
DATABASE_URL=postgresql+psycopg2://usuario:clave@host:5432/postgres?sslmode=require
```

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health` | Salud de FastAPI y PostgreSQL |
| GET | `/health/llm` | Salud del motor semántico, ruta conservada por compatibilidad |
| POST | `/webhooks/whatsapp/inbound` | Entrada real desde WhatsApp |
| POST | `/simulate/inbound` | Simulación manual |
| POST | `/campaigns/send` | Campaña inicial |
| GET/POST | `/contacts` | Gestión de contactos |
| GET | `/contacts/{phone}/messages` | Historial |

Respuesta de salud semántica:

```json
{
  "status": "ok",
  "engine": "tfidf_semantic",
  "intents_loaded": 8,
  "probe": {
    "text": "hola",
    "intent": "saludo",
    "confidence": 1.0
  }
}
```

## Ejecución

```powershell
docker compose up -d
python scripts/init_db.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

En otra terminal:

```powershell
cd bridge
npm start
```

## Pruebas

```powershell
python -m pytest -q
```

La suite cubre reglas, TF-IDF, Levenshtein, alias, errores ortográficos, bajas,
ruido silencioso, plantillas, campañas, API y persistencia.

## Seguridad

- `.env` está ignorado por Git.
- `INBOUND_API_KEY` protege webhook y envío saliente.
- El servidor saliente escucha por defecto solo en `127.0.0.1`.
- `stop_bot` tiene verificación doble.
- No se inventan datos institucionales variables.
- El historial se conserva para auditoría.

## Estructura relevante

```text
app/
  main.py
  config.py
  services/
    semantic_engine.py
    knowledge_base.py
    intent_classifier.py
    chatbot_service.py
    conversation_service.py
    campaign_service.py
  database/
    models.py
    repositories.py
  whatsapp/
    bridge_sender.py
    sender.py
  data/
    intent_corpus.json
    conocimiento_institucional.json
    carreras.json
    institucion.json
    respuestas_base.json
bridge/
  index.js
docker-compose.yml
tests/
```
