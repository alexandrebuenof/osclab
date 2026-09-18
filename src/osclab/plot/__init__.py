"""Preparar dados para desenho: reduzir amostras, escalas e marcações de eixo.

Fica fora de `web/` de propósito. Não é apresentação bonita — é conta, e conta
precisa de teste. O relatório (marco 0.7) vai usar exatamente as mesmas funções
para desenhar as figuras dele, sem navegador nenhum no meio.
"""

from osclab.plot import escala, janela, serie

__all__ = ["escala", "janela", "serie"]
