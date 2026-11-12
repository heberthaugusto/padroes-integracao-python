# 🔗 Padrões de Integração em Python

> Sete padrões para integrar uma plataforma de e-commerce a um ERP sem perder pedidos, sem duplicar e sem acordar de madrugada. Cada módulo nasceu de um problema real enfrentado numa integração em produção (cerca de 1.600 pedidos por mês) e foi reescrito aqui de forma genérica, com dados fictícios e testes automatizados.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Flask](https://img.shields.io/badge/Flask-000000?style=flat&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![pytest](https://img.shields.io/badge/pytest-27_testes-0A9EDC?style=flat&logo=pytest&logoColor=white)](https://docs.pytest.org)

> ⚖️ **Uso do código.** Exemplos didáticos escritos pelo autor a partir da sua experiência profissional, sem a lógica de negócio, os dados ou o código de qualquer empresa. Todos os direitos reservados. Não é permitido o uso comercial sem autorização.

---

## 🎯 Por que este repositório

Integrar dois sistemas é fácil no dia em que tudo funciona. O difícil é o resto: o ERP desligado à noite, dois webhooks do mesmo pedido chegando juntos, a plataforma mudando um status por conta própria, a promoção que precisa entrar às 8h e sair às 18h, o pedido que mistura produto e curso. Cada módulo aqui resolve um desses problemas de forma isolada e testável.

A arquitetura completa em que esses padrões foram aplicados está descrita no [estudo de caso da integração e-commerce x ERP](https://github.com/heberthaugusto/estudo-caso-integracao-ecommerce-erp).

## 📦 Os padrões

| Módulo | Problema | Solução |
|---|---|---|
| [`webhook_app.py`](padroes/webhook_app.py) | Webhook sem assinatura é porta aberta; webhook lento é reenviado e duplica | Flask com validação HMAC-SHA256, resposta 200 imediata, processamento em thread e enfileiramento em falha |
| [`estado_json.py`](padroes/estado_json.py) | Dois eventos do mesmo pedido chegam juntos e ambos decidem importar | Lock por chave + mapa de estado em JSON com gravação atômica. `processar_uma_vez` garante idempotência |
| [`fila_retentativas.py`](padroes/fila_retentativas.py) | O ERP fica desligado fora do horário comercial e o log enche de erro de conexão | Fila persistente sem prazo de desistência, com deduplicação, contador de tentativas e janela de funcionamento do sistema externo |
| [`sincronizacao_com_espera.py`](padroes/sincronizacao_com_espera.py) | Estoque sobe antes da precificação do lote e o site vende com preço velho | Todo aumento de estoque espera um prazo antes de ser propagado; diminuições vão na hora |
| [`agenda_promocoes.py`](padroes/agenda_promocoes.py) | A plataforma não agenda preço promocional | Relógio a cada minuto sobre uma agenda em cache, relida da fonte a cada 5 minutos e resistente a queda do banco. Decisão em função pura |
| [`dividir_pedido_misto.py`](padroes/dividir_pedido_misto.py) | Produto físico e serviço no mesmo pedido seguem fluxos fiscais diferentes | Divisão em dois pedidos com rateio de desconto em `Decimal`, conferência cruzada entre plataforma e ERP e soma fechando ao centavo. Na dúvida, não divide |
| [`status_idempotente.py`](padroes/status_idempotente.py) | "Já está nesse status" tratado como erro gerou 3.000 retentativas num pedido | Classificar a resposta da API: objetivo alcançado por outro caminho é sucesso |

## ✨ Lições que o código carrega

- **Idempotência não é opcional.** Webhooks são reenviados, reconciliações reprocessam, humanos clicam duas vezes. Toda ação precisa poder rodar de novo sem efeito colateral.
- **Fila sem prazo de desistência, mas com contador.** O sistema externo pode ficar horas fora. O que denuncia um item preso é o número de tentativas, não um timeout.
- **Funções puras para as decisões.** `decidir`, `dividir_pedido`, `classificar_resposta` e `decidir_envio_estoque` não tocam rede nem disco, por isso todos os cenários têm teste.
- **Na dúvida, não faça.** Quando duas fontes discordam ou a conta não fecha, o padrão é recuar para o caminho manual e registrar o motivo, nunca criar um dado errado.
- **Dinheiro é `Decimal`.** Com arredondamento explícito e a diferença de centavos indo para um lugar definido.
- **Cache como resiliência.** A última leitura boa da fonte vale até ela voltar. Uma promoção não deixa de entrar porque o banco caiu às 7h59.

## 🚀 Como rodar

```bash
pip install -r requirements.txt
pytest                       # 27 testes, menos de 1 segundo
```

Servidor de exemplo com fila e lock funcionando de ponta a ponta:

```bash
python exemplos/servidor_exemplo.py                   # terminal 1
python exemplos/enviar_webhook_assinado.py criado 42  # terminal 2
python exemplos/enviar_webhook_assinado.py pago 42
```

O "ERP" simulado fica fora do ar em minutos ímpares. Envie um evento nesse momento e veja a ação cair em `exemplos/dados/fila.json`; no minuto seguinte a fila reprocessa e o pedido aparece em `exemplos/dados/estado.json`. Envie o mesmo evento duas vezes e observe que nada duplica.

## 📁 Estrutura

```
├── padroes/                 Um módulo por padrão, com docstring explicando o problema e a solução
├── tests/                   Um arquivo de testes por módulo (pytest)
├── exemplos/
│   ├── servidor_exemplo.py          Receptor completo: webhook + lock + estado + fila
│   └── enviar_webhook_assinado.py   Cliente que assina e envia um evento
├── requirements.txt
└── pytest.ini
```

## 🧰 Stack

Python 3.10+, Flask, `threading`, `hmac`, `decimal`, `dataclasses`, pytest. Sem banco de dados e sem dependência de nenhuma plataforma: tudo que é externo entra por injeção de dependência (funções e clientes passados por parâmetro), o que é também o que torna o código testável.

---

## 👤 Autor

**Heberth Augusto**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=flat)](https://www.linkedin.com/in/heberth-augusto-ti/)
[![GitHub](https://img.shields.io/badge/GitHub-100000?style=flat&logo=github&logoColor=white)](https://github.com/heberthaugusto)

*Desenvolvido com IA generativa (Claude) como ferramenta de trabalho, a partir de padrões projetados, validados e mantidos pelo autor em produção.*
