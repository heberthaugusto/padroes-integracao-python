from datetime import datetime

from padroes.fila_retentativas import FilaRetentativas, JanelaFuncionamento


def test_janela_de_funcionamento():
    janela = JanelaFuncionamento({1: ("07:40", "18:30"), 6: ("07:40", "13:30")})
    assert janela.no_ar(datetime(2026, 10, 26, 9, 0))        # segunda, 9h
    assert not janela.no_ar(datetime(2026, 10, 26, 23, 0))   # segunda, 23h
    assert janela.no_ar(datetime(2026, 10, 31, 12, 0))       # sábado, 12h
    assert not janela.no_ar(datetime(2026, 10, 31, 15, 0))   # sábado, 15h
    assert not janela.no_ar(datetime(2026, 11, 1, 10, 0))    # domingo


def test_enfileirar_nao_duplica(tmp_path):
    fila = FilaRetentativas(tmp_path / "fila.json")
    assert fila.enfileirar("criado", 10) is True
    assert fila.enfileirar("criado", 10) is False
    assert fila.enfileirar("pago", 10) is True
    assert len(fila.itens()) == 2


def test_reprocessar_remove_sucesso_e_conta_falha(tmp_path):
    fila = FilaRetentativas(tmp_path / "fila.json")
    fila.enfileirar("criado", 1)
    fila.enfileirar("criado", 2)
    fila.enfileirar("pago", 3)

    def criar(chave):
        return chave == 1  # só o pedido 1 dá certo

    def pagar(chave):
        raise ConnectionError("ERP fora do ar")

    resumo = fila.reprocessar({"criado": criar, "pago": pagar})
    assert resumo == {"processados": 1, "pendentes": 2, "pulado": False}
    restantes = {(i["acao"], i["chave"]): i["tentativas"] for i in fila.itens()}
    assert restantes == {("criado", 2): 1, ("pago", 3): 1}

    fila.reprocessar({"criado": criar, "pago": pagar})
    assert fila.presos(minimo_tentativas=2) == [i for i in fila.itens()]


def test_fora_da_janela_nao_tenta(tmp_path):
    janela = JanelaFuncionamento({1: ("08:00", "18:00")})
    fila = FilaRetentativas(tmp_path / "fila.json", janela=janela)
    fila.enfileirar("criado", 1)
    chamadas = []
    resumo = fila.reprocessar({"criado": lambda c: chamadas.append(c) or True},
                              agora=datetime(2026, 10, 26, 22, 0))
    assert resumo["pulado"] is True
    assert chamadas == []
    assert fila.itens()[0]["tentativas"] == 0
