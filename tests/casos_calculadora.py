"""Registros sintéticos para a calculadora — COMTRADE 1999 ASCII a 2000 Hz.

Montados por FASOR (o valor eficaz de cada trecho) mais a contínua que torna a
corrente contínua no tempo, como num circuito RL. Os carimbos e a senoide saem
do mesmo vetor de instantes (a lição da `fabrica.py`).

    alimentador  nomes de outro fabricante («Current IA», «Voltage A-G»), o
                 neutro medido «Current IN» SEM relação de TC declarada, uma
                 «Vbat» em V contínuo, e falta AG. O Zap AG com
                 k0 = 0,68∠−4° foi construído para dar 1,2 + j3,6 Ω.
    trafo        estilo SIPROTEC, nomes LONGOS: duas trincas de corrente
                 («TC BUC 69kV:I A» a 400/5, «TC EXT 13-8kV:I A» a 2000/5), uma
                 de tensão, uma diferencial em pu («87T:I diff.:phs A») e um
                 digital de 27 letras («MAIN : Timer stage N elaps.»).
"""

from __future__ import annotations

import cmath
import math
from pathlib import Path

import numpy as np

TAXA, F = 2000.0, 60.0
W = 2 * math.pi * F
K0 = cmath.rect(0.68, math.radians(-4.0))
ZAP = complex(1.2, 3.6)
#: Onde os cursores caem: pré-falta e falta sustentada.
T_PRE, T_FALTA = 0.06, 0.195


def polar(m: float, graus: float) -> complex:
    return cmath.rect(m, math.radians(graus))


def onda(t: np.ndarray, trechos, tau: float | None = None) -> np.ndarray:
    """`trechos` = [(t_ini, fasor eficaz)]; troca de fasor em cada t_ini."""
    y = np.zeros_like(t)
    for k, (t0, fas) in enumerate(trechos):
        t1 = trechos[k + 1][0] if k + 1 < len(trechos) else 1e9
        m = (t >= t0) & (t < t1)
        y[m] = math.sqrt(2) * np.real(fas * np.exp(1j * W * t[m]))
        if tau and k > 0 and abs(fas) > 0:
            salto = math.sqrt(2) * np.real((trechos[k - 1][1] - fas) * np.exp(1j * W * t0))
            y[m] += salto * np.exp(-(t[m] - t0) / tau)
    return y


def escrever(pasta: Path, nome: str, estacao: str, rele: str, canais, digitais, n: int) -> Path:
    """canais = [(nome, fase, unidade, série, prim, sec)]; devolve o `.cfg`."""
    cfg = [
        f"{estacao},{rele},1999",
        f"{len(canais) + len(digitais)},{len(canais)}A,{len(digitais)}D",
    ]
    fatores = []
    for k, (nm, ph, uu, y, p, s) in enumerate(canais):
        a = float(np.max(np.abs(y))) / 30000 or 1.0
        fatores.append(a)
        cfg.append(f"{k + 1},{nm},{ph},,{uu},{a:.9g},0,0,-32767,32767,{p:g},{s:g},S")
    for k, (nm, _) in enumerate(digitais):
        cfg.append(f"{k + 1},{nm},,,0")
    cfg += [
        "60",
        "1",
        f"{TAXA:g},{n}",
        "27/10/2026,14:03:11.250000",
        "27/10/2026,14:03:11.350000",
        "ASCII",
        "1",
    ]
    (pasta / f"{nome}.cfg").write_bytes(("\r\n".join(cfg) + "\r\n").encode("latin-1"))
    linhas = []
    for i in range(n):
        vals = [str(int(round(c[3][i] / fatores[j]))) for j, c in enumerate(canais)]
        dig = [str(int(d[1][i])) for d in digitais]
        linhas.append(",".join([str(i + 1), str(int(round(i / TAXA * 1e6))), *vals, *dig]))
    (pasta / f"{nome}.dat").write_bytes(("\r\n".join(linhas) + "\r\n").encode("latin-1"))
    return pasta / f"{nome}.cfg"


def alimentador(pasta: Path) -> Path:
    n = 700
    t = np.arange(n) / TAXA
    tf, ta = 0.100, 0.210
    va0, vb0, vc0 = polar(66.4, 0), polar(66.4, -120), polar(66.4, 120)
    ia0, ib0, ic0 = polar(2.1, -25), polar(2.0, -145), polar(2.05, 95)
    iaf = polar(28.0, -68)
    tres_i0 = iaf + ib0 + ic0
    vaf = ZAP * (iaf + K0 * tres_i0)
    canais = [
        ("Voltage A-G", "", "V", onda(t, [(0, va0), (tf, vaf), (ta, va0 * 0.99)]), 13800, 115),
        (
            "Voltage B-G",
            "",
            "V",
            onda(t, [(0, vb0), (tf, polar(68.5, -122)), (ta, vb0)]),
            13800,
            115,
        ),
        (
            "Voltage C-G",
            "",
            "V",
            onda(t, [(0, vc0), (tf, polar(67.9, 121)), (ta, vc0)]),
            13800,
            115,
        ),
        ("Current IA", "", "A", onda(t, [(0, ia0), (tf, iaf), (ta, 0j)], tau=0.018), 600, 5),
        ("Current IB", "", "A", onda(t, [(0, ib0), (ta, 0j)]), 600, 5),
        ("Current IC", "", "A", onda(t, [(0, ic0), (ta, 0j)]), 600, 5),
        # o neutro medido, num toroide cuja relação o arquivo NÃO declara
        (
            "Current IN",
            "",
            "A",
            onda(t, [(0, (ia0 + ib0 + ic0) * 0.5), (tf, tres_i0 * 0.5), (ta, 0j)], tau=0.018),
            0,
            0,
        ),
        ("Vbat", "", "V", 125.4 + 0.3 * np.sin(2 * math.pi * 3 * t), 1, 1),
    ]
    trip = ((t >= tf + 0.045) & (t < ta + 0.02)).astype(int)
    return escrever(
        pasta, "CALC_ALIMENTADOR", "SE CENTAURO", "AL05", canais, [("Trip 51N", trip)], n
    )


def trafo(pasta: Path) -> Path:
    n = 800
    t = np.arange(n) / TAXA
    tf, ta = 0.100, 0.200
    carga = [polar(3.0, -20 - 120 * k) for k in range(3)]
    ib = polar(22.0, -165)
    falta_x = [polar(2.7, -20), ib, -ib]
    g = polar(0.5, 30) / math.sqrt(3)

    def lado_w(fx):
        a, b, c = fx
        return [(a - b) * g, (b - c) * g, (c - a) * g]

    cw, fw = lado_w(carga), lado_w(falta_x)
    canais = []
    for k, f in enumerate("ABC"):
        canais.append(
            (
                f"TC BUC 69kV:I {f}",
                "",
                "A",
                onda(t, [(0, cw[k]), (tf, fw[k]), (ta, 0j)], tau=0.02),
                400,
                5,
            )
        )
    for k, f in enumerate("ABC"):
        canais.append(
            (
                f"TC EXT 13-8kV:I {f}",
                "",
                "A",
                onda(t, [(0, carga[k]), (tf, falta_x[k]), (ta, 0j)], tau=0.02),
                2000,
                5,
            )
        )
    vpre = [polar(66.4, -120 * k) for k in range(3)]
    vf = [polar(66.0, 0), polar(36.0, -150), polar(36.0, 150)]
    for k, f in enumerate("ABC"):
        canais.append(
            (
                f"TP BAR 13-8kV:V {f}",
                "",
                "V",
                onda(t, [(0, vpre[k]), (tf, vf[k]), (ta, vpre[k] * 0.98)]),
                13800,
                115,
            )
        )
    canais.append(("87T:I diff.:phs A", "", "I/IrObj", 0.02 + 0.001 * np.sin(W * t), 1, 1))
    trip = ((t >= tf + 0.035) & (t < ta + 0.02)).astype(int)
    return escrever(
        pasta,
        "CALC_TRAFO_TC_BUC",
        "SE ANDROMEDA",
        "TR1 7UT",
        canais,
        [("MAIN : Timer stage N elaps.", trip)],
        n,
    )


def ler(cfg: Path):
    from osclab.formats.comtrade import ComtradeReader

    return ComtradeReader().read(cfg)
