from datetime import datetime, timedelta, timezone

from padroes.sincronizacao_com_espera import SincronizacaoComEspera, decidir_envio_estoque


def test_decisao_de_envio():
    assert decidir_envio_estoque(10, 5) == "enviar"      # venda: diminuiu
    assert decidir_envio_estoque(10, 10) == "enviar"     # igual
    assert decidir_envio_estoque(10, 40) == "aguardar"   # recebimento: aumentou
    assert decidir_envio_estoque(0, 40) == "aguardar"
    assert decidir_envio_estoque(None, 40) == "enviar"   # destino desconhecido


def test_espera_e_conclusao(tmp_path):
    t0 = datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc)
    fila = SincronizacaoComEspera(tmp_path / "pendentes.json", espera_segundos=90 * 60)

    assert fila.agendar("SKU-1", agora=t0) is True
    assert fila.agendar("SKU-1", agora=t0 + timedelta(minutes=30)) is False  # mantém a 1ª detecção
    fila.agendar("SKU-2", agora=t0 + timedelta(minutes=10))

    assert fila.prontos(agora=t0 + timedelta(minutes=89)) == []
    assert fila.prontos(agora=t0 + timedelta(minutes=95)) == ["SKU-1"]
    assert fila.prontos(agora=t0 + timedelta(minutes=120)) == ["SKU-1", "SKU-2"]

    fila.concluir("SKU-1")
    assert list(fila.pendentes()) == ["SKU-2"]
