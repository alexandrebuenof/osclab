"""Em que unidade a tela mostra cada grupo: `A` ou `kA`, `V` ou `kV`.

## O problema que este módulo resolve

Em valores primários os números explodem. Uma linha de 230 kV tem pico
fase-terra de **187 794 V**: sete dígitos que não cabem na coluna da tabelinha
nem no eixo vertical. Corrente de falta primária chega a dezenas de milhares de
ampères.

## A regra que não é óbvia: o prefixo é do REGISTRO, não do valor

Seria natural escolher o prefixo pelo número que está sendo mostrado — 20 000 A
vira `20 kA`, 200 A continua `200 A`. É o pior jeito possível numa
oscilografia: a unidade mudaria enquanto o cursor anda pela onda, e o eixo
trocaria de `kA` para `A` ao dar zoom na pré-falta. Unidade que pisca é pior
que número comprido, porque quem lê rápido não repara na troca.

Então o prefixo é decidido **uma vez por grupo, pelo maior valor absoluto do
registro inteiro** naquele lado (primário ou secundário). Escolhido, vale para
o eixo, para a tabelinha e para todo o registro — zoom não muda unidade.

## Por que o limiar é 10 000 e não 1 000

Corrente de falta secundária e boa parte da primária vive na casa dos milhares.
`6743 A` cabe e se lê de imediato; `6,743 kA` é a mesma coisa escrita pior. O
prefixo só compensa quando o número passa de cinco dígitos.

Corrente tem outra particularidade: dentro do mesmo registro ela varia mil
vezes entre a carga e a falta. Com o prefixo escolhido pela falta, a carga
aparece como `0,020 kA` — pequeno, mas legível, e sem a unidade ter mudado.
"""

from __future__ import annotations

import numpy as np

from osclab.formats.base import Record
from osclab.plot import conversao

#: Acima disto o prefixo `k` compensa. Abaixo, o número inteiro se lê melhor.
LIMIAR = 10_000.0

#: Só estas ganham prefixo. Um arquivo que já declara `kA` não vira `kkA`.
PREFIXAVEIS = {"A", "V"}


def _maximo_do_grupo(registro: Record, canais, lado: str) -> float:
    """O maior valor absoluto do grupo no registro INTEIRO, já convertido."""
    maior = 0.0
    for canal in canais:
        bruto = registro.analog[canal.index]
        convertido, _, _ = conversao.converter(bruto, canal, lado)
        finitos = convertido[np.isfinite(convertido)]
        if finitos.size:
            maior = max(maior, float(np.abs(finitos).max()))
    return maior


def do_grupo(registro: Record, canais, unidade: str,
             lado: str) -> tuple[float, str]:
    """`(divisor, unidade_mostrada)` de um grupo de canais.

    O divisor é 1 ou 1000; a unidade mostrada é a do arquivo, com `k` na frente
    quando o divisor for 1000.
    """
    limpa = (unidade or "").strip()
    if limpa.upper() not in PREFIXAVEIS or not canais:
        return (1.0, limpa)

    if _maximo_do_grupo(registro, canais, lado) < LIMIAR:
        return (1.0, limpa)
    return (1000.0, f"k{limpa}")


def por_unidade(registro: Record, lado: str) -> dict[str, tuple[float, str]]:
    """O mesmo, para todos os grupos de uma vez, indexado pela unidade do arquivo.

    Existe para o desenho e a leitura do cursor usarem **a mesma conta**. Se
    cada um decidisse por si, o gráfico mostraria `kA` e o cursor leria `A` no
    mesmo instante — e o usuário acreditaria no que estivesse olhando.
    """
    grupos: dict[str, list] = {}
    for canal in registro.analog_channels:
        grupos.setdefault(canal.unit.strip(), []).append(canal)

    return {
        unidade: do_grupo(registro, canais, unidade, lado)
        for unidade, canais in grupos.items()
    }
