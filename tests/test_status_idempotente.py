from types import SimpleNamespace

from padroes.status_idempotente import ERRO, JA_ESTAVA, OK, avancar_status, classificar_resposta


def test_classificacao():
    assert classificar_resposta(200, "") == OK
    assert classificar_resposta(400, "Fulfillment order already in status DELIVERED") == JA_ESTAVA
    assert classificar_resposta(400, "Can't update fulfillment order") == JA_ESTAVA
    assert classificar_resposta(400, "invalid tracking code") == ERRO
    assert classificar_resposta(500, "") == ERRO


class ClienteFalso:
    def __init__(self, status_code, text):
        self.resposta = SimpleNamespace(status_code=status_code, text=text)
        self.chamadas = []

    def patch(self, url, json):
        self.chamadas.append((url, json))
        return self.resposta


def test_ja_estava_conta_como_sucesso():
    cliente = ClienteFalso(400, "fulfillment order already delivered")
    assert avancar_status(cliente, "/orders/1/fulfillment", "DELIVERED") is True


def test_erro_real_devolve_false():
    cliente = ClienteFalso(500, "internal error")
    assert avancar_status(cliente, "/orders/1/fulfillment", "PACKED") is False
    assert cliente.chamadas == [("/orders/1/fulfillment", {"status": "PACKED"})]
