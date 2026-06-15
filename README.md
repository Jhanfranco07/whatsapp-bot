# Orientador USIL

Prototipo conversacional modular para registrar interesados, enviar una campaña
inicial por WhatsApp Web, simular mensajes entrantes, clasificar intenciones,
guardar conversaciones en PostgreSQL y responder con información controlada.

Documentación técnica completa: [ARQUITECTURA.md](ARQUITECTURA.md)

El proyecto está desarrollado completamente en Python. No usa n8n ni la API
oficial de WhatsApp Business.

## Arquitectura

```text
Contacto PostgreSQL
  -> CampaignService
  -> WhatsAppProvider
  -> BridgeProvider / dry-run

Webhook o simulador inbound
  -> ConversationService
      -> verifica stop_bot persistente
  -> IntentClassifier
      -> reglas rápidas para consultas simples
      -> SemanticEngine: reglas, TF-IDF y Levenshtein
  -> ChatbotService
  -> PostgreSQL
  -> respuesta JSON o proveedor configurado
```

La lógica del chatbot, PostgreSQL, recepción y envío están desacoplados.
`BridgeProvider` implementa `WhatsAppProvider` y reutiliza la sesión autenticada
del puente `whatsapp-web.js`.

## Funciones

- Contactos únicos por teléfono y normalización para Perú.
- Historial inbound y outbound.
- Clasificación determinista por reglas, patrones y diccionarios.
- Respuestas controladas mediante plantillas y datos institucionales.
- Contexto ampliable desde `app/data/conocimiento_institucional.json`.
- Respuestas controladas, sin inventar costos, fechas o beneficios.
- Baja persistente mediante `stop_bot` y bloqueo de campañas a contactos dados de baja.
- Base de conocimiento ampliable con respuestas y fuentes verificadas.
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

## Inicio real con WhatsApp Web

Este es el flujo para usar el chatbot con mensajes reales. La simulación descrita
más adelante es opcional y no inicia WhatsApp Web.

### 1. Preparar la base e importar el Excel

Ejecuta estos comandos desde la raíz del proyecto:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/init_db.py
python scripts/import_contacts.py --file dataAlumnos.xlsx
```

El Excel debe estar dentro del proyecto. El importador reconoce `COMPLETO` como
nombre y `CELULAR` como teléfono.

### 2. Enviar la campaña inicial por WhatsApp

El modo recomendado reutiliza la sesión persistente del puente y envía sin abrir
y cerrar WhatsApp Web por cada contacto. En `.env`, configura:

```text
WHATSAPP_PROVIDER=bridge
BRIDGE_HEADLESS=false
```

Primero inicia el backend y el puente como se explica en el paso 3. Cuando la
consola muestre `Puente listo`, prueba con un solo número:

```powershell
python scripts/send_campaign.py --phone 51999999999
```

Para enviar a todos los contactos importados que todavía pueden recibir
campañas:

```powershell
python scripts/send_campaign.py
```

El script espera 5 segundos entre contactos. Puedes cambiarlo con `--delay`,
por ejemplo `python scripts/send_campaign.py --delay 10`.

Para dejar la campaña ejecutándose como proceso oculto en Windows:

```powershell
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "scripts\send_campaign.py --delay 5" `
  -RedirectStandardOutput "campaign.stdout.log" `
  -RedirectStandardError "campaign.stderr.log" `
  -WindowStyle Hidden
```

Consulta el resultado en `campaign.stdout.log` y los errores en
`campaign.stderr.log`. FastAPI y el puente deben continuar activos.

El envío se realiza mediante la misma sesión de `whatsapp-web.js` que recibe y
responde mensajes. Se abre una sola ventana persistente de WhatsApp Web; puedes
minimizarla y se reutilizará para toda la campaña. La consola del puente y
FastAPI deben permanecer ejecutándose. `BRIDGE_HEADLESS=true` intenta ocultar
Chromium por completo, pero WhatsApp Web puede no iniciar correctamente en todos
los equipos.

La integración no es oficial. Evita enviar grandes cantidades en poco tiempo,
contacta únicamente personas autorizadas y respeta inmediatamente las bajas
para reducir el riesgo de restricciones de WhatsApp.

### 3. Iniciar el chatbot que responde mensajes reales

Mantén abiertas dos terminales.

Terminal 1, desde la raíz del proyecto:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Terminal 2, desde la raíz del proyecto:

```powershell
cd bridge
npm start
```

La primera vez aparecerá un QR. Escanéalo desde WhatsApp en
`Dispositivos vinculados > Vincular dispositivo`. Cuando aparezca
`Puente listo. Esperando mensajes entrantes...`, el chatbot ya está activo.

La sesión queda guardada automáticamente en `bridge/.wwebjs_auth`. En los
siguientes inicios normalmente solo debes volver a ejecutar las dos terminales;
no borres esa carpeta si quieres conservar la sesión. Si WhatsApp cierra o
invalida la sesión, aparecerá un nuevo QR.

Para detener el chatbot, presiona `Ctrl+C` en ambas terminales.


### PostgreSQL local con Docker

```powershell
docker compose up -d
python scripts/init_db.py
```

Usa `DB_MODE=local` con la URL incluida en `.env.example`. Para Supabase u otro
PostgreSQL remoto usa `DB_MODE=cloud` y configura `DATABASE_URL`.

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

Con `WHATSAPP_PROVIDER=bridge`, inicia primero FastAPI y el puente. Después:

```powershell
python scripts/send_campaign.py --limit 1
```

Para probar primero con una sola persona:

```powershell
python scripts/send_campaign.py --phone 51984738899
```

El proveedor antiguo `pywhatkit` sigue disponible configurando
`WHATSAPP_PROVIDER=pywhatkit`, pero abre WhatsApp Web para cada envío.

## Probar sin WhatsApp Web

Estos comandos solo simulan una conversación contra el backend. No vinculan
WhatsApp Web ni dejan el chatbot escuchando mensajes reales.

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

Para el procedimiento completo de arranque, consulta
[Inicio real con WhatsApp Web](#inicio-real-con-whatsapp-web).

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
2. Se verifica en PostgreSQL si el contacto tiene `stop_bot=true`.
3. Se aplican reglas rápidas para consultas simples y seguras.
4. Se genera una respuesta desde plantillas y datos institucionales controlados.
5. Se guarda la conversación en PostgreSQL.
6. Se responde automáticamente en el mismo chat, salvo que el contacto esté detenido.

Cuando un contacto escribe `basta`, `stop`, `ya no` o una frase equivalente,
el sistema confirma la baja y guarda `stop_bot=true`. Los mensajes posteriores
se registran, pero el bot ya no responde ni incluye al contacto en campañas.
La baja exige una solicitud explícita: risas y respuestas breves como `JAJAJA`,
`XD`, `OK`, `YA`, `AJA` o `no gracias` nunca activan `stop_bot`.

`INBOUND_API_KEY` protege el webhook y debe coincidir entre FastAPI y el puente.

## Motor semántico local

El sistema no depende de servicios LLM externos. `SemanticEngine` clasifica en
cascada mediante reglas exactas, alias de carreras, TF-IDF por caracteres y
Levenshtein para consultas de baja confianza. El índice se construye una sola
vez al iniciar FastAPI usando `app/data/intent_corpus.json`.

Verifica el motor con:

```text
GET http://localhost:8000/health/llm
```

El nombre del endpoint se conserva por compatibilidad, pero devuelve el estado
del motor `tfidf_semantic`.

## Agregar información real

El archivo `app/data/conocimiento_institucional.json` permite agregar respuestas
confirmadas sin modificar Python. Cada entrada debe incluir:

- `palabras_clave`: formas en las que el usuario puede preguntar.
- `respuesta`: texto revisado por una persona responsable.
- `fuente_url`: enlace oficial que respalda la respuesta.
- `verificado_el`: fecha de la última revisión.

El bot prioriza estas entradas verificadas antes de responder con una plantilla.
No solicita llamadas ni promete derivaciones; cuando alguien pide contacto
humano, comparte únicamente los canales oficiales definidos en
`app/data/institucion.json`.

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
- PostgreSQL debe configurarse antes de usar servicios persistentes.
- El motor semántico funciona localmente sin servicios LLM.

## Mejoras futuras

- API oficial de WhatsApp Business.
- Migraciones Alembic.
- Panel administrativo y dashboard.
- Analítica de conversiones y RAG con fuentes oficiales.
