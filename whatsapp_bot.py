"""
LavaYa Miraflores — Bot de WhatsApp con IA (Claude)
=====================================================
El bot usa Claude Haiku para entender cualquier pregunta del cliente
en lenguaje natural y tomar pedidos automáticamente.

Plataforma: Flask + Meta WhatsApp Cloud API + Anthropic API
Deploy:     Railway.app
"""

import os
import json
import re
import requests
from datetime import datetime
from flask import Flask, request, jsonify
import anthropic

app    = Flask(__name__)
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# ── Historial de conversaciones por número de teléfono ───────────────────────
conversations: dict[str, list] = {}
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "pedidos.json")

# ── System prompt — toda la info del negocio ──────────────────────────────────
SYSTEM_PROMPT = """\
Sos el asistente de WhatsApp de *LavaYa Miraflores*, una lavandería con delivery \
en Miraflores, Lima, Perú.

Tu personalidad: profesional, amable y moderno. Hablas en español latino \
neutro con "tú" — NUNCA uses "vos", "usted", "necesitás", "querés", "podés" \
ni ninguna forma argentina. Siempre di "necesitas", "quieres", "puedes". \

FORMATO OBLIGATORIO: \
- Siempre usa emojis relevantes (🧺🚚✅💰🕐📍) \
- Cuando ofrezcas opciones, SIEMPRE ponlas como lista numerada así: \
  1️⃣ Opción uno \
  2️⃣ Opción dos \
  3️⃣ Opción tres \
- Separa bien los párrafos para que sea fácil de leer en WhatsApp \
- Máximo 6 líneas por mensaje \
- El cliente puede responder con el número o escribir lo que quiera

━━━ BIENVENIDA ━━━
Cuando el cliente saluda (hola, buenas, buenos días, holi, hey, etc.), \
SIEMPRE responde con EXACTAMENTE este texto — sin cambiar una sola palabra, \
sin importar si ya conversaron antes:

¡Hola! 😊 Bienvenido a LavaYa Miraflores 🧺

Recogemos, lavamos y entregamos tu ropa en 24-48 horas en Miraflores.

¿Cómo te puedo ayudar hoy?

1️⃣ Quiero lavar mi ropa
2️⃣ Consultar precios
3️⃣ Tengo una pregunta

━━━ SERVICIOS Y PRECIOS ━━━
- Lavado al peso:        S/ 9 por kg
- Lavado + planchado:    S/ 12 por kg
- Dry clean camisa:      S/ 11 por prenda
- Dry clean pantalón:    S/ 12 por prenda
- Dry clean terno:       S/ 25 por unidad
- Ropa de cama:          S/ 22.50 por pieza (mínimo 2 piezas = S/ 45)
- Zapatillas:            S/ 30 por par
- Express (cualquier servicio): +S/ 8 adicional → entrega en 24h garantizada
- Entrega normal: 24 a 48 horas

━━━ INFORMACIÓN CLAVE ━━━
- Zona de cobertura: Miraflores. Próximamente San Isidro y Barranco.
- Pago: Yape, Plin, efectivo al entregar, o transferencia bancaria.
- Sin cargos ocultos. El precio que se dice es el que se cobra.
- El cliente habla con una persona real, no con una app impersonal.
- El papá del dueño hace el delivery con su camioneta.
- Si el cliente tiene dudas sobre si una prenda necesita dry clean,
  recomendalo para prendas delicadas, trajes, lana, seda, o con etiqueta
  "dry clean only".

━━━ PREGUNTAS FRECUENTES ━━━
P: ¿Por qué elegir LavaYa y no GetLavado?
R: GetLavado cobra S/ 12 de comisión oculta que muchos no ven al pedir.
   Nosotros no cobramos comisiones — el precio es fijo y transparente.

P: ¿Por qué elegir LavaYa y no Classic Premium?
R: Classic Premium tarda 4 a 6 días. Nosotros entregamos en 24-48h.

P: ¿Cómo sé que mi ropa está segura?
R: Trabajamos con lavanderías socias de confianza en Miraflores.
   Si algo sale mal, lo resolvemos sin costo adicional.

P: ¿Qué es el dry clean?
R: Limpieza sin agua usando solventes especiales. Ideal para ropa delicada,
   trajes, prendas con etiqueta "dry clean only".

━━━ TOMAR PEDIDOS ━━━
Cuando el cliente quiera hacer un pedido, sigue EXACTAMENTE este flujo \
paso a paso. Haz UNA pregunta a la vez, espera la respuesta, luego la siguiente.

PASO 1 — Mostrar servicios:
"¿Qué servicio necesitas? 🧺

🔹 Lavado al peso — S/ 9/kg
🔹 Lavado + planchado — S/ 12/kg
🔹 Dry clean camisa — S/ 11
🔹 Dry clean pantalón — S/ 12
🔹 Dry clean terno — S/ 25
🔹 Ropa de cama — S/ 22.50/pieza (mín. 2 piezas)
🔹 Zapatillas — S/ 30/par
🔹 Servicio express — +S/ 8 (entrega en 24h)

Escribe el servicio que necesitas."

PASO 2 — Preguntar cantidad según el servicio elegido.

PASO 3 — Preguntar si desea express:
"¿Deseas servicio express? ⚡
✅ Sí — entrega en 24h (+S/ 8)
❌ No — entrega normal 24-48h"

PASO 4 — Pedir nombre: "¿Cuál es tu nombre completo? 👤"

PASO 5 — Pedir dirección: "¿Cuál es tu dirección en Miraflores? 📍"

PASO 6 — Pedir horario de recojo:
"¿A qué hora podemos pasar a recoger? 🕐
🌅 Mañana — 8am a 12pm
🌇 Tarde — 12pm a 6pm
📝 Otro horario — escríbelo"

PASO 7 — Mostrar resumen completo y pedir confirmación:
"📋 *Resumen de tu pedido:*

🧺 Servicio: [servicio]
📦 Cantidad: [cantidad]
👤 Nombre: [nombre]
📍 Dirección: [dirección]
🕐 Recojo: [horario]
💰 Total estimado: [precio]

¿Confirmas tu pedido?
✅ Sí, confirmar
❌ Cancelar"

Cuando el cliente confirme, al FINAL del mensaje agrega exactamente esto \
(sin espacios, el cliente no lo ve):

PEDIDO_LISTO:{"servicio":"...","cantidad":"...","express":true/false,"nombre":"...","direccion":"...","horario":"..."}

Si el cliente cancela, no generes el bloque PEDIDO_LISTO.

━━━ LÍMITES ━━━
- Solo hablás de LavaYa y sus servicios. Si te preguntan otra cosa,
  decís amablemente que solo podés ayudar con la lavandería.
- Si el cliente se pone grosero, respondés con calma y profesionalismo.
- No inventés precios ni servicios que no están en la lista de arriba.
"""


# ── Guardar pedidos ───────────────────────────────────────────────────────────
def save_order(phone: str, data: dict) -> int:
    orders = []
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                orders = json.load(f)
        except (json.JSONDecodeError, IOError):
            orders = []

    data["id"]       = len(orders) + 1
    data["telefono"] = phone.replace("whatsapp:", "")
    data["fecha"]    = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["estado"]   = "pendiente"
    orders.append(data)

    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

    return data["id"]


def extract_order(text: str) -> tuple[dict | None, str]:
    pattern = r"PEDIDO_LISTO:\{.*?\}"
    match   = re.search(pattern, text, re.DOTALL)

    if not match:
        return None, text

    try:
        json_str = match.group(0).replace("PEDIDO_LISTO:", "")
        pedido   = json.loads(json_str)
    except json.JSONDecodeError:
        return None, text

    clean_text = text[:match.start()].strip() + "\n" + text[match.end():].strip()
    clean_text = clean_text.strip()

    return pedido, clean_text


# ── Lógica principal ──────────────────────────────────────────────────────────
def handle_message(phone: str, message: str) -> str:
    if phone not in conversations:
        conversations[phone] = []

    conversations[phone].append({
        "role":    "user",
        "content": message,
    })

    recent_messages = conversations[phone][-30:]

    try:
        response = client.messages.create(
            model      = "claude-haiku-4-5-20251001",
            max_tokens = 600,
            system     = SYSTEM_PROMPT,
            messages   = recent_messages,
        )
        reply = response.content[0].text

    except anthropic.APIError as e:
        reply = (
            "Lo siento, estoy teniendo un problema técnico en este momento. "
            "Escribinos en unos minutos o llamanos directamente 🙏"
        )
        print(f"[ERROR Anthropic API] {e}")

    pedido, reply_clean = extract_order(reply)

    if pedido:
        order_id = save_order(phone, pedido)
        reply_clean = reply_clean.replace("#{id}", f"#{order_id}")
        if f"#{order_id}" not in reply_clean:
            reply_clean += f"\n\n📋 Tu número de pedido es *#{order_id}*"

    conversations[phone].append({
        "role":    "assistant",
        "content": reply_clean,
    })

    return reply_clean


# ── Enviar mensaje via Meta Graph API ────────────────────────────────────────
def send_whatsapp_message(to: str, text: str) -> None:
    token    = os.environ.get("WHATSAPP_TOKEN", "")
    phone_id = os.environ.get("PHONE_NUMBER_ID", "")
    url      = f"https://graph.facebook.com/v18.0/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to":   to,
        "type": "text",
        "text": {"body": text},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code not in (200, 201):
            print(f"[ERROR Meta API] {r.status_code} — {r.text}")
    except requests.RequestException as e:
        print(f"[ERROR send_whatsapp_message] {e}")


# ── Webhook de Meta WhatsApp Cloud API ───────────────────────────────────────
VERIFY_TOKEN = "lavaya2024"

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[Webhook] Verificación exitosa ✅")
        return challenge, 200
    else:
        print("[Webhook] Token incorrecto ❌")
        return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}

    try:
        entry   = data["entry"][0]
        changes = entry["changes"][0]["value"]

        if "messages" not in changes:
            return "OK", 200

        msg         = changes["messages"][0]
        from_number = msg["from"]
        msg_type    = msg.get("type", "")

        if msg_type == "text":
            incoming_msg = msg["text"]["body"].strip()
        else:
            incoming_msg = "[sticker/imagen/audio]"

        if not incoming_msg:
            return "OK", 200

        reply = handle_message(from_number, incoming_msg)
        send_whatsapp_message(from_number, reply)

    except (KeyError, IndexError, TypeError) as e:
        print(f"[ERROR parsing webhook] {e} — data: {data}")

    return "OK", 200


# ── Panel de pedidos ──────────────────────────────────────────────────────────
@app.route("/pedidos")
def ver_pedidos():
    if not os.path.exists(ORDERS_FILE):
        return "<h2 style='font-family:sans-serif'>No hay pedidos todavía 📭</h2>"

    with open(ORDERS_FILE, "r", encoding="utf-8") as f:
        orders = json.load(f)

    rows = ""
    for o in reversed(orders):
        express = "⚡ Sí" if o.get("express") else "No"
        estado  = o.get("estado", "pendiente")
        color   = {
            "pendiente": "#FF9800",
            "en camino": "#2196F3",
            "entregado": "#4CAF50",
            "cancelado": "#F44336",
        }.get(estado, "#999")

        rows += f"""
        <tr>
          <td>#{o.get('id','')}</td>
          <td>{o.get('fecha','')}</td>
          <td><strong>{o.get('nombre','')}</strong></td>
          <td>{o.get('telefono','')}</td>
          <td>{o.get('servicio','')}</td>
          <td>{o.get('cantidad','')}</td>
          <td>{o.get('direccion','')}</td>
          <td>{o.get('horario','')}</td>
          <td>{express}</td>
          <td>
            <span style="background:{color};color:white;padding:3px 10px;
                         border-radius:12px;font-size:12px;font-weight:bold">
              {estado.upper()}
            </span>
          </td>
        </tr>"""

    pendientes = sum(1 for o in orders if o.get("estado") == "pendiente")

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>LavaYa — Pedidos</title>
<meta http-equiv="refresh" content="30">
<style>
  body  {{ font-family: -apple-system, sans-serif; padding: 24px; background: #f0f4f8; margin: 0; }}
  h1    {{ color: #1D9E75; margin: 0 0 4px; }}
  .stats {{ display:flex; gap:16px; margin: 16px 0; }}
  .stat {{ background:white; border-radius:10px; padding:12px 20px;
           box-shadow:0 1px 3px rgba(0,0,0,.1); }}
  .stat strong {{ display:block; font-size:24px; color:#1D9E75; }}
  table {{ border-collapse: collapse; width: 100%; background: white;
           box-shadow: 0 1px 4px rgba(0,0,0,.1); border-radius: 10px;
           overflow: hidden; }}
  th    {{ background: #1D9E75; color: white; padding: 11px 13px;
           text-align: left; font-size: 12px; text-transform: uppercase;
           letter-spacing: .5px; }}
  td    {{ padding: 10px 13px; border-bottom: 1px solid #eee; font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  small {{ color: #999; font-size: 11px; display:block; margin-top:
