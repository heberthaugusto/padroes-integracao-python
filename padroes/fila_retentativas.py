"""
Fila de retentativas persistente e janela de funcionamento.

Problema que resolve
--------------------
O ERP de uma loja física costuma ficar desligado fora do horário
comercial. Um pedido feito no site às 23h chega por webhook, a
integração tenta falar com o ERP e recebe "connection refused". Isso não
é uma falha real, é o servidor desligado. A ação precisa ser guardada
e repetida quando o sistema voltar, sem prazo de desistência e sem
duplicar.

Componentes
-----------
``JanelaFuncionamento``
    Define em que horários o sistema externo está disponível. Fora da janela a
    fila não tenta, o que evita registrar erros de conexão à noite
    e no fim de semana.

``FilaRetentativas``
    Lista de ações pendentes (``acao`` + ``chave``) salva em JSON. Não
    aceita a mesma ação duas vezes para a mesma chave. Cada passada de
    reprocessamento chama a função registrada para a ação; sucesso tira
    da fila, falha só incrementa o contador de tentativas (o contador é o
    que indica um item preso, que precisa de intervenção humana).

Uma função de ação devolve True quando concluiu, False quando deve ser
tentada de novo, ou levanta exceção (tratada como "tentar de novo").
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path


class JanelaFuncionamento:
    """Horários em que o sistema externo fica ligado.

    ``horarios`` mapeia o dia da semana (1 = segunda ... 7 = domingo) para
    uma tupla ("HH:MM", "HH:MM"). Dias ausentes contam como desligado.
    """

    def __init__(self, horarios):
        self._janelas = {}
        for dia, (inicio, fim) in horarios.items():
            self._janelas[int(dia)] = (self._minutos(inicio), self._minutos(fim))

    @staticmethod
    def _minutos(hhmm):
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    def no_ar(self, agora=None):
        agora = agora or datetime.now()
        janela = self._janelas.get(agora.isoweekday())
        if not janela:
            return False
        inicio, fim = janela
        return inicio <= agora.hour * 60 + agora.minute <= fim


class FilaRetentativas:
    def __init__(self, caminho, janela=None, logger=None):
        self.caminho = Path(caminho)
        self.janela = janela
        self._lock = threading.Lock()
        self._log = logger or (lambda msg: None)

    # ----- persistência --------------------------------------------------
    def _ler(self):
        if not self.caminho.exists():
            return []
        try:
            with open(self.caminho, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _gravar(self, fila):
        temporario = self.caminho.with_suffix(self.caminho.suffix + ".tmp")
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(fila, f, indent=2, ensure_ascii=False)
        os.replace(temporario, self.caminho)

    # ----- operações -----------------------------------------------------
    def itens(self):
        with self._lock:
            return list(self._ler())

    def enfileirar(self, acao, chave):
        """Adiciona a ação, a menos que já esteja na fila para a mesma chave."""
        with self._lock:
            fila = self._ler()
            if any(i["acao"] == acao and i["chave"] == chave for i in fila):
                return False
            fila.append({"acao": acao, "chave": chave, "tentativas": 0,
                         "enfileirado_em": datetime.now().isoformat(timespec="seconds")})
            self._gravar(fila)
            self._log(f"[FILA] '{acao}' de {chave} enfileirada para retentativa")
            return True

    def remover(self, acao, chave):
        with self._lock:
            fila = [i for i in self._ler() if not (i["acao"] == acao and i["chave"] == chave)]
            self._gravar(fila)

    def incrementar(self, acao, chave):
        with self._lock:
            fila = self._ler()
            for item in fila:
                if item["acao"] == acao and item["chave"] == chave:
                    item["tentativas"] += 1
            self._gravar(fila)

    def reprocessar(self, acoes, agora=None):
        """Uma passada pela fila. ``acoes`` mapeia nome da ação -> função(chave).

        Devolve um resumo {"processados": n, "pendentes": n, "pulado": bool}.
        """
        if self.janela and not self.janela.no_ar(agora):
            return {"processados": 0, "pendentes": len(self.itens()), "pulado": True}

        processados = 0
        for item in self.itens():
            acao, chave = item["acao"], item["chave"]
            funcao = acoes.get(acao)
            if funcao is None:
                self._log(f"[FILA] ação desconhecida '{acao}', mantida na fila")
                continue
            try:
                sucesso = funcao(chave)
            except Exception as e:  # falha de conexão, timeout etc.
                sucesso = False
                self._log(f"[FILA] '{acao}' de {chave} ainda sem sucesso: {e}")
            if sucesso:
                self.remover(acao, chave)
                processados += 1
                self._log(f"[FILA] '{acao}' de {chave} concluída e removida")
            else:
                self.incrementar(acao, chave)
        return {"processados": processados, "pendentes": len(self.itens()), "pulado": False}

    def rodar_em_loop(self, acoes, intervalo_segundos, parar=None):
        """Reprocessa a fila a cada ``intervalo_segundos`` até ``parar`` (Event) ser acionado.
        Pensado para rodar numa thread daemon ao lado do servidor de webhooks."""
        parar = parar or threading.Event()
        while not parar.is_set():
            self.reprocessar(acoes)
            parar.wait(intervalo_segundos)

    def presos(self, minimo_tentativas):
        """Itens com excesso de tentativas, candidatos a alerta para a equipe."""
        return [i for i in self.itens() if i["tentativas"] >= minimo_tentativas]
