"""
Agenda de promoções (ativar e retirar preço promocional no horário certo).

Problema que resolve
--------------------
No ERP a promoção tem data e hora de início e de fim. A plataforma de
e-commerce só tem um campo "preço promocional", sem agendamento. É preciso
aplicar o preço no início da promoção e retirá-lo no fim.

Desenho
-------
Duas frequências separadas, para não sobrecarregar a fonte de dados:

* a **agenda** é relida da fonte (banco do ERP) a cada alguns minutos e
  salva em arquivo. Se a fonte cair, a última agenda salva continua
  valendo, então uma promoção ainda entra e sai no horário certo;
* o **relógio** roda a cada minuto, sem tocar na fonte: compara a agenda
  com o que já está aplicado no destino e decide o que fazer.

A decisão (``decidir``) é uma função pura: recebe agenda, aplicadas e o
instante atual, e devolve a lista de ações. Isso permite testar todos os
cenários (início futuro, fim passado, preço alterado, promoção apagada,
fonte fora do ar) sem banco e sem API.

Regras de validação do cadastro (``validar_promocao``):
* sem data final: ignorada;
* sem hora final: vale até 23:59:59 da data final;
* sem início: começa assim que for cadastrada;
* preço promocional igual ou maior que o normal: ignorada;
* início depois do fim: ignorada.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path


FORMATO = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class Promocao:
    sku: str
    preco_normal: float
    preco_promo: float
    inicio: str | None  # FORMATO, ou None para "imediato"
    fim: str            # FORMATO

    def vigente(self, agora):
        inicio = datetime.strptime(self.inicio, FORMATO) if self.inicio else None
        fim = datetime.strptime(self.fim, FORMATO)
        return (inicio is None or inicio <= agora) and agora < fim


def validar_promocao(sku, preco_normal, preco_promo, inicio, data_fim, hora_fim=None):
    """Converte um cadastro bruto em ``Promocao`` ou devolve (None, motivo).

    ``inicio`` é um datetime ou None; ``data_fim`` é um ``date``;
    ``hora_fim`` é um ``time`` ou None.
    """
    if data_fim is None:
        return None, "sem data final"
    if preco_normal <= 0:
        return None, "preço normal zerado"
    if preco_promo >= preco_normal:
        return None, "preço promocional não é menor que o normal"

    if hora_fim is not None:
        fim = datetime.combine(data_fim, hora_fim)
    else:
        fim = datetime.combine(data_fim, datetime.min.time()) + timedelta(days=1)  # até 23:59:59

    if inicio is not None and inicio >= fim:
        return None, "início depois do fim"

    return Promocao(
        sku=str(sku),
        preco_normal=round(float(preco_normal), 2),
        preco_promo=round(float(preco_promo), 2),
        inicio=inicio.strftime(FORMATO) if inicio else None,
        fim=fim.strftime(FORMATO),
    ), None


def _mesmo_preco(a, b):
    try:
        return abs(float(a) - float(b)) < 0.005
    except (TypeError, ValueError):
        return False


def decidir(agenda, aplicadas, agora, fonte_ok=True):
    """Função pura. Devolve uma lista de ações:

    ("aplicar", sku, Promocao)  quando a promoção está vigente e ainda não
                                foi aplicada, ou foi aplicada com valores diferentes;
    ("retirar", sku, motivo)    quando algo aplicado não deve mais estar.

    ``agenda``: {sku: Promocao} lido da fonte.
    ``aplicadas``: {sku: {"preco_normal", "preco_promo", "fim", ...}} o que
    a integração já colocou no destino.
    ``fonte_ok``: False quando a agenda veio do cache porque a fonte caiu.
    Nesse caso só se retira o que já passou do fim gravado; nunca se
    conclui que "sumiu da agenda" só porque a fonte não respondeu.
    """
    acoes = []

    for sku, promo in sorted(agenda.items()):
        if not promo.vigente(agora):
            continue
        atual = aplicadas.get(sku)
        if (not atual
                or not _mesmo_preco(atual.get("preco_promo"), promo.preco_promo)
                or not _mesmo_preco(atual.get("preco_normal"), promo.preco_normal)
                or atual.get("fim") != promo.fim):
            acoes.append(("aplicar", sku, promo))

    for sku in sorted(aplicadas):
        promo = agenda.get(sku)
        if promo and promo.vigente(agora):
            continue
        if promo:
            fim = datetime.strptime(promo.fim, FORMATO)
            motivo = "fim da promoção" if agora >= fim else "início adiado na fonte"
        elif fonte_ok:
            motivo = "promoção apagada ou alterada na fonte"
        else:
            fim = datetime.strptime(aplicadas[sku]["fim"], FORMATO)
            if agora < fim:
                continue  # sem fonte e ainda dentro do prazo gravado: mantém
            motivo = "fim da promoção"
        acoes.append(("retirar", sku, motivo))

    return acoes


class AgendaComCache:
    """Relê a agenda da fonte no máximo a cada ``intervalo_segundos`` e
    guarda a última leitura válida em arquivo. ``ler_fonte`` é uma função sem
    argumentos que devolve {sku: Promocao} ou levanta exceção."""

    def __init__(self, caminho, ler_fonte, intervalo_segundos=300, relogio=time.time):
        self.caminho = Path(caminho)
        self.ler_fonte = ler_fonte
        self.intervalo = intervalo_segundos
        self.relogio = relogio
        self._ultima_leitura = 0.0
        self.fonte_com_falha = False

    def _ler_cache(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                bruto = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return {sku: Promocao(**dados) for sku, dados in bruto.get("itens", {}).items()}

    def _gravar_cache(self, itens):
        temporario = self.caminho.with_suffix(self.caminho.suffix + ".tmp")
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump({"lido_em": datetime.now().strftime(FORMATO),
                       "itens": {sku: asdict(p) for sku, p in itens.items()}},
                      f, indent=2, ensure_ascii=False)
        os.replace(temporario, self.caminho)

    def obter(self, forcar=False):
        """Devolve (itens, veio_da_fonte)."""
        if not forcar and self.relogio() - self._ultima_leitura < self.intervalo:
            return self._ler_cache(), False
        try:
            itens = self.ler_fonte()
        except Exception:
            self._ultima_leitura = self.relogio()  # tenta de novo só no próximo intervalo
            self.fonte_com_falha = True
            return self._ler_cache(), False
        self._ultima_leitura = self.relogio()
        self.fonte_com_falha = False
        self._gravar_cache(itens)
        return itens, True
