"""
Atualização de status idempotente ("já está assim" é sucesso, não erro).

A lição
-------
Uma integração avança o status de um pedido na plataforma (embalado,
despachado, entregue) conforme o ERP evolui. Só que a plataforma também
muda status por conta própria: a transportadora marca "entregue", a
equipe ajusta algo à mão. Quando a integração chega depois e pede para
colocar um status que já está lá (ou já foi ultrapassado), a API recusa
com 400 e uma mensagem do tipo "fulfillment order already ... / can't
update".

Se esse 400 for tratado como erro, o pedido entra na fila de retentativas
e nunca sai: a condição que causa a recusa nunca muda. Em produção isso
apareceu como dois pedidos com cerca de 3.000 tentativas cada.

A correção é classificar a resposta: o objetivo era "o pedido estar no
status X"; se ele já está, o objetivo foi alcançado, só que por outro
caminho. Devolve sucesso, registra um aviso e o pedido sai do radar.

``classificar_resposta`` é pura e testável; ``avancar_status`` mostra o
uso com um cliente HTTP injetado (qualquer objeto com ``patch(url, json)``
que devolva algo com ``status_code`` e ``text``).
"""

import logging

OK = "ok"
JA_ESTAVA = "ja_estava"
ERRO = "erro"

# Trechos que, numa resposta 400, indicam "o status já é esse ou mais avançado".
# Ajuste conforme as mensagens da plataforma com que você integra.
SINAIS_JA_ESTAVA = ("already", "can't update", "cannot update", "já está", "nao pode ser atualizado")


def classificar_resposta(status_code, texto):
    """Devolve OK, JA_ESTAVA ou ERRO a partir da resposta da API."""
    if status_code == 200:
        return OK
    texto = (texto or "").lower()
    if status_code == 400 and any(s in texto for s in SINAIS_JA_ESTAVA):
        return JA_ESTAVA
    return ERRO


def avancar_status(cliente_http, url, status, extras=None, logger=None):
    """Tenta colocar o recurso em ``status``. Devolve True quando o objetivo
    foi alcançado (pela chamada ou porque já estava), False em erro real."""
    log = logger or logging.getLogger(__name__)
    payload = {"status": status, **(extras or {})}
    resposta = cliente_http.patch(url, json=payload)
    resultado = classificar_resposta(resposta.status_code, resposta.text)

    if resultado == OK:
        log.info("status atualizado para %s em %s", status, url)
        return True
    if resultado == JA_ESTAVA:
        log.warning("recurso já estava em %s (ou além) em %s; tratando como sucesso para não retentar para sempre", status, url)
        return True
    log.error("erro ao atualizar status em %s: %s - %s", url, resposta.status_code, (resposta.text or "")[:200])
    return False
