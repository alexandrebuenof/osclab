"""Localização de falta por SEQUÊNCIA NEGATIVA, dois terminais, sem sincronismo.

## A ideia

A tensão de sequência negativa NO PONTO DA FALTA é uma só. Ela pode ser
calculada a partir de S, descendo a linha com a corrente de S, ou a partir de
R, com a corrente de R — e a falta está onde as duas dão o mesmo MÓDULO:

    |V2S − m·Z2L·I2S|  =  |V2R − (1−m)·Z2L·I2R|

`m` é a posição em pu da linha, a partir de S, e `Z2L` a impedância de
sequência negativa da linha inteira (= Z1 numa linha transposta). Ao quadrado,
os dois lados viram `A·m² + B·m + C = 0`.

**Não precisa de sincronismo:** de cada terminal só entra o ângulo de I2
contra o V2 DO MESMO terminal. Os dois lados da igualdade são módulos, e girar
um terminal inteiro não muda módulo nenhum.

## A planilha que isto substitui

É a conta da `LocDef_SeqNeg.xls` da distribuidora, com os mesmos nomes
(`a`…`h`, `A`, `B`, `C`, `m1`, `m2`). A planilha tem um erro na célula C72:
o primeiro numerador usa `B²` onde deveria usar `−B`, e é daí que sai a «raiz
irreal» da casa dos milhões. A segunda raiz está certa. Conferido em
22/10/2026 contra o caso COXIPO – BARRO DURO da própria planilha: m2 =
0,006230, 0,058 km de COXIPO, e os dois lados da igualdade fecham.

## Unidades

Tudo em PRIMÁRIO: volt, ampère e ohm da linha. Misturar secundário de um lado
e primário do outro dá um número na ordem de grandeza certa e errado —
quem garante a base é `fasores_de`, que converte pelo TC/TP declarado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from osclab.dsp import fasor as fasor_mod
from osclab.dsp import simetricas
from osclab.formats import conjuntos
from osclab.formats.base import Record
from osclab.plot import conversao, unidades

#: Folga nas bordas da linha: um m de −0,01 é a falta no barramento de S lida
#: com o erro de medida, não falta externa.
FOLGA = 0.02


@dataclass(frozen=True)
class Resultado:
    m1: float
    m2: float
    #: A raiz que cai na linha, ou `None` (nenhuma, ou as duas).
    m: float | None
    A: float
    B: float
    C: float
    delta: float

    def para_json(self) -> dict:
        return {"m1": self.m1, "m2": self.m2, "m": self.m, "A": self.A,
                "B": self.B, "C": self.C, "delta": self.delta}


def localizar(v2s: complex, i2s: complex, v2r: complex, i2r: complex,
              z2l: complex) -> Resultado | None:
    """As duas raízes de `A·m² + B·m + C = 0` e a que cai na linha.

    `None` quando a conta não tem solução real (Δ < 0) ou degenera (A = 0):
    corrente zero num dos lados, ou linha sem impedância.
    """
    if abs(i2s) == 0 or abs(i2r) == 0 or abs(z2l) == 0:
        return None
    # Os nomes da planilha: a+jb = I2S·Z2S = −V2S; c+jd = I2S·Z2L;
    # e+jf = Z2R + Z2L, com Z2R = −V2R/I2R; g+jh = Z2L.
    ab = -v2s
    cd = i2s * z2l
    ef = -v2r / i2r + z2l
    gh = z2l
    quadrado = abs(i2r) ** 2
    A = quadrado * abs(gh) ** 2 - abs(cd) ** 2
    B = (-2 * quadrado * (ef.real * gh.real + ef.imag * gh.imag)
         - 2 * (ab.real * cd.real + ab.imag * cd.imag))
    C = quadrado * abs(ef) ** 2 - abs(ab) ** 2
    delta = B * B - 4 * A * C
    if A == 0 or delta < 0 or not math.isfinite(delta):
        return None
    raiz = math.sqrt(delta)
    # A forma ESTÁVEL de Bhaskara: `(−B ± √Δ)/2A` subtrai dois números quase
    # iguais numa das raízes quando 4AC ≪ B², e a raiz perde algarismos (numa
    # rede simétrica, 0,50526 onde a resposta é 0,500000 — validação
    # independente, 24/10/2026). `q = −(B + sgn(B)·√Δ)/2` dá as duas sem isso.
    q = -0.5 * (B + math.copysign(raiz, B))
    if q == 0:
        return None
    m1, m2 = (C / q, q / A) if B >= 0 else (q / A, C / q)
    boas = [m for m in (m1, m2) if -FOLGA <= m <= 1 + FOLGA]
    return Resultado(m1=m1, m2=m2, m=boas[0] if len(boas) == 1 else None,
                     A=A, B=B, C=C, delta=delta)


# ---------------------------------------------------------------------------
# V2 e I2 de um registro, em primário
# ---------------------------------------------------------------------------

def _fasor(registro: Record, canal: int, n: int) -> complex | None:
    """O fasor (eficaz) do ciclo que TERMINA na amostra `n`.

    A taxa é a do TRECHO que contém `n` (`Record.trechos`), e não
    `sample_rates[0]`: esta vale 0 num `.cfg` com `nrates = 0` (SEL-751,
    311C) e erra a janela num registro de taxa múltipla. Janela que
    atravessa a fronteira entre dois trechos não é um ciclo: `None`.
    """
    n = int(n)
    trecho = next((t for t in registro.trechos if t.inicio <= n < t.fim), None)
    if trecho is None:
        return None
    por_ciclo = fasor_mod.ciclo_em_amostras(trecho.taxa_hz, registro.line_frequency)
    if por_ciclo < fasor_mod.MINIMO_POR_CICLO:
        return None
    pesos = fasor_mod.pesos_do_ciclo(por_ciclo)
    inicio = n - pesos.size + 1
    if inicio < trecho.inicio or n + 1 > registro.analog.shape[1]:
        return None
    f = fasor_mod.de_janela(registro.analog[canal, inicio:int(n) + 1],
                            por_ciclo, pesos)
    if f is None:
        return None
    return f.fundamental * complex(math.cos(math.radians(f.angulo)),
                                   math.sin(math.radians(f.angulo)))


def _em_primario(registro: Record, canal: int, valor: complex) -> complex | None:
    """Volt e ampère primários: TC/TP declarado e prefixo `k` tirado.

    `None` quando o canal está em secundário e o arquivo não declara a
    relação — sem ela, não se converte (ver o CLAUDE.md).
    """
    c = registro.analog_channels[canal]
    fator = unidades.fator_do_prefixo(c.unit)[0]
    if not c.is_primary:
        razao = conversao.relacao(c)
        if razao <= 1.0:
            return None
        fator *= razao
    return valor * fator


def fasores_de(registro: Record, amostra: int) -> dict:
    """`{"v2", "i2", "aviso"}` na amostra, em primário.

    Usa a PRIMEIRA trinca de tensão e a primeira de corrente com sinal. A
    tensão tem de ser de FASE: de trinca fase-fase o V2 sai girado de 30° e
    multiplicado por √3, e a conta erraria sem aviso.
    """
    achados = [c for c in conjuntos.de_registro(registro)
               if not c.sem_sinal and not c.e_de_linha]
    corrente = next((c for c in achados if c.grandeza == "I"), None)
    tensao = next((c for c in achados if c.grandeza == "V"), None)
    if corrente is None or tensao is None:
        return {"v2": None, "i2": None,
                "aviso": "o registro não tem trinca de tensão de FASE e de corrente"}

    def sequencia(conj) -> complex | None:
        fasores = []
        for fase in "ABC":
            bruto = _fasor(registro, conj.canais[fase], amostra)
            if bruto is None:
                return None
            primario = _em_primario(registro, conj.canais[fase], bruto)
            if primario is None:
                return None
            fasores.append(primario)
        return simetricas.de_fasores(*fasores)[2]

    v2, i2 = sequencia(tensao), sequencia(corrente)
    aviso = ""
    if v2 is None or i2 is None:
        aviso = ("sem relação de TC/TP declarada, ou o cursor está no primeiro "
                 "ciclo do registro")
    return {"v2": v2, "i2": i2, "aviso": aviso,
            "canais_v": [registro.analog_channels[tensao.canais[f]].name for f in "ABC"],
            "canais_i": [registro.analog_channels[corrente.canais[f]].name for f in "ABC"]}


# ---------------------------------------------------------------------------
# A linha: de onde vêm Z2L e o comprimento
# ---------------------------------------------------------------------------

#: A ordem das fontes, pedida por ele em 22/10/2026: a base de dados, os
#: ajustes do IED A, os do IED B e, em último caso, o que se digita.
FONTES = ("base", "A", "B", "manual")


def _numero(bruto) -> float | None:
    try:
        valor = float(str(bruto).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return valor if math.isfinite(valor) else None


#: Quilômetros por milha: o `LLUNIT` do 411L diz `MI` em parte do parque.
KM_POR_MILHA = 1.609344


def _comprimento(ajustes: dict[str, str]) -> tuple[float | None, str]:
    """O comprimento da linha em km, e o nome do ajuste de onde saiu.

    No SEL-411L o `LL` do `.HDR` é ajuste OCULTO, o padrão de fábrica 100,00;
    o comprimento de verdade é o `LLR`, na unidade do `LLUNIT` (`MI` ou `KM`).
    Ler o `LL` ali poria a falta a uma fração de uma linha de 100 km que não
    existe. Sem `LLR`, vale o `LL` — o do 421, do 451 e do 311C.
    """
    llr = _numero(ajustes.get("LLR"))
    if llr and llr > 0:
        unidade = str(ajustes.get("LLUNIT", "")).strip().upper()
        if unidade in ("MI", "MILE", "MILES"):
            return llr * KM_POR_MILHA, "LLR (mi)"
        return llr, "LLR"
    return _numero(ajustes.get("LL")), "LL"


def linha_dos_ajustes(ajustes: dict[str, str], rtp_rtc: float | None) -> dict:
    """`Z1MAG`/`Z1ANG`/`LL` do relé, levados a ohm PRIMÁRIO.

    O ajuste da SEL é secundário; sem `RTP/RTC` não há como passar para
    primário, e a fonte é recusada com o motivo — não se converte por palpite.
    """
    modulo = _numero(ajustes.get("Z1MAG"))
    angulo = _numero(ajustes.get("Z1ANG"))
    km, nome_km = _comprimento(ajustes)
    if modulo is None or angulo is None or not modulo:
        return {"ok": False, "motivo": "o arquivo não traz Z1MAG e Z1ANG"}
    if not km or km <= 0:
        return {"ok": False, "motivo": "o arquivo não traz o comprimento (LL)"}
    if not rtp_rtc:
        return {"ok": False,
                "motivo": "Z1MAG é secundário e falta RTP/RTC para passar a primário"}
    z = modulo * rtp_rtc * complex(math.cos(math.radians(angulo)),
                                    math.sin(math.radians(angulo)))
    saida = {"ok": True, "r": z.real, "x": z.imag, "km": km,
             "como": (f"Z1MAG {modulo:g} Ω sec ∠ Z1ANG {angulo:g}° × RTP/RTC "
                      f"{rtp_rtc:g}; {nome_km} {km:g} km").replace(".", ",")}
    # O Z0 é opcional: a seq. negativa não usa, o laço de terra precisa (k0).
    mod0, ang0 = _numero(ajustes.get("Z0MAG")), _numero(ajustes.get("Z0ANG"))
    if mod0 and ang0 is not None:
        z0 = mod0 * rtp_rtc * complex(math.cos(math.radians(ang0)),
                                      math.sin(math.radians(ang0)))
        saida.update(r0=z0.real, x0=z0.imag)
        saida["como"] += f"; Z0MAG {mod0:g} ∠ Z0ANG {ang0:g}°".replace(".", ",")
    # A capacitância (`b1`/`b0`) NÃO sai daqui: nenhum ajuste do parque a traz
    # com nome que se possa ler sem palpite. Vem da base ou do que se digita;
    # sem ela, a seq. negativa fica na linha concentrada.
    return saida


def linha_digitada(manual: dict | None, rtp_rtc: float | None) -> dict:
    """O que se digitou: `R + jX` total, ou `|Z| ∠ θ`, ou por km.

    `base` diz se o número é primário ou secundário; secundário só vale com
    RTP/RTC do registro.
    """
    m = manual or {}
    km = _numero(m.get("km"))
    if not km or km <= 0:
        return {"ok": False, "motivo": "digite o comprimento da linha"}
    forma = str(m.get("forma") or "rx")
    z = None
    if forma == "rx":
        r, x = _numero(m.get("r")), _numero(m.get("x"))
        if r is not None and x is not None:
            z = complex(r, x)
    elif forma == "pol":
        mod, ang = _numero(m.get("mod")), _numero(m.get("ang"))
        if mod is not None and ang is not None:
            z = mod * complex(math.cos(math.radians(ang)), math.sin(math.radians(ang)))
    elif forma == "km":
        r, x = _numero(m.get("rkm")), _numero(m.get("xkm"))
        if r is not None and x is not None:
            z = complex(r, x) * km
    if z is None or abs(z) == 0:
        return {"ok": False, "motivo": "digite a impedância da linha"}
    # O Z0, na mesma forma e na mesma base do Z1. Opcional.
    z0 = None
    if forma == "rx":
        r0, x0 = _numero(m.get("r0")), _numero(m.get("x0"))
        z0 = complex(r0, x0) if r0 is not None and x0 is not None else None
    elif forma == "pol":
        mod0, ang0 = _numero(m.get("mod0")), _numero(m.get("ang0"))
        if mod0 is not None and ang0 is not None:
            z0 = mod0 * complex(math.cos(math.radians(ang0)), math.sin(math.radians(ang0)))
    elif forma == "km":
        r0, x0 = _numero(m.get("r0km")), _numero(m.get("x0km"))
        z0 = complex(r0, x0) * km if r0 is not None and x0 is not None else None
    if z0 is not None and abs(z0) == 0:
        z0 = None
    # A susceptância shunt (µS), OPCIONAL: da linha inteira em `rx`/`pol`, por
    # km em `km`. Com ela a seq. negativa usa a linha DISTRIBUÍDA; sem ela, a
    # concentrada — a capacitância não se inventa.
    sufixo, escala_km = ("km", km) if forma == "km" else ("", 1.0)
    b1, b0 = (_numero(m.get(f"b1{sufixo}")), _numero(m.get(f"b0{sufixo}")))
    b1 = b1 * escala_km if b1 is not None and b1 > 0 else None
    b0 = b0 * escala_km if b0 is not None and b0 > 0 else None
    if str(m.get("base") or "prim") == "sec":
        if not rtp_rtc:
            return {"ok": False,
                    "motivo": "em secundário precisa de RTP/RTC, e o registro não declara"}
        z *= rtp_rtc
        z0 = None if z0 is None else z0 * rtp_rtc
        # Admitância vai ao contrário da impedância: Y_prim = Y_sec / (RTP/RTC).
        b1 = None if b1 is None else b1 / rtp_rtc
        b0 = None if b0 is None else b0 / rtp_rtc
    saida = {"ok": True, "r": z.real, "x": z.imag, "km": km, "como": "digitado"}
    if z0 is not None:
        saida.update(r0=z0.real, x0=z0.imag)
    if b1 is not None:
        saida["b1"] = b1
    if b0 is not None:
        saida["b0"] = b0
    return saida


# ---------------------------------------------------------------------------
# O pacote da tela
# ---------------------------------------------------------------------------

def _polar(z: complex | None) -> dict | None:
    if z is None:
        return None
    return {"mod": abs(z), "ang": math.degrees(math.atan2(z.imag, z.real))}


def _amostra(registro: Record, t: float) -> int:
    import numpy as np
    tempo = registro.time
    i = int(np.searchsorted(tempo, t))
    if i >= tempo.size:
        return tempo.size - 1
    if i > 0 and abs(tempo[i - 1] - t) <= abs(tempo[i] - t):
        return i - 1
    return i


def montar(terminais: list[dict], fontes: dict, pedida: str, s: str) -> dict:
    """Junta tudo: `terminais` = `[{letra, nome, registro, t}]`, já no tempo
    de cada registro; `fontes` = `{base, A, B, manual}`, cada uma `{ok, …}`.

    `pedida` é a fonte que o usuário escolheu, ou `auto` — a primeira que
    estiver `ok` na ordem de `FONTES`. `s` é a letra do IED que faz o papel
    de terminal S.
    """
    medidos = []
    for term in terminais:
        n = _amostra(term["registro"], term["t"])
        f = fasores_de(term["registro"], n)
        medidos.append({"letra": term["letra"], "nome": term["nome"],
                        "v2": f["v2"], "i2": f["i2"], "aviso": f["aviso"],
                        "canais_v": f.get("canais_v", []),
                        "canais_i": f.get("canais_i", [])})

    usada = None
    if pedida in FONTES and fontes.get(pedida, {}).get("ok"):
        usada = pedida
    elif pedida == "auto":
        usada = next((f for f in FONTES if fontes.get(f, {}).get("ok")), None)

    pacote = {
        "terminais": [{**{k: v for k, v in t.items() if k not in ("v2", "i2")},
                       "v2": _polar(t["v2"]), "i2": _polar(t["i2"])} for t in medidos],
        "fontes": fontes, "fonte": usada, "pedida": pedida, "s": s,
        "resultado": None, "aviso": "",
    }
    por_letra = {t["letra"]: t for t in medidos}
    r_letra = next((t["letra"] for t in medidos if t["letra"] != s), None)
    lado_s, lado_r = por_letra.get(s), por_letra.get(r_letra)
    if lado_s is None or lado_r is None:
        pacote["aviso"] = "precisa de dois IEDs na aba, um em cada terminal"
        return pacote
    pacote["r"] = r_letra
    if usada is None:
        pacote["aviso"] = "falta o parâmetro da linha"
        return pacote
    if None in (lado_s["v2"], lado_s["i2"], lado_r["v2"], lado_r["i2"]):
        pacote["aviso"] = lado_s["aviso"] or lado_r["aviso"] or "sem V2/I2 no cursor"
        return pacote
    linha = fontes[usada]
    z2l = complex(linha["r"], linha["x"])
    res = localizar(lado_s["v2"], lado_s["i2"], lado_r["v2"], lado_r["i2"], z2l)
    if res is None:
        pacote["aviso"] = "a equação não tem solução real com estes valores"
        return pacote
    km = linha["km"]
    pacote["resultado"] = {**res.para_json(), "km": km,
                           "km_de_s": None if res.m is None else res.m * km,
                           "km_de_r": None if res.m is None else (1 - res.m) * km}
    return pacote
