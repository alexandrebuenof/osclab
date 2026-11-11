"""Os números da janela «parâmetros» do painel localizador.

A janela põe lado a lado as fontes da linha — os ajustes do relé (A e, com
dois IEDs, B), a linha escolhida na base de dados e o que se digitou — e diz
qual delas entra na conta. Tudo o que ela mostra é número, e por isso mora
aqui, com teste, e não no JavaScript:

* `fichas`: cada fonte escrita nas grandezas da tabela (R, X, |Z|, ∠ de Z1 e
  de Z0, |k0|, ∠k0, comprimento, B1), em primário e em secundário, em ohm da
  linha inteira e em ohm por km. A tela só escolhe qual das quatro vistas
  pinta;
* `comparacao`: cada coluna contra a coluna EM USO, campo a campo — a célula
  que passa da tolerância a tela pinta de vermelho, sem escrever a diferença;
* `selo`: os ajustes do relé contra a linha da base (ou a digitada) em Z1,
  Z0/k0 e comprimento — o selo «⚠ relé ≠ base» do cabeçalho do painel, com o
  detalhe para o hover;
* `digitado_parcial`: o que se digitou, levado a primário mesmo incompleto —
  é o que deixa a coluna «Digitado» se completar sozinha (|Z|, ∠, k0) e mudar
  de vista (primário/secundário, Ω/km) sem perder o que estava escrito.

As tolerâncias foram propostas na maquete do localizador (10/11/2026) e
aprovadas com a variante 17: módulo 2 %, ângulo 1°, comprimento 1 km ou 1 %,
o que for maior.

Leitor universal: nada aqui depende de fabricante. Os ajustes chegam já
convertidos em linha (`seqneg.linha_dos_ajustes`); o k0 que o próprio relé
grava, quando grava, vem de `plot.impedancia.k0_de` e vence o calculado só na
coluna dele.
"""

from __future__ import annotations

import math

#: |Z|, R, X, |k0| e B1: diferença relativa à coluna em uso, em %.
TOL_MODULO_PCT = 2.0
#: ∠Z1, ∠Z0, ∠k0: diferença absoluta, em graus.
TOL_ANGULO_GRAUS = 1.0
#: Comprimento: 1 km ou 1 % da coluna em uso, o que for MAIOR.
TOL_KM = 1.0
TOL_KM_PCT = 1.0

TEXTO_TOLERANCIA = ("tolerância: |Z|, R, X, |k0| e B1 2 %; ângulos 1°; "
                    "comprimento 1 km ou 1 % (o que for maior)")

#: As vistas da tabela.
BASES = ("prim", "sec")
UNIDADES = ("ohm", "km")

#: Os campos de uma coluna, na ordem da tabela.
CAMPOS = ("r", "x", "mod", "ang", "r0", "x0", "mod0", "ang0", "k0mod", "k0ang", "km", "b1")
#: Campos que são ângulo (comparam-se em graus) e os que não dependem da vista.
ANGULOS = ("ang", "ang0", "k0ang")
#: Campos que se DIGITAM na coluna «Digitado»; o resto ela calcula.
DIGITAVEIS = ("r", "x", "r0", "x0", "km", "b1")


# ---------------------------------------------------------------------------
# Números e texto
# ---------------------------------------------------------------------------

def numero(bruto) -> float | None:
    """`"12,5"` → 12.5; vazio ou lixo → `None`."""
    if bruto is None:
        return None
    try:
        v = float(str(bruto).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def texto(v: float | None, significativos: int = 5) -> str:
    """Cinco algarismos significativos (a regra das casas do projeto), com
    vírgula e sem zeros à direita. `None` → `""`."""
    if v is None or not math.isfinite(v):
        return ""
    if v == 0:
        return "0"
    casas = max(0, significativos - 1 - int(math.floor(math.log10(abs(v)))))
    s = f"{v:.{casas}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def texto_angulo(v: float | None) -> str:
    """Ângulo com duas casas: a tolerância é 1°, e o centésimo mostra que a
    diferença de 0,99° não passou dela."""
    return "" if v is None or not math.isfinite(v) else f"{v:.2f}".replace(".", ",")


def _graus(z: complex) -> float:
    return math.degrees(math.atan2(z.imag, z.real))


def _difang(a: float, b: float) -> float:
    """`a − b` em graus, no intervalo (−180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------------------
# Uma linha numa vista
# ---------------------------------------------------------------------------

def k0_da_linha(linha: dict) -> complex | None:
    """`(Z0 − Z1) / (3·Z1)` da linha, ou `None` sem Z0 (ou Z1 nulo)."""
    r, x, r0, x0 = (linha.get(k) for k in ("r", "x", "r0", "x0"))
    if None in (r, x, r0, x0):
        return None
    z1 = complex(r, x)
    if abs(z1) == 0:
        return None
    return (complex(r0, x0) - z1) / (3.0 * z1)


def valores(linha: dict, base: str, unidade: str, rtp_rtc: float | None,
            k0: complex | None = None) -> dict[str, float | None] | None:
    """A linha (em PRIMÁRIO: `r`, `x`, `r0`, `x0`, `km`, `b1`) numa vista.

    `base`: `prim` ou `sec` (secundário pelo `rtp_rtc`; sem ele, `None`).
    `unidade`: `ohm` (linha inteira) ou `km` (por quilômetro; sem comprimento,
    `None`). Ângulos e k0 não mudam com a vista. `k0`: o que o relé grava, quando
    grava — vence o calculado. Campos que a linha não tem saem `None`.
    """
    if base == "sec" and not rtp_rtc:
        return None
    km = linha.get("km")
    if unidade == "km" and not (km and km > 0):
        return None
    fator = 1.0 / rtp_rtc if base == "sec" else 1.0
    por = km if unidade == "km" else 1.0
    sai: dict[str, float | None] = dict.fromkeys(CAMPOS)
    sai["km"] = km
    for suf, (rk, xk) in (("", ("r", "x")), ("0", ("r0", "x0"))):
        r, x = linha.get(rk), linha.get(xk)
        if r is None or x is None:
            continue
        z = complex(r, x) * fator / por
        sai[f"r{suf}"], sai[f"x{suf}"] = z.real, z.imag
        sai[f"mod{suf}"], sai[f"ang{suf}"] = abs(z), _graus(z) if abs(z) else None
    b1 = linha.get("b1")
    if b1:
        # Admitância vai ao contrário da impedância: Y_sec = Y_prim · RTP/RTC.
        sai["b1"] = b1 / fator / por
    k = k0 if k0 is not None else k0_da_linha(linha)
    if k is not None:
        sai["k0mod"], sai["k0ang"] = abs(k), _graus(k) if abs(k) else None
    return sai


def _escritos(vals: dict[str, float | None] | None) -> dict[str, str] | None:
    if vals is None:
        return None
    return {c: (texto_angulo(v) if c in ANGULOS else texto(v, 4 if c == "k0mod" else 5))
            for c, v in vals.items()}


def ficha(linha: dict, rtp_rtc: float | None, k0: complex | None = None) -> dict:
    """`{base: {unidade: {campo: texto} | None}}` — as quatro vistas de uma linha."""
    return {b: {u: _escritos(valores(linha, b, u, rtp_rtc, k0)) for u in UNIDADES}
            for b in BASES}


# ---------------------------------------------------------------------------
# O que se digitou
# ---------------------------------------------------------------------------

def digitado_parcial(m: dict | None, rtp_rtc: float | None) -> dict:
    """O que se digitou, em PRIMÁRIO e na linha inteira, par a par.

    `m` traz `base` (`prim`/`sec`), `forma` (`rx` = ohm da linha inteira, `km` =
    ohm por km) e os campos `r`, `x`, `r0`, `x0`, `b1` — ou `rkm`, `xkm`,
    `r0km`, `x0km`, `b1km` — e `km`. O que falta fica de fora: um R sem o X não
    é impedância, e por km sem o comprimento não é linha. Secundário sem
    `rtp_rtc` não se converte — sai vazio, que é o honesto.
    """
    m = m or {}
    forma = "km" if str(m.get("forma") or "rx") == "km" else "rx"
    sufixo = "km" if forma == "km" else ""
    km = numero(m.get("km"))
    km = km if km and km > 0 else None
    sai: dict = {}
    if km:
        sai["km"] = km
    if str(m.get("base") or "prim") == "sec":
        if not rtp_rtc:
            return sai
        fator = rtp_rtc
    else:
        fator = 1.0
    if forma == "km" and not km:
        return sai
    por = km if forma == "km" else 1.0
    for suf, (rk, xk) in (("", ("r", "x")), ("0", ("r0", "x0"))):
        a = numero(m.get(f"r{suf}{sufixo}"))
        b = numero(m.get(f"x{suf}{sufixo}"))
        if a is None or b is None:
            continue
        z = complex(a, b) * por * fator
        sai[rk], sai[xk] = z.real, z.imag
    b1 = numero(m.get(f"b1{sufixo}"))
    if b1 and b1 > 0:
        sai["b1"] = b1 * por / fator
    return sai


def como_digitado(linha: dict, base: str, unidade: str,
                  rtp_rtc: float | None) -> dict | None:
    """A linha (primário) escrita como o formulário de digitar a guarda:
    `{forma, base, r, x, r0, x0, km, b1}` (ou os `…km`). É o que a coluna
    «Digitado» passa a conter quando se troca de vista — o número continua o
    mesmo, escrito na vista nova."""
    vals = valores(linha, base, unidade, rtp_rtc)
    if vals is None:
        # Secundário sem relação, ou Ω/km sem comprimento: não há como
        # escrever ali, e a tela mantém o que está digitado.
        return None
    sufixo = "km" if unidade == "km" else ""
    sai = {"forma": "km" if unidade == "km" else "rx", "base": base,
           "km": texto(linha.get("km"))}
    for c in ("r", "x", "r0", "x0", "b1"):
        sai[f"{c}{sufixo}"] = texto(vals.get(c))
    return sai


# ---------------------------------------------------------------------------
# Cada coluna contra a coluna em uso
# ---------------------------------------------------------------------------

def _difere_relativo(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    if b == 0:
        return a != 0
    return abs(a - b) / abs(b) * 100.0 > TOL_MODULO_PCT


def _difere_angulo(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(_difang(a, b)) > TOL_ANGULO_GRAUS


def _difere_km(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) > max(TOL_KM, TOL_KM_PCT / 100.0 * abs(b))


def diferencas(a: dict[str, float | None], b: dict[str, float | None]) -> dict[str, bool]:
    """Campo a campo, se `a` difere de `b` além da tolerância (mesma vista).

    R e X não têm tolerância própria: são o mesmo Z em outra forma, e ficam
    vermelhos junto com |Z| ou ∠Z. Comparados sozinhos a 2 %, um ângulo que
    difere 0,9° (dentro) mudaria o R de uma linha de 80° em 8 % — a tabela
    diria que o mesmo número está e não está fora.
    """
    sai = {c: False for c in CAMPOS}
    for suf in ("", "0"):
        m = _difere_relativo(a.get(f"mod{suf}"), b.get(f"mod{suf}"))
        g = _difere_angulo(a.get(f"ang{suf}"), b.get(f"ang{suf}"))
        sai[f"mod{suf}"], sai[f"ang{suf}"] = m, g
        sai[f"r{suf}"] = sai[f"x{suf}"] = m or g
    sai["k0mod"] = _difere_relativo(a.get("k0mod"), b.get("k0mod"))
    sai["k0ang"] = _difere_angulo(a.get("k0ang"), b.get("k0ang"))
    sai["km"] = _difere_km(a.get("km"), b.get("km"))
    sai["b1"] = _difere_relativo(a.get("b1"), b.get("b1"))
    return sai


def comparacao(linhas: dict[str, dict], usada: str | None,
               k0s: dict[str, complex] | None = None) -> dict:
    """`{unidade: {fonte: {campo: difere}}}` — cada fonte contra a EM USO.

    `linhas`: as fontes que têm linha (em primário). Compara-se em primário:
    o secundário divide todas as colunas pela mesma relação e não muda nada;
    o Ω/km, não — com comprimentos diferentes, o mesmo Z total é outro Z por
    km, e a tela mostra o número da vista que está aberta.
    """
    k0s = k0s or {}
    if not usada or usada not in linhas:
        return {}
    sai: dict = {}
    for u in UNIDADES:
        ref = valores(linhas[usada], "prim", u, None, k0s.get(usada))
        if ref is None:
            continue
        sai[u] = {}
        for nome, linha in linhas.items():
            if nome == usada:
                continue
            vals = valores(linha, "prim", u, None, k0s.get(nome))
            if vals is not None:
                sai[u][nome] = diferencas(vals, ref)
    return sai


# ---------------------------------------------------------------------------
# O selo «⚠ relé ≠ base» do cabeçalho
# ---------------------------------------------------------------------------

def _sinal(v: float) -> str:
    return "+" if v > 0 else "−" if v < 0 else "±"


def divergencias(rele: dict, outra: dict, k0_rele: complex | None = None) -> list[dict]:
    """Os ajustes do relé contra a linha `outra`, em primário: Z1, Z0, k0 e o
    comprimento. Cada item traz os dois números escritos e a diferença — é o
    detalhe do hover do selo."""
    a = valores(rele, "prim", "ohm", None, k0_rele) or {}
    b = valores(outra, "prim", "ohm", None) or {}
    dif = diferencas(a, b)
    itens = []
    if a.get("km") and b.get("km"):
        d = a["km"] - b["km"]
        itens.append({"campo": "comprimento (LL)", "rele": f"{texto(a['km'], 4)} km",
                      "outra": f"{texto(b['km'], 4)} km",
                      "dif": f"{_sinal(d)}{texto(abs(d), 3)} km", "difere": dif["km"]})
    for suf, nome in (("", "Z1"), ("0", "Z0")):
        if a.get(f"mod{suf}") is None or b.get(f"mod{suf}") is None:
            continue
        dm = (a[f"mod{suf}"] - b[f"mod{suf}"]) / b[f"mod{suf}"] * 100.0
        itens.append({"campo": f"|{nome}|", "rele": f"{texto(a[f'mod{suf}'], 4)} Ω",
                      "outra": f"{texto(b[f'mod{suf}'], 4)} Ω",
                      "dif": f"{_sinal(dm)}{abs(dm):.1f} %".replace(".", ","),
                      "difere": dif[f"mod{suf}"]})
        if a.get(f"ang{suf}") is not None and b.get(f"ang{suf}") is not None:
            da = _difang(a[f"ang{suf}"], b[f"ang{suf}"])
            itens.append({"campo": f"∠{nome}", "rele": f"{texto_angulo(a[f'ang{suf}'])}°",
                          "outra": f"{texto_angulo(b[f'ang{suf}'])}°",
                          "dif": f"{_sinal(da)}{texto_angulo(abs(da))}°",
                          "difere": dif[f"ang{suf}"]})
    if a.get("k0mod") is not None and b.get("k0mod") is not None:
        dm = (a["k0mod"] - b["k0mod"]) / b["k0mod"] * 100.0 if b["k0mod"] else 0.0
        itens.append({"campo": "|k0|", "rele": texto(a["k0mod"], 4),
                      "outra": texto(b["k0mod"], 4),
                      "dif": f"{_sinal(dm)}{abs(dm):.1f} %".replace(".", ","),
                      "difere": dif["k0mod"]})
        if a.get("k0ang") is not None and b.get("k0ang") is not None:
            da = _difang(a["k0ang"], b["k0ang"])
            itens.append({"campo": "∠k0", "rele": f"{texto_angulo(a['k0ang'])}°",
                          "outra": f"{texto_angulo(b['k0ang'])}°",
                          "dif": f"{_sinal(da)}{texto_angulo(abs(da))}°",
                          "difere": dif["k0ang"]})
    return itens


def selo(fontes: dict, usada: str | None, letras: list[str],
         k0s: dict[str, complex] | None = None) -> list[dict]:
    """Um bloco por relé cujos ajustes DIFEREM da linha comparada.

    A comparada é a base escolhida — ou a digitada, quando é ela que está em
    uso (ou quando não há base). Só sai bloco quando algo passa da tolerância:
    o selo é aviso, e aviso que aparece sem nada errado ensina a ignorá-lo.
    """
    k0s = k0s or {}
    if usada == "manual" and (fontes.get("manual") or {}).get("ok"):
        alvo = "manual"
    elif (fontes.get("base") or {}).get("ok"):
        alvo = "base"
    elif (fontes.get("manual") or {}).get("ok"):
        alvo = "manual"
    else:
        return []
    blocos = []
    for letra in letras:
        rele = fontes.get(letra) or {}
        if not rele.get("ok"):
            continue
        itens = divergencias(rele, fontes[alvo], k0s.get(letra))
        if any(i["difere"] for i in itens):
            blocos.append({"rele": letra, "com": alvo, "itens": itens,
                           "tolerancia": TEXTO_TOLERANCIA})
    return blocos


# ---------------------------------------------------------------------------
# Tudo junto, para a rota
# ---------------------------------------------------------------------------

def montar(fontes: dict, usada: str | None, letras: list[str], rtp_rtc: float | None,
           manual: dict | None, k0s: dict[str, complex] | None = None) -> dict:
    """O bloco `parametros` do pacote da localização.

    `fontes`: as de `seqneg` (`base`, `A`, `B`, `manual`), com `ok`. A coluna
    «Digitado» entra mesmo incompleta (`digitado_parcial`): é assim que ela se
    completa enquanto se digita. `rtp_rtc` é o do registro A — o secundário da
    tabela inteira é o daquele relé.
    """
    k0s = k0s or {}
    linhas = {f: fontes[f] for f in ("A", "B", "base") if (fontes.get(f) or {}).get("ok")}
    parcial = digitado_parcial(manual, rtp_rtc)
    colunas = dict(linhas)
    if parcial:
        colunas["manual"] = parcial
    completas = dict(linhas)
    if (fontes.get("manual") or {}).get("ok"):
        completas["manual"] = parcial
    return {
        "fichas": {f: ficha(linha, rtp_rtc, k0s.get(f)) for f, linha in colunas.items()},
        "comparacao": comparacao(completas, usada, k0s),
        "selo": selo(fontes, usada, letras, k0s),
        "tolerancia": TEXTO_TOLERANCIA,
        "rtp_rtc": rtp_rtc,
        # O formulário de digitar escrito em cada vista: trocar de vista
        # converte o que estava escrito, sem a tela fazer conta nenhuma.
        "digitado_em": ({b: {u: como_digitado(parcial, b, u, rtp_rtc) for u in UNIDADES}
                         for b in BASES} if parcial else None),
    }
