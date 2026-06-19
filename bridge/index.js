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

const client = new Client({
  authStrategy: new LocalAuth({
    clientId: "orientador-usil",
    dataPath: path.resolve(__dirname, ".wwebjs_auth"),
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
  console.error("Falló la autenticación de WhatsApp:", message);
});

client.on("disconnected", (reason) => {
  clientReady = false;
  console.error("WhatsApp Web se desconectó:", reason);
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

outboundServer.listen(outboundPort, outboundHost, () => {
  console.log(`Envío saliente disponible en http://${outboundHost}:${outboundPort}/send`);
});

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

async function processMessage(message) {
  if (message.fromMe || message.from === "status@broadcast" || message.from.endsWith("@g.us")) {
    return;
  }

  const text = (message.body || "").trim();
  if (!text) {
    return;
  }

  try {
    const phoneNumber = await resolvePhoneNumber(message);
    console.log(`Mensaje recibido de ${phoneNumber}: ${text}`);

    const response = await fetch(`${apiUrl}/webhooks/whatsapp/inbound`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { "X-Inbound-Api-Key": apiKey } : {}),
      },
      body: JSON.stringify({
        phone_number: phoneNumber,
        message: text,
        timestamp: new Date(Number(message.timestamp) * 1000).toISOString(),
        raw_payload: {
          whatsapp_message_id: message.id?._serialized || null,
          whatsapp_source_id: message.author || message.from,
          source: "whatsapp-web.js",
        },
        send_reply: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`FastAPI respondió ${response.status}: ${await response.text()}`);
    }

    const result = await response.json();
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

client.on("message", (message) => {
  const contactId = message.author || message.from;
  const previous = contactQueues.get(contactId) || Promise.resolve();
  const current = previous.then(() => processMessage(message));

  contactQueues.set(contactId, current);
  current.finally(() => {
    if (contactQueues.get(contactId) === current) {
      contactQueues.delete(contactId);
    }
  });
});

console.log(`Conectando el puente con ${apiUrl}...`);
client.initialize();
