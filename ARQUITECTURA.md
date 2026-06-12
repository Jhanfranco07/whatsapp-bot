# Arquitectura y funcionamiento del Orientador USIL por WhatsApp

## 1. Descripción general

Este proyecto es un prototipo de orientación universitaria por WhatsApp para
USIL. Permite:

- Importar y almacenar contactos.
- Enviar una campaña inicial a contactos autorizados.
- Recibir mensajes reales mediante una sesión vinculada de WhatsApp Web.
- Comprender consultas sobre carreras, admisión, campo laboral, costos, campus
  e información institucional.
- Responder mediante reglas, plantillas controladas y Ollama local.
- Guardar contactos, mensajes y contexto conversacional en PostgreSQL/Supabase.
- Respetar permanentemente las solicitudes explícitas de baja.

El sistema no usa la API oficial de WhatsApp Business. La recepción en tiempo
real se realiza con `whatsapp-web.js`, que automatiza una sesión de WhatsApp Web.
Por ello debe considerarse una integración no oficial y usarse solamente con
una cuenta autorizada.

## 2. Stack tecnológico

| Componente | Tecnología | Responsabilidad |
|---|---|---|
| API y lógica principal | Python, FastAPI | Recibir mensajes, ejecutar reglas y coordinar servicios |
| Persistencia | PostgreSQL en Supabase | Guardar contactos, mensajes, campañas y conversaciones |
| ORM | SQLAlchemy | Acceder a PostgreSQL mediante modelos y repositorios |
| Validación de API | Pydantic | Validar entradas, respuestas y configuración |
| WhatsApp entrante/saliente | Node.js, `whatsapp-web.js` | Escuchar mensajes y responder en el mismo chat |
| Campaña inicial | PyWhatKit | Abrir WhatsApp Web y enviar mensajes iniciales |
| Inteligencia artificial local | Ollama, `qwen3.5:0.8b` | Comprender y redactar consultas que requieren explicación |
| Pruebas | Pytest | Verificar reglas, servicios, API, campañas y Ollama |

## 3. Arquitectura de alto nivel

```text
Usuario de WhatsApp
        |
        v
WhatsApp Web vinculado
        |
        v
bridge/index.js (whatsapp-web.js)
        |
        | POST /webhooks/whatsapp/inbound
        v
FastAPI - app/main.py
        |
        v
ConversationService
        |
        +--> PostgreSQL/Supabase: busca o crea contacto
        |
        +--> verifica stop_bot
        |
        +--> IntentClassifier
        |       |
        |       +--> reglas rápidas y seguras
        |       |
        |       +--> Ollama HTTP cuando se necesita comprensión o explicación
        |
        +--> ChatbotService
        |       |
        |       +--> plantilla controlada
        |       |
        |       +--> respuesta redactada por Ollama
        |
        +--> PostgreSQL/Supabase: guarda inbound, outbound y contexto
        |
        v
Respuesta JSON para bridge/index.js
        |
        v
Respuesta enviada al chat de WhatsApp si should_reply=true
```

## 4. Flujo completo de un mensaje entrante

### 4.1 Recepción desde WhatsApp Web

El archivo `bridge/index.js` crea un cliente de `whatsapp-web.js` usando
`LocalAuth`.

La sesión autenticada se almacena dentro de:

```text
bridge/.wwebjs_auth/
```

Al recibir un mensaje, el puente ignora:

- Mensajes enviados por la propia cuenta.
- Estados de WhatsApp.
- Mensajes de grupos.
- Mensajes sin texto.

Después envía a FastAPI:

```http
POST /webhooks/whatsapp/inbound
Content-Type: application/json
X-Inbound-Api-Key: ...
```

Ejemplo conceptual:

```json
{
  "phone_number": "51999999999",
  "message": "¿En qué trabaja alguien de Administración?",
  "timestamp": "2026-06-12T15:00:00Z",
  "raw_payload": {
    "whatsapp_message_id": "...",
    "source": "whatsapp-web.js"
  },
  "send_reply": false
}
```

El puente no necesita que FastAPI envíe directamente por PyWhatKit. Recibe
`bot_reply` en el JSON y responde en el mismo chat mediante
`message.reply(...)`.

### 4.2 Procesamiento en FastAPI

`app/main.py` recibe el webhook y crea un `ConversationService`.

El servicio:

1. Normaliza el teléfono.
2. Busca el contacto en PostgreSQL o lo crea.
3. Recupera el contexto anterior de la conversación.
4. Comprueba si el contacto tiene `stop_bot=true`.
5. Clasifica el mensaje.
6. Genera una respuesta cuando corresponde.
7. Guarda el mensaje entrante.
8. Guarda el mensaje saliente solamente si realmente será respondido.
9. Actualiza contacto, intención, estado y contexto.
10. Devuelve el resultado al puente.

## 5. Regla persistente `stop_bot`

`stop_bot` es la protección principal para respetar una baja.

Solo se activa cuando existe una solicitud explícita, por ejemplo:

- `basta`
- `stop`
- `detente`
- `ya no me escriban`
- `no quiero mensajes`
- `quiero darme de baja`

No se activa con:

- `JAJAJA`
- `XD`
- `OK`
- `YA`
- `AJA`
- `no gracias`
- Bromas o mensajes ambiguos

Si Ollama clasifica incorrectamente un mensaje como baja, el
`IntentClassifier` vuelve a verificar el texto original y descarta la baja si
no existe una expresión explícita.

Cuando `stop_bot=true`:

- El mensaje entrante todavía se guarda para auditoría.
- No se genera ni guarda mensaje saliente.
- El puente no responde.
- El contacto queda excluido de campañas futuras.

## 6. Clasificación híbrida: reglas y Ollama

La clasificación vive en `app/services/intent_classifier.py`.

### 6.1 Reglas rápidas

Las reglas se ejecutan primero porque son rápidas, predecibles y seguras.

Se usan principalmente para:

- Solicitudes explícitas de baja.
- Ruidos conversacionales conocidos.
- Saludos y agradecimientos.
- Admisión, costos, campus y enlaces.
- Carreras exactas o alias conocidos.
- Palabras con errores ortográficos frecuentes.

Ejemplos:

```text
"adminsitracion" -> Administración
"sitemas"        -> Ingeniería de Sistemas
"derehco"        -> Derecho
```

### 6.2 Ruido conversacional

Mensajes sin una consulta real se clasifican como `ruido_conversacional`.

Ejemplos:

```text
JAJAJA
XD
OK
YA
AJA
```

Estos mensajes se guardan, pero devuelven:

```json
{
  "intent": "ruido_conversacional",
  "should_reply": false,
  "bot_reply": null
}
```

### 6.3 Uso de Ollama

Ollama cumple dos funciones separadas:

1. Clasifica mensajes que las reglas no comprenden usando `/api/generate` y
   temperatura `0.2`.
2. Redacta la respuesta final de todas las intenciones no triviales usando
   `/api/chat`, historial conversacional y temperatura `0.45`.

El redactor final se usa especialmente para:

- Explicar de qué trata una carrera.
- Describir campo laboral general.
- Comparar carreras.
- Explicar modalidades.
- Consultas institucionales.
- Interpretar mensajes que las reglas no comprenden claramente.

La aplicación no inicia, instala ni administra Ollama. Para clasificación llama:

```http
POST http://localhost:11434/api/generate
```

Cuerpo principal:

```json
{
  "model": "qwen3.5:0.8b",
  "prompt": "...",
  "stream": false,
  "think": false,
  "options": {
    "temperature": 0.2,
    "num_predict": 400
  }
}
```

`think=false` reduce el tiempo de respuesta. El timeout evita que una llamada
bloqueada detenga indefinidamente la conversación.

Para la redacción final llama:

```http
POST http://localhost:11434/api/chat
```

El payload conversacional contiene:

- El prompt de sistema con límites y hechos institucionales.
- La información de la carrera detectada.
- Los últimos tres mensajes guardados.
- La plantilla controlada como guía de contenido.
- El mensaje actual del usuario.

Si `/api/chat` falla o devuelve una respuesta inválida, el sistema usa la
plantilla estática como fallback.

## 7. Contrato de respuesta de Ollama

El prompt está en `app/llm/prompts.py`. Ollama debe devolver solamente JSON.

Estructura esperada:

```json
{
  "intent": "consulta_campo_laboral",
  "confidence": 0.9,
  "classifier": "ollama",
  "entities": {
    "carrera": "Administración",
    "tema": "campo_laboral"
  },
  "response": "Respuesta breve y segura...",
  "should_reply": true,
  "stop_bot": false
}
```

`app/llm/service.py` valida la respuesta:

- Rechaza intenciones desconocidas.
- Limita `confidence` entre `0` y `1`.
- Exige una carrera para `consulta_carrera_especifica`.
- Recalcula decisiones sensibles.
- No permite que el modelo controle libremente una baja.
- Marca ruido y contenido fuera de alcance como silencioso.

El contexto institucional enviado a Ollama vive en:

```text
app/data/institucion.json
```

Esto reduce invenciones y mantiene las respuestas dentro de información
institucional controlada.

## 8. Generación de respuestas

`app/services/chatbot_service.py` decide cómo responder.

### Plantillas controladas

Se usan directamente para baja, ruido y saludos. Para las demás intenciones
funcionan como guía de contenido y fallback resiliente:

- Admisión.
- Costos.
- Campus.
- Listado de carreras.
- Malla y duración.
- Baja.
- Saludos y agradecimientos.

Las variantes viven en:

```text
app/data/respuestas_base.json
```

Se seleccionan variantes aleatorias para evitar respuestas repetitivas.

### Respuestas de Ollama

Se usan como redacción final para todas las respuestas no triviales. Las respuestas:

- Deben ser breves y naturales.
- No deben solicitar datos personales.
- No deben prometer empleabilidad.
- No deben inventar costos, fechas, vacantes o requisitos.
- Deben usar información institucional controlada.
- Pueden incluir un cierre variado con un enlace oficial.
- Reciben los últimos tres mensajes para continuar la conversación naturalmente.
- Se truncan si superan 800 caracteres.
- Eliminan emojis cuando el usuario no utilizó emojis.

Si la respuesta ya contiene un enlace de USIL, el backend evita agregar otro
cierre repetido.

## 9. Persistencia en PostgreSQL/Supabase

Los modelos están definidos en `app/database/models.py`.

### Tabla `contacts`

Guarda el estado actual de cada contacto:

- Nombre y teléfono.
- Carrera de interés.
- Origen.
- Estado conversacional.
- Última intención.
- `opt_out`.
- `stop_bot`.
- Fecha del último mensaje.

### Tabla `messages`

Guarda el historial completo:

- Dirección `inbound` u `outbound`.
- Texto.
- Intención.
- Entidades detectadas.
- Payload original.
- Fecha.

### Tabla `conversations`

Guarda el contexto resumido:

- Último mensaje del usuario.
- Último mensaje del bot.
- Estado actual.
- Última carrera mencionada.
- Último tema consultado.
- Otros datos contextuales.

### Tabla `campaign_messages`

Registra cada intento de campaña:

- Mensaje enviado.
- Contacto.
- Estado de envío.
- Error.
- Fecha de envío.

### Tabla `advisor_requests`

Conserva compatibilidad con solicitudes de asesor existentes, aunque el flujo
actual evita insistir o solicitar datos personales.

## 10. Campañas iniciales

La campaña inicial se coordina desde:

```text
app/services/campaign_service.py
scripts/send_campaign.py
```

Antes de enviar, se excluyen contactos con:

- `opt_out=true`
- `stop_bot=true`
- Estado `SALIR`
- Estado `NO_INTERESADO`

PyWhatKit sirve solamente para campañas iniciales. No recibe mensajes.

## 11. Endpoints principales

| Método | Ruta | Uso |
|---|---|---|
| GET | `/` | Información básica del servicio |
| GET | `/health` | Verifica API y PostgreSQL |
| GET | `/health/llm` | Verifica Ollama y el modelo |
| POST | `/webhooks/whatsapp/inbound` | Entrada real desde el puente |
| POST | `/simulate/inbound` | Simulación manual |
| POST | `/campaigns/send` | Envía campaña inicial |
| GET | `/contacts` | Lista contactos |
| POST | `/contacts` | Crea contacto |
| POST | `/contacts/import` | Importa contactos |
| GET | `/contacts/{phone}/messages` | Consulta historial |
| GET | `/advisor-requests` | Lista solicitudes existentes |

La documentación interactiva está disponible en:

```text
http://127.0.0.1:8000/docs
```

## 12. Configuración mediante `.env`

Variables principales:

```dotenv
DATABASE_URL=postgresql+psycopg2://...
INBOUND_API_KEY=una-clave-compartida
BRIDGE_API_URL=http://127.0.0.1:8000

WHATSAPP_PROVIDER=pywhatkit
WHATSAPP_DRY_RUN=true

LLM_PROVIDER=ollama
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:0.8b
OLLAMA_THINK=false
OLLAMA_TEMPERATURE=0.2
OLLAMA_MAX_TOKENS=400
OLLAMA_TIMEOUT=120
```

`.env` contiene secretos y no debe publicarse en Git.

## 13. Cómo ejecutar el sistema

### Inicializar tablas

```powershell
cd C:\Users\PC\Downloads\enviarWHATSAPP
python scripts/init_db.py
```

### Verificar Ollama

```powershell
python scripts/check_ollama.py
```

### Ejecutar FastAPI

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Ejecutar el puente de WhatsApp Web

En otra terminal:

```powershell
cd C:\Users\PC\Downloads\enviarWHATSAPP\bridge
npm start
```

La primera vez debe escanearse el QR desde:

```text
WhatsApp > Dispositivos vinculados
```

Después, `LocalAuth` reutiliza la sesión guardada.

## 14. Cómo verificar el funcionamiento

### Salud de FastAPI y PostgreSQL

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### Salud de Ollama

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/llm
```

### Simular un mensaje

```powershell
python scripts/simulate_inbound.py `
  --phone 51999999999 `
  --message "¿En qué trabaja alguien de Administración?"
```

### Casos recomendados

| Mensaje | Resultado esperado |
|---|---|
| `Administración` | Información inicial de la carrera |
| `¿En qué trabaja alguien de Administración?` | Respuesta explicativa con Ollama |
| `¿Cuánto cuesta?` | Respuesta segura y portal de admisión |
| `JAJAJA` | Guardado sin respuesta |
| `sabes zonificar` | Fuera de alcance, sin respuesta |
| `basta de mensajes` | Confirma baja y activa `stop_bot=true` |
| Mensaje después de la baja | Guardado sin respuesta |

## 15. Pruebas automatizadas

Ejecutar:

```powershell
python -m pytest -q
```

Las pruebas cubren:

- Clasificación por reglas.
- Errores ortográficos.
- Ruido conversacional silencioso.
- Protección contra bajas falsas de Ollama.
- Baja persistente.
- Respuestas controladas.
- Flujo de conversación.
- Campañas y exclusión de contactos.
- Contrato HTTP de Ollama.
- Endpoints FastAPI.

Las pruebas reales contra PostgreSQL requieren una base exclusiva definida en
`TEST_DATABASE_URL`.

## 16. Seguridad y controles

- `INBOUND_API_KEY` protege el webhook entre el puente y FastAPI.
- `.env` no debe subirse al repositorio.
- Las decisiones de baja no dependen únicamente de Ollama.
- Costos, fechas, vacantes y requisitos exactos no son inventados.
- El sistema evita solicitar nombre, DNI, correo o celular durante la
  conversación.
- Los mensajes de grupos y estados son ignorados por el puente.
- El historial se conserva para auditoría.

## 17. Limitaciones

- `whatsapp-web.js` es una integración no oficial.
- WhatsApp puede cambiar su funcionamiento y romper la automatización.
- La sesión depende del navegador y de la cuenta vinculada.
- Ollama debe estar ejecutándose localmente para respuestas generativas.
- El modelo liviano puede equivocarse; por ello existen reglas y validaciones.
- No existe todavía un panel administrativo para revisar conversaciones.
- La inicialización usa SQLAlchemy y SQL directo; una evolución recomendable es
  usar migraciones con Alembic.

## 18. Estructura principal del proyecto

```text
app/
  main.py                         API FastAPI
  config.py                       Configuración .env
  services/
    conversation_service.py       Orquestación de mensajes
    intent_classifier.py          Reglas y selección de Ollama
    chatbot_service.py            Generación final de respuestas
    campaign_service.py           Campañas iniciales
  llm/
    ollama_provider.py            Cliente HTTP de Ollama
    service.py                    Validación del contrato LLM
    prompts.py                    Instrucciones para el modelo
  database/
    models.py                     Tablas SQLAlchemy
    repositories.py               Consultas y persistencia
  data/
    institucion.json              Contexto institucional controlado
    carreras.json                 Carreras y alias
    respuestas_base.json          Plantillas y cierres
bridge/
  index.js                        Puente WhatsApp Web -> FastAPI
scripts/
  init_db.py                      Inicialización de PostgreSQL
  import_contacts.py              Importación de contactos
  send_campaign.py                Campaña inicial
  simulate_inbound.py             Simulación de mensajes
  check_ollama.py                 Verificación de Ollama
tests/                             Pruebas automatizadas
```

## 19. Resumen de la decisión arquitectónica

La arquitectura es híbrida porque combina:

- Reglas para velocidad, seguridad y decisiones sensibles.
- Plantillas para información que debe mantenerse controlada.
- Ollama para comprensión semántica y respuestas más naturales.
- PostgreSQL/Supabase para conservar estado y trazabilidad.
- `whatsapp-web.js` para conectar la conversación real con la API.

La idea central es que la IA ayuda a comprender y orientar, pero no controla
por sí sola acciones sensibles como detener permanentemente el bot ni inventa
información institucional variable.
