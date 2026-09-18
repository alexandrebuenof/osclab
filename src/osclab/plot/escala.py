"""Escalas e marcações de eixo.

Matemática pura, sem nada de navegador — e é justamente por isso que fica aqui,
no Python, com teste. Um eixo com escala errada **desenha bonito e mente**: a
onda tem a forma certa, o número ao lado está errado, e ninguém percebe olhando.

As marcações seguem a regra 1-2-5: um eixo só é fácil de ler quando os números
nele são redondos. `0, 0.2, 0.4` se lê de relance; `0, 0.173, 0.346` não.
"""

from __future__ import annotations

import math

#: Os únicos passos que produzem números redondos, em qualquer potência de 10.
_PASSOS = (1.0, 2.0, 5.0, 10.0)


def passo_bonito(intervalo: float, alvo: int = 5) -> float:
    """O passo redondo mais próximo de dividir `intervalo` em `alvo` partes."""
    if intervalo <= 0 or alvo < 1:
        return 0.0
    bruto = intervalo / alvo
    magnitude = 10.0 ** math.floor(math.log10(bruto))
    for passo in _PASSOS:
        if bruto <= passo * magnitude:
            return passo * magnitude
    return 10.0 * magnitude


def marcacoes(minimo: float, maximo: float, alvo: int = 5) -> list[float]:
    """Onde pôr as marcações entre `minimo` e `maximo`, em números redondos.

    Pode devolver menos ou mais que `alvo`: o compromisso é a favor dos números
    redondos, não da quantidade.
    """
    if not (math.isfinite(minimo) and math.isfinite(maximo)) or maximo <= minimo:
        return []
    passo = passo_bonito(maximo - minimo, alvo)
    if passo <= 0:
        return []

    inicio = math.ceil(minimo / passo) * passo
    saida: list[float] = []
    n = 0
    while True:
        valor = inicio + n * passo
        if valor > maximo + passo * 1e-9:
            break
        # O zero tem que sair exatamente zero: `-0.0` e `1.1e-17` aparecem na
        # tela como "-0" e "0.00000000000000001".
        saida.append(0.0 if abs(valor) < passo * 1e-9 else valor)
        n += 1
        if n > 1000:                      # cinto de seguranca contra laco infinito
            break
    return saida


def faixa(minimo: float, maximo: float, margem: float = 0.05) -> tuple[float, float]:
    """A faixa vertical que o gráfico vai usar, a partir dos dados.

    Duas escolhas, as duas de domínio e não de estética:

    * **Sinal alternado fica simétrico em torno do zero.** Uma corrente que vai
      de -6743 a +6735 desenhada numa faixa assimétrica esconde que ela é
      simétrica — e a linha do zero, que é a referência para ler defasagem,
      sairia fora do meio.
    * **Sinal que nunca fica negativo começa no zero.** Uma tensão de bateria
      entre 133 e 135 V numa faixa simétrica viraria uma linha reta colada no
      topo, sem nenhuma informação.
    """
    if not (math.isfinite(minimo) and math.isfinite(maximo)):
        return (-1.0, 1.0)
    if minimo >= 0:
        topo = maximo if maximo > 0 else 1.0
        return (0.0, topo * (1.0 + margem))
    if maximo <= 0:
        base = minimo if minimo < 0 else -1.0
        return (base * (1.0 + margem), 0.0)
    limite = max(abs(minimo), abs(maximo)) * (1.0 + margem)
    return (-limite, limite)


def casas_decimais(intervalo: float) -> int:
    """Quantas casas mostrar num eixo que cobre `intervalo`.

    Sem isto, um eixo de corrente de falta vira `6735.2450000001` e um eixo de
    corrente de carga vira `0`.
    """
    if intervalo <= 0 or not math.isfinite(intervalo):
        return 2
    return int(min(6, max(0, 2 - math.floor(math.log10(intervalo)))))
