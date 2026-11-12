"""O «refinar» da localização por sequência negativa de dois terminais.

Escolhido pelo Alexandre em 11/11/2026 (variante 11 da maquete, ramo
`maquete/refino`). O painel localizador dá o km da seq. negativa com os dois
registros alinhados pelo início da falta de cada um; o refino deixa CONFERIR
esse alinhamento e o número:

* o deslocamento `d` de B — o instante `t` de A cai em `t + d` em B —, que
  vem AUTOMÁTICO (`plot/alinhamento.deslocamento`, pelo início da falta, o
  mesmo do resto da aba) ou MANUAL: um número, ou dois pontos marcados (o
  início da falta em A e em B). O manual cai sempre numa amostra de B:
  entre duas amostras não há medida;
* uma SEGUNDA OPINIÃO sobre o `d`, independente do detector de início: a
  correlação das envoltórias |I2| de A e de B em volta da falta de A. Quando
  as duas discordam em mais de ¼ de ciclo, a tela avisa — avisa, não troca;
* V2, I2 e o ângulo de I2 contra o V2 do MESMO terminal, num instante, e o km
  pela conta da LocDef (`seqneg.localizar`; com B1 da linha, a distribuída de
  `ldl.seqneg_distribuida`). Cada número diz a origem: lido, digitado, ou
  tirado da impedância de fonte atrás do terminal (`V2 = −Z2fonte·I2`) — o
  caminho de um terminal que não grava tensão;
* a curva do km no tempo com o `d` em uso, e a mediana dela no platô.

**O deslocamento escolhido aqui VALE para o painel** (decidido pelo
Alexandre em 11/11/2026): o manual — arrastado, marcado ou o «usar» da
correlação — passa a ser o `d` do painel localizador, que o diz com o selo
«alinhado à mão». Fica GRAVADO ao lado do registro, como a correção de fase
(`acervo.gravar_refino`, um `refino.json` na pasta de A chaveado pelo sha de
B; o par visto de B lê `−d`): reabrir dá o mesmo km, o Ctrl+Z não o desfaz, e
voltar ao automático no refino o apaga. A conta do `d` do painel é
`deslocamento_do_painel`.

Tudo em PRIMÁRIO e em fasor EFICAZ, como em `ldl.py`.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

import numpy as np

from osclab.faultloc import ldl, seqneg
from osclab.formats import conjuntos
from osclab.formats.base import Filtering, Record
from osclab.plot import alinhamento

#: Até onde a correlação procura, em ciclos, para cada lado do automático.
CICLOS_DE_BUSCA = 6.0
#: Discordância entre o automático e a correlação que vira aviso, em ciclos.
#: A correlação erra ~3 ms quando os disjuntores dos dois lados abrem em
#: tempos diferentes (a descida da envoltória entra na conta): abaixo de ¼ de
#: ciclo, não se avisa.
DISCORDANCIA_EM_CICLOS = 0.25
#: A curva do km só vale onde há I2 nos dois lados: abaixo desta fração do
#: maior |I2| de cada terminal a conta divide ruído por ruído.
FRACAO_MINIMA_DE_I2 = 0.05


# ---------------------------------------------------------------------------
# Um terminal
# ---------------------------------------------------------------------------

@dataclass
class Lado:
    """O que um registro entrega ao refino: fasores, ondas e a grade."""

    letra: str
    nome: str
    registro: Record
    v: dict | None          # fasor eficaz primário por fase (V)
    i: dict | None          # (A)
    v2: np.ndarray | None
    i2: np.ndarray | None
    inst_v: list | None     # instantâneo primário por fase, em kV
    inst_i: list | None     # em A
    nomes_v: list
    nomes_i: list
    passo: float            # intervalo entre amostras (s)
    taxa: float
    por_ciclo: float
    filtrado: bool
    aviso: str


def _trincas(registro: Record):
    """A primeira trinca de tensão de FASE e a primeira de corrente, com sinal.

    A escolha é a mesma de `ldl.terminal` — o número do refino e o do painel
    saem dos mesmos canais. A diferença é que aqui cada trinca vale sozinha: um
    terminal sem tensão continua dando I2 (e a tela pede V2 de outro jeito).
    """
    achados = [c for c in conjuntos.de_registro(registro)
               if not c.sem_sinal and not c.e_de_linha]
    return (next((c for c in achados if c.grandeza == "V"), None),
            next((c for c in achados if c.grandeza == "I"), None))


def lado(registro: Record, letra: str, nome: str) -> Lado:
    tv, ti = _trincas(registro)

    def nomes(conj):
        return [registro.analog_channels[conj.canais[f]].name for f in "ABC"]

    def inst(conj, divisor):
        # canais[fase]: a fase pelo VÍNCULO do canal, nunca pela posição
        if conj is None:
            return None
        saida = []
        for f in "ABC":
            fator = ldl._fator_primario(registro, conj.canais[f])
            if fator is None:
                return None
            saida.append(registro.analog[conj.canais[f]] * (fator / divisor))
        return saida

    v = ldl._trinca(registro, tv) if tv is not None else None
    i = ldl._trinca(registro, ti) if ti is not None else None
    aviso = ""
    if tv is None:
        aviso = "não grava tensão de fase"
    elif v is None:
        aviso = "sem relação de TP declarada"
    if ti is None or i is None:
        aviso = (aviso + "; " if aviso else "") + "sem corrente utilizável"
    taxas = [t.taxa_hz for t in registro.trechos if t.taxa_hz > 0]
    taxa = max(taxas) if taxas else float(registro.base_rate_hz or 0.0)
    passo = float(np.median(np.diff(registro.time))) if registro.time.size > 1 else 1e-3
    return Lado(letra=letra, nome=nome, registro=registro, v=v, i=i,
                v2=ldl.seq2(v) if v is not None else None,
                i2=ldl.seq2(i) if i is not None else None,
                inst_v=inst(tv, 1000.0), inst_i=inst(ti, 1.0),
                nomes_v=nomes(tv) if tv is not None else [],
                nomes_i=nomes(ti) if ti is not None else [],
                passo=passo, taxa=taxa,
                por_ciclo=taxa / (registro.line_frequency or 60.0),
                filtrado=registro.filtering == Filtering.FILTRADO, aviso=aviso)


def ciclo(ld: Lado) -> float:
    return 1.0 / (ld.registro.line_frequency or 60.0)


def amostra(tempo: np.ndarray, t: float) -> int:
    """A amostra mais perto de `t` (sem interpolar)."""
    i = int(np.clip(np.searchsorted(tempo, t), 0, tempo.size - 1))
    if i > 0 and abs(tempo[i - 1] - t) <= abs(tempo[i] - t):
        i -= 1
    return i


# ---------------------------------------------------------------------------
# O alinhamento
# ---------------------------------------------------------------------------

def no_grid(d: float, passo: float) -> float:
    """O `d` numa amostra de B: múltiplo do intervalo de B."""
    return round(d / passo) * passo if passo > 0 else d


def correlacao(a: Lado, b: Lado, d_centro: float) -> dict | None:
    """A segunda opinião: correlação de |I2| de A e de B, por deslocamento.

    O trecho de A vai de 2 ciclos antes do início da falta DELE a 7 depois —
    a subida e a descida da envoltória, as partes de forma marcada. O pico é o
    `d` em que B tem a mesma forma. Não depende do detector de início de B,
    que é justamente o que erra quando B começa a gravar com a falta já em
    curso (o caso R2 da maquete: o automático cai no disparo e erra 40 ms).

    Um laço por DESLOCAMENTO (~10² candidatos), cada um vetorizado.
    """
    if a.i2 is None or b.i2 is None:
        return None
    t0 = alinhamento.instante_da_falta(a.registro)
    if t0 is None:
        return None
    um = ciclo(a)
    ta = a.registro.time
    janela = (ta >= t0 - 2 * um) & (ta <= t0 + 7 * um)
    env_a = np.abs(a.i2[janela])
    ok_a = np.isfinite(env_a)
    if ok_a.sum() < 8:
        return None
    passo = b.passo
    n = int(CICLOS_DE_BUSCA * um / passo)
    ds = no_grid(d_centro, passo) + passo * np.arange(-n, n + 1)
    env_b = np.abs(b.i2)
    rs = np.full(ds.size, np.nan)
    for k, d in enumerate(ds):
        idx = ldl._mais_proximas(b.registro.time, ta[janela] + d)
        eb = np.where(idx >= 0, env_b[np.clip(idx, 0, env_b.size - 1)], np.nan)
        ok = ok_a & np.isfinite(eb)
        if ok.sum() < 0.5 * ok_a.sum():
            continue
        x, y = env_a[ok] - env_a[ok].mean(), eb[ok] - eb[ok].mean()
        den = math.sqrt(float((x * x).sum() * (y * y).sum()))
        rs[k] = float((x * y).sum()) / den if den > 0 else np.nan
    if not np.isfinite(rs).any():
        return None
    k = int(np.nanargmax(rs))
    return {"d": float(ds[k]), "r": float(rs[k])}


def alinhar(a: Lado, b: Lado, modo: str, manual: dict | None) -> dict:
    """O `d` em uso, o automático, a correlação e as marcas do manual.

    `manual` = `{"d": s}` (um número) ou `{"ta": s, "tb": s}` (o mesmo ponto
    marcado em A e em B, cada um no tempo do próprio registro); uma marca
    sozinha é guardada e devolvida, mas não alinha nada ainda.
    """
    auto = alinhamento.deslocamento(a.registro, b.registro, "falta")
    corr = correlacao(a, b, auto["d"])
    um = ciclo(a)
    confere = None
    if corr is not None:
        dif = corr["d"] - auto["d"]
        # um terminal filtrado pelo relé (.CEV) e o outro bruto: a envoltória
        # do filtrado chega até um ciclo DEPOIS, e a correlação mede esse
        # atraso junto — mostra-se, mas não vira aviso
        mistura = a.filtrado != b.filtrado
        confere = {"d": corr["d"], "r": corr["r"], "dif": dif, "mistura": mistura,
                   "discorda": (not mistura) and abs(dif) > DISCORDANCIA_EM_CICLOS * um}
    m = manual or {}
    d_manual, marcas = None, None

    def numero(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return v if math.isfinite(v) else None
    ta, tb, dm = numero(m.get("ta")), numero(m.get("tb")), numero(m.get("d"))
    if ta is not None:
        ta = float(a.registro.time[amostra(a.registro.time, ta)])
    if tb is not None:
        tb = float(b.registro.time[amostra(b.registro.time, tb)])
    if ta is not None and tb is not None:
        d_manual, marcas = tb - ta, {"ta": ta, "tb": tb}
    else:
        if dm is not None:
            d_manual = no_grid(dm, b.passo)
        if ta is not None or tb is not None:
            marcas = {"ta": ta, "tb": tb}
    usado = auto["d"] if (modo != "manual" or d_manual is None) else d_manual
    return {"auto": auto, "confere": confere, "manual": {"d": d_manual, "marcas": marcas},
            "modo": "manual" if modo == "manual" else "auto", "d": usado,
            "passo_a": a.passo, "passo_b": b.passo, "ciclo": um}


def deslocamento_do_painel(reg_b: Record, d_auto: float, pedido) -> dict:
    """O `d` do painel localizador: o da aba, ou o MANUAL escolhido no refino.

    `pedido` é o número (s) que a tela mandou — `None` quando o refino está no
    automático. O manual cai na grade de B (`no_grid`), como no refino: o
    painel e a janela usam o MESMO `d`, e o km dos dois é o mesmo. Um pedido
    que não é número finito é ignorado (vale o automático), e o painel não
    diz «alinhado à mão».
    """
    try:
        dm = float(pedido) if pedido is not None else None
    except (TypeError, ValueError):
        dm = None
    if dm is None or not math.isfinite(dm):
        return {"d": d_auto, "manual": False, "auto": d_auto}
    t = reg_b.time
    passo = float(np.median(np.diff(t))) if t.size > 1 else 1e-3
    return {"d": no_grid(dm, passo), "manual": True, "auto": d_auto}


# ---------------------------------------------------------------------------
# A leitura num instante, e o km
# ---------------------------------------------------------------------------

def _ajeita(g: float) -> float:
    g = (g + 180.0) % 360.0 - 180.0
    return 180.0 if g == -180.0 else g


def _num(x) -> float | None:
    try:
        v = float(str(x).strip().replace(",", ".").replace("−", "-"))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def valores(ld: Lado, n: int | None, digitado: dict | None) -> dict:
    """|V2| (kV), |I2| (A) e ∠I2−∠V2 (°) de um terminal, cada um com a ORIGEM.

    V2 é a referência (0°) do próprio terminal: só o ângulo RELATIVO entra na
    conta, e é por isso que ela não precisa de sincronismo. `digitado` pode
    trazer `v2` (kV), `i2` (A), `ang` (°) — que valem no lugar do lido, em
    todos os instantes — ou `z2f_mod`/`z2f_ang`, a impedância de sequência
    negativa da fonte atrás do terminal (ohm primário), de onde sai
    `V2 = −Z2f·I2`: com I2 a 0°, V2 fica a θ+180°, e o ângulo de I2 contra V2
    é −(θ+180°).
    """
    dg = digitado or {}
    v2 = i2 = None
    if n is not None and n >= 0:
        if ld.v2 is not None and math.isfinite(abs(ld.v2[n])):
            v2 = complex(ld.v2[n])
        if ld.i2 is not None and math.isfinite(abs(ld.i2[n])):
            i2 = complex(ld.i2[n])
    lido = {"v2": abs(v2) / 1000.0 if v2 is not None else None,
            "i2": abs(i2) if i2 is not None else None,
            "ang": (_ajeita(math.degrees(cmath.phase(i2) - cmath.phase(v2)))
                    if v2 is not None and i2 is not None and abs(v2) > 0 and abs(i2) > 0
                    else None)}
    saida = dict(lido)
    origem = {k: ("lido" if lido[k] is not None else "") for k in lido}
    for k in ("v2", "i2", "ang"):
        x = _num(dg.get(k))
        if x is not None:
            saida[k], origem[k] = x, "digitado"
    z2f_mod, z2f_ang = _num(dg.get("z2f_mod")), _num(dg.get("z2f_ang"))
    if z2f_mod and z2f_ang is not None and saida["i2"] is not None \
            and origem["v2"] != "digitado":
        saida["v2"] = z2f_mod * saida["i2"] / 1000.0
        saida["ang"] = _ajeita(-(z2f_ang + 180.0))
        origem["v2"] = origem["ang"] = "fonte"
    return {**saida, "origem": origem, "lido": lido}


def _complexos(val: dict) -> tuple[complex, complex] | None:
    if val["v2"] is None or val["i2"] is None or val["ang"] is None:
        return None
    return (complex(val["v2"] * 1000.0, 0.0),
            val["i2"] * cmath.exp(1j * math.radians(val["ang"])))


def km_no_instante(va: dict, vb: dict, linha: dict | None, s: str) -> dict:
    """O km pela seq. negativa a partir do terminal `s`, com os valores dados.

    `linha` = `{r, x, km, b1?, perfil?}` (ohm primário da linha inteira; Z2L =
    Z1L numa linha transposta). Com B1 a conta é a distribuída; com perfil
    (linha em trechos), a fração vira km pelo perfil, como no painel.
    """
    if not linha:
        return {"km": None, "motivo": "falta o parâmetro da linha"}
    ca, cb = _complexos(va), _complexos(vb)
    if ca is None or cb is None:
        sem_v = [x for x, c, v in (("A", ca, va), ("B", cb, vb))
                 if c is None and v["v2"] is None]
        if sem_v:
            return {"km": None, "motivo": f"falta V2 de {' e '.join(sem_v)}: digite V2, ou a "
                                          "impedância de fonte atrás do terminal"}
        falta = [x for x, c in (("A", ca), ("B", cb)) if c is None]
        return {"km": None, "motivo": f"falta V2/I2 de {' e '.join(falta)} neste instante"}
    z = complex(linha["r"], linha["x"])
    total = float(linha["km"])
    res = seqneg.localizar(*ca, *cb, z)
    if res is None:
        return {"km": None, "motivo": "a equação não tem solução real com estes valores"}
    m = res.m
    modelo = "concentrada"
    b1 = linha.get("b1")
    if m is not None and b1:
        md = ldl.seqneg_distribuida(np.array([ca[0]]), np.array([ca[1]]), np.array([cb[0]]),
                                    np.array([cb[1]]), z, float(b1) * 1e-6, np.array([m]))
        if math.isfinite(md[0]):
            m, modelo = float(md[0]), "distribuída"
    if m is None:
        return {"km": None, "m1": res.m1, "m2": res.m2,
                "motivo": "nenhuma das duas raízes cai na linha (ou as duas caem)"}
    de_a = float(ldl.km_pelo_perfil(np.array([m]), linha.get("perfil"), total)[0])
    km = de_a if s == "A" else total - de_a
    return {"km": km, "km_de_a": de_a, "km_de_b": total - de_a, "m": m,
            "m1": res.m1, "m2": res.m2, "pct": km / total * 100.0 if total else None,
            "modelo": modelo, "motivo": ""}


def leitura(a: Lado, b: Lado, d: float, t: float | None, linha, s: str,
            digitados: dict | None) -> dict | None:
    """O que um cursor lê: a amostra de A mais perto de `t`, a de B em `t + d`."""
    if t is None:
        return None
    na = amostra(a.registro.time, t)
    idx = ldl._mais_proximas(b.registro.time, np.array([float(a.registro.time[na]) + d]))
    nb = int(idx[0])
    va = valores(a, na, (digitados or {}).get("A"))
    vb = valores(b, nb if nb >= 0 else None, (digitados or {}).get("B"))
    return {"t": float(a.registro.time[na]), "na": na,
            "tb": float(b.registro.time[nb]) if nb >= 0 else None, "nb": nb,
            "A": va, "B": vb, "km": km_no_instante(va, vb, linha, s)}


def curva_km(a: Lado, b: Lado, d: float, linha, s: str,
             digitados: dict | None) -> dict | None:
    """O km no tempo de A com o `d` em uso, e a mediana dele no platô.

    Com a impedância de fonte digitada para um terminal sem tensão, o V2 dele
    sai de `−Z2f·I2` amostra a amostra. Um V2/I2 digitado como NÚMERO não
    entra na curva — número parado não é série. Devolve `{km, plato, mediana,
    dispersao}`, com `km` do tamanho do tempo de A (NaN onde não vale).
    """
    if not linha:
        return None

    def v2_de(ld: Lado):
        dg = (digitados or {}).get(ld.letra) or {}
        zm, za = _num(dg.get("z2f_mod")), _num(dg.get("z2f_ang"))
        if ld.v2 is None and zm and za is not None and ld.i2 is not None:
            return -zm * cmath.exp(1j * math.radians(za)) * ld.i2
        return ld.v2
    v2a, v2b = v2_de(a), v2_de(b)
    if v2a is None or v2b is None or a.i2 is None or b.i2 is None:
        return None
    idx = ldl._mais_proximas(b.registro.time, a.registro.time + d)
    v2b_al, i2b_al = ldl._no(v2b, idx), ldl._no(b.i2, idx)
    z = complex(linha["r"], linha["x"])
    total = float(linha["km"])
    m = ldl.seqneg_vetor(v2a, a.i2, v2b_al, i2b_al, z)
    if linha.get("b1"):
        m = ldl.seqneg_distribuida(v2a, a.i2, v2b_al, i2b_al, z, float(linha["b1"]) * 1e-6, m)
    de_a = ldl.km_pelo_perfil(m, linha.get("perfil"), total)
    km = de_a if s == "A" else total - de_a
    with np.errstate(invalid="ignore"):
        ia, ib = np.abs(a.i2), np.abs(i2b_al)
        tem = ((ia > FRACAO_MINIMA_DE_I2 * np.nanmax(ia))
               & (ib > FRACAO_MINIMA_DE_I2 * np.nanmax(ib)))
    km = np.where(tem, km, np.nan)
    # o platô: o de A, e o de B trazido para o tempo de A quando B tem as
    # duas trincas — como em `ldl._preparar`
    term_a = ldl.terminal(a.registro)
    plato = ldl._plato(term_a) if term_a.v is not None else None
    if plato is not None and b.v is not None:
        term_b = ldl.terminal(b.registro)
        pb = ldl._plato(term_b) if term_b.v is not None else None
        if pb is not None:
            t0, t1 = max(plato[0], pb[0] - d), min(plato[1], pb[1] - d)
            plato = (t0, t1) if t1 > t0 else None
    mediana = disp = None
    if plato is not None:
        t = a.registro.time
        vals = km[(t >= plato[0]) & (t <= plato[1])]
        vals = vals[np.isfinite(vals)]
        if vals.size:
            mediana = float(np.median(vals))
            disp = float(np.percentile(vals, 90) - np.percentile(vals, 10)) / 2.0
    return {"km": km, "plato": list(plato) if plato else None, "mediana": mediana,
            "dispersao": disp, "total": total}
