from datetime import date, datetime, time

import pytest

from padroes.agenda_promocoes import AgendaComCache, Promocao, decidir, validar_promocao


def promo(sku, inicio, fim, normal=10.0, promocional=7.9):
    return Promocao(sku, normal, promocional, inicio, fim)


def test_validacao_do_cadastro():
    ok, _ = validar_promocao("1", 10, 7.9, None, date(2026, 11, 10))
    assert ok.inicio is None and ok.fim == "2026-11-11 00:00:00"  # sem hora: vale o dia inteiro

    ok, _ = validar_promocao("1", 10, 7.9, datetime(2026, 11, 1, 8, 0), date(2026, 11, 10), time(18, 0))
    assert ok.inicio == "2026-11-01 08:00:00" and ok.fim == "2026-11-10 18:00:00"

    assert validar_promocao("1", 10, 7.9, None, None)[1] == "sem data final"
    assert validar_promocao("1", 10, 12, None, date(2026, 11, 10))[1] == "preço promocional não é menor que o normal"
    assert validar_promocao("1", 0, 0, None, date(2026, 11, 10))[1] == "preço normal zerado"
    assert validar_promocao("1", 10, 7.9, datetime(2026, 12, 1), date(2026, 11, 10))[1] == "início depois do fim"


def test_decidir_aplicar_e_retirar():
    agora = datetime(2026, 11, 5, 12, 0)
    agenda = {
        "A": promo("A", None, "2026-11-10 00:00:00"),                    # vigente, ainda não aplicada
        "B": promo("B", "2026-11-06 00:00:00", "2026-11-10 00:00:00"),   # futura
        "C": promo("C", None, "2026-11-10 00:00:00", promocional=6.5),   # vigente, aplicada com outro preço
        "D": promo("D", None, "2026-11-01 00:00:00"),                    # já acabou, está aplicada
    }
    aplicadas = {
        "C": {"preco_normal": 10.0, "preco_promo": 7.9, "fim": "2026-11-10 00:00:00"},
        "D": {"preco_normal": 10.0, "preco_promo": 7.9, "fim": "2026-11-01 00:00:00"},
        "E": {"preco_normal": 10.0, "preco_promo": 7.9, "fim": "2026-11-20 00:00:00"},  # sumiu da agenda
    }
    acoes = decidir(agenda, aplicadas, agora, fonte_ok=True)
    assert [(a, s) for a, s, _ in acoes] == [("aplicar", "A"), ("aplicar", "C"), ("retirar", "D"), ("retirar", "E")]
    assert acoes[2][2] == "fim da promoção"
    assert acoes[3][2] == "promoção apagada ou alterada na fonte"


def test_sem_fonte_nao_retira_antes_do_fim():
    agora = datetime(2026, 11, 5, 12, 0)
    aplicadas = {"E": {"preco_normal": 10.0, "preco_promo": 7.9, "fim": "2026-11-20 00:00:00"},
                 "F": {"preco_normal": 10.0, "preco_promo": 7.9, "fim": "2026-11-01 00:00:00"}}
    acoes = decidir({}, aplicadas, agora, fonte_ok=False)
    assert acoes == [("retirar", "F", "fim da promoção")]  # E continua, a fonte só está fora


def test_agenda_com_cache_sobrevive_a_queda_da_fonte(tmp_path):
    relogio = {"t": 1000.0}
    leituras = {"n": 0, "falhar": False}

    def ler_fonte():
        leituras["n"] += 1
        if leituras["falhar"]:
            raise ConnectionError("banco fora")
        return {"A": promo("A", None, "2026-11-10 00:00:00")}

    agenda = AgendaComCache(tmp_path / "agenda.json", ler_fonte, intervalo_segundos=300, relogio=lambda: relogio["t"])

    itens, da_fonte = agenda.obter()
    assert da_fonte and "A" in itens and leituras["n"] == 1

    relogio["t"] += 60
    itens, da_fonte = agenda.obter()           # dentro do intervalo: usa o cache
    assert not da_fonte and "A" in itens and leituras["n"] == 1

    relogio["t"] += 300
    leituras["falhar"] = True
    itens, da_fonte = agenda.obter()           # fonte caiu: continua com a última agenda boa
    assert not da_fonte and "A" in itens and agenda.fonte_com_falha
