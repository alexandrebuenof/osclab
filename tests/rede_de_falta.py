"""Gerador de faltas para validar a LDL — INDEPENDENTE do `test_ldl.py`.

O `test_ldl.py` resolve a rede em SEQUÊNCIAS e desenha senoides puras com um
degrau na falta. Serve para prender a conta, mas um sintético só confirma as
suposições com que foi feito (ver «A falta vem ANTES do disparo» no
CLAUDE.md). Este gerador nasceu da validação independente de 24/10/2026 e
parte de outro lugar:

- **a rede é resolvida em FASE**, não em sequência: fonte trifásica atrás de
  uma matriz 3×3, linha transposta em **π em cascata com capacitância shunt**
  (seções de até 5 km) ou concentrada sem C, disjuntor por polo, falta por
  resistores — na linha, numa barra ou numa linha vizinha;
- **a mesma lista de elementos é resolvida duas vezes**: em regime a 60 Hz,
  por admitância nodal complexa (a «verdade» dos fasores, de onde sai o erro
  INERENTE de cada método), e no tempo, por um mini-EMTP trapezoidal a
  12 kHz. A falta entra num instante qualquer da onda — a componente contínua
  sai da física, não de uma fórmula — e cada polo abre no ZERO da corrente;
- **o registro sai como um relé gravaria**: anti-aliasing, decimação com fase
  de amostragem diferente em cada terminal, ruído e quantização de 16 bits,
  COMTRADE em primário ou secundário, `.CEV` filtrado a 8 ou 4 amostras por
  ciclo (cosseno de um ciclo, corrente em ampère inteiro TRUNCADO e tensão em
  kV com duas casas, como o leitor documenta), TC saturando, polaridade
  invertida, fases trocadas, erro de relógio. O `TRIP` sobe 25 ms DEPOIS do
  início da falta: a falta vem antes do disparo, sempre.

Convenção de medida: tensão da BARRA e corrente do DISJUNTOR, positiva da
barra para a linha; `m` contado a partir de S (o IED A). Nada aqui é dado
real.

Dois laços em Python ficam, e são de propósito: o passo do EMTP e o fluxo do
TC saturado são RECORRÊNCIAS — cada amostra depende da anterior, e não há
como vetorizá-las no tempo. Dentro de cada passo tudo é numpy. O programa
(`src/`) continua sem laço por amostra; isto é a bancada de ensaio dele.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from osclab.formats.base import (
    AnalogChannel,
    Filtering,
    FilteringSource,
    Record,
    SampleRate,
    StatusChannel,
)

F0 = 60.0
W = 2 * math.pi * F0
A_OP = cmath.exp(2j * math.pi / 3)
FS = 12000.0            #: a taxa do EMTP: múltiplo de 2000, 1200, 480 e 240 Hz
R_FECHADO = 1e-3        #: ohm de um contato fechado
R_MIN_FALTA = 0.01      #: o «Rf = 0»
TERRA = -1


def _mat_seq(x0: complex, x1: complex) -> np.ndarray:
    """A matriz de fase 3×3 de um elemento transposto, a partir de X0 e X1."""
    m = np.full((3, 3), (x0 - x1) / 3.0, dtype=complex)
    m[np.diag_indices(3)] = (x0 + 2 * x1) / 3.0
    return m


def seq(fa, fb, fc):
    """(X0, X1, X2) de três fasores de fase — X0, não 3X0."""
    a = A_OP
    return ((fa + fb + fc) / 3, (fa + a * fb + a * a * fc) / 3,
            (fa + a * a * fb + a * fc) / 3)


# ---------------------------------------------------------------------------
# O cenário
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Linha:
    """Parâmetros POR QUILÔMETRO; `c1`/`c0` em F/km."""

    km: float
    z1: complex
    z0: complex
    c1: float
    c0: float

    @property
    def Z1(self) -> complex:
        return self.z1 * self.km

    @property
    def Z0(self) -> complex:
        return self.z0 * self.km


#: 138 kV, 100 km, cabo 336 MCM típico — a linha da validação.
LT_100 = Linha(100.0, complex(0.10, 0.50), complex(0.40, 1.55), 9.0e-9, 6.0e-9)


@dataclass(frozen=True)
class Cenario:
    """Uma falta. `local`: «linha», «barraS», «barraR», «externaS», «externaR»
    (a 30 % de uma linha vizinha, atrás de S ou depois de R).

    As fontes têm |Z1| = SIR·|Z1 da linha| no ângulo `ang_fonte`, e Z0 = 0,8·Z1;
    `delta` é o quanto a fonte S está adiantada de R (exportação de S).
    """

    linha: Linha = LT_100
    m: float = 0.5
    tipo: str = "AG"            # AG BG CG AB BC CA ABG BCG CAG ABC
    rf: float = 0.0
    local: str = "linha"
    capacitancia: bool = True   # False: linha concentrada, só série
    sir_s: float = 1.0
    sir_r: float = 1.0
    ang_fonte: float = 85.0
    delta: float = 15.0
    vbase: float = 138e3

    @property
    def km_verdadeiro(self) -> float:
        return self.m * self.linha.km

    def fonte(self, sir: float) -> tuple[complex, complex]:
        z1 = sir * abs(self.linha.Z1) * cmath.exp(1j * math.radians(self.ang_fonte))
        return z1, 0.8 * z1

    def parametros(self) -> dict:
        """A linha como o usuário a digitaria: Z1 e Z0 nominais, em ohm primário."""
        L = self.linha
        return {"r": L.Z1.real, "x": L.Z1.imag, "km": L.km,
                "r0": L.Z0.real, "x0": L.Z0.imag}


class _Rede:
    """A lista de elementos — a mesma para o regime e para o tempo."""

    def __init__(self):
        self.conhecido: list[bool] = []
        self.rl: list[tuple] = []     # (nós de, nós até, Z 3×3 a 60 Hz)
        self.cap: list[tuple] = []    # (nós, C 3×3)
        self.res: list[list] = []     # [n1, n2, R, etiqueta, fechado]
        self.fontes: list[tuple] = []  # (nós, fasores)

    def barra(self, conhecido: bool = False) -> np.ndarray:
        inicio = len(self.conhecido)
        self.conhecido.extend([conhecido] * 3)
        return np.arange(inicio, inicio + 3)

    def no(self) -> int:
        self.conhecido.append(False)
        return len(self.conhecido) - 1


def _construir(c: Cenario) -> tuple[_Rede, np.ndarray, np.ndarray]:
    """A rede do cenário, e as barras onde S e R medem."""
    r = _Rede()
    L = c.linha
    vf = c.vbase / math.sqrt(3)
    abc = np.array([1, A_OP ** 2, A_OP])
    es, sb, sl, rl, rb, er = (r.barra(i in (0, 5)) for i in range(6))
    r.fontes.append((es, vf * cmath.exp(1j * math.radians(c.delta)) * abc))
    r.fontes.append((er, vf * abc))
    r.rl.append((es, sb, _mat_seq(*reversed(c.fonte(c.sir_s)))))
    r.rl.append((er, rb, _mat_seq(*reversed(c.fonte(c.sir_r)))))
    for k in range(3):
        r.res.append([sb[k], sl[k], R_FECHADO, "disjS", True])
        r.res.append([rb[k], rl[k], R_FECHADO, "disjR", True])

    def trecho(de, ate, km):
        if km <= 1e-9:
            for k in range(3):
                r.res.append([de[k], ate[k], R_FECHADO, "fixo", True])
            return
        if not c.capacitancia:
            r.rl.append((de, ate, _mat_seq(L.z0 * km, L.z1 * km)))
            return
        n = max(1, math.ceil(km / 5.0))
        ls = km / n
        meia_c = _mat_seq(L.c0 * ls / 2, L.c1 * ls / 2).real
        atual = de
        for j in range(n):
            prox = ate if j == n - 1 else r.barra()
            r.rl.append((atual, prox, _mat_seq(L.z0 * ls, L.z1 * ls)))
            r.cap.append((atual, meia_c))
            r.cap.append((prox, meia_c))
            atual = prox

    if c.local == "linha":
        f = r.barra()
        trecho(sl, f, c.m * L.km)
        trecho(f, rl, (1 - c.m) * L.km)
    else:
        trecho(sl, rl, L.km)
        if c.local in ("barraS", "barraR"):
            f = sb if c.local == "barraS" else rb
        else:
            f = r.barra()
            base = rb if c.local == "externaR" else sb
            r.rl.append((base, f, _mat_seq(0.3 * L.Z0, 0.3 * L.Z1)))

    # A falta: fase-terra por Rf; fase-fase por Rf entre as fases; bifásica-
    # terra e trifásica com as fases unidas num ponto e Rf desse ponto à terra.
    fases = [k for k, x in enumerate("ABC") if x in c.tipo.replace("G", "")]
    terra = c.tipo.endswith("G")
    rf = max(c.rf, R_MIN_FALTA)
    if len(fases) == 1:
        r.res.append([f[fases[0]], TERRA, rf, "falta", False])
    elif len(fases) == 2 and not terra:
        r.res.append([f[fases[0]], f[fases[1]], rf, "falta", False])
    else:
        ponto = r.no()
        r.res.append([ponto, TERRA, 1e7, "fixo", True])
        for k in fases:
            r.res.append([f[k], ponto, R_MIN_FALTA if terra else rf, "falta", False])
        if terra:
            r.res.append([ponto, TERRA, rf, "falta", False])
    return r, sb, rb


def _carimbar(Y: np.ndarray, de, ate, G: np.ndarray) -> None:
    """Soma o ramo `de → ate` (vetores de nós; TERRA é ignorada) em Y."""
    de, ate = np.asarray(de), np.asarray(ate)
    for nos_a, nos_b, sinal in ((de, de, 1), (ate, ate, 1), (de, ate, -1), (ate, de, -1)):
        ok_a, ok_b = nos_a >= 0, nos_b >= 0
        Y[np.ix_(nos_a[ok_a], nos_b[ok_b])] += sinal * G[np.ix_(ok_a, ok_b)]


# ---------------------------------------------------------------------------
# Regime a 60 Hz: a verdade dos fasores
# ---------------------------------------------------------------------------

def _resolver(r: _Rede, falta: bool) -> np.ndarray:
    """As tensões EFICAZES de todos os nós, com a falta ou sem ela."""
    n = len(r.conhecido)
    conhecido = np.array(r.conhecido)
    Y = np.zeros((n, n), complex)
    for de, ate, Z in r.rl:
        _carimbar(Y, de, ate, np.linalg.inv(Z))
    for nos, C in r.cap:
        _carimbar(Y, nos, np.full(3, TERRA), 1j * W * C)
    for n1, n2, R, etiqueta, fechado in r.res:
        if fechado or (falta and etiqueta == "falta"):
            _carimbar(Y, [n1], [n2], np.array([[1.0 / R]]))
    V = np.zeros(n, complex)
    for nos, fasores in r.fontes:
        V[nos] = fasores
    d, k = ~conhecido, conhecido
    V[d] = np.linalg.solve(Y[np.ix_(d, d)], -Y[np.ix_(d, k)] @ V[k])
    return V


def _regime(r: _Rede, sb, rb, falta: bool) -> dict:
    """Fasores EFICAZES da tensão da barra e da corrente do disjuntor em S e R."""
    V = _resolver(r, falta)
    saida = {}
    for lado, barra in (("S", sb), ("R", rb)):
        disj = [x for x in r.res if x[3] == f"disj{lado}"]
        saida[f"V{lado}"] = V[barra]
        saida[f"I{lado}"] = np.array([(V[x[0]] - V[x[1]]) / x[2] for x in disj])
    return saida


def seqneg_ideal(cen: Cenario) -> float:
    """A seq. negativa 2T sobre os fasores EXATOS — o erro inerente do método.

    `|V2S − m·Z·I2S| = |V2R − (1−m)·Z·I2R|`, resolvida aqui de novo, sem
    passar por `seqneg.py`. NaN quando nenhuma raiz (ou as duas) cai na linha.
    """
    f = _regime(*_construir(cen), falta=True)
    z = cen.linha.Z1
    v2s, i2s = seq(*f["VS"])[2], seq(*f["IS"])[2]
    v2r, i2r = seq(*f["VR"])[2], seq(*f["IR"])[2]
    b, c, e = z * i2s, v2r - z * i2r, z * i2r
    A = abs(b) ** 2 - abs(e) ** 2
    B = -2 * (v2s * b.conjugate()).real - 2 * (c * e.conjugate()).real
    C = abs(v2s) ** 2 - abs(c) ** 2
    delta = B * B - 4 * A * C
    if delta < 0 or A == 0:
        return float("nan")
    q = -0.5 * (B + math.copysign(math.sqrt(delta), B))
    boas = [x for x in (q / A, C / q) if -0.02 <= x <= 1.02]
    return boas[0] * cen.linha.km if len(boas) == 1 else float("nan")


def laco_ideal(cen: Cenario, laco: str) -> float:
    """O laço pela reatância, no IED A, sobre os fasores exatos."""
    f = _regime(*_construir(cen), falta=True)
    V, i = f["VS"], f["IS"]
    z1, z0 = cen.linha.Z1, cen.linha.Z0
    k = {"A": 0, "B": 1, "C": 2}
    if laco.endswith("N"):
        i_laco = i[k[laco[0]]] + (z0 - z1) / (3 * z1) * i.sum()
        v_laco = V[k[laco[0]]]
    else:
        v_laco = V[k[laco[0]]] - V[k[laco[1]]]
        i_laco = i[k[laco[0]]] - i[k[laco[1]]]
    return (v_laco / i_laco).imag / z1.imag * cen.linha.km


# ---------------------------------------------------------------------------
# No tempo: mini-EMTP trapezoidal
# ---------------------------------------------------------------------------

def simular(cen: Cenario, t_falta: float = 0.12, abre_s: float | None = 0.075,
            abre_r: float | None = 0.08, extingue: float | None = None,
            duracao: float | None = None) -> dict:
    """V da barra e I do disjuntor de S e R, a `FS`, em valor INSTANTÂNEO.

    `t_falta` não pode cair antes de ~0,12 s: o registro começa 0,1 s antes da
    falta, e os filtros do relé (o cosseno de um ciclo do .CEV) precisam de um
    ciclo de história. Antes disso o arquivo começaria com o filtro ENCHENDO —
    uma rampa que nenhum relé grava e que o detector lê, com razão, como falta.
    `duracao` padrão: até 0,27 s depois da falta.

    `abre_s`, `abre_r` e `extingue` são o COMANDO, em segundos depois do
    início da falta; cada polo (ou a própria falta, num arco que se apaga)
    abre no primeiro zero da sua corrente. `None`: não abre. Uma falta
    externa é eliminada por outro disjuntor — `extingue`, com S e R fechados.
    """
    r, sb, rb = _construir(cen)
    duracao = t_falta + 0.27 if duracao is None else duracao
    dt = 1.0 / FS
    n = len(r.conhecido)
    conhecido = np.array(r.conhecido)
    d, k = np.nonzero(~conhecido)[0], np.nonzero(conhecido)[0]
    ix = lambda nos: np.where(np.asarray(nos) < 0, n, np.asarray(nos))  # noqa: E731

    # Modelo companheiro dos ramos RL (trapézio): i = G·v + h.
    grupos = []
    for dim in (3, 1):
        ramos = [b for b in r.rl if len(b[0]) == dim]
        if not ramos:
            continue
        Z = np.array([b[2] for b in ramos])
        R, L = Z.real, Z.imag / W
        grupos.append({"de": np.array([ix(b[0]) for b in ramos]),
                       "ate": np.array([ix(b[1]) for b in ramos]),
                       "G": np.linalg.inv(R + 2 * L / dt), "K": 2 * L / dt - R, "Z": Z})
    nos_c = np.array([ix(c[0]) for c in r.cap]).reshape(-1, 3)
    C = np.array([c[1] for c in r.cap]).reshape(-1, 3, 3)
    Gc = 2 * C / dt
    n1 = np.array([ix([x[0]])[0] for x in r.res])
    n2 = np.array([ix([x[1]])[0] for x in r.res])
    Rr = np.array([x[2] for x in r.res])
    estado = np.array([x[4] for x in r.res])
    etiqueta = np.array([x[3] for x in r.res])

    def fatorar(estado):
        Y = np.zeros((n + 1, n + 1))
        for g in grupos:
            for b in range(g["de"].shape[0]):
                _carimbar(Y, g["de"][b], g["ate"][b], g["G"][b])
        for b in range(nos_c.shape[0]):
            _carimbar(Y, nos_c[b], np.full(3, n), Gc[b])
        for j in np.nonzero(estado)[0]:
            _carimbar(Y, [n1[j]], [n2[j]], np.array([[1.0 / Rr[j]]]))
        Y = Y[:n, :n] + 1e-9 * np.eye(n)      # nó isolado não singulariza
        return np.linalg.inv(Y[np.ix_(d, d)]), Y[np.ix_(d, k)]

    # Condição inicial: o regime de pré-falta (eficaz), um passo antes do zero.
    Vf = np.concatenate([_resolver(r, falta=False), [0]])
    inst = lambda X, t: math.sqrt(2) * np.real(X * np.exp(1j * W * t))  # noqa: E731
    v_1 = inst(Vf, -dt)
    ein = "bij,bj->bi"
    for g in grupos:
        i_1 = inst(np.einsum(ein, np.linalg.inv(g["Z"]), Vf[g["de"]] - Vf[g["ate"]]), -dt)
        g["h"] = np.einsum(ein, g["G"], v_1[g["de"]] - v_1[g["ate"]]
                           + np.einsum(ein, g["K"], i_1))
    hc = (np.einsum(ein, Gc, v_1[nos_c])
          + inst(np.einsum(ein, 1j * W * C, Vf[nos_c]), -dt))

    comandos = [(t_falta, "fecha", "falta")]
    for atraso, alvo in ((abre_s, "disjS"), (abre_r, "disjR"), (extingue, "falta")):
        if atraso is not None:
            comandos.append((t_falta + atraso, "abre", alvo))
    Yinv, Yuk = fatorar(estado)
    passos = int(round(duracao * FS))
    saida = np.zeros((12, passos))
    pendente = np.zeros(len(r.res), bool)     # polo esperando o zero
    sinal = np.zeros(len(r.res))
    V = np.zeros(n + 1)
    for p in range(passos):
        t = p * dt
        for cmd in [c for c in comandos if t >= c[0]]:
            comandos.remove(cmd)
            alvo = etiqueta == cmd[2]
            if cmd[1] == "fecha":
                estado = estado | alvo
                Yinv, Yuk = fatorar(estado)
            else:
                pendente |= alvo & estado
        for nos, fasores in r.fontes:
            V[nos] = inst(fasores, t)
        J = np.zeros(n + 1)
        for g in grupos:
            np.add.at(J, g["de"], -g["h"])
            np.add.at(J, g["ate"], g["h"])
        np.add.at(J, nos_c, hc)
        V[d] = Yinv @ (J[d] - Yuk @ V[k])
        V[n] = 0.0
        for g in grupos:
            vb = V[g["de"]] - V[g["ate"]]
            ib = np.einsum(ein, g["G"], vb) + g["h"]
            g["h"] = np.einsum(ein, g["G"], vb + np.einsum(ein, g["K"], ib))
        vc = V[nos_c]
        hc = 2 * np.einsum(ein, Gc, vc) - hc   # i_c = Gc·v − h; h' = Gc·v + i_c
        i_res = np.where(estado, (V[n1] - V[n2]) / Rr, 0.0)
        saida[0:3, p], saida[6:9, p] = V[sb], V[rb]
        saida[3:6, p] = i_res[etiqueta == "disjS"]
        saida[9:12, p] = i_res[etiqueta == "disjR"]
        if pendente.any():
            s = np.sign(i_res)
            zero = pendente & (sinal != 0) & (s != sinal)
            sinal = np.where(pendente & (s != 0), s, sinal)
            if zero.any():
                estado = estado & ~zero
                pendente &= ~zero
                Yinv, Yuk = fatorar(estado)
    return {"t": np.arange(passos) / FS, "x": saida, "t_falta": t_falta}


def regime(cen: Cenario, falta: bool = True) -> dict:
    """`{"VS", "IS", "VR", "IR"}` em fasor eficaz — para conferir o EMTP."""
    return _regime(*_construir(cen), falta=falta)


def t_da_incidencia(graus: float, delta: float = 15.0) -> float:
    """O primeiro instante depois de 0,13 s em que a tensão VA de S passa por `graus`.

    Com a falta entrando em 0° a DC é máxima numa fonte indutiva; em 90°,
    quase nenhuma.
    """
    fase0, alvo = math.radians(delta), math.radians(graus)
    k = math.ceil((0.13 * W + fase0 - alvo) / (2 * math.pi))
    return (alvo - fase0 + 2 * math.pi * k) / W


# ---------------------------------------------------------------------------
# O registro, como um relé gravaria
# ---------------------------------------------------------------------------

def _passa_baixas(x: np.ndarray, fc: float) -> np.ndarray:
    """Butterworth de 2ª ordem, causal — aplicado pela resposta ao impulso.

    A recorrência do filtro é rodada uma vez, num impulso, até a resposta cair
    abaixo de 1e-12 do pico; o sinal é filtrado por convolução. É o mesmo
    filtro, sem laço por amostra.
    """
    k = math.tan(math.pi * fc / FS)
    q = math.sqrt(2)
    nrm = 1 + q * k + k * k
    b0 = k * k / nrm
    b = (b0, 2 * b0, b0)
    a1, a2 = 2 * (k * k - 1) / nrm, (1 - q * k + k * k) / nrm
    h = np.zeros(400)
    y1 = y2 = 0.0
    for j in range(h.size):
        h[j] = (b[j] if j < 3 else 0.0) - a1 * y1 - a2 * y2
        y2, y1 = y1, h[j]
    h = h[: int(np.nonzero(np.abs(h) > 1e-12 * np.abs(h).max())[0][-1]) + 1]
    return np.array([np.convolve(linha, h)[: linha.size] for linha in x])


def _tc_saturado(i_sec: np.ndarray, carga_ohm: float, fluxo_joelho: float,
                 lm: float = 50.0, lsat: float = 1e-3) -> np.ndarray:
    """A corrente secundária de um TC com núcleo saturável (Euler implícito).

    `i_sec` já dividida pela relação; o fluxo `λ` integra `R·i2`, e acima do
    joelho a indutância de magnetização cai de `lm` para `lsat`.
    """
    g = carga_ohm / FS
    saida = np.empty_like(i_sec)
    lam = 0.0
    for j, ip in enumerate(i_sec):
        novo = (lam + g * ip) / (1 + g / lm)
        if abs(novo) > fluxo_joelho:
            s = math.copysign(1.0, novo)
            novo = (lam + g * (ip - s * fluxo_joelho / lm + s * fluxo_joelho / lsat)) \
                / (1 + g / lsat)
            novo = s * max(s * novo, fluxo_joelho)
            im = s * fluxo_joelho / lm + (novo - s * fluxo_joelho) / lsat
        else:
            im = novo / lm
        lam = novo
        saida[j] = ip - im
    return saida


@dataclass
class Formato:
    """Como o relé grava. `tipo`: «comtrade» ou «cev» (filtrado da SEL).

    `saturacao`: o fluxo de joelho em fração do fluxo da corrente SIMÉTRICA de
    falta `i_falta` (eficaz, primário) — abaixo de 1 o TC satura mesmo sem DC.
    """

    tipo: str = "comtrade"
    taxa: float = 2000.0           # comtrade 2000/1200; cev 480/240
    escala: str = "S"              # P ou S (o .CEV é sempre P)
    rtc: tuple = (600.0, 5.0)
    rtp: tuple = (138000.0, 115.0)
    fase_amostra: int = 0          # deslocamento da grade, em passos do EMTP
    pre_s: float = 0.1
    pos_s: float = 0.25
    erro_relogio_s: float = 0.0
    ruido: float = 2e-4            # fração do fundo de escala
    saturacao: float | None = None
    i_falta: float = 0.0
    inverte_i: bool = False
    troca_bc: bool = False
    seed: int = 0


def gravar(sim: dict, lado: str, fmt: Formato, trip_s: float | None = 0.025,
           nome: str = "SE") -> Record:
    """O `Record` do terminal `lado` («S» = IED A, «R» = IED B).

    `trip_s`: o digital TRIP sobe tanto DEPOIS do início da falta.
    """
    j0 = 0 if lado == "S" else 6
    v, i = sim["x"][j0:j0 + 3].copy(), sim["x"][j0 + 3:j0 + 6].copy()
    if fmt.inverte_i:
        i = -i
    if fmt.troca_bc:
        v, i = v[[0, 2, 1]], i[[0, 2, 1]]
    rtc, rtp = fmt.rtc[0] / fmt.rtc[1], fmt.rtp[0] / fmt.rtp[1]
    if fmt.saturacao:
        carga = 2.0
        joelho = fmt.saturacao * (fmt.i_falta * math.sqrt(2) / rtc) * carga / W
        i = np.array([_tc_saturado(f / rtc, carga, joelho) * rtc for f in i])
    rng = np.random.default_rng(fmt.seed)
    t_falta = sim["t_falta"]
    k0 = int(round((t_falta - fmt.pre_s) * FS))
    k1 = min(int(round((t_falta + fmt.pos_s) * FS)), sim["t"].size)
    passo = int(round(FS / fmt.taxa))
    idx = np.arange(k0 + fmt.fase_amostra, k1, passo)
    if fmt.tipo == "comtrade":
        dados = _passa_baixas(np.vstack([v, i]), 0.3 * fmt.taxa)[:, idx]
        if fmt.escala == "S":
            dados = dados / np.array([rtp] * 3 + [rtc] * 3)[:, None]
        fundo = np.max(np.abs(dados), axis=1, keepdims=True) * 1.05
        dados = dados + rng.normal(size=dados.shape) * fundo * fmt.ruido
        lsb = fundo / (2 ** 15 - 1)
        dados = np.round(dados / lsb) * lsb
        unidade_v, escala, filtragem = "V", fmt.escala, Filtering.BRUTO
    else:
        # O relatório filtrado da SEL: AA de 16 a/c, cosseno de um ciclo, e o
        # arquivo em valor EFICAZ — corrente em A inteiro truncado, tensão em
        # kV com duas casas. O leitor multiplica por √2; aqui também.
        n = int(round(FS / F0))
        nucleo = (2.0 / n) * np.cos(2 * np.pi * np.arange(n) / n)
        bruto = _passa_baixas(np.vstack([v, i]), 0.3 * 960)
        filtrado = np.array([np.convolve(s, nucleo)[: s.size] for s in bruto])[:, idx]
        ef = filtrado / math.sqrt(2)
        ef[:3] = np.round(ef[:3] / 1000.0, 2)
        ef[3:] = np.trunc(ef[3:])
        dados = ef * math.sqrt(2)
        unidade_v, escala, filtragem = "kV", "P", Filtering.FILTRADO
    n = dados.shape[1]
    tempo = np.arange(n) / fmt.taxa
    canais = [AnalogChannel(index=k, name=f"V{f}Y", unit=unidade_v, phase=f,
                            primary=fmt.rtp[0], secondary=fmt.rtp[1], scaling=escala)
              for k, f in enumerate("ABC")]
    canais += [AnalogChannel(index=3 + k, name=f"I{f}W", unit="A", phase=f,
                             primary=fmt.rtc[0], secondary=fmt.rtc[1], scaling=escala)
               for k, f in enumerate("ABC")]
    t_inicio = sim["t"][idx[0]]
    inicio = datetime(2026, 10, 24, 3, 0, 0) + timedelta(seconds=t_inicio
                                                         + fmt.erro_relogio_s)
    status = np.zeros((1, n), dtype=np.int8)
    disparo = None
    if trip_s is not None:
        tt = t_falta + trip_s - t_inicio
        status[0, tempo >= tt] = 1
        disparo = inicio + timedelta(seconds=tt)
    return Record(source=None, format_name=fmt.tipo, station=nome, device_id=nome,
                  line_frequency=F0, start_time=inicio, trigger_time=disparo,
                  analog_channels=tuple(canais),
                  status_channels=(StatusChannel(index=0, name="TRIP"),),
                  sample_rates=(SampleRate(rate_hz=fmt.taxa, last_sample=n),),
                  analog=dados, status=status, time=tempo,
                  filtering=filtragem, filtering_source=FilteringSource.DECLARADO)


def corrente_de_falta(cen: Cenario, lado: str = "S") -> float:
    """O maior eficaz de fase no disjuntor durante a falta, em primário."""
    return float(np.abs(regime(cen)[f"I{lado}"]).max())
