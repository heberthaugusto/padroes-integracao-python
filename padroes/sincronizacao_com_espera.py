"""
Sincronização com espera (propagar uma mudança só depois de um prazo).

Problema que resolve
--------------------
Quando uma mercadoria é recebida, o estoque sobe no ERP na hora, mas a
precificação do lote novo só acontece um pouco depois. Se a integração
propagar o estoque imediatamente, o site vende por alguns minutos com o
preço antigo.

A solução é tratar todo AUMENTO de estoque como possível recebimento:
em vez de enviar na hora, a chave entra numa fila com o horário em que a
mudança foi detectada e só é enviada quando a espera (por exemplo 1h30)
termina. Diminuições de estoque (vendas) continuam indo na hora, porque
aí o risco é o contrário, vender o que não tem.

``SincronizacaoComEspera`` guarda as chaves pendentes em JSON, para a
espera sobreviver a uma reinicialização do serviço. Uma rotina periódica
chama ``prontos()`` e, para cada chave, busca os dados atuais na fonte e
propaga preço e estoque juntos.
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


def decidir_envio_estoque(estoque_no_destino, estoque_novo):
    """Regra de decisão isolada, fácil de testar.

    Devolve "aguardar" quando houve aumento (possível recebimento de
    mercadoria) e "enviar" nos demais casos. Se o valor atual no destino
    é desconhecido, envia, porque não há como detectar aumento.
    """
    if estoque_no_destino is None:
        return "enviar"
    return "aguardar" if estoque_novo > estoque_no_destino else "enviar"


class SincronizacaoComEspera:
    def __init__(self, caminho, espera_segundos):
        self.caminho = Path(caminho)
        self.espera = timedelta(seconds=espera_segundos)
        self._lock = threading.Lock()

    def _ler(self):
        if not self.caminho.exists():
            return {}
        try:
            with open(self.caminho, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _gravar(self, dados):
        temporario = self.caminho.with_suffix(self.caminho.suffix + ".tmp")
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        os.replace(temporario, self.caminho)

    def agendar(self, chave, agora=None):
        """Marca a chave como pendente. Se já estava pendente, mantém o
        horário original (a espera conta a partir da primeira detecção)."""
        agora = agora or datetime.now(timezone.utc)
        with self._lock:
            dados = self._ler()
            if str(chave) not in dados:
                dados[str(chave)] = {"detectado_em": agora.isoformat()}
                self._gravar(dados)
                return True
            return False

    def prontos(self, agora=None):
        """Chaves cuja espera já terminou, em ordem de detecção."""
        agora = agora or datetime.now(timezone.utc)
        with self._lock:
            dados = self._ler()
        prontos = []
        for chave, info in dados.items():
            detectado_em = datetime.fromisoformat(info["detectado_em"])
            if agora - detectado_em >= self.espera:
                prontos.append((detectado_em, chave))
        return [chave for _, chave in sorted(prontos)]

    def concluir(self, chave):
        with self._lock:
            dados = self._ler()
            if dados.pop(str(chave), None) is not None:
                self._gravar(dados)

    def pendentes(self):
        with self._lock:
            return dict(self._ler())
