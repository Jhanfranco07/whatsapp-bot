const path = require("path");
const http = require("http");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

require("dotenv").config({ path: path.resolve(__dirname, "..", ".env") });

const apiUrl = process.env.BRIDGE_API_URL || "http://127.0.0.1:8000";
const apiKey = process.env.INBOUND_API_KEY || "";
const outboundHost = process.env.BRIDGE_OUTBOUND_HOST || "127.0.0.1";
const outboundPort = Number(process.env.BRIDGE_OUTBOUND_PORT || 3001);
const headless = (process.env.BRIDGE_HEADLESS || "true").toLowerCase() === "true";
let clientReady = false;
let shuttingDown = false;
let messageDebounceMs = Number(process.env.BRIDGE_MESSAGE_DEBOUNCE_SECONDS || 3) * 1000;
let settingsRefreshTimer = null;

class SafeLocalAuth extends LocalAuth {
  async logout() {
    try {
      await super.logout();
    } catch (error) {
      const message = String(error?.message || error);
      if (message.includes("EBUSY") || message.includes("EPERM")) {
        console.warn(
          "La sesión anterior está siendo liberada por Windows. " +
          "El puente continuará y mostrará un nuevo QR cuando esté listo."
        );
        return;
      }
      throw error;
    }
  }
}

const client = new Client({
  authStrategy: new SafeLocalAuth({
    clientId: "orientador-usil",
    dataPath: path.resolve(__dirname, ".wwebjs_auth"),
    rmMaxRetries: 15,
  }),
  puppeteer: {
    headless,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

client.on("qr", (qr) => {
  console.log("\nEscanea este QR desde WhatsApp > Dispositivos vinculados:\n");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("Sesión de WhatsApp autenticada.");
});

client.on("ready", () => {
  clientReady = true;
  console.log("Puente listo. Esperando mensajes entrantes...");
});

client.on("auth_failure", (message) => {
  clientReady = false;
  console.error("No se pudo validar la sesión de WhatsApp. Espera el nuevo QR para vincularla.");
  if (message) {
    console.error(`Detalle: ${message}`);
  }
});

client.on("disconnected", (reason) => {
  clientReady = false;
  if (reason === "LOGOUT") {
    console.warn("WhatsApp cerró la sesión guardada. Preparando una nueva vinculación...");
  } else {
    console.warn(`WhatsApp Web se desconectó (${reason}). Reinicia el puente si no se recupera.`);
  }
});

function sendJson(response, status, payload) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(payload));
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
      if (body.length > 100000) {
        reject(new Error("Solicitud demasiado grande"));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolve(JSON.parse(body || "{}"));
      } catch {
        reject(new Error("JSON inválido"));
      }
    });
    request.on("error", reject);
  });
}

const outboundServer = http.createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    return sendJson(response, clientReady ? 200 : 503, { ok: clientReady });
  }

  if (request.method !== "POST" || request.url !== "/send") {
    return sendJson(response, 404, { error: "Ruta no encontrada" });
  }
  if (apiKey && request.headers["x-inbound-api-key"] !== apiKey) {
    return sendJson(response, 401, { error: "Clave inválida" });
  }
  if (!clientReady) {
    return sendJson(response, 503, { error: "WhatsApp todavía no está listo" });
  }

  try {
    const payload = await readJson(request);
    const phoneNumber = String(payload.phone_number || "").replace(/\D/g, "");
    const message = String(payload.message || "").trim();
    if (!phoneNumber || !message) {
      return sendJson(response, 422, { error: "phone_number y message son obligatorios" });
    }

    const numberId = await client.getNumberId(phoneNumber);
    if (!numberId) {
      return sendJson(response, 422, { error: "El número no está registrado en WhatsApp" });
    }
    const sent = await client.sendMessage(numberId._serialized, message);
    console.log(`Mensaje saliente enviado a ${phoneNumber}.`);
    return sendJson(response, 200, {
      ok: true,
      message_id: sent.id?._serialized || null,
    });
  } catch (error) {
    console.error("No se pudo enviar mensaje saliente:", error.message);
    return sendJson(response, 500, { error: error.message });
  }
});

function startOutboundServer() {
  return new Promise((resolve, reject) => {
    const onError = (error) => {
      outboundServer.off("listening", onListening);
      reject(error);
    };
    const onListening = () => {
      outboundServer.off("error", onError);
      console.log(`Envío saliente disponible en http://${outboundHost}:${outboundPort}/send`);
      resolve();
    };
    outboundServer.once("error", onError);
    outboundServer.once("listening", onListening);
    outboundServer.listen(outboundPort, outboundHost);
  });
}

async function waitForApi() {
  let warned = false;
  while (!shuttingDown) {
    try {
      const response = await fetch(`${apiUrl}/health`, {
        signal: AbortSignal.timeout(5000),
      });
      if (response.ok) {
        if (warned) {
          console.log("FastAPI está disponible. Continuando con WhatsApp...");
        }
        return;
      }
    } catch {
      // FastAPI puede estar iniciando todavía.
    }
    if (!warned) {
      console.warn(`FastAPI no está disponible en ${apiUrl}. Reintentando cada 5 segundos...`);
      warned = true;
    }
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
}

async function refreshRuntimeSettings() {
  try {
    const response = await fetch(`${apiUrl}/bridge/settings`, {
      headers: apiKey ? { "X-Inbound-Api-Key": apiKey } : {},
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      return;
    }
    const settings = await response.json();
    const seconds = Number(settings.bot_message_debounce_seconds);
    if (Number.isFinite(seconds) && seconds >= 1 && seconds <= 15) {
      messageDebounceMs = seconds * 1000;
    }
  } catch {
    // Se conserva el último valor conocido si FastAPI está temporalmente ocupado.
  }
}

async function resolvePhoneNumber(message) {
  const sourceId = message.author || message.from;
  let phoneId = sourceId;

  if (sourceId.endsWith("@lid")) {
    const [mapping] = await client.getContactLidAndPhone([sourceId]);
    phoneId = mapping?.pn;
    if (!phoneId) {
      throw new Error(`No se pudo resolver el teléfono real para ${sourceId}`);
    }
  }

  return phoneId.replace(/@(c\.us|s\.whatsapp\.net)$/, "");
}

async function postInbound(payload) {
  let lastError;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      const response = await fetch(`${apiUrl}/webhooks/whatsapp/inbound`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(apiKey ? { "X-Inbound-Api-Key": apiKey } : {}),
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(15000),
      });
      if (response.ok) {
        return await response.json();
      }
      const detail = await response.text();
      lastError = new Error(`FastAPI respondió ${response.status}: ${detail}`);
      if (response.status < 500 && response.status !== 429) {
        throw lastError;
      }
    } catch (error) {
      lastError = error;
      if (
        String(error?.message || "").includes("respondió 4") &&
        !String(error?.message || "").includes("respondió 429")
      ) {
        throw error;
      }
    }
    if (attempt < 5) {
      const waitMs = Math.min(15000, 1000 * 2 ** (attempt - 1));
      console.warn(`FastAPI no respondió. Reintento ${attempt}/5 en ${waitMs / 1000}s...`);
      await new Promise((resolve) => setTimeout(resolve, waitMs));
    }
  }
  throw lastError || new Error("FastAPI no respondió después de 5 intentos");
}

async function processMessages(messages) {
  const message = messages[messages.length - 1];
  const text = messages.map((item) => (item.body || "").trim()).filter(Boolean).join("\n");
  try {
    const phoneNumber = await resolvePhoneNumber(message);
    console.log(
      `${messages.length} mensaje(s) recibido(s) de ${phoneNumber}; procesando una sola respuesta.`
    );

    const result = await postInbound({
      phone_number: phoneNumber,
      message: text,
      timestamp: new Date(Number(message.timestamp) * 1000).toISOString(),
      raw_payload: {
        whatsapp_message_id: message.id?._serialized || null,
        whatsapp_message_ids: messages.map((item) => item.id?._serialized).filter(Boolean),
        grouped_message_count: messages.length,
        whatsapp_source_id: message.author || message.from,
        source: "whatsapp-web.js",
      },
      send_reply: true,
    });
    if (result.should_reply && result.bot_reply) {
      console.log(
        `Respuesta encolada para ${phoneNumber}. Intent: ${result.intent}. Clasificador: ${result.classification_source}`
      );
    } else {
      console.log(`Mensaje guardado sin respuesta para ${phoneNumber}. Intent: ${result.intent}`);
    }
  } catch (error) {
    console.error(`No se pudo procesar el mensaje de ${message.author || message.from}:`, error.message);
  }
}

const contactQueues = new Map();
const pendingMessages = new Map();

client.on("message", (message) => {
  if (
    message.fromMe ||
    message.from === "status@broadcast" ||
    message.from.endsWith("@g.us") ||
    !(message.body || "").trim()
  ) {
    return;
  }
  const contactId = message.author || message.from;
  const pending = pendingMessages.get(contactId) || { messages: [], timer: null };
  pending.messages.push(message);
  clearTimeout(pending.timer);
  pending.timer = setTimeout(() => {
    pendingMessages.delete(contactId);
    const batch = pending.messages;
    const previous = contactQueues.get(contactId) || Promise.resolve();
    const current = previous.then(() => processMessages(batch));
    contactQueues.set(contactId, current);
    current.finally(() => {
      if (contactQueues.get(contactId) === current) {
        contactQueues.delete(contactId);
      }
    });
  }, messageDebounceMs);
  pendingMessages.set(contactId, pending);
});

async function shutdown(exitCode = 0) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  clientReady = false;
  clearInterval(settingsRefreshTimer);
  for (const pending of pendingMessages.values()) {
    clearTimeout(pending.timer);
  }
  try {
    if (outboundServer.listening) {
      await new Promise((resolve) => outboundServer.close(resolve));
    }
    await client.destroy();
  } catch {
    // El navegador puede haberse cerrado antes que Node.
  }
  process.exit(exitCode);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
process.on("unhandledRejection", (error) => {
  console.error(`El puente no pudo continuar: ${error?.message || error}`);
  shutdown(1);
});
process.on("uncaughtException", (error) => {
  const message = String(error?.message || error);
  if (message.includes("EBUSY") && message.includes(".wwebjs_auth")) {
    console.error(
      "Windows mantiene bloqueada la sesión de WhatsApp. Cierra otras instancias del puente y vuelve a ejecutar npm start."
    );
  } else {
    console.error(`El puente se detuvo: ${message}`);
  }
  shutdown(1);
});

async function main() {
  console.log(`Conectando el puente con ${apiUrl}...`);
  await waitForApi();
  if (shuttingDown) {
    return;
  }
  await refreshRuntimeSettings();
  console.log(
    `Agrupación de mensajes configurada en ${messageDebounceMs / 1000} segundo(s).`
  );
  settingsRefreshTimer = setInterval(refreshRuntimeSettings, 30000);
  try {
    await startOutboundServer();
  } catch (error) {
    if (error.code === "EADDRINUSE") {
      console.error(
        `El puerto ${outboundPort} ya está ocupado. Cierra la otra instancia del bridge antes de ejecutar npm start.`
      );
    } else {
      console.error(`No se pudo iniciar el servidor saliente: ${error.message}`);
    }
    return shutdown(1);
  }
  try {
    await client.initialize();
  } catch (error) {
    console.error(`No se pudo iniciar WhatsApp Web: ${error.message}`);
    return shutdown(1);
  }
}

main();
