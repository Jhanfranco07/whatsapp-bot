const path = require("path");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

require("dotenv").config({ path: path.resolve(__dirname, "..", ".env") });

const apiUrl = process.env.BRIDGE_API_URL || "http://127.0.0.1:8000";
const apiKey = process.env.INBOUND_API_KEY || "";

const client = new Client({
  authStrategy: new LocalAuth({
    clientId: "orientador-usil",
    dataPath: path.resolve(__dirname, ".wwebjs_auth"),
  }),
  puppeteer: {
    headless: false,
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
  console.log("Puente listo. Esperando mensajes entrantes...");
});

client.on("auth_failure", (message) => {
  console.error("Falló la autenticación de WhatsApp:", message);
});

client.on("disconnected", (reason) => {
  console.error("WhatsApp Web se desconectó:", reason);
});

client.on("message", async (message) => {
  if (message.fromMe || message.from === "status@broadcast" || message.from.endsWith("@g.us")) {
    return;
  }

  const phoneNumber = message.from.replace("@c.us", "");
  const text = (message.body || "").trim();
  if (!text) {
    return;
  }

  console.log(`Mensaje recibido de ${phoneNumber}: ${text}`);

  try {
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
          source: "whatsapp-web.js",
        },
        send_reply: false,
      }),
    });

    if (!response.ok) {
      throw new Error(`FastAPI respondió ${response.status}: ${await response.text()}`);
    }

    const result = await response.json();
    await message.reply(result.bot_reply);
    console.log(`Respuesta enviada a ${phoneNumber}. Intent: ${result.intent}`);
  } catch (error) {
    console.error(`No se pudo procesar el mensaje de ${phoneNumber}:`, error.message);
  }
});

console.log(`Conectando el puente con ${apiUrl}...`);
client.initialize();
