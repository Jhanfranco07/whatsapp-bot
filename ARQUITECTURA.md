# Arquitectura del Orientador USIL por WhatsApp

## Descripcion

Este proyecto opera conversaciones y campañas por WhatsApp para orientar
interesados de USIL. FastAPI procesa cada mensaje, clasifica la intencion con un
motor semantico local, genera respuestas desde datos institucionales controlados
y guarda contactos, conversaciones, campañas y mensajes salientes en PostgreSQL.

No depende de APIs LLM ni servicios externos de inteligencia artificial. La
integracion de WhatsApp usa `whatsapp-web.js`, por lo que debe tratarse como una
integracion no oficial.

## Stack

| Componente | Tecnologia |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| Motor semantico | scikit-learn TF-IDF, python-Levenshtein |
| Persistencia | PostgreSQL local, Supabase u otro PostgreSQL remoto |
| ORM | SQLAlchemy |
| Migraciones | Alembic |
| WhatsApp | Node.js, whatsapp-web.js |
| Envio saliente | BridgeProvider + cola `outbound_messages` |
| Pruebas | Pytest |

## Flujo principal

```text
Usuario de WhatsApp
        |
        v
bridge/index.js
        |
        | POST /webhooks/whatsapp/inbound
        | send_reply=true
        v
FastAPI
        |
        v
ConversationService
        |
        +--> verifica stop_bot
        +--> aplica rate limit
        +--> IntentClassifier
        |       |
        |       +--> SemanticEngine singleton
        |               +--> reglas exactas
        |               +--> alias de carreras
        |               +--> TF-IDF
        |               +--> Levenshtein
        |
        +--> ChatbotService
        |       +--> KnowledgeBase
        |       +--> respuestas_base.json
        |       +--> carreras.json
        |       +--> institucion.json
        |
        +--> PostgreSQL
        |       +--> contacts
        |       +--> messages
        |       +--> conversations
        |       +--> outbound_messages
        |
        v
Worker scripts/process_outbound.py
        |
        v
OutboundQueueService
        |
        +--> BridgeProvider
                |
                v
        bridge/index.js POST /send
                |
                v
        WhatsApp Web
```

La regla de arquitectura es que todo mensaje saliente operativo queda registrado
en PostgreSQL antes de intentar enviarse. Esto permite auditar, reintentar y
recuperar mensajes cuando el bridge o WhatsApp Web fallan.

## Bridge bidireccional

`bridge/index.js` mantiene la sesion autenticada mediante `LocalAuth` en
`bridge/.wwebjs_auth/`.

Funciones:

- Recibe mensajes de chats individuales.
- Ignora grupos, estados y mensajes propios.
- Resuelve identificadores `@lid` al telefono real.
- Mantiene una cola por contacto para preservar el orden de mensajes entrantes.
- Expone `GET /health` y `POST /send`.
- Ejecuta envios salientes ordenados por FastAPI mediante `BridgeProvider`.

El bridge ya no responde directamente con `message.reply`. Cuando recibe un
mensaje, lo reenvia a FastAPI con `send_reply=true`; FastAPI decide, registra y
despacha la respuesta. El bridge queda como adaptador de transporte, no como
dueño de la logica conversacional.

## Cola saliente persistente

La tabla `outbound_messages` es la fuente de verdad para mensajes salientes que
deben enviarse por WhatsApp.

Estados:

- `pending`: mensaje registrado y listo para enviarse.
- `retrying`: fallo recuperable; queda programado para otro intento.
- `sent`: el proveedor confirmo el envio.
- `failed`: se agotaron los intentos configurados.
- `cancelled`: el mensaje se invalido antes del envio, por ejemplo por una baja.

Campos clave:

- `phone_number`: destino normalizado.
- `message_text`: cuerpo enviado.
- `source`: origen logico, por ejemplo `conversation` o `campaign`.
- `source_id`: referencia del origen.
- `priority`: precedencia operativa del mensaje.
- `scheduled_at`: instante desde el que el mensaje puede ser reclamado.
- `locked_at`: instante en que un worker reclamo el mensaje.
- `provider`: proveedor usado para el intento.
- `attempts` y `max_attempts`: control de reintentos.
- `next_attempt_at`: proximo intento programado.
- `sent_at`: fecha de envio exitoso.
- `error_message`: ultimo error conocido.
- `raw_response`: respuesta cruda del proveedor.

`OutboundQueueService` centraliza:

- Creacion de mensajes salientes.
- Despacho por `WhatsAppProvider`.
- Registro de proveedor, errores y respuesta cruda.
- Conteo de intentos.
- Backoff simple entre reintentos.
- Procesamiento serial y seguro de pendientes.

Prioridades actuales:

| Origen | Prioridad |
|---|---:|
| Campaña | 10 |
| Respuesta conversacional | 90 |
| Confirmación de baja | 100 |

La prioridad no interrumpe un envio que ya comenzo. Se aplica al reclamar el
siguiente mensaje. Por ello, si la campaña esta enviando el mensaje 51 y llegan
cinco respuestas, termina el envio en curso, procesa primero las respuestas y
despues retoma la campaña.

Worker continuo recomendado:

```powershell
python scripts/process_outbound.py --watch --poll 1 --sent-delay 2
```

Procesamiento manual para diagnostico:

```powershell
python scripts/process_outbound.py --limit 1
```

Procesamiento por API:

```text
POST /outbound/dispatch?limit=1
```

El endpoint exige `X-Admin-Api-Key` cuando `ADMIN_API_KEY` esta configurada.

## Concurrencia

Existen cuatro niveles de proteccion:

1. El bridge serializa mensajes entrantes por contacto mediante colas de
   promesas.
2. `ConversationService` utiliza un `asyncio.Lock` por telefono normalizado.
3. El worker adquiere un advisory lock transaccional de PostgreSQL para que
   solamente un proceso seleccione el siguiente envio global.
4. La fila se reclama con `FOR UPDATE SKIP LOCKED`, evitando que dos workers
   procesen el mismo mensaje.

Contactos distintos pueden procesar su entrada concurrentemente, pero dos
mensajes del mismo contacto mantienen su orden dentro de un mismo proceso. La
salida a WhatsApp es globalmente serial: un solo mensaje se despacha cada vez,
incluso si se levantan varios workers por error.

`ContactRepository.get_or_create` usa una transaccion anidada para tolerar
creaciones simultaneas del mismo telefono.

Los locks conversacionales y el rate limit siguen viviendo en memoria del
proceso. Si FastAPI escala a multiples workers o contenedores, esa coordinacion
por contacto debe moverse a PostgreSQL o Redis. La coordinacion del envio
saliente ya reside en PostgreSQL.

## Motor semantico

`app/services/semantic_engine.py` implementa un pipeline en cascada.

### Nivel 1: reglas exactas

Se ejecuta siempre primero:

- Bajas explicitas.
- Ruido conversacional.
- Saludos.
- Agradecimientos.
- Presentacion de nombre.

Una baja solo se activa con frases explicitas como `basta`, `stop`,
`ya no me escriban` o `quiero darme de baja`.

Mensajes como `JAJAJA`, `XD`, `OK`, `YA`, `AJA` y `no gracias` nunca activan
`stop_bot`.

### Nivel 2: carreras y temas

El motor carga `app/data/carreras.json` una sola vez. Detecta nombres canonicos
y alias, incluyendo errores frecuentes:

```text
adminsitracion -> Administracion
sitemas        -> Ingenieria de Sistemas
derehco        -> Derecho
big data       -> Ciencia de Datos
```

Si encuentra una carrera y un tema, produce una intencion compuesta como
`consulta_campo_laboral`, `consulta_costos`, `consulta_malla` o
`consulta_modalidad`.

### Nivel 3: TF-IDF

El corpus vive en `app/data/intent_corpus.json`. Contiene ocho intenciones y al
menos veinte ejemplos por intencion.

Configuracion:

```python
TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
```

El uso de n-gramas de caracteres permite tolerar errores ortograficos.

Si la similitud maxima es menor a `0.25`, retorna `fuera_de_alcance`.

### Nivel 4: Levenshtein

Cuando la similitud coseno esta entre `0.25` y `0.40`, se combina con distancia
Levenshtein:

```text
score_final = 0.7 * score_coseno + 0.3 * (1 - levenshtein_normalizado)
```

### Singleton

`get_semantic_engine()` crea el indice una sola vez y lo reutiliza durante toda
la vida de la aplicacion.

## Clasificador

`IntentClassifier` mantiene la interfaz:

```python
intent, entities = classifier.classify(message, conversation_context)
```

Internamente delega en `SemanticEngine` y conserva una segunda verificacion para
impedir bajas falsas.

## Generacion de respuestas

`ChatbotService` no genera texto libre. Selecciona variantes aleatorias desde
`app/data/respuestas_base.json` e interpola:

- Carrera.
- Descripcion controlada.
- Campo laboral controlado.
- Portal oficial.
- Portal de admision.
- Lista de campus.

Las respuestas:

- Se limitan a 800 caracteres.
- Eliminan emojis cuando el usuario no uso emojis.
- Usan fallback estatico si falla una interpolacion.
- No inventan costos, fechas, vacantes ni requisitos.

Antes de elegir una plantilla, `KnowledgeBase` consulta
`app/data/conocimiento_institucional.json`. Ese archivo puede crecer con
respuestas revisadas, palabras clave, fecha de verificacion y una fuente
oficial. Si encuentra contexto coincidente, la respuesta verificada tiene
prioridad.

El sistema no registra solicitudes humanas ni promete llamadas. Las consultas
de contacto reciben unicamente telefonos, correo y enlaces oficiales definidos
en `app/data/institucion.json`.

## Persistencia

### `contacts`

Estado actual del contacto, telefono, carrera de interes, ultima intencion,
`opt_out` y `stop_bot`.

### `messages`

Historial completo inbound y outbound con intencion, entidades y payload. Sirve
como historial conversacional visible.

### `conversations`

Ultimo estado y contexto resumido de la conversacion.

### `outbound_messages`

Cola persistente de mensajes salientes. Registra prioridad, programacion,
estado, intentos, bloqueo, proveedor, errores y respuesta cruda.

### `campaign_messages`

Estado historico de cada destinatario de campaña. Se crea como `pending` al
programar el envio y se actualiza cuando el worker confirma o agota el envio.

## Baja persistente

Cuando se detecta por primera vez una solicitud explicita de baja:

- El mensaje entrante se guarda.
- Se encola una unica confirmacion con prioridad 100.
- El contacto queda con `opt_out=true` y `stop_bot=true`.
- El contacto queda excluido de campañas futuras.

Si el contacto ya tenia `stop_bot=true`, los mensajes posteriores se guardan
para auditoria, pero no generan ni encolan una nueva respuesta.

Ademas, antes de despachar cada mensaje de campaña el worker vuelve a consultar
`opt_out`, `stop_bot` y el estado del contacto. Si la baja ocurrio despues de
programar la campaña, el mensaje pendiente se marca `cancelled` y no se envia.

## Campañas

El proveedor recomendado es `BridgeProvider`, que reutiliza la sesion de
WhatsApp Web.

```powershell
python scripts/send_campaign.py --limit 600 --delay 60
```

`CampaignService` no abre WhatsApp ni envia directamente. Selecciona contactos
elegibles, crea su `campaign_messages` y programa cada `outbound_messages` con
prioridad 10. El intervalo se calcula mediante `scheduled_at` y el worker
respeta ademas una separacion minima real entre campañas, configurada con
`CAMPAIGN_MINIMUM_GAP_SECONDS` (60 segundos por defecto).

La separacion se calcula desde el ultimo envio de campaña confirmado, no desde
el horario teorico. Asi, una pausa para atender conversaciones no provoca una
rafaga de mensajes de campaña atrasados al reanudarse.

Un contacto con un registro previo `pending`, `retrying` o `sent` para la misma
campaña no vuelve a programarse. Esto permite reejecutar el comando sin duplicar
destinatarios ya procesados.

## Base de datos local o cloud

### Local con Docker

```powershell
docker compose up -d
python scripts/init_db.py
```

`scripts/init_db.py` ejecuta `alembic upgrade head`. Las migraciones viven en
`migrations/`.

Configuracion:

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

| Metodo | Ruta | Uso |
|---|---|---|
| GET | `/health` | Salud de FastAPI y PostgreSQL |
| GET | `/health/llm` | Salud del motor semantico, ruta conservada por compatibilidad |
| GET | `/admin` | Panel administrativo basico |
| GET | `/admin/metrics` | Metricas operativas |
| GET/POST | `/admin/knowledge` | Conocimiento verificable |
| POST | `/webhooks/whatsapp/inbound` | Entrada real desde WhatsApp |
| POST | `/simulate/inbound` | Simulacion manual |
| POST | `/campaigns/send` | Campaña inicial |
| POST | `/outbound/dispatch` | Despacha mensajes pendientes de la cola saliente |
| GET/POST | `/contacts` | Gestion de contactos |
| GET | `/contacts/{phone}/messages` | Historial |

Respuesta de salud semantica:

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

## Ejecucion

```powershell
docker compose up -d
python scripts/init_db.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

En una segunda terminal se ejecuta el bridge:

```powershell
cd bridge
npm start
```

En una tercera terminal se ejecuta el unico despachador operativo:

```powershell
python scripts/process_outbound.py --watch --poll 1 --sent-delay 2
```

Produccion en contenedores:

```powershell
docker compose -f docker-compose.prod.yml up --build
```

FastAPI clasifica y encola; el bridge mantiene la sesion de WhatsApp; el worker
decide el orden y realiza todos los envios. Ninguno de los otros procesos debe
enviar mensajes por su cuenta.

## Pruebas

```powershell
python -m pytest -q
```

La suite cubre reglas, TF-IDF, Levenshtein, alias, errores ortograficos, bajas,
ruido silencioso, plantillas, campañas, API, persistencia y cola saliente.

## Seguridad

- `.env` esta ignorado por Git.
- `INBOUND_API_KEY` protege webhook y envio saliente.
- `POST /outbound/dispatch` exige `X-Admin-Api-Key` si `ADMIN_API_KEY` esta
  configurada.
- El servidor saliente escucha por defecto solo en `127.0.0.1`.
- `stop_bot` tiene verificacion doble.
- No se inventan datos institucionales variables.
- El historial y los intentos salientes se conservan para auditoria.

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
    outbound_queue_service.py
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
migrations/
  versions/
    0002_outbound_queue.py
    0003_outbound_scheduler.py
scripts/
  process_outbound.py
  send_campaign.py
docker-compose.yml
tests/
```
