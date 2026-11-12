"""Envia um evento assinado (HMAC-SHA256) para o servidor de exemplo.

    python exemplos/enviar_webhook_assinado.py criado 42
"""
import hashlib
import hmac
import json
import os
import sys
import urllib.request

SEGREDO = os.environ.get("WEBHOOK_SEGREDO", "troque-este-segredo")
URL = os.environ.get("WEBHOOK_URL", "http://127.0.0.1:5000/webhooks")

evento = sys.argv[1] if len(sys.argv) > 1 else "criado"
pedido_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1

corpo = json.dumps({"id": pedido_id, "evento": evento}).encode()
assinatura = hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()

req = urllib.request.Request(f"{URL}/{evento}", data=corpo, method="POST",
                             headers={"Content-Type": "application/json", "X-Webhook-Signature": assinatura})
with urllib.request.urlopen(req) as resp:
    print(resp.status, resp.read().decode())
