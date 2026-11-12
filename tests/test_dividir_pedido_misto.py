from decimal import Decimal

import pytest

from padroes.dividir_pedido_misto import FISICO, SERVICO, Item, NaoDividir, dividir_pedido


def itens_exemplo():
    return [
        Item("1", "CHOC-1KG", Decimal("45.90"), 2, FISICO),
        Item("2", "CURSO-01", Decimal("250.00"), 1, SERVICO),
    ]


def test_divide_com_rateio_e_centavos_fechando():
    # subtotal 341.80, cupom 10%, frete 25.00 -> total 332.62
    div = dividir_pedido(itens_exemplo(), subtotal="341.80", desconto="34.18", frete="25.00", total="332.62",
                         tipos_no_erp={"CHOC-1KG": FISICO, "CURSO-01": SERVICO})
    assert div.servico.desconto == Decimal("25.00")       # 34.18 * 250/341.80 = 25.0029 -> 25.00
    assert div.produtos.desconto == Decimal("9.18")       # o resto fica nos produtos
    assert div.produtos.frete == Decimal("25.00") and div.servico.frete == Decimal("0.00")
    assert div.produtos.total + div.servico.total == Decimal("332.62")
    assert [i.sku for i in div.produtos.itens] == ["CHOC-1KG"]
    assert [i.sku for i in div.servico.itens] == ["CURSO-01"]


def test_nao_divide_quando_fontes_discordam():
    with pytest.raises(NaoDividir, match="CURSO-01 é servico na plataforma e fisico no ERP"):
        dividir_pedido(itens_exemplo(), "341.80", "0", "25.00", "366.80",
                       tipos_no_erp={"CHOC-1KG": FISICO, "CURSO-01": FISICO})


def test_nao_divide_sku_desconhecido_no_erp():
    with pytest.raises(NaoDividir, match="não existe no ERP"):
        dividir_pedido(itens_exemplo(), "341.80", "0", "25.00", "366.80", tipos_no_erp={"CHOC-1KG": FISICO})


def test_nao_divide_se_total_nao_bate():
    with pytest.raises(NaoDividir, match="não bate com o total pago"):
        dividir_pedido(itens_exemplo(), "341.80", "0", "25.00", "300.00",
                       tipos_no_erp={"CHOC-1KG": FISICO, "CURSO-01": SERVICO})


def test_pedido_so_fisico_nao_e_misto():
    so_fisico = [Item("1", "CHOC-1KG", Decimal("45.90"), 1, FISICO)]
    with pytest.raises(NaoDividir, match="não é misto"):
        dividir_pedido(so_fisico, "45.90", "0", "0", "45.90", tipos_no_erp={"CHOC-1KG": FISICO})
