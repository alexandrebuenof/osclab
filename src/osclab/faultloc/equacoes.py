"""As equações dos métodos de localização, DESCRITAS em árvore para a janela
«? métodos» do painel localizador desenhar (variante 06 da maquete
`maquete/metodos`, escolhida em 12/11/2026).

A equação é DESENHADA — fração com traço, índice, |·| e {·} que esticam,
Im{} —, não digitada em texto corrido. Mas o desenho é só pintura: o que a
equação diz, os símbolos e os números «neste registro» saem daqui, e a tela
(`static/js/metodos-loc.js`) recebe a árvore e pinta. Cada nó é um
dicionário pequeno:

    {"t": "v", "x": "V", "sub": "2S", "id": "V2S"}   variável (itálica), com índice
    {"t": "n", "x": "1"}                              número (reto)
    {"t": "o", "x": "−"}                              operador (com folga dos lados)
    {"t": "p", "x": "·"}                              operador apertado (produto)
    {"t": "txt", "x": "km"}                           texto corrido, na fonte da tela
    {"t": "fn", "f": "Im", "x": nó}                   Im{…}, Re{…}
    {"t": "d", "k": "abs" | "par" | "chave", "x": nó} delimitadores que esticam
    {"t": "frac", "a": nó, "b": nó}                   fração com traço
    {"t": "r", "x": [nós]}                            sequência

Os SÍMBOLOS de cada método (`id → o que é`) vão junto: passar o mouse num
símbolo acende o mesmo símbolo em todas as equações do método e diz o que ele
é.

**A fração do laço não se aninha.** A forma direta seria
`m = Im{V_laço / I_laço} / X1L` — uma fração dentro das chaves dentro de outra
fração, com o numerador encolhido a 84 % e as chaves esticadas a duas alturas.
Em vez disso a equação principal é `m = Im{Z_laço} / X1L` e a impedância do
laço vem numa auxiliar, `Z_laço = V_laço / I_laço`: uma fração de cada vez, e
o `Z_laço` é a grandeza que o engenheiro de proteção já conhece — é a que o
relé de distância mede.
"""
from __future__ import annotations


def v(x, sub=None, sup=None, id=None):  # noqa: A002 - é o nome do campo
    return {"t": "v", "x": x, "sub": sub, "sup": sup, "id": id or (x + (sub or ""))}


def n(x):
    return {"t": "n", "x": str(x)}


def o(x):
    return {"t": "o", "x": x}


def p(x="·"):
    return {"t": "p", "x": x}


def txt(x):
    return {"t": "txt", "x": x}


def r(*x):
    return {"t": "r", "x": list(x)}


def fn(f, x):
    return {"t": "fn", "f": f, "x": x}


def d(k, *x):
    return {"t": "d", "k": k, "x": r(*x)}


def frac(a, b):
    return {"t": "frac", "a": a, "b": b}


def conj(base):
    """O conjugado: `ΔI*` — o asterisco no expoente."""
    return {**base, "sup": "∗"}


def texto(no) -> str:
    """A mesma equação em texto corrido — o rótulo acessível (`aria-label`)."""
    t = no["t"]
    if t == "r":
        return "".join(texto(x) for x in no["x"])
    if t == "v":
        return no["x"] + (no.get("sub") or "") + (no.get("sup") or "").replace("∗", "*")
    if t in ("n", "p"):
        return no["x"]
    if t == "txt":
        return f" {no['x']} "
    if t == "o":
        return f" {no['x']} "
    if t == "fn":
        return f"{no['f']}{{{texto(no['x'])}}}"
    if t == "d":
        a, b = {"abs": ("|", "|"), "par": ("(", ")"), "chave": ("{", "}")}[no["k"]]
        return a + texto(no["x"]) + b
    if t == "frac":
        return f"({texto(no['a'])}) / ({texto(no['b'])})"
    raise ValueError(f"nó desconhecido: {t!r}")


def _eq(papel, arvore):
    return {"papel": papel, "arvore": arvore, "texto": " ".join(texto(arvore).split())}


# ---------------------------------------------------------------------------
# As equações, método a método
# ---------------------------------------------------------------------------

M = v("m")
Z2 = v("Z", "2L", id="Z2L")
Z1L = v("Z", "1L", id="Z1L")
V_LACO = v("V", "laço")
I_LACO = v("I", "laço")

EQUACOES = {
    "seqneg": [
        _eq("principal", r(
            d("abs", v("V", "2S"), o("−"), M, p(), Z2, p(), v("I", "2S")),
            o("="),
            d("abs", v("V", "2R"), o("−"), d("par", n(1), o("−"), M), p(), Z2, p(),
              v("I", "2R")))),
    ],
    "laco": [
        _eq("principal", r(M, o("="), frac(fn("Im", v("Z", "laço")), v("X", "1L")))),
        _eq("auxiliar", r(v("Z", "laço"), o("="), frac(V_LACO, I_LACO))),
        _eq("auxiliar", r(I_LACO, o("="), v("I", "φ"), o("+"), v("k", "0"), p(),
                          n(3), v("I", "0"))),
        _eq("auxiliar", r(v("k", "0"), o("="),
                          frac(r(v("Z", "0L"), o("−"), Z1L), r(n(3), p(), Z1L)))),
    ],
    "takagi": [
        _eq("principal", r(M, o("="), frac(fn("Im", r(V_LACO, p(), conj(v("ΔI")))),
                                           fn("Im", r(Z1L, p(), I_LACO, p(),
                                                      conj(v("ΔI"))))))),
        _eq("auxiliar", r(v("ΔI"), o("="), I_LACO, o("−"), v("I", "pré"))),
    ],
    "takagi_i2": [
        _eq("principal", r(M, o("="), frac(fn("Im", r(V_LACO, p(), conj(v("I", "2")))),
                                           fn("Im", r(Z1L, p(), I_LACO, p(),
                                                      conj(v("I", "2"))))))),
    ],
}

#: O que cada símbolo é. Vale para os quatro métodos (o mesmo `id` quer dizer
#: a mesma coisa em todos); cada método só leva os que usa. `{S}` e `{R}` são
#: os terminais como a tela os chama — «IED A»/«IED B» com duas oscilografias,
#: «este relé» com uma (nunca «IED A» com um só).
SIMBOLOS = {
    "m": "posição da falta, em fração da linha (0 no terminal S, 1 no R)",
    "d": "distância da falta a partir do terminal S ({S})",
    "L": "comprimento da linha em uso",
    "V2S": "tensão de sequência negativa no terminal S ({S})",
    "I2S": "corrente de sequência negativa no terminal S, para a linha",
    "V2R": "tensão de sequência negativa no terminal R ({R})",
    "I2R": "corrente de sequência negativa no terminal R, para a linha",
    "Z2L": "impedância de sequência negativa da linha inteira (= Z1L)",
    "Z1L": "impedância de sequência positiva da linha inteira",
    "Z0L": "impedância de sequência zero da linha inteira",
    "X1L": "reatância de sequência positiva da linha inteira",
    "Zlaço": "impedância aparente do laço — a que o relé de distância mede",
    "Vlaço": "tensão do laço da falta: Vφ no de terra, Vφ1 − Vφ2 no de fase",
    "Ilaço": "corrente do laço, compensada por k0 no de terra",
    "Iφ": "corrente da fase com defeito",
    "k0": "fator de compensação de terra",
    "I0": "corrente de sequência zero (3I0 é o resíduo)",
    "ΔI": "corrente superposta: a da falta menos a da pré-falta",
    "Ipré": "corrente do laço na pré-falta (um ciclo antes do início)",
    "I2": "corrente de sequência negativa do laço — só a falta a produz",
}

#: «como calcula» SEM a equação, que é desenhada ao lado. (O `ldl.COMO_CALCULA`,
#: com a fórmula em texto, continua indo no pacote: é o hover da legenda.)
FRASE = {
    "seqneg": ("Iguala a tensão de sequência negativa no ponto da falta vista pelos dois "
               "terminais."),
    "laco": "Reatância do laço da falta, dividida pela reatância da linha.",
    "takagi": "Reatância referida à corrente superposta, a da falta menos a da pré-falta.",
    "takagi_i2": "Reatância referida à I2 do laço, que só a falta produz.",
}
#: O `ldl.DETALHE` sem as fórmulas que viraram equação auxiliar.
DETALHE = {
    "laco": ("No laço de terra a corrente é compensada por k0; no de fase, V e I são as "
             "diferenças entre as duas fases. Um terminal, sem pré-falta."),
}


def ids(no, saida=None) -> list[str]:
    """Os `id` das variáveis de uma árvore, na ordem em que aparecem."""
    saida = [] if saida is None else saida
    t = no["t"]
    if t == "v":
        saida.append(no["id"])
    elif t == "r":
        for x in no["x"]:
            ids(x, saida)
    elif t in ("fn", "d"):
        ids(no["x"], saida)
    elif t == "frac":
        ids(no["a"], saida)
        ids(no["b"], saida)
    return saida


def br(x: float, casas: int) -> str:
    """O número com vírgula decimal e as casas pedidas."""
    return f"{x:.{casas}f}".replace(".", ",")


#: As casas de cada número «neste registro»: a fração com quatro (um décimo
#: de milésimo de 137 km são 14 m — abaixo de qualquer número que se patrulhe),
#: o comprimento com uma (como no cabeçalho do painel), o km com duas (como no
#: gráfico).
CASAS_M, CASAS_LINHA, CASAS_KM = 4, 1, 2


def neste(km: float | None, km_linha: float | None):
    """«neste registro» como conta: `d = m · L = 0,4120 × 137,0 km = 56,45 km`.

    `None` sem número (o método não mediu, ou não há linha): a tela mostra o
    porquê, que vem no `motivo` do método.
    """
    if km is None or not km_linha:
        return None
    m = km / km_linha
    return r(v("d"), o("="), M, p(), v("L"), o("="), n(br(m, CASAS_M)), o("×"),
             n(br(km_linha, CASAS_LINHA)), txt("km"), o("="), n(br(km, CASAS_KM)), txt("km"))


def anexar(pacote: dict) -> dict:
    """Devolve o pacote com `equacoes`, `frase`, `simbolos`, `m`, os textos
    dos números e `neste` em cada método, e `terminais_da_ajuda` (como a
    janela chama S e R).

    Não mexe no pacote recebido nem nos métodos dele — o `ldl.montar` guarda
    o pacote entre pedidos, e cada pedido recebe uma cópia.
    """
    km_linha = pacote.get("km_linha")
    dois = len(pacote.get("terminais") or ()) > 1
    s, rr = ("IED A", "IED B") if dois else ("este relé", "outro terminal")
    metodos = {}
    for nome, info in (pacote.get("metodos") or {}).items():
        eqs = EQUACOES.get(nome, [])
        usados: list[str] = []
        for e in eqs:
            ids(e["arvore"], usados)
        conta = neste(info.get("km"), km_linha)
        if conta is not None:
            ids(conta, usados)
        novo = dict(info)
        km = info.get("km")
        m = (km / km_linha) if (km is not None and km_linha) else None
        novo.update(
            equacoes=eqs,
            frase=FRASE.get(nome, info.get("como", "")),
            detalhe=DETALHE.get(nome, info.get("detalhe", "")),
            simbolos={i: SIMBOLOS[i].format(S=s, R=rr)
                      for i in dict.fromkeys(usados) if i in SIMBOLOS},
            m=m,
            m_txt=br(m, CASAS_M) if m is not None else None,
            km_txt=br(km, CASAS_KM) if km is not None else None,
            disp_txt=(br(info["dispersao"], CASAS_KM)
                      if info.get("dispersao") is not None else None),
            neste=conta,
            quantos="dois terminais" if nome == "seqneg" else "um terminal",
        )
        metodos[nome] = novo
    saida = dict(pacote)
    saida["metodos"] = metodos
    # Os rótulos do desenho S — m — R. S é sempre o deste registro; no
    # método de um terminal o R «não entra» na conta.
    saida["terminais_da_ajuda"] = {"s": f"S · {s}", "r": f"R · {rr}",
                                   "r_de_um": "R · não entra"}
    return saida
