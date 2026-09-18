"""Para onde a janela de tempo vai quando o usuário amplia ou arrasta.

O navegador sabe de pixel; este módulo sabe de segundos. O mouse manda um
**gesto** — "ampliar 0,8 em torno deste instante", "andar 12 ms para trás" — e
aqui se decide qual janela isso vira de verdade.

## Por que a conta não fica no JavaScript

Três regras deste arquivo só se descobrem analisando falta, e erradas elas
enganam sem parecer erro:

* **A janela nunca encolhe além de algumas amostras.** Ampliar até sobrar uma
  amostra desenha uma reta entre dois pontos — parece um sinal limpo, e não é
  sinal nenhum. Oito amostras é o piso: menos do que isso não tem forma de onda
  para ver.
* **A janela nunca sai do registro.** Arrastar para além do fim mostraria uma
  tela vazia que o usuário lê como "o sinal acabou".
* **Arrastar preserva a largura.** Ao bater na borda, a janela *desliza* e para;
  não encolhe. Largura mudando sozinha durante o arrasto é a receita para o
  usuário perder a noção da escala de tempo.

## O ponto sob o cursor não se mexe

É o que faz o zoom parecer natural: a roda amplia *em torno* de onde o mouse
está, então o detalhe que se está olhando continua debaixo do cursor. Sem isso,
ampliar joga o ponto de interesse para fora da tela e o usuário passa a
perseguir a falta com o arrasto.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.formats.base import Record

#: Piso da janela, em amostras. Abaixo disso não há forma de onda para ver.
MINIMO_AMOSTRAS = 8

#: Limites de um gesto de zoom. Uma roda de mouse manda ~0,8 por entalhe; o
#: teto existe só para um pedido malformado não virar uma conta absurda.
FATOR_MINIMO = 0.02
FATOR_MAXIMO = 50.0


def extensao(registro: Record) -> tuple[float, float]:
    """O primeiro e o último instante do registro, em segundos."""
    t = registro.time
    if t.size == 0:
        return (0.0, 0.0)
    return (float(t[0]), float(t[-1]))


def passo(registro: Record) -> float:
    """O intervalo médio entre amostras, em segundos.

    Média, e não o primeiro intervalo: registro com mais de uma taxa de
    amostragem tem passos diferentes ao longo do arquivo, e o que interessa
    aqui é uma ordem de grandeza para calcular o piso da janela.
    """
    t = registro.time
    if t.size < 2:
        return 0.0
    total = float(t[-1]) - float(t[0])
    return total / (t.size - 1) if total > 0 else 0.0


def janela_minima(total: float, intervalo: float) -> float:
    """A menor janela que ainda mostra forma de onda."""
    if total <= 0:
        return 0.0
    if intervalo > 0:
        return min(total, MINIMO_AMOSTRAS * intervalo)
    return total * 1e-4          # registro sem passo conhecido: 1/10000 do todo


def limitar(t0: float, t1: float, de: float | None, ate: float | None,
            intervalo: float = 0.0) -> tuple[float, float]:
    """A janela realmente mostrável: dentro do registro e não menor que o piso.

    Toda janela passa por aqui antes de virar desenho — inclusive a que o
    usuário digitou na URL. É o único lugar que conhece as bordas.
    """
    total = t1 - t0
    if not (math.isfinite(t0) and math.isfinite(t1)) or total <= 0:
        return (t0, t1)

    de = t0 if de is None else float(de)
    ate = t1 if ate is None else float(ate)
    if not (math.isfinite(de) and math.isfinite(ate)):
        return (t0, t1)
    if ate < de:
        de, ate = ate, de

    largura = min(max(ate - de, janela_minima(total, intervalo)), total)

    # Encolher ou alargar acontece em torno do centro; escorregar para dentro
    # das bordas acontece sem mudar a largura.
    centro = (de + ate) / 2.0
    de, ate = centro - largura / 2.0, centro + largura / 2.0
    if de < t0:
        de, ate = t0, t0 + largura
    if ate > t1:
        de, ate = t1 - largura, t1
    return (max(de, t0), min(ate, t1))


def ampliar(t0: float, t1: float, de: float, ate: float, fator: float,
            foco: float | None, intervalo: float = 0.0) -> tuple[float, float]:
    """Multiplica a largura da janela por `fator`, fixando o ponto `foco`.

    `fator` menor que 1 aproxima; maior que 1 afasta. O instante `foco` — onde
    o cursor está — continua na mesma posição relativa da tela.
    """
    de, ate = limitar(t0, t1, de, ate, intervalo)
    largura = ate - de
    if largura <= 0:
        return (de, ate)

    if not math.isfinite(fator) or fator <= 0:
        return (de, ate)
    fator = min(max(fator, FATOR_MINIMO), FATOR_MAXIMO)

    if foco is None or not math.isfinite(foco):
        foco = (de + ate) / 2.0
    foco = min(max(float(foco), de), ate)

    parte = (foco - de) / largura         # onde o cursor está, de 0 a 1
    nova = largura * fator
    novo_de = foco - parte * nova
    return limitar(t0, t1, novo_de, novo_de + nova, intervalo)


def deslocar(t0: float, t1: float, de: float, ate: float, delta: float,
             intervalo: float = 0.0) -> tuple[float, float]:
    """Anda `delta` segundos com a janela, sem mudar a largura."""
    de, ate = limitar(t0, t1, de, ate, intervalo)
    if not math.isfinite(delta):
        return (de, ate)
    return limitar(t0, t1, de + delta, ate + delta, intervalo)


def resolver(registro: Record, *, de: float | None = None,
             ate: float | None = None, zoom: float | None = None,
             foco: float | None = None, andar: float | None = None,
             tudo: bool = False) -> tuple[float, float]:
    """A janela que o pedido da tela produz.

    `tudo` desfaz o zoom — é o botão direito do mouse. Os gestos se aplicam
    sobre a janela que a tela já estava mostrando (`de`/`ate`), e não sobre o
    registro inteiro: é o que torna o zoom cumulativo.
    """
    t0, t1 = extensao(registro)
    intervalo = passo(registro)

    if tudo:
        return (t0, t1)

    atual = limitar(t0, t1, de, ate, intervalo)
    if zoom is not None:
        return ampliar(t0, t1, *atual, zoom, foco, intervalo)
    if andar is not None:
        return deslocar(t0, t1, *atual, andar, intervalo)
    return atual


def inteiro(t0: float, t1: float, de: float, ate: float) -> bool:
    """A janela cobre o registro todo? (a tela usa para dizer se há zoom)"""
    total = t1 - t0
    if total <= 0:
        return True
    folga = total * 1e-6
    return (de - t0) <= folga and (t1 - ate) <= folga


def instante_por_amostra(registro: Record, alvo: float) -> float:
    """O instante da amostra mais próxima de `alvo`.

    Serve para o pedido do navegador não pedir uma janela entre duas amostras,
    o que faria o recorte oscilar de um pixel a cada gesto.
    """
    t = registro.time
    if t.size == 0:
        return alvo
    i = int(np.clip(np.searchsorted(t, alvo), 0, t.size - 1))
    if i > 0 and abs(float(t[i - 1]) - alvo) <= abs(float(t[i]) - alvo):
        i -= 1
    return float(t[i])
