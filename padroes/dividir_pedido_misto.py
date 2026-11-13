"""
Divisão de pedido misto (produto físico + serviço no mesmo pedido).

Problema que resolve
--------------------
Um cliente compra, no mesmo pedido, um produto físico e um serviço (um
curso presencial, por exemplo). No ERP os dois saem por fluxos fiscais
diferentes: o produto gera nota de produto e passa por expedição e
rastreio; o serviço gera nota de serviço e não tem envio. Importar o
pedido inteiro num único fluxo exige cancelamento e relançamento manual.

A solução divide o pedido em dois antes de importar, com três cuidados:

1. **Duas fontes precisam concordar** sobre o que é serviço: a plataforma
   (que separa os itens em partes "com envio" e "sem envio") e o ERP (tipo
   do produto no cadastro). Se discordarem, não divide.
2. **Os valores precisam fechar ao centavo.** O desconto é rateado
   proporcionalmente ao valor dos itens de cada lado, a diferença de
   arredondamento fica no pedido de produtos, o frete vai inteiro para
   os produtos, e a soma dos dois pedidos é conferida contra o total pago.
3. **Em caso de divergência, não divide.** Qualquer conferência que falhe devolve
   ``NaoDividir`` com o motivo, e o pedido segue o caminho antigo
   (tratamento manual), sem risco de criar pedidos com valores errados.

Tudo em ``Decimal`` com arredondamento explícito. Valores monetários nunca em float.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENTAVO = Decimal("0.01")
FISICO = "fisico"
SERVICO = "servico"


class NaoDividir(Exception):
    """O pedido não deve ser dividido; ``str(e)`` traz o motivo."""


@dataclass(frozen=True)
class Item:
    id: str
    sku: str
    preco: Decimal
    quantidade: int
    tipo_na_plataforma: str  # FISICO ou SERVICO, conforme a parte do pedido em que a plataforma colocou o item

    @property
    def total(self):
        return dinheiro(self.preco) * self.quantidade


@dataclass(frozen=True)
class Parte:
    itens: tuple
    subtotal: Decimal
    desconto: Decimal
    frete: Decimal

    @property
    def total(self):
        return self.subtotal - self.desconto + self.frete


@dataclass(frozen=True)
class Divisao:
    produtos: Parte
    servico: Parte


def dinheiro(valor):
    return Decimal(str(valor if valor is not None else "0")).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def eh_misto(itens):
    tipos = {i.tipo_na_plataforma for i in itens}
    return tipos == {FISICO, SERVICO}


def dividir_pedido(itens, subtotal, desconto, frete, total, tipos_no_erp):
    """Divide o pedido em (produtos, serviço) ou levanta ``NaoDividir``.

    ``tipos_no_erp`` mapeia sku -> FISICO | SERVICO, conforme o cadastro do
    ERP. É a segunda fonte de verdade.
    """
    itens = list(itens)
    if not eh_misto(itens):
        raise NaoDividir("o pedido não é misto")

    # 1) As duas fontes precisam concordar item a item
    for item in itens:
        tipo_erp = tipos_no_erp.get(item.sku)
        if tipo_erp is None:
            raise NaoDividir(f"SKU {item.sku} não existe no ERP")
        if tipo_erp != item.tipo_na_plataforma:
            raise NaoDividir(
                f"SKU {item.sku} é {item.tipo_na_plataforma} na plataforma e {tipo_erp} no ERP")

    fisicos = [i for i in itens if i.tipo_na_plataforma == FISICO]
    servicos = [i for i in itens if i.tipo_na_plataforma == SERVICO]

    # 2) Valores
    subtotal = dinheiro(subtotal)
    desconto = dinheiro(desconto)
    frete = dinheiro(frete)
    total = dinheiro(total)

    sub_fis = sum((i.total for i in fisicos), Decimal("0"))
    sub_srv = sum((i.total for i in servicos), Decimal("0"))
    if sub_fis + sub_srv != subtotal:
        raise NaoDividir(f"a soma dos itens ({sub_fis + sub_srv}) não bate com o subtotal ({subtotal})")

    # Rateio proporcional do desconto; a diferença de centavos fica nos produtos
    if subtotal > 0:
        desc_srv = (desconto * sub_srv / subtotal).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    else:
        desc_srv = Decimal("0.00")
    desc_fis = desconto - desc_srv

    produtos = Parte(tuple(fisicos), sub_fis, desc_fis, frete)
    servico = Parte(tuple(servicos), sub_srv, desc_srv, Decimal("0.00"))

    # 3) Conferência final contra o total pago
    if produtos.total + servico.total != total:
        raise NaoDividir(
            f"a soma dos dois pedidos ({produtos.total} + {servico.total}) não bate com o total pago ({total})")

    return Divisao(produtos=produtos, servico=servico)
