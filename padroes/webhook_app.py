"""
Receptor de webhooks em Flask: assinatura, resposta rápida, processamento em segundo plano.

Três regras para um webhook que não dá dor de cabeça
----------------------------------------------------
1. **Verifique a assinatura.** Plataformas de e-commerce assinam o corpo
   da requisição com HMAC-SHA256 usando o segredo do aplicativo e mandam
   o resultado num cabeçalho. Sem a verificação, qualquer pessoa que
   descubra a URL consegue disparar ações no ERP. A comparação usa
   ``hmac.compare_digest`` para não vazar informação pelo tempo de resposta.

2. **Responda 200 em milissegundos.** A plataforma espera a resposta por
   poucos segundos; se demorar, reenvia o evento, e aí o mesmo pedido
   chega duas vezes. Então o endpoint só valida, registra e devolve 200.
   O trabalho pesado (falar com o ERP) roda numa thread.

3. **Falhou, enfileira.** Se o processamento em segundo plano falhar
   (ERP fora do ar, por exemplo), o evento vai para a fila de
   retentativas em vez de se perder. Combinado com o lock por pedido
   (``estado_json``), eventos duplicados viram no-ops.

``criar_app`` recebe as dependências por parâmetro, o que permite testar
o receptor com o cliente de testes do Flask, sem rede e sem ERP.
"""

import hashlib
import hmac
import logging
import threading

from flask import Flask, jsonify, request

log = logging.getLogger(__name__)


def assinatura_valida(corpo_bruto, segredo, assinatura_recebida):
    """Confere o HMAC-SHA256 (hex) do corpo da requisição."""
    if not assinatura_recebida or not segredo:
        return False
    esperada = hmac.new(segredo.encode("utf-8"), corpo_bruto, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, assinatura_recebida.strip().lower())


def criar_app(segredo, processadores, fila=None, cabecalho_assinatura="X-Webhook-Signature",
              executar_em_thread=True):
    """Monta a aplicação Flask.

    ``processadores`` mapeia o nome do evento (parte final da URL) para
    uma função ``f(payload)``; ela devolve True/False ou levanta exceção.
    ``fila`` é uma ``FilaRetentativas`` (opcional). Em falha, o evento é
    enfileirado como (evento, id) para ser reprocessado depois.
    """
    app = Flask(__name__)

    def _processar(evento, payload):
        chave = payload.get("id")
        try:
            ok = processadores[evento](payload)
        except Exception as e:  # ERP fora do ar, timeout, erro inesperado
            log.error("falha ao processar %s de %s: %s", evento, chave, e)
            ok = False
        if not ok and fila is not None and chave is not None:
            fila.enfileirar(evento, chave)

    @app.post("/webhooks/<evento>")
    def receber(evento):
        if evento not in processadores:
            return jsonify({"erro": "evento desconhecido"}), 404

        corpo = request.get_data()  # bytes crus, exatamente o que foi assinado
        if not assinatura_valida(corpo, segredo, request.headers.get(cabecalho_assinatura)):
            log.warning("assinatura inválida em %s (origem %s)", evento, request.remote_addr)
            return jsonify({"erro": "assinatura inválida"}), 401

        payload = request.get_json(silent=True) or {}
        log.info("evento %s recebido para id %s", evento, payload.get("id"))

        if executar_em_thread:
            threading.Thread(target=_processar, args=(evento, payload), daemon=True).start()
        else:
            _processar(evento, payload)  # útil em testes

        return jsonify({"status": "ok"}), 200

    @app.get("/webhooks/ping")
    def ping():
        return jsonify({"status": "ok"}), 200

    return app
