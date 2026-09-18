"""O que os cursores leem: valor de cada canal num instante, e o tempo entre eles.

## Por que esta leitura não pode sair do desenho

O gráfico não mostra as amostras: mostra o **mínimo e o máximo de cada coluna de
pixel** (ver `plot/serie.py`). É o certo para desenhar — nenhum pico some — e é
justamente por isso que ler o valor do traço na tela daria o número errado:
metade dos pontos desenhados é um mínimo, metade é um máximo, e nenhum dos dois
é "o valor naquele instante".

Por isso o cursor pergunta ao servidor, que vai à amostra de verdade.

## O cursor cai em cima de uma amostra, sempre

Entre duas amostras não existe medida — existe interpolação, que é palpite. Num
registro a 16 amostras/ciclo, meia amostra é 11° de defasagem: um palpite desses
estraga fasor e localização de falta. Então o instante pedido é encostado na
amostra mais próxima, e é **essa** que a tela desenha e lê.

## Tempo: sempre nas duas unidades

Cada instante e o intervalo entre os cursores saem em **ms** e em **ciclos**, e
a tela escolhe qual mostrar. São as duas linguagens do ofício: o relatório e o
ajuste do relé falam em ms; a conversa fala em ciclos ("o disjuntor abriu em 2,5
ciclos").

**Não se calcula frequência a partir do intervalo.** `1/Δt` é tentador e engana
duas vezes: o usuário lê como "a frequência do sistema na falta", e a precisão
não sustenta a leitura. A 20 amostras/ciclo, uma amostra são 0,83 ms num período
de 16,67 ms — **±5 %, ou ±3 Hz**, que é justamente a diferença que se queria
enxergar. Medir frequência exige muitos ciclos e implementação própria.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.formats import fases
from osclab.formats.base import Record
from osclab.plot import conversao, unidades
from osclab.plot.conversao import LADOS


def indice(registro: Record, instante: float) -> int:
    """O índice da amostra mais próxima de `instante`."""
    t = registro.time
    if t.size == 0:
        return 0
    if not math.isfinite(instante):
        return 0
    i = int(np.clip(np.searchsorted(t, instante), 0, t.size - 1))
    if i > 0 and abs(float(t[i - 1]) - instante) <= abs(float(t[i]) - instante):
        i -= 1
    return i


def _num(x: float) -> float | None:
    """JSON não tem NaN nem infinito; canal saturado ou vazio vira `null`."""
    return float(x) if math.isfinite(x) else None


def casas(valor: float | None) -> int:
    """Quantas casas decimais mostrar num valor lido.

    Fixar uma casa para tudo erra dos dois lados: `6743,2 A` de corrente de
    falta primária tem uma casa que ninguém usa e que só rouba largura da
    coluna, enquanto `0,3 A` de corrente de fuga esconde justamente o dígito
    que interessa. A regra segue a ordem de grandeza, mirando **cinco dígitos
    significativos**.

    ## Por que cinco e não quatro

    O erro que o arredondamento introduz é meia casa decimal, e ele é pior no
    começo de cada década. Com quatro dígitos, `10,0` erra 0,5 % — a mesma ordem
    de grandeza do erro do próprio relé, e é desconfortável que a tela contribua
    tanto quanto o instrumento. Com cinco, `10,00` erra 0,05 %: uma ordem abaixo,
    ou seja, o display deixa de aparecer na conta.

    Custa um caractere de largura na tabelinha. Vale.
    """
    if valor is None or not math.isfinite(valor):
        return 1
    grandeza = abs(valor)
    if grandeza >= 1000:
        return 0                 # 6743 A — abaixo do ampère já não há medida
    if grandeza >= 100:
        return 1                 # 152,7 A
    if grandeza >= 10:
        return 2                 # 12,35 A
    if grandeza >= 1:
        return 3                 # 2,354 A
    return 4                     # 0,3123 A — corrente de fuga


def casas_do_tempo(resolucao: float) -> int:
    """Casas decimais para um tempo cuja resolução real é `resolucao`.

    A resolução de um instante não é escolha de gosto: é o **intervalo entre
    amostras**. Num registro a 1200 Hz, duas amostras vizinhas distam 0,833 ms —
    escrever `225,000 ms` promete microssegundo onde não há, rouba largura da
    coluna e ainda trunca na tela.

    A regra devolve a menor quantidade de casas em que duas amostras vizinhas
    ainda saem diferentes: 1 casa a 1200 Hz (225,0 · 225,8 · 226,7), 2 casas a
    20 kHz, e zero casa num registro muito lento.
    """
    if not math.isfinite(resolucao) or resolucao <= 0:
        return 3
    return int(min(max(math.ceil(-math.log10(resolucao)), 0), 6))


def _resolucoes(registro: Record) -> tuple[int, int]:
    """Quantas casas mostrar no tempo, em ms e em ciclos."""
    t = registro.time
    if t.size < 2:
        return (3, 2)
    passo = (float(t[-1]) - float(t[0])) / (t.size - 1)
    frequencia = float(registro.line_frequency or 0.0)
    return (
        casas_do_tempo(passo * 1000.0),
        casas_do_tempo(passo * frequencia) if frequencia > 0 else 2,
    )


def _em_uma_amostra(registro: Record, i: int, lado: str, escalas: dict) -> dict:
    """Tudo que a tela mostra de um cursor parado na amostra `i`.

    `escalas` vem de `unidades.por_unidade` — a MESMA que o desenho usou. Se
    cada um decidisse o prefixo por si, o gráfico mostraria `kA` e o cursor
    leria `A` no mesmo instante, e o usuário acreditaria no que estivesse
    olhando.
    """
    t = float(registro.time[i])
    disparo = _instante_do_disparo(registro)
    frequencia = float(registro.line_frequency or 0.0)

    valores = []
    for canal in registro.analog_channels:
        bruto = np.array([registro.analog[canal.index, i]], dtype=np.float64)
        convertido, lado_final, foi = conversao.converter(bruto, canal, lado)
        fase, _ = fases.da_canal(canal)
        divisor, mostrada = escalas.get(canal.unit.strip(), (1.0, canal.unit.strip()))
        valor = _num(convertido[0] / divisor)
        valores.append({
            "nome": canal.name,
            "unidade": mostrada,
            "fase": fase,
            "lado": lado_final,
            "convertido": foi,
            "valor": valor,
            "casas": casas(valor),
        })

    desde_o_disparo = t - disparo
    return {
        "t": round(t, 9),
        "amostra": int(i),
        "ms": round(desde_o_disparo * 1000.0, 6),
        "ciclos": round(desde_o_disparo * frequencia, 4) if frequencia > 0 else None,
        "valores": valores,
    }


def _instante_do_disparo(registro: Record) -> float:
    if registro.trigger_time is None or registro.start_time is None:
        return 0.0
    return (registro.trigger_time - registro.start_time).total_seconds()


def entre(registro: Record, a: dict, b: dict) -> dict:
    """O que separa os dois cursores: tempo e diferença de cada canal.

    A subtração canal a canal sai daqui, e não do navegador, pela mesma razão
    que tudo mais: é número. Afundamento de tensão e salto de corrente entre
    dois instantes vão para o relatório; conta que vai para relatório tem teste.
    """
    segundos = b["t"] - a["t"]
    frequencia = float(registro.line_frequency or 0.0)

    diferencas = []
    for va, vb in zip(a["valores"], b["valores"], strict=True):
        if va["valor"] is None or vb["valor"] is None:
            diferencas.append({"nome": va["nome"], "unidade": va["unidade"],
                               "valor": None, "casas": 1})
            continue
        d = vb["valor"] - va["valor"]
        diferencas.append({"nome": va["nome"], "unidade": va["unidade"],
                           "valor": d, "casas": casas(d)})

    return {
        "segundos": round(segundos, 9),
        "ms": round(segundos * 1000.0, 6),
        "ciclos": round(segundos * frequencia, 4) if frequencia > 0 else None,
        "valores": diferencas,
    }


def em(registro: Record, pedidos: list[tuple[float | None, int, float]],
       lado: str = "arquivo") -> dict:
    """A leitura dos cursores.

    Cada pedido é `(instante_em_segundos, passo_em_amostras, passo_em_ciclos)`.
    Os dois passos são o que as setas do teclado mandam. Andar **um ciclo** é
    pedido em ciclos, não em amostras: quantas amostras cabem num ciclo depende
    da taxa de amostragem e da frequência nominal do registro, e essa conta é
    daqui — o navegador não tem por que saber que um SEL-411L a 60 Hz anda 32
    amostras e um GE a 96 amostras/ciclo anda 96.
    """
    if lado not in LADOS:
        lado = "arquivo"
    if lado == "arquivo":
        lado = conversao.lado_natural(registro)

    n = registro.n_samples
    por_ciclo = float(registro.samples_per_cycle or 0.0)
    escalas = unidades.por_unidade(registro, lado)

    cursores = []
    for instante, passo, ciclos in pedidos:
        if instante is None or n == 0:
            cursores.append(None)
            continue
        andar = int(passo)
        if ciclos and por_ciclo > 0:
            andar += int(round(float(ciclos) * por_ciclo))
        i = int(np.clip(indice(registro, instante) + andar, 0, n - 1))
        cursores.append(_em_uma_amostra(registro, i, lado, escalas))

    casas_ms, casas_ciclos = _resolucoes(registro)
    presentes = [c for c in cursores if c is not None]
    return {
        "cursores": cursores,
        "entre": entre(registro, presentes[0], presentes[1])
        if len(presentes) == 2 else None,
        "lado_pedido": lado,
        "amostras_por_ciclo": round(por_ciclo, 4),
        "casas_ms": casas_ms,
        "casas_ciclos": casas_ciclos,
    }
