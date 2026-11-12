"""A janela «refinar» da seq. negativa: o pacote que a tela desenha.

A conta é de `faultloc/refino.py`; aqui só se ARRUMA para a tela, como os
outros módulos de `plot/`: a janela de tempo (os gestos vão por
`plot/navegacao`), a escala de cada gráfico, as curvas reduzidas por mínimo e
máximo de cada coluna de pixel, as marcações do eixo e os números já escritos
(`leitura.casas`). O JavaScript só converte valor em pixel.

As VISTAS (variante 11 da maquete, 11/11/2026):

* `tri` — quatro gráficos, nesta ordem: correntes de A, de B, tensões de A,
  de B, cada um com as três fases;
* `mono` — dois: corrente e tensão, A e B sobrepostos, de UMA fase — a do
  VÍNCULO de fase do canal (`conjuntos`), nunca a posição;
* `seq` (liga/desliga, nos dois modos) — cada gráfico troca o conteúdo pela
  sequência negativa DELE: o eficaz |X2| (grosso) e a onda Re{X2}·√2 (fina).

B cai em `t − d` em TODO sinal dele: o registro anda inteiro.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.faultloc import refino as rf
from osclab.formats.base import Record
from osclab.plot import alinhamento, escala, navegacao, serie
from osclab.plot import leitura as leitura_mod

#: As cores (tokens do CSS) — os nomes, não os códigos: o tema decide.
FASES = ("--fase-a", "--fase-b", "--fase-c")
COR_DO_TERMINAL = {"A": "--refino-a", "B": "--refino-b"}
NOME_DA_GRANDEZA = {"V": "tensões", "I": "correntes"}


def txt(x, casas: int | None = None) -> str:
    """O número como a tela escreve: cinco algarismos (`leitura.casas`), vírgula."""
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
        return "—"
    c = leitura_mod.casas(x) if casas is None else casas
    return f"{x:.{c}f}".replace("-", "−").replace(".", ",")


def _limpa(arr) -> list:
    return [None if not math.isfinite(x) else round(float(x), 6) for x in arr]


def _recorte(tela: np.ndarray, de: float, ate: float, passo: float) -> slice:
    i0 = max(0, int(np.searchsorted(tela, de - passo)) - 1)
    i1 = min(tela.size, int(np.searchsorted(tela, ate + passo, side="right")) + 1)
    return slice(i0, max(i1, i0 + 1))


def reduz(tempo: np.ndarray, linhas: list, colunas: int) -> dict:
    """Mínimo e máximo por coluna (`serie.reduzir`). `amostras` diz se cada
    ponto é uma amostra de verdade — só aí a tela pode marcar um ponto em
    cada uma (quando couberem 6 px entre duas)."""
    if tempo.size == 0:
        return {"t": [], "v": [[] for _ in linhas], "amostras": False}
    r = serie.reduzir(tempo, np.vstack(linhas), colunas)
    return {"t": _limpa(r.tempo), "v": [_limpa(x) for x in r.valores],
            "amostras": not r.reduzido}


def _escala(arrays) -> dict:
    vals = [np.asarray(x)[np.isfinite(x)] for x in arrays]
    vals = [x for x in vals if x.size]
    maior = max((float(np.max(np.abs(x))) for x in vals), default=1.0) or 1.0
    lo, hi = escala.faixa(-maior, maior)
    return {"min": lo, "max": hi, "marcas": escala.marcacoes(lo, hi, 6)}


def _prefixo_i(*lados: rf.Lado) -> tuple[str, float]:
    """O `k` é do REGISTRO, não do valor: decidido uma vez, pelo maior pico."""
    maior = 0.0
    for ld in lados:
        if ld.inst_i is not None:
            maior = max(maior, max(float(np.nanmax(np.abs(x))) for x in ld.inst_i))
    return ("kA", 1000.0) if maior >= 10000 else ("A", 1.0)


def graficos(a: rf.Lado, b: rf.Lado, d: float, de: float, ate: float, colunas: int,
             vista: str, seq: bool, fase: str) -> list[dict]:
    uni_i, div_i = _prefixo_i(a, b)
    unidade = {"V": "kV", "I": uni_i}

    def recorte(ld: rf.Lado):
        tela = ld.registro.time - (d if ld.letra == "B" else 0.0)
        fatia = _recorte(tela, de, ate, ld.passo)
        return tela[fatia], fatia

    def inst(ld: rf.Lado, g: str):
        x = ld.inst_v if g == "V" else ld.inst_i
        return None if x is None else ([y / div_i for y in x] if g == "I" else x)

    def falta(ld: rf.Lado, nome: str) -> dict:
        return {"terminal": ld.letra, "nome": nome, "falta": True, "aviso": ld.aviso}

    def de_fase(ld: rf.Lado, g: str, fases: str, cor, valores: list) -> list:
        y = inst(ld, g)
        if y is None:
            return [falta(ld, f"{NOME_DA_GRANDEZA[g]} de {ld.letra}")]
        tela, fatia = recorte(ld)
        nomes = ld.nomes_v if g == "V" else ld.nomes_i
        saida = []
        for f in fases:
            k = "ABC".index(f)
            yy = y[k][fatia]
            valores.append(yy)
            red = reduz(tela, [yy], colunas)
            saida.append({"terminal": ld.letra, "fase": f, "cor": cor(k),
                          "nome": nomes[k] + (f" ({ld.letra})" if vista == "mono" else ""),
                          "t": red["t"], "onda": red["v"][0], "amostras": red["amostras"]})
        return saida

    def de_seq(ld: rf.Lado, g: str, valores: list) -> dict:
        x2 = ld.v2 if g == "V" else ld.i2
        nome = f"{'V2' if g == 'V' else 'I2'} {ld.letra}"
        if x2 is None:
            return falta(ld, nome)
        div = 1000.0 if g == "V" else div_i
        tela, fatia = recorte(ld)
        onda = (np.real(x2) * math.sqrt(2.0) / div)[fatia]
        env = (np.abs(x2) / div)[fatia]
        valores += [onda, env]
        red = reduz(tela, [onda, env], colunas)
        return {"terminal": ld.letra, "nome": nome, "cor": COR_DO_TERMINAL[ld.letra],
                "t": red["t"], "onda": red["v"][0], "env": red["v"][1],
                "amostras": red["amostras"]}

    saida = []
    if vista == "tri":
        for g in ("I", "V"):                    # corrente primeiro
            for ld in (a, b):
                valores: list = []
                series = ([de_seq(ld, g, valores)] if seq
                          else de_fase(ld, g, "ABC", lambda k: FASES[k], valores))
                titulo = (f"{ld.letra} · {NOME_DA_GRANDEZA[g]}"
                          + (" · sequência negativa" if seq else ""))
                vazio = all(s.get("falta") for s in series)
                saida.append({"id": f"{ld.letra}-{g}", "titulo": titulo, "terminal": ld.letra,
                              "grandeza": g, "unidade": unidade[g], "series": series,
                              "vazio": (ld.aviso or "sem sinal") if vazio else "",
                              "escala": _escala(valores)})
        return saida
    for g in ("I", "V"):
        valores = []
        if seq:
            series = [de_seq(a, g, valores), de_seq(b, g, valores)]
        else:
            series = []
            for ld in (a, b):
                series += de_fase(ld, g, fase, lambda k, ld=ld: COR_DO_TERMINAL[ld.letra],
                                  valores)
        titulo = (NOME_DA_GRANDEZA[g].capitalize()
                  + (" · sequência negativa" if seq else f" · fase {fase}"))
        saida.append({"id": f"mono-{g}", "titulo": titulo, "grandeza": g, "unidade": unidade[g],
                      "series": series, "escala": _escala(valores)})
    return saida


def _leitura_escrita(no: dict | None) -> dict | None:
    if not no:
        return no
    for k in ("A", "B"):
        v = no[k]
        v["txt"] = {"v2": txt(v["v2"]), "i2": txt(v["i2"]), "ang": txt(v["ang"], 1)}
        v["lido"]["txt"] = {"v2": txt(v["lido"]["v2"]), "i2": txt(v["lido"]["i2"]),
                            "ang": txt(v["lido"]["ang"], 1)}
    km = no["km"]
    km["txt"] = {"km": txt(km.get("km"), 2), "pct": txt(km.get("pct"), 1)}
    return no


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def linha_do_pedido(bruta) -> dict | None:
    """A linha que a tela manda (a mesma do painel): `{r, x, km, b1?, perfil?}`."""
    if not isinstance(bruta, dict):
        return None
    linha = {k: _num(bruta.get(k)) for k in ("r", "x", "km", "b1")}
    if linha["r"] is None or linha["x"] is None or not linha["km"]:
        return None
    perfil = bruta.get("perfil")
    if isinstance(perfil, list) and all(isinstance(p, (list, tuple)) and len(p) == 2
                                        for p in perfil):
        linha["perfil"] = [[float(p[0]), float(p[1])] for p in perfil]
    return linha


def montar(reg_a: Record, nome_a: str, reg_b: Record, nome_b: str, corpo: dict) -> dict:
    """O pacote da janela. `corpo`: `modo` (auto|manual) e `manual` do
    alinhamento, `vista` (tri|mono), `fase`, `seq`, `s` (A|B), a janela
    `de`/`ate` com o `gesto`, os cursores `t1`/`t2`, a `linha`, os
    `digitados` e as `colunas` de pixel."""
    a, b = rf.lado(reg_a, "A", nome_a), rf.lado(reg_b, "B", nome_b)
    alin = rf.alinhar(a, b, str(corpo.get("modo") or "auto"), corpo.get("manual"))
    d = alin["d"]
    linha = linha_do_pedido(corpo.get("linha"))
    s = "B" if corpo.get("s") == "B" else "A"
    digitados = corpo.get("digitados") if isinstance(corpo.get("digitados"), dict) else {}

    um = rf.ciclo(a)
    inicio_a = alinhamento.instante_da_falta(reg_a)
    gesto = corpo.get("gesto") or {}
    de, ate = _num(corpo.get("de")), _num(corpo.get("ate"))
    if de is None or ate is None:
        # do pouco antes do início da falta em A a um pouco depois da abertura
        t0 = (inicio_a if inicio_a is not None else float(reg_a.time[0])) - 4 * um
        de, ate = navegacao.limitar(float(reg_a.time[0]), float(reg_a.time[-1]),
                                    t0, t0 + 14 * um, a.passo)
    else:
        de, ate = navegacao.resolver(reg_a, de=de, ate=ate, zoom=_num(gesto.get("zoom")),
                                     foco=_num(gesto.get("foco")),
                                     andar=_num(gesto.get("andar")),
                                     tudo=bool(gesto.get("tudo")))
    try:
        colunas = max(100, min(6000, int(corpo.get("colunas") or 900)))
    except (TypeError, ValueError):
        colunas = 900
    vista = "mono" if corpo.get("vista") == "mono" else "tri"
    seq = bool(corpo.get("seq"))
    fase = str(corpo.get("fase") or "A")[:1].upper()
    fase = fase if fase in "ABC" else "A"

    zero = inicio_a if inicio_a is not None else float(reg_a.time[0])
    marcas_t = [{"t": zero + ms / 1000.0, "ms": ms}
                for ms in escala.marcacoes((de - zero) * 1000.0, (ate - zero) * 1000.0, 7)]
    inicio_b = alinhamento.instante_da_falta(reg_b)
    eventos = {"inicio_a": inicio_a, "inicio_b": None if inicio_b is None else inicio_b - d}

    cursores = {k: _leitura_escrita(rf.leitura(a, b, d, _num(corpo.get(k)), linha, s,
                                               digitados))
                for k in ("t1", "t2")}
    km_curva = None
    curva = rf.curva_km(a, b, d, linha, s, digitados)
    if curva is not None:
        tela = reg_a.time
        fatia = _recorte(tela, de, ate, a.passo)
        total = curva["total"]
        y = np.clip(curva["km"][fatia], -0.2 * total, 1.2 * total)
        red = reduz(tela[fatia], [y], colunas)
        lo, hi = -0.05 * total, 1.05 * total
        km_curva = {"t": red["t"], "v": red["v"][0], "plato": curva["plato"],
                    "escala": {"min": lo, "max": hi, "marcas": escala.marcacoes(0, total, 5)},
                    "mediana": curva["mediana"],
                    "txt": {"mediana": txt(curva["mediana"], 2),
                            "dispersao": txt(curva["dispersao"], 2)}}

    cf = alin["confere"]
    al = {
        "modo": alin["modo"], "d": d,
        "auto": {"d": alin["auto"]["d"], "por": alin["auto"]["por"],
                 "nome": alinhamento.NOMES.get(alin["auto"]["por"], alin["auto"]["por"])},
        "manual": alin["manual"],
        "confere": None if cf is None else {"d": cf["d"], "discorda": cf["discorda"],
                                             "mistura": cf["mistura"]},
        "passo_a": alin["passo_a"], "passo_b": alin["passo_b"], "ciclo": alin["ciclo"],
        "txt": {"usado": txt(d * 1000.0, 2), "menos_usado": txt(-d * 1000.0, 2),
                "auto": txt(alin["auto"]["d"] * 1000.0, 2),
                "relogio": (None if alin["auto"].get("relogio_ms") is None
                            else txt(alin["auto"]["relogio_ms"], 2)),
                "confere": None if cf is None else txt(cf["d"] * 1000.0, 2),
                "dif": None if cf is None else txt(cf["dif"] * 1000.0, 2),
                "passo_a": txt(a.passo * 1000.0, 3), "passo_b": txt(b.passo * 1000.0, 3)},
    }

    def descreve(ld: rf.Lado) -> dict:
        return {"letra": ld.letra, "nome": ld.nome, "por_ciclo": round(ld.por_ciclo, 3),
                "por_ciclo_txt": txt(ld.por_ciclo, int(ld.por_ciclo != round(ld.por_ciclo))),
                "aviso": ld.aviso, "tem_v": ld.v is not None}
    return {
        "terminais": [descreve(a), descreve(b)],
        "alinhamento": al,
        "janela": {"de": de, "ate": ate, "zero": zero, "marcas_t": marcas_t},
        "graficos": graficos(a, b, d, de, ate, colunas, vista, seq, fase),
        "vista": vista, "seq": seq, "fase": fase,
        "eventos": eventos, "cursores": cursores, "km_curva": km_curva,
        "linha": linha, "s": s, "nomes": {"A": nome_a, "B": nome_b},
    }
