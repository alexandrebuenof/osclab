"""Primário × secundário: a relação de TC/TP aplicada aos valores.

Mora num módulo só porque duas telas precisam da mesma conta — o desenho da
janela e a leitura dos cursores. Duas implementações da mesma conta é como elas
divergem: o gráfico mostraria 6,7 kA e o cursor leria 5,6 A no mesmo instante.

A regra que não é óbvia: **quando o arquivo não declara a relação, não se
converte.** Um palpite aqui vira corrente de falta errada no relatório.
"""

from __future__ import annotations

import math

import numpy as np

#: Em que lado a tela pode pedir os valores. `arquivo` não é uma opção da tela:
#: é o que chega quando ninguém pediu nada, e vira o lado natural do registro.
LADOS = ("arquivo", "primario", "secundario")


def lado_natural(registro) -> str:
    """O lado em que o registro já está, pela maioria dos canais analógicos.

    É o padrão da tela. Abrir uma oscilografia já convertida seria surpresa: o
    usuário veria um número diferente do que o relé gravou sem ter pedido.
    """
    primarios = sum(1 for c in registro.analog_channels if c.is_primary)
    total = len(registro.analog_channels)
    return "primario" if total and primarios * 2 > total else "secundario"


def relacao(canal) -> float:
    """A relação de transformação declarada, ou 0 quando não dá para usar."""
    p, s = float(canal.primary or 0.0), float(canal.secondary or 0.0)
    if p <= 0 or s <= 0:
        return 0.0
    razao = p / s
    if not math.isfinite(razao) or razao <= 0:
        return 0.0
    return razao


def converter(valores: np.ndarray, canal, pedido: str):
    """Devolve `(valores, lado_resultante, foi_convertido)`."""
    lado = "primario" if canal.is_primary else "secundario"
    if pedido == "arquivo" or pedido == lado:
        return valores, lado, False

    razao = relacao(canal)
    if razao <= 0:
        return valores, lado, False        # o arquivo não declarou: não inventa

    if pedido == "primario":
        return valores * razao, "primario", True
    return valores / razao, "secundario", True
