"""O plano alfa (87L): a razão entre a corrente dos dois terminais.

## O que ele é

O diferencial de linha da SEL não compara módulos: compara o NÚMERO COMPLEXO
`k = I_remoto / I_local`, fase por fase. Numa falta externa a mesma corrente
entra por um terminal e sai pelo outro — `k ≈ 1∠180°`. Numa interna as duas
correntes vão para dentro da linha, e `k` vira para perto de 0°. A região de
RESTRIÇÃO é um setor de coroa em volta de 1∠180°, desenhado por dois ajustes:
`87LR` (o raio: de `1/87LR` a `87LR`) e `87LANG` (a abertura, centrada em
180°). Ver `docs/plano-alfa-87l.md`.

## Local e remoto são duas TRINCAS do mesmo registro

O multi-registro ainda não existe. Então o local e o remoto são duas trincas
de corrente que o MESMO arquivo traz — `G1` e `G2` —, como num relé que grava
as duas pontas de um equipamento. Com uma trinca só não há plano: o painel
diz que falta o outro terminal, e não desenha nada.

## Ou um terminal em cada REGISTRO

Com mais de um registro na aba (ver `plot/varios.py`), o local pode ser uma
trinca do IED A e o remoto uma do IED B — os dois relés de uma linha, cada um
com o seu arquivo. O fasor do outro registro é tomado na amostra dele mais
perto do instante da aba e GIRADO pela fração de tempo que sobra
(`e^{jω·Δt}`): é conta exata, sem interpolar a onda. O que resta de erro é o
do ALINHAMENTO, e ele vai escrito no painel em graus:

* pela hora do arquivo, com os dois relógios sincronizados: o erro dos
  relógios — perto de 0,02° com GPS;
* pelo início da falta ou pelo disparo: uma amostra do registro mais lento —
  10,8° a 2000 Hz, 21,6° a 1000 Hz;
* «refinar pela pré-falta», quando pedido: o deslocamento é acertado para a
  corrente de carga atravessar a linha a 180°. Supõe uma pré-falta normal,
  por isso só entra se o usuário pedir, e o resíduo vai escrito.

## A base é o AMPÈRE PRIMÁRIO dos dois lados

TC de 600/5 de um lado e 1200/5 do outro, comparados em secundário, deslocam
todo o traçado por um fator 2 — e isso se lê no plano exatamente como
outfeed. Por isso `k` sai das correntes em PRIMÁRIO. Sem relação declarada
num lado, a corrente fica como foi gravada e o rodapé diz isso: converter por
palpite seria pior.

O `pu` da tabela é outra coisa: é só o tamanho de cada corrente perto da
nominal do TC DELA, para ler «carga» ou «falta» de relance.

## Sem corrente, sem ponto

Quando a corrente do lado do DENOMINADOR está abaixo de `PISO_EM_PU` da base
dele, a razão é ruído dividido por ruído: o ponto não existe. Acontece o tempo
todo em `3I0` e `I2`, que só existem durante a falta, e na carga leve.

## A tela não decide número nenhum

`k`, os módulos em pu, os ângulos e a DECISÃO (restringe, opera, sem
corrente) saem daqui para todo ponto da trajetória. A tela só escolhe qual
ponto é o do cursor e converte em pixel.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.dsp import envoltoria, simetricas
from osclab.formats import conjuntos
from osclab.formats.base import Record
from osclab.plot import alinhamento, conversao, fasorial

#: O tipo do painel. Ver `plot/paineis.py`.
TIPO = "alfa"

#: Os sinais que um plano alfa pode ter, na ordem do menu.
SINAIS = ("A", "B", "C", "3I0", "I2")
NOMES = {"A": "IA", "B": "IB", "C": "IC", "3I0": "3I0", "I2": "I2"}
CORES = {"A": "--fase-a", "B": "--fase-b", "C": "--fase-c",
         "3I0": "--calculado-1", "I2": "--calculado-2"}

#: Até três por painel: mais que isso vira um novelo no plano.
MAXIMO_DE_SINAIS = 3

#: Os típicos da SEL, para quando o arquivo não traz o ajuste — um relé de
#: outro fabricante, ou um COMTRADE sem `.HDR`. A tela diz a origem.
R87_PADRAO = 6.0
ANG87_PADRAO = 195.0

#: Onde o relé escreve a região: o 411L por elemento — o de FASE é o que vale
#: para as correntes de fase do plano —, o 311L num par só. Os valores do
#: parque (25/10/2026) são 6 e 195 nos dois, com o mesmo significado do
#: nosso raio e da nossa abertura: o plano generalizado do 411L (|k| ≤ 1) é
#: o mesmo setor dobrado sobre si, porque a coroa de 1/R a R é simétrica.
NOMES_DO_RAIO = ("87LPR", "87LR")
NOMES_DO_ANGULO = ("87LPA", "87LANG")


def ajuste_lido(ajustes: dict | None, nomes) -> tuple[float, str] | None:
    """`(valor, nome)` do primeiro ajuste que existir e for número."""
    pares = {str(n).strip().upper(): str(v).strip()
             for n, v, *_ in ((ajustes or {}).get("ajustes") or ())}
    for nome in nomes:
        try:
            return float(pares[nome].replace(",", ".")), nome
        except (KeyError, ValueError):
            continue
    return None


def _valor_e_origem(do_painel, lido, padrao):
    """O que vale e por quê: o digitado manda; depois o lido; depois o típico.

    A tela devolve o valor que recebeu, então «digitado» é o que DIFERE do
    lido (ou do típico, sem lido) — igual a ele, a origem continua a dele.
    """
    if do_painel is not None:
        referencia = lido[0] if lido else padrao
        if abs(float(do_painel) - referencia) > 1e-9:
            return float(do_painel), "digitado", ""
    if lido:
        return lido[0], "lido", lido[1]
    return padrao, "padrão", ""

#: Abaixo de 5 % da nominal do TC do denominador não há ponto: a razão de
#: dois ruídos não é medida. É a ordem do limiar da SEL para o 87L.
PISO_EM_PU = 0.05

#: Quantos pontos cada trajetória leva, no máximo. Menos que o plano complexo
#: porque aqui cada ponto leva SEIS números, não dois.
MAXIMO_DE_PONTOS = 4000

RESTRINGE = "restringe"
OPERA = "opera"
SEM_CORRENTE = "sem corrente"


def trincas_de_corrente(registro: Record) -> list:
    """As trincas de CORRENTE com sinal, na ordem do arquivo."""
    return [c for c in conjuntos.de_registro(registro)
            if c.grandeza == "I" and not c.sem_sinal and not c.e_de_linha]


def _escolher(trincas: list, rotulo: str, fora: str = ""):
    """A trinca com este rótulo (`G2`), ou a primeira que não é `fora`."""
    for c in trincas:
        if rotulo and c.rotulo == rotulo and c.rotulo != fora:
            return c
    for c in trincas:
        if c.rotulo != fora:
            return c
    return None


def _fasores_da_trinca(registro: Record, trinca) -> tuple[dict, bool]:
    """`({"A": …, "B": …, "C": …}, convertida)`: o fasor EFICAZ de cada fase
    em cada amostra, em ampère PRIMÁRIO quando o arquivo deixa converter."""
    canais = {c.index: c for c in registro.analog_channels}
    saida = {}
    convertida = True
    for fase, indice in zip(("A", "B", "C"), trinca.abc, strict=True):
        canal = canais[indice]
        valores, lado_final, _ = conversao.converter(registro.analog[indice],
                                                     canal, "primario")
        if lado_final != "primario":
            convertida = False
        saida[fase] = (envoltoria.calcular_fasores(
            valores, registro.trechos, registro.line_frequency) / math.sqrt(2.0))
    zero, _, negativa = simetricas.de_fasores(saida["A"], saida["B"], saida["C"])
    saida["3I0"] = zero
    saida["I2"] = negativa
    return saida, convertida


def _base(registro: Record, trinca, fasores_: dict) -> tuple[float, str]:
    """`(base, origem)`: a nominal PRIMÁRIA do TC, ou o maior do registro."""
    canal = next(c for c in registro.analog_channels if c.index == trinca.abc[0])
    base, _ = fasorial.base_do_canal(registro, canal, "primario", 1.0)
    if base and base > 0:
        return float(base), "nominal do TC"
    maior = 0.0
    for fase in ("A", "B", "C"):
        m = np.abs(fasores_[fase])
        m = m[np.isfinite(m)]
        if m.size:
            maior = max(maior, float(m.max()))
    return (maior or 1.0), "o maior módulo do registro"


def decidir(k: np.ndarray, r87: float, ang87: float) -> np.ndarray:
    """`True` onde `k` está DENTRO da região de restrição.

    Dentro: `1/87LR ≤ |k| ≤ 87LR` e `|∠k − 180°| ≤ 87LANG/2`. A região é
    simétrica sob a inversão de `k` (trocar o ponto de vista), e por isso a
    decisão não depende de qual lado é o denominador.
    """
    modulo = np.abs(k)
    angulo = np.degrees(np.angle(k)) % 360.0
    return ((modulo >= 1.0 / r87) & (modulo <= r87)
            & (np.abs(angulo - 180.0) <= ang87 / 2.0))


def _arredondar(valores: np.ndarray) -> list:
    """Seis algarismos significativos, e `None` onde não há número."""
    return [None if not math.isfinite(v) else float(f"{v:.6g}")
            for v in np.asarray(valores, dtype=np.float64).tolist()]


def _angulo(z: np.ndarray) -> np.ndarray:
    """O ângulo em graus, em (−180, 180], com NaN onde `z` não existe."""
    a = np.degrees(np.angle(z))
    a[~np.isfinite(z)] = np.nan
    return a


def _chave(letra: str, trinca) -> str:
    """`G2` no registro A; `B|G1` no B — a mesma regra dos ids de sinal."""
    return trinca.rotulo if letra == "A" else f"{letra}|{trinca.rotulo}"


def _no_eixo_da_aba(base: Record, indices: np.ndarray, outro: Record,
                    fasores_: dict, d: float) -> dict:
    """Os fasores de `outro` nos instantes da aba (`indices` do A), girados.

    Para cada instante `t` da aba, o instante no outro registro é `t + d`; a
    amostra dele mais perto é `j`, e o fasor dela é girado de `ω·(t + d − t_j)`
    — a fração de amostra que sobra. Fora do outro registro, NaN.
    """
    alvo = base.time[indices] + d
    t = outro.time
    j = np.clip(np.searchsorted(t, alvo), 1, t.size - 1)
    j = np.where(np.abs(t[j - 1] - alvo) <= np.abs(t[j] - alvo), j - 1, j)
    fora = (alvo < t[0] - 1e-12) | (alvo > t[-1] + 1e-12)
    giro = np.exp(1j * 2.0 * np.pi * float(base.line_frequency or 60.0) * (alvo - t[j]))
    saida = {}
    for chave, valores in fasores_.items():
        v = valores[j] * giro
        v[fora] = np.nan + 0j
        saida[chave] = v
    return saida


def _refino(base: Record, indices: np.ndarray, loc: dict, rem: dict) -> dict:
    """O giro que põe a corrente de carga da pré-falta a 180°, e o resíduo.

    A janela é a pré-falta do A, longe das bordas: do segundo ciclo até um
    ciclo antes do início da falta. Soma as três fases.
    """
    f = float(base.line_frequency or 60.0)
    falta = alinhamento.instante_da_falta(base)
    t = base.time[indices]
    if falta is None:
        return {"aplicado": False, "motivo": "sem início de falta no IED A para "
                "saber onde está a pré-falta"}
    janela = (t > t[0] + 1.5 / f) & (t < falta - 1.0 / f)
    soma = 0j
    angulos = []
    for fase in ("A", "B", "C"):
        z = rem[fase][janela] * np.conj(loc[fase][janela])
        z = z[np.isfinite(z)]
        soma += z.sum()
        angulos.append(np.angle(z))
    if not janela.any() or abs(soma) == 0:
        return {"aplicado": False, "motivo": "pré-falta curta demais"}
    correcao = np.pi - np.angle(soma)
    todos = np.concatenate(angulos) + correcao
    residuo = np.degrees(np.std(np.angle(np.exp(1j * (todos - np.pi)))))
    return {"aplicado": True,
            "correcao_graus": round(float(np.degrees(np.angle(np.exp(1j * correcao)))), 2),
            "residuo_graus": round(float(residuo), 2),
            "giro": complex(np.exp(1j * correcao))}


def montar(registro: Record, painel, outros: list | None = None,
           ajustes: dict | None = None) -> dict:
    """O pacote de um plano alfa: trincas, ajustes e a trajetória de cada sinal.

    `outros` é `[(letra, registro, deslocamento)]` — os outros registros da
    aba, com o deslocamento que `plot/alinhamento.deslocamento` deu.
    """
    r87, r87_origem, r87_var = _valor_e_origem(
        getattr(painel, "r87", None), ajuste_lido(ajustes, NOMES_DO_RAIO), R87_PADRAO)
    ang87, ang87_origem, ang87_var = _valor_e_origem(
        getattr(painel, "ang87", None), ajuste_lido(ajustes, NOMES_DO_ANGULO), ANG87_PADRAO)
    vista = "remoto" if getattr(painel, "vista", "local") == "remoto" else "local"
    escolhidos = [s for s in (painel.sinais or ()) if s in SINAIS]
    escolhidos = list(dict.fromkeys(escolhidos))[:MAXIMO_DE_SINAIS]
    if not painel.sinais:
        escolhidos = ["A", "B", "C"]

    pacote = {
        "id": painel.id,
        "tipo": TIPO,
        "nome": painel.nome or "Plano alfa",
        "do_padrao": painel.do_padrao,
        "vista": vista,
        "r87": r87,
        "ang87": ang87,
        "r87_origem": r87_origem,
        "ang87_origem": ang87_origem,
        "sinais": [{"id": s, "sinal": NOMES[s], "cor": CORES[s]}
                   for s in escolhidos],
        "local": None,
        "remoto": None,
        "falta": "",
        "pontos": {"n": [], "t": []},
        "passo": 1,
        "trajetorias": {},
        "rodape": [],
        "trincas": [],
    }

    # As candidatas: as trincas do A e, com mais registros na aba, as de cada
    # um deles, com a letra na chave (`B|G1`). A ordem é só o PADRÃO; a
    # engrenagem deixa escolher (pedido dele, 22/10/2026).
    outros = list(outros or [])
    candidatas = [("A", c, registro, None) for c in trincas_de_corrente(registro)]
    for letra, outro, desl in outros:
        candidatas += [(letra, c, outro, desl) for c in trincas_de_corrente(outro)]
    pacote["trincas"] = [{"rotulo": _chave(ied, c),
                          "nome": c.nome + ("" if ied == "A" else f" · IED {ied}")}
                         for ied, c, _, _ in candidatas]
    por_chave = {_chave(ied, c): (ied, c, r, dd) for ied, c, r, dd in candidatas}

    def escolher(pedido: str, fora: str, preferir_outro: bool):
        if pedido in por_chave and pedido != fora:
            return por_chave[pedido]
        ordem = sorted(candidatas, key=lambda x: (x[0] == "A") if preferir_outro else 0)
        return next((x for x in ordem if _chave(x[0], x[1]) != fora), None)

    local = escolher(getattr(painel, "local", "") or "", "", False)
    # Com outro registro na aba, o remoto padrão é a primeira trinca DELE: os
    # dois terminais de uma linha, cada um no seu arquivo.
    remoto = escolher(getattr(painel, "remoto", "") or "",
                      _chave(local[0], local[1]) if local else "", bool(outros))
    if local is None or remoto is None:
        pacote["falta"] = ("Este registro tem uma trinca de corrente só: o "
                           "plano alfa precisa da corrente do OUTRO terminal. "
                           "Ponha o registro do outro terminal nesta aba, em "
                           "«+ adicionar oscilografia».")
        if local is not None:
            pacote["local"] = {"rotulo": _chave(local[0], local[1]), "nome": local[1].nome}
        return pacote

    pacote["local"] = {"rotulo": _chave(local[0], local[1]), "nome": local[1].nome,
                       "ied": local[0]}
    pacote["remoto"] = {"rotulo": _chave(remoto[0], remoto[1]), "nome": remoto[1].nome,
                        "ied": remoto[0]}

    n = registro.n_samples
    passo = max(1, math.ceil(n / MAXIMO_DE_PONTOS)) if n else 1
    indices = np.arange(0, n, passo, dtype=np.int64)
    tempo = registro.time

    def do_terminal(escolha):
        letra, trinca, reg, desl = escolha
        fas, convertido = _fasores_da_trinca(reg, trinca)
        base, origem = _base(reg, trinca, fas)
        if letra == "A":
            return {k: v[indices] for k, v in fas.items()}, convertido, base, origem
        return (_no_eixo_da_aba(registro, indices, reg, fas, desl["d"]),
                convertido, base, origem)

    do_local, conv_l, base_l, origem_l = do_terminal(local)
    do_remoto, conv_r, base_r, origem_r = do_terminal(remoto)

    # O ângulo ENTRE registros: quanto ele sustenta, e o refino pedido.
    entre = local[0] != remoto[0]
    incerteza = 0.0
    if entre:
        for letra, _, reg, desl in (local, remoto):
            if letra == "A":
                continue
            parte = alinhamento.incerteza_em_graus(registro, reg, desl)
            incerteza = None if (incerteza is None or parte is None) else incerteza + parte
    refino = {"aplicado": False, "motivo": ""}
    if entre and getattr(painel, "refinar", False):
        refino = _refino(registro, indices, do_local, do_remoto)
        if refino.get("aplicado"):
            giro = refino.pop("giro")
            do_remoto = {k: v * giro for k, v in do_remoto.items()}
            incerteza = refino["residuo_graus"]
    pacote["entre_ieds"] = entre
    pacote["incerteza_graus"] = (None if incerteza is None
                                 else round(float(incerteza), 3))
    pacote["refino"] = {k: v for k, v in refino.items() if k != "giro"}

    trajetorias = {}
    for s in escolhidos:
        il = do_local[s]
        ir = do_remoto[s]
        if vista == "local":
            num, den, base_den = ir, il, base_l
        else:
            num, den, base_den = il, ir, base_r
        com_corrente = np.isfinite(den) & (np.abs(den) >= PISO_EM_PU * base_den)
        k = np.full(indices.shape, np.nan + 0j, dtype=np.complex128)
        k[com_corrente] = num[com_corrente] / den[com_corrente]
        dentro = decidir(k, r87, ang87)
        decisao = np.where(~com_corrente, SEM_CORRENTE,
                           np.where(dentro, RESTRINGE, OPERA))
        # Onde nem o fasor existe (o primeiro ciclo), não há decisão.
        decisao = np.where(np.isfinite(den) & np.isfinite(num), decisao, "")
        # Os ângulos de I local e I remoto contados do I LOCAL do mesmo
        # sinal no mesmo instante: o local fica em 0° e o remoto mostra
        # quanto gira em relação a ele — a leitura que a tabela pede.
        with np.errstate(invalid="ignore", divide="ignore"):
            ref = np.where(np.abs(il) > 0, il / np.abs(il), np.nan)
        trajetorias[s] = {
            "re": _arredondar(k.real),
            "im": _arredondar(k.imag),
            "modulo": _arredondar(np.abs(k)),
            "angulo": _arredondar(_angulo(k)),
            "loc_pu": _arredondar(np.abs(il) / base_l),
            "rem_pu": _arredondar(np.abs(ir) / base_r),
            "rem_ang": _arredondar(_angulo(ir * np.conj(ref))),
            "decisao": decisao.tolist(),
        }

    def canais_de(escolha):
        letra, trinca, reg, _ = escolha
        nomes = ", ".join(f'"{reg.analog_channels[i].name}"' for i in trinca.abc)
        return nomes + ("" if letra == "A" else f" (IED {letra})")

    rodape = [
        f"local {pacote['local']['rotulo']} — {canais_de(local)}",
        f"remoto {pacote['remoto']['rotulo']} — {canais_de(remoto)}",
        f"1 pu: {base_l:.4g} A no local ({origem_l}) · {base_r:.4g} A no "
        f"remoto ({origem_r})",
        _rodape_da_regiao(r87, r87_origem, r87_var, ang87, ang87_origem, ang87_var),
        f"sem ponto onde a corrente do denominador fica abaixo de "
        f"{PISO_EM_PU:.0%} da nominal",
    ]
    desligado = any(
        str(n).strip().upper() == "E87L" and str(v).strip().upper().startswith("N")
        for n, v, *_ in ((ajustes or {}).get("ajustes") or ()))
    if desligado:
        rodape.insert(0, "E87L := N — o diferencial de linha está DESLIGADO neste "
                         "relé: a região desenhada é a do ajuste, mas o relé não "
                         "a usou para decidir nada")
    if entre:
        if refino.get("aplicado"):
            rodape.insert(0, f"ângulo entre os dois registros refinado pela "
                          f"pré-falta: girado {refino['correcao_graus']:+.1f}°, "
                          f"resíduo ± {refino['residuo_graus']:.1f}° — supõe a "
                          "carga atravessando a linha")
        elif incerteza is None:
            outros_regs = [reg for letra, _, reg, _ in (local, remoto) if letra != "A"]
            sem_fuso = not alinhamento.fuso_declarado(registro, *outros_regs)
            rodape.insert(0, "ângulo entre os dois registros SEM precisão "
                          "conhecida: " + ("o fuso dos carimbos não foi "
                                           "declarado num dos arquivos"
                                           if sem_fuso else
                                           "o relógio de um deles não está "
                                           "sincronizado")
                          + ". Use «refinar pela pré-falta».")
        else:
            rodape.insert(0, f"ângulo entre os dois registros: ± {incerteza:.2f}°")
            # Relógios travados não bastam entre FABRICANTES diferentes: o
            # atraso do filtro de entrada de cada relé pode não estar
            # compensado no COMTRADE.
            fabs = {alinhamento.fabricante(reg) for _, _, reg, _ in (local, remoto)}
            if len(fabs) > 1 and "" not in fabs:
                rodape.insert(1, "IEDs de fabricantes diferentes: o atraso "
                              "interno do filtro de entrada pode não estar "
                              "compensado no COMTRADE e somar alguns graus")
        if refino.get("motivo"):
            rodape.append(f"refino não aplicado: {refino['motivo']}")
    if not (conv_l and conv_r):
        rodape.append("sem relação de TC declarada num dos lados: k compara as "
                      "correntes como foram gravadas, e pode estar fora de "
                      "base")
    if passo > 1:
        rodape.append(f"registro longo: um ponto a cada {passo} amostras")

    pacote.update({
        "passo": int(passo),
        "pontos": {"n": indices.tolist(),
                   "t": [round(float(x), 9) for x in tempo[indices]]},
        "trajetorias": trajetorias,
        "rodape": rodape,
    })
    return pacote


def _rodape_da_regiao(r87, r_origem, r_var, ang87, a_origem, a_var) -> str:
    """De onde saiu a região de restrição, sem depender do hover."""
    def um(nome, valor, origem, variavel, sufixo=""):
        if origem == "lido":
            return f"{variavel} {valor:g}{sufixo} (do relé)"
        if origem == "digitado":
            return f"{nome} {valor:g}{sufixo} (digitado)"
        return f"{nome} {valor:g}{sufixo} (típico da SEL — o arquivo não traz)"
    return (um("raio", r87, r_origem, r_var) + " · "
            + um("abertura", ang87, a_origem, a_var, "°")
            + "; mude na engrenagem")
