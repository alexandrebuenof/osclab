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


#: Os prefixos que uma potência pode receber, do maior para o menor.
#:
#: Tensão e corrente param no `k` porque não existe oscilografia com megavolt.
#: Potência não: uma linha de 230 kV com 1000 A são 398 MVA, e `398000000 VA`
#: não se lê. O `G` entra pelo mesmo motivo — uma interligação de 765 kV passa
#: do bilhão.
PREFIXOS_DE_POTENCIA = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""))

#: As unidades-base de potência. `VA` é a que serve de régua: P, Q e S têm a
#: mesma ordem de grandeza, e dar prefixos diferentes a elas faria `P` e `S`
#: do MESMO vão aparecerem em escalas diferentes lado a lado.
UNIDADES_DE_POTENCIA = ("W", "var", "VA")


def fator_do_prefixo(unidade: str) -> tuple[float, str]:
    """`"kV"` → `(1000.0, "V")`. O que o ARQUIVO já declarou.

    É daqui que sai a primeira metade da resposta: `kV × A` é **kVA**, e isso
    se sabe do cabeçalho do COMTRADE, sem olhar amostra nenhuma. A segunda
    metade — se aquilo deve aparecer como kVA ou MVA — é a grandeza dos
    números, e essa só as amostras dizem.
    """
    limpa = (unidade or "").strip()
    for fator, prefixo in PREFIXOS_DE_POTENCIA:
        if prefixo and limpa.startswith(prefixo) and len(limpa) > 1:
            return (fator, limpa[1:])
    return (1.0, limpa)


def _potencia_do_registro(registro: Record, lado: str) -> tuple[float, str] | None:
    """`(divisor, prefixo)` da potência deste registro, ou `None`.

    `None` quando não há vínculo nenhum: sem par corrente×tensão não existe
    potência a escalar.

    O divisor leva do número que sai da conta — que está na unidade do
    ARQUIVO, `kV × A` — para o número que a tela escreve. Os dois fatores
    entram: o que o arquivo já declarou (`fator_do_prefixo`) e o que a
    grandeza pede.

    O máximo é estimado por `1,5 × |V|max × |I|max`, que é o teto de
    `3·V·I` com fasores de pico. Teto e não valor exato de propósito: o exato
    exigiria calcular as seis DFTs aqui dentro, e errar o prefixo para cima
    escreve `0,4 MVA` onde `400 kVA` caberia — enquanto o caminho exato
    custaria o dobro do tempo de abrir o registro para ganhar um dígito.
    """
    vinculos = getattr(registro, "vinculos_de_potencia", None) or {}
    if not vinculos:
        return None
    por_grandeza: dict[str, tuple[float, float]] = {}
    for canal in registro.analog_channels:
        fator, base = fator_do_prefixo(canal.unit)
        if base.upper() not in PREFIXAVEIS:
            continue
        bruto = registro.analog[canal.index]
        convertido, _, _ = conversao.converter(bruto, canal, lado)
        finitos = convertido[np.isfinite(convertido)]
        if not finitos.size:
            continue
        pico = float(np.abs(finitos).max())
        antes = por_grandeza.get(base.upper(), (0.0, 1.0))
        if pico * fator > antes[0] * antes[1]:
            por_grandeza[base.upper()] = (pico, fator)
    if "V" not in por_grandeza or "A" not in por_grandeza:
        return None
    (pico_v, fator_v), (pico_i, fator_i) = por_grandeza["V"], por_grandeza["A"]

    # O que o ARQUIVO já diz: `kV × A` = ×1000 antes de qualquer medição.
    natural = fator_v * fator_i
    # O teto em VA de verdade, para escolher o prefixo.
    teto = 1.5 * pico_v * fator_v * pico_i * fator_i
    # Duas regras, nesta ordem.
    #
    # 1. Abaixo de `LIMIAR` não há prefixo nenhum — a mesma regra de A e V, e
    #    pela mesma razão: `1725 W` se lê de imediato, `1,725 kW` é a mesma
    #    coisa escrita pior.
    # 2. Acima dele, o MAIOR prefixo que ainda deixa o número ≥ 1. É o que põe
    #    `398 MW` no lugar de `398383 kW` e de `398383000 W`.
    if teto < LIMIAR:
        return (1.0 / natural, "")
    for fator, prefixo in PREFIXOS_DE_POTENCIA:
        if teto >= fator:
            return (fator / natural, prefixo)
    return (1.0 / natural, "")


def por_unidade(registro: Record, lado: str) -> dict[str, tuple[float, str]]:
    """O mesmo, para todos os grupos de uma vez, indexado pela unidade do arquivo.

    Existe para o desenho e a leitura do cursor usarem **a mesma conta**. Se
    cada um decidisse por si, o gráfico mostraria `kA` e o cursor leria `A` no
    mesmo instante — e o usuário acreditaria no que estivesse olhando.
    """
    grupos: dict[str, list] = {}
    for canal in registro.analog_channels:
        grupos.setdefault(canal.unit.strip(), []).append(canal)

    saida = {
        unidade: do_grupo(registro, canais, unidade, lado)
        for unidade, canais in grupos.items()
    }
    # As potências entram na mesma tabela, com UM prefixo para as três: P, Q e
    # S do mesmo vão têm a mesma ordem de grandeza, e prefixos diferentes as
    # fariam aparecer em escalas diferentes lado a lado.
    escala = _potencia_do_registro(registro, lado)
    if escala is not None:
        divisor, prefixo = escala
        for base in UNIDADES_DE_POTENCIA:
            saida[base] = (divisor, f"{prefixo}{base}")
    return saida
