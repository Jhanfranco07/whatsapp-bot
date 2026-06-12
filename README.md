# Orientador USIL

Prototipo conversacional modular para registrar interesados, enviar una campaña
inicial por WhatsApp Web, simular mensajes entrantes, clasificar intenciones,
guardar conversaciones en PostgreSQL y derivar solicitudes a asesores.

Documentación técnica completa: [ARQUITECTURA.md](ARQUITECTURA.md)

El proyecto está desarrollado completamente en Python. No usa n8n ni la API
oficial de WhatsApp Business.

## Arquitectura

```text
Contacto PostgreSQL
  -> CampaignService
  -> WhatsAppProvider
  -> PyWhatKitProvider / dry-run

Webhook o simulador inbound
  -> ConversationService
      -> verifica stop_bot persistente
  -> IntentClassifier
      -> reglas rápidas para consultas simples
      -> Ollama para explicaciones, campo laboral y comparaciones
  -> ChatbotService
  -> PostgreSQL
  -> respuesta JSON o proveedor configurado
```

La lógica del chatbot, PostgreSQL, recepción y envío están desacoplados.
`pywhatkit` solamente implementa `WhatsAppProvider`, por lo que puede
reemplazarse posteriormente.

## Funciones

- Contactos únicos por teléfono y normalización para Perú.
- Historial inbound y outbound.
- Clasificación determinista por reglas, patrones y diccionarios.
- Respuestas híbridas: plantillas controladas y Ollama local cuando aporta valor.
- Respuestas controladas, sin inventar costos, fechas o beneficios.
- Baja persistente mediante `stop_bot` y bloqueo de campañas a contactos dados de baja.
- Solicitudes de asesor sin duplicados pendientes.
- API FastAPI y scripts de consola.
- Modo `WHATSAPP_DRY_RUN=true` para no abrir WhatsApp Web.

## Instalación

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con las credenciales locales de PostgreSQL. `.env` está excluido
por `.gitignore`.

## PostgreSQL

El sistema no admite SQLite. Crea una base PostgreSQL:

```powershell
createdb orientador_usil
python scripts/init_db.py
```

La URL predeterminada de ejemplo es:

```text
postgresql+psycopg2://postgres:postgres@localhost:5432/orientador_usil
```

Si tu usuario o contraseña son diferentes, actualiza `DATABASE_URL` en `.env`.

## Ejecutar API

```powershell
uvicorn app.main:app --reload
```

Documentación interactiva: `http://localhost:8000/docs`

Endpoints principales:

- `GET /health`
- `POST /contacts`
- `POST /contacts/import`
- `GET /contacts`
- `GET /contacts/{phone_number}/messages`
- `POST /campaigns/send`
- `POST /webhooks/whatsapp/inbound`
- `POST /simulate/inbound`
- `GET /advisor-requests`

## Importar contactos

CSV, JSON o Excel con `phone_number` y columnas opcionales `full_name`, `school`,
`grade`, `email`, `career_interest` y `source`:

```powershell
python scripts/import_contacts.py --file contactos.csv
```

La hoja original `dataAlumnos.xlsx` también puede importarse directamente. El
script reconoce `COMPLETO` como nombre y `CELULAR` como teléfono:

```powershell
python scripts/import_contacts.py --file dataAlumnos.xlsx
```

La campaña siempre consulta PostgreSQL para poder respetar las bajas.

## Enviar campaña

Mantén `WHATSAPP_DRY_RUN=true` durante las pruebas:

```powershell
python scripts/send_campaign.py --limit 1
```

Para envío real, inicia sesión en WhatsApp Web y cambia
`WHATSAPP_DRY_RUN=false`. `pywhatkit` controla el navegador y no permite recibir
mensajes.

Para probar primero con una sola persona:

```powershell
python scripts/send_campaign.py --phone 51984738899
```

## Simular conversación

```powershell
python scripts/simulate_inbound.py --phone 51999999999 --message "quiero saber sobre ingeniería de sistemas"
```

O mediante HTTP en Windows:

```powershell
curl.exe -X POST http://localhost:8000/webhooks/whatsapp/inbound `
  -H "Content-Type: application/json" `
  -d "{\"phone_number\":\"51999999999\",\"message\":\"quiero saber sobre ingeniería de sistemas\",\"raw_payload\":{}}"
```

El webhook registra el inbound, clasifica la intención, genera y registra la
respuesta outbound, actualiza el estado y devuelve `bot_reply`. Por defecto no
intenta enviar esa respuesta por WhatsApp. Puedes enviar mediante el proveedor
configurado usando `"send_reply": true`; úsalo con cuidado porque `pywhatkit`
abre el navegador.

## Recibir y responder mensajes reales

El puente opcional `bridge/` usa `whatsapp-web.js` para escuchar mensajes
entrantes desde una sesión vinculada de WhatsApp Web. Es una integración no
oficial: puede dejar de funcionar o provocar restricciones de WhatsApp. Úsala
solo como prototipo y con una cuenta autorizada para pruebas.

Mantén FastAPI ejecutándose en una terminal:

```powershell
python -m uvicorn app.main:app --reload
```

En otra terminal, inicia el puente:

```powershell
cd bridge
npm install
npm start
```

La primera vez aparecerá un código QR. Escanéalo desde WhatsApp en
`Dispositivos vinculados`. Cuando aparezca `Puente listo`, cada mensaje nuevo:

1. Se envía al webhook FastAPI.
2. Se verifica en Supabase si el contacto tiene `stop_bot=true`.
3. Se aplican reglas rápidas para consultas simples y seguras.
4. Se usa una plantilla o se consulta Ollama para explicaciones, campo laboral y comparaciones.
5. Se guarda la conversación en Supabase.
6. Se responde automáticamente en el mismo chat, salvo que el contacto esté detenido.

Cuando un contacto escribe `basta`, `stop`, `ya no` o una frase equivalente,
el sistema confirma la baja y guarda `stop_bot=true`. Los mensajes posteriores
se registran, pero el bot ya no responde ni incluye al contacto en campañas.
La baja exige una solicitud explícita: risas y respuestas breves como `JAJAJA`,
`XD`, `OK`, `YA`, `AJA` o `no gracias` nunca activan `stop_bot`.

`INBOUND_API_KEY` protege el webhook y debe coincidir entre FastAPI y el puente.

## Ollama local opcional

Ollama se integra como proveedor LLM local mediante HTTP. La aplicación no
instala, inicia ni administra el proceso de Ollama. Las reglas existentes
siempre tienen prioridad para consultas simples y seguras. Ollama se utiliza
para consultas explicativas sobre una carrera, campo laboral, comparaciones y
como respaldo cuando las reglas no comprenden el mensaje.

Ollama devuelve un contrato JSON validado con intención, confianza, entidades y
una respuesta. El backend recalcula las decisiones sensibles (`response_key`,
`should_escalate` y `stop_bot`) y usa plantillas para admisión, costos, campus,
listado de carreras, bajas y derivación a asesores.

Las respuestas redactadas por Ollama mantienen un tono breve de orientación y
usan cierres variados con enlaces oficiales. El backend descarta cualquier baja
propuesta por el modelo cuando el mensaje original no solicita detenerse de
forma explícita.

El contexto institucional controlado vive en `app/data/institucion.json` e
incluye portal oficial, admisión, contacto, campus, internacionalidad, catálogo
oficial de carreras y políticas de respuesta. Ollama usa ese contexto para
clasificar y redactar respuestas acotadas sin inventar información.

Intenciones LLM soportadas:

```text
saludo, consulta_carreras, consulta_carrera_especifica, consulta_campo_laboral,
comparacion_carrera, consulta_admision, consulta_costos, consulta_campus,
quiere_asesor, agradecimiento, despedida,
detener_conversacion, fuera_de_alcance, no_entendido
```

Configuración:

```text
LLM_PROVIDER=ollama
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:0.8b
OLLAMA_THINK=false
OLLAMA_TEMPERATURE=0.2
OLLAMA_MAX_TOKENS=400
OLLAMA_TIMEOUT=120
```

Verifica que Ollama y el modelo estén disponibles:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
python scripts/check_ollama.py
```

Con FastAPI ejecutándose, también puedes consultar:

```text
GET http://localhost:8000/health/llm
```

Si Ollama no está ejecutándose, `/health/llm` devuelve HTTP `503` con un mensaje
claro. Durante una conversación, el chatbot registra el error y continúa con
las reglas y la plantilla `no_entendido`.

## Pruebas

```powershell
python -m pytest
```

Las pruebas unitarias nunca usan SQLite. Para ejecutar también las pruebas
reales de persistencia, define una base PostgreSQL exclusiva:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg2://postgres:clave@localhost:5432/orientador_usil_test"
python -m pytest
```

## Limitaciones actuales

- `whatsapp-web.js` es una integración no oficial y puede dejar de funcionar.
- La sesión vinculada de WhatsApp Web debe mantenerse autenticada.
- `pywhatkit` depende del navegador y solo sirve para campañas iniciales.
- PostgreSQL debe configurarse antes de usar servicios persistentes.
- Las respuestas LLM requieren que Ollama esté ejecutándose localmente.

## Mejoras futuras

- Adaptador propio con whatsapp-web.js o Baileys.
- API oficial de WhatsApp Business.
- Migraciones Alembic.
- Panel para asesores y dashboard.
- Analítica de conversiones y RAG con fuentes oficiales.
