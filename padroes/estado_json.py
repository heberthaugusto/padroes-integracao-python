"""
Estado persistente em JSON e lock por chave.

Problema que resolve
--------------------
Uma integração entre plataforma de e-commerce e ERP precisa lembrar o que
já fez com cada pedido (foi importado? com qual id no ERP? a nota já foi
enviada?). Sem isso, um webhook reenviado ou uma reconciliação periódica
reprocessa o mesmo pedido e cria duplicidade.

Dois mecanismos simples resolvem a maior parte dos casos:

1. ``EstadoJson``: um mapa chave -> dicionário, salvo em arquivo JSON com
   gravação atômica (escreve num temporário e renomeia). Se o processo
   cair no meio da escrita, o arquivo anterior continua íntegro.
2. ``LocksPorChave``: um ``threading.Lock`` por chave. Dois eventos do
   mesmo pedido que chegam quase juntos (ex.: "criado" e "pago" num Pix
   aprovado na hora) passam um de cada vez pela decisão "já importei?".
   Eventos de pedidos diferentes não esperam uns pelos outros.

O padrão de uso é sempre o mesmo: travar a chave, reler o estado dentro
do lock, decidir, gravar.
"""

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path


class EstadoJson:
    """Mapa chave -> dict persistido em JSON, com gravação atômica e thread-safe."""

    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self._lock = threading.Lock()

    # ----- arquivo -------------------------------------------------------
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
        os.replace(temporario, self.caminho)  # troca atômica no mesmo sistema de arquivos

    # ----- operações -----------------------------------------------------
    def obter(self, chave):
        """Devolve o dict da chave, ou None se não existir."""
        with self._lock:
            return self._ler().get(str(chave))

    def gravar(self, chave, **campos):
        """Cria ou atualiza a chave, mesclando os campos informados."""
        with self._lock:
            dados = self._ler()
            entrada = dados.setdefault(str(chave), {})
            entrada.update(campos)
            self._gravar(dados)
            return dict(entrada)

    def remover(self, chave):
        with self._lock:
            dados = self._ler()
            if dados.pop(str(chave), None) is not None:
                self._gravar(dados)

    def listar(self, filtro=None):
        """Devolve {chave: dict} de todas as entradas, ou só as que passam no filtro."""
        with self._lock:
            dados = self._ler()
        if filtro is None:
            return dados
        return {k: v for k, v in dados.items() if filtro(v)}


class LocksPorChave:
    """Um lock por chave, criado sob demanda."""

    def __init__(self):
        self._locks = {}
        self._guarda = threading.Lock()

    def obter(self, chave):
        with self._guarda:
            if chave not in self._locks:
                self._locks[chave] = threading.Lock()
            return self._locks[chave]

    @contextmanager
    def travar(self, chave):
        lock = self.obter(chave)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()


def processar_uma_vez(estado, locks, chave, acao, campo="processado"):
    """Executa ``acao()`` no máximo uma vez por chave, mesmo com chamadas
    concorrentes. Devolve o resultado da ação, ou o valor já gravado se a
    chave tinha sido processada antes.

    ``acao`` deve devolver algo serializável em JSON (ex.: o id gerado no
    ERP), que fica guardado no estado para as próximas etapas.
    """
    with locks.travar(chave):
        entrada = estado.obter(chave)
        if entrada and entrada.get(campo) is not None:
            return entrada[campo]
        resultado = acao()
        estado.gravar(chave, **{campo: resultado})
        return resultado
