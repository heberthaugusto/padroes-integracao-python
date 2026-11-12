import hashlib
import hmac
import json

import pytest

from padroes.fila_retentativas import FilaRetentativas
from padroes.webhook_app import criar_app

SEGREDO = "segredo-de-teste"


def assinar(corpo: bytes):
    return hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()


@pytest.fixture
def ambiente(tmp_path):
    recebidos = []
    fila = FilaRetentativas(tmp_path / "fila.json")

    def criado(payload):
        recebidos.append(payload["id"])
        return True

    def pago(payload):
        raise ConnectionError("ERP fora do ar")

    app = criar_app(SEGREDO, {"criado": criado, "pago": pago}, fila=fila, executar_em_thread=False)
    return app.test_client(), recebidos, fila


def test_assinatura_valida_processa(ambiente):
    cliente, recebidos, _ = ambiente
    corpo = json.dumps({"id": 42}).encode()
    resp = cliente.post("/webhooks/criado", data=corpo, content_type="application/json",
                        headers={"X-Webhook-Signature": assinar(corpo)})
    assert resp.status_code == 200
    assert recebidos == [42]


def test_assinatura_invalida_rejeita(ambiente):
    cliente, recebidos, _ = ambiente
    corpo = json.dumps({"id": 42}).encode()
    resp = cliente.post("/webhooks/criado", data=corpo, content_type="application/json",
                        headers={"X-Webhook-Signature": "0" * 64})
    assert resp.status_code == 401
    assert recebidos == []

    resp = cliente.post("/webhooks/criado", data=corpo, content_type="application/json")  # sem cabeçalho
    assert resp.status_code == 401


def test_falha_no_processamento_enfileira(ambiente):
    cliente, _, fila = ambiente
    corpo = json.dumps({"id": 7}).encode()
    resp = cliente.post("/webhooks/pago", data=corpo, content_type="application/json",
                        headers={"X-Webhook-Signature": assinar(corpo)})
    assert resp.status_code == 200  # a plataforma recebe 200 mesmo assim; a ação fica na fila
    assert [(i["acao"], i["chave"]) for i in fila.itens()] == [("pago", 7)]


def test_evento_desconhecido(ambiente):
    cliente, _, _ = ambiente
    corpo = b"{}"
    resp = cliente.post("/webhooks/inexistente", data=corpo, headers={"X-Webhook-Signature": assinar(corpo)})
    assert resp.status_code == 404
