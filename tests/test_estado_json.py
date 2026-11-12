import threading

from padroes.estado_json import EstadoJson, LocksPorChave, processar_uma_vez


def test_gravar_e_obter(tmp_path):
    estado = EstadoJson(tmp_path / "estado.json")
    estado.gravar("123", id_erp=555, nota_enviada=False)
    estado.gravar("123", nota_enviada=True)  # mescla, não substitui
    assert estado.obter("123") == {"id_erp": 555, "nota_enviada": True}
    assert estado.obter("999") is None


def test_listar_com_filtro(tmp_path):
    estado = EstadoJson(tmp_path / "estado.json")
    estado.gravar("1", nota_enviada=True)
    estado.gravar("2", nota_enviada=False)
    pendentes = estado.listar(lambda e: not e.get("nota_enviada"))
    assert list(pendentes) == ["2"]


def test_arquivo_corrompido_vira_vazio(tmp_path):
    caminho = tmp_path / "estado.json"
    caminho.write_text("{isso não é json")
    assert EstadoJson(caminho).obter("x") is None


def test_processar_uma_vez_com_concorrencia(tmp_path):
    """Dez threads tentam importar o mesmo pedido ao mesmo tempo; a ação roda uma vez só."""
    estado = EstadoJson(tmp_path / "estado.json")
    locks = LocksPorChave()
    execucoes = []

    def importar():
        execucoes.append(1)
        return 777  # id gerado no ERP

    resultados = []
    threads = [threading.Thread(target=lambda: resultados.append(
        processar_uma_vez(estado, locks, "pedido-1", importar, campo="id_erp"))) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(execucoes) == 1
    assert resultados == [777] * 10
    assert estado.obter("pedido-1")["id_erp"] == 777


def test_locks_diferentes_nao_bloqueiam():
    locks = LocksPorChave()
    with locks.travar("a"):
        assert locks.obter("b").acquire(blocking=False)
        locks.obter("b").release()
