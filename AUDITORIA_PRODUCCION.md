# Auditoria de produccion

Fecha: 2026-06-22

## Corregido

- El compose productivo incluye PostgreSQL, API, bridge y worker.
- API y bridge tienen healthchecks; el worker espera a que WhatsApp este listo.
- Los contenedores reinician ante fallos y limitan el crecimiento de logs.
- Los procesos de aplicacion se ejecutan con usuarios sin privilegios.
- PostgreSQL y el endpoint saliente del bridge no se publican al host.
- Produccion rechaza claves administrativas vacias o predeterminadas.
- Contactos, campañas, simulacion e historial requieren clave administrativa.
- Los mensajes inbound son idempotentes por ID de WhatsApp.
- El bridge reintenta fallos temporales de FastAPI sin duplicar respuestas.
- Excel y CSV se validan antes de importar y tienen limite de tamaño y filas.
- Los recursos del panel son locales; no se confia la clave a un CDN externo.
- Dependencias Python y Node no reportan vulnerabilidades conocidas.

## Verificacion

- Suite automatizada: 186 pruebas aprobadas y 3 de integracion omitidas.
- `npm audit --omit=dev`: sin vulnerabilidades.
- `pip-audit -r requirements.txt`: sin vulnerabilidades.
- `docker compose config`: configuracion valida.
- Migracion activa: `0005_inbound_idempotency`.

## Riesgos residuales

- `whatsapp-web.js` no es una API oficial y WhatsApp puede cerrar o restringir
  la sesion. Ningun cambio de software elimina este riesgo.
- Los locks conversacionales y el rate limit viven en memoria. La configuracion
  productiva debe mantener una sola replica de FastAPI hasta moverlos a Redis o
  PostgreSQL.
- El compose enlaza la API solo a localhost y no incorpora TLS. Para acceso
  remoto se necesita un proxy HTTPS y control de acceso adicional.
- Los volumenes `usil_pgdata` y `whatsapp_auth` requieren una politica externa
  de copias de seguridad.
- Las tres pruebas PostgreSQL de integracion requieren `TEST_DATABASE_URL` con
  una base exclusiva y no se ejecutan contra la base operativa.
- La imagen Docker no pudo construirse durante esta auditoria porque Docker
  Desktop no estaba iniciado; la configuracion Compose si fue validada.
