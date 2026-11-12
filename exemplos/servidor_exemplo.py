"""
Sobe um receptor de webhooks completo, com fila de retentativas e lock por pedido.

    python exemplos/servidor_exemplo.py

Em outro terminal, envie um evento assinado:

    python exemplos/enviar_webhook_assinado.py criado 42
    python exemplos/enviar_webhook_assinado.py pago 42

O "ERP" aqui é simulado: fica fora do ar em minutos ímpares, para você
ver a fila de retentativas em ação (arquivo exemplos/dados/fila.json).
"""
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite rodar de qualquer pasta

from padroes.estado_json import EstadoJson, LocksPorChave, processar_uma_vez
from padroes.fila_retentativas import FilaRetentativas
from padroes.webhook_app import criar_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("exemplo")

SEGREDO = os.environ.get("WEBHOOK_SEGREDO", "troque-este-segredo")
DADOS = Path(__file__).parent / "dados"
DADOS.mkdir(exist_ok=True)

estado = EstadoJson(DADOS / "estado.json")
locks = LocksPorChave()
fila = FilaRetentativas(DADOS / "fila.json", logger=log.info)


def erp_importar_pedido(pedido_id):
    """Simula o ERP: fora do ar em minutos ímpares."""
    if datetime.now().minute % 2 == 1:
        raise ConnectionError("ERP fora do ar (minuto ímpar)")
    return 1000 + int(pedido_id)  # id gerado no ERP


def criado(payload):
    pedido_id = payload["id"]
    id_erp = processar_uma_vez(estado, locks, pedido_id, lambda: erp_importar_pedido(pedido_id), campo="id_erp")
    log.info("pedido %s importado no ERP com id %s", pedido_id, id_erp)
    return True


def pago(payload):
    pedido_id = payload["id"]
    entrada = estado.obter(pedido_id)
    if not entrada or entrada.get("id_erp") is None:
        criado(payload)  # o evento "pago" chegou antes do "criado": importa agora
    estado.gravar(pedido_id, pago=True)
    log.info("pedido %s marcado como pago", pedido_id)
    return True


# A fila usa as mesmas funções, recebendo só a chave
acoes_da_fila = {"criado": lambda chave: criado({"id": chave}), "pago": lambda chave: pago({"id": chave})}
threading.Thread(target=fila.rodar_em_loop, args=(acoes_da_fila, 15), daemon=True).start()

app = criar_app(SEGREDO, {"criado": criado, "pago": pago}, fila=fila)

if __name__ == "__main__":
    app.run(port=5000, debug=False)
