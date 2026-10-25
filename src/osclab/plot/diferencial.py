"""O diferencial de transformador (87T): Iop × Irt, fase por fase.

## O que ele mostra

O 87T compara a corrente que entra no trafo por um lado com a que sai pelo
outro. Depois de as duas irem para a MESMA base (relação, defasamento do grupo
de ligação, retirada da sequência zero), a soma delas — a corrente de
OPERAÇÃO, `Iop` — é zero em carga e em falta externa, e grande em falta
interna. A corrente de RESTRIÇÃO, `Irt`, diz o tamanho da corrente que passa:
quanto maior ela, mais erro de TC se tolera, e é por isso que a característica
sobe em rampa (os slopes). O plano Iop × Irt é como o relé decide.

## Lado 1 e lado 2 são duas TRINCAS do mesmo registro

Como no plano alfa: `G1` e `G2`, escolhíveis. Um relé de trafo grava os dois
enrolamentos no mesmo arquivo, então aqui não falta nada do multi-registro.

## A compensação é aplicada às AMOSTRAS

É o que o relé faz: a matriz de compensação (as 13 da SEL, `0` a `12`) é real,
3 × 3, e multiplica as amostras instantâneas de cada lado. Assim a 2ª e a 5ª
harmônicas passam pelo mesmo caminho que a fundamental, e a harmônica medida
depois é a da corrente DIFERENCIAL — que é onde o relé a mede. Medir a
harmônica de cada lado separado daria outro número.

A matriz `m` gira a sequência positiva de `+m·30°` (e a negativa de `−m·30°`)
e, para `m ≠ 0`, tira a sequência zero:

    M[i][j] = (2/3)·cos(m·30° − (i − j)·120°)        m = 1 … 12
    M = identidade                                    m = 0

Com `m = 1` sai exatamente a `CTC(1)` da IEEE C37.91, `(1/√3)·[[1,−1,0],
[0,1,−1],[−1,0,1]]`; com `m = 12`, `I − (1/3)·[1]`, que só tira a zero.

## A base é o TAP, em SECUNDÁRIO

O relé trabalha em ampère secundário dividido pelo TAP de cada lado — `TAP =
MVA·1000 / (√3 · kV · RTC)`, vezes √3 com TC em delta. Então cada canal vai
para o SECUNDÁRIO antes de tudo, e pelo RTC do AJUSTE — o número com que o
relé faz a conta —, não pela relação declarada no arquivo: o `.CEV` da SEL
grava em primário com relação `1/1`, e a relação do arquivo, quando existe e
discorda do ajuste, já marca o RTC como suspeito. Canal gravado em
secundário entra como está.

## A característica, e o que varia por fabricante

A forma adotada é a de dois slopes com ponto de quebra:

    limiar(Irt) = máx( Pickup,  S1·Irt )                       Irt ≤ BP1
    limiar(Irt) = máx( Pickup,  S1·BP1 + S2·(Irt − BP1) )       Irt > BP1

É a da SEL 787/487E em espírito, mas **cada fabricante desenha a sua**: a
Siemens põe o slope 2 partindo de um «base point» no eixo, e há relés em que o
segundo slope passa pela origem. O desenho e a decisão saem desta forma — e o
rodapé diz isso.

## A decisão, amostra a amostra

    Iop > 87U                                 opera 87U   (ignora harmônica)
    Iop ≤ limiar                              restringe
    2ª da Iop > Bloqueio 2ª                   bloqueado 2ª
    5ª da Iop > Bloqueio 5ª                   bloqueado 5ª
    resto                                     opera

O MODO muda o meio: «por fase» bloqueia só a fase com harmônica; «cruzado»
bloqueia as três quando qualquer uma tem; «restrição» não bloqueia — soma a
harmônica ao limiar (`limiar + Iop·(h2/PCT2 + h5/PCT5)`) e a fase só opera se
passar dele.

## Os ajustes: lidos, deduzidos, suspeitos, digitados, ou faltando

O `.CEV`/`.hdr` da SEL traz `MVA := 25.00` e companhia; o COMTRADE de outro
fabricante não traz nada. Cada ajuste sai daqui com um de cinco estados, e o
**gráfico só é desenhado quando todos têm valor** — o suspeito conta só depois
de aceito. Um ajuste lido que não fecha com o próprio registro (RTC diferente
da relação declarada no arquivo, TAP diferente do calculado, valor fora da
faixa usual) vira SUSPEITO: nunca bloqueia, mas também não é usado sem que
alguém olhe.

## A tela não decide número nenhum

Iop, Irt, o limiar, as harmônicas, a decisão, a curva da característica e os
limites dos eixos saem daqui. A tela escolhe o ponto do cursor e pinta.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.dsp import envoltoria
from osclab.dsp.fasor import ciclo_em_amostras
from osclab.formats import ajustes as ajustes_mod
from osclab.formats import conjuntos
from osclab.formats.base import Record
from osclab.plot import conversao
from osclab.plot.alfa import _escolher

#: O tipo do painel. Ver `plot/paineis.py`.
TIPO = "diferencial"

#: Os sinais: as três fases. Sequência não tem sentido aqui — a compensação
#: já tirou a zero, e a negativa sai das mesmas três.
SINAIS = ("A", "B", "C")
NOMES = {"A": "IA", "B": "IB", "C": "IC"}
CORES = {"A": "--fase-a", "B": "--fase-b", "C": "--fase-c"}

#: Quantos pontos cada trajetória leva, no máximo (como no plano alfa).
MAXIMO_DE_PONTOS = 4000

#: Abaixo desta Iop (pu) a razão harmônica/fundamental é ruído sobre ruído: a
#: harmônica não é medida (sai `None`) e não bloqueia nada.
IOP_MINIMA_PARA_HARMONICA = 0.05

#: Tolerâncias das conferências contra o próprio registro.
TOLERANCIA_DO_TAP = 0.05
TOLERANCIA_DO_RTC = 0.01

RESTRINGE = "restringe"
OPERA = "opera"
OPERA_87U = "opera 87U"
BLOQUEADO_2 = "bloqueado 2ª"
BLOQUEADO_5 = "bloqueado 5ª"

#: Os estados de um ajuste.
COLETADO = "coletado"
SUSPEITO = "suspeito"
FALTA = "falta"
DIGITADO = "digitado"
DEDUZIDO = "deduzido"
ESTADOS = (COLETADO, SUSPEITO, FALTA, DIGITADO, DEDUZIDO)

#: As equações que o usuário escolhe. `[chave, fórmula, quem usa]`. Onde não
#: há certeza de qual fabricante usa qual, o texto diz isso em vez de afirmar.
EQUACOES_IOP = (
    ("entrando", "|I1 + I2|",
     "os dois TCs medem a corrente ENTRANDO no trafo — a convenção usual"),
    ("invertido", "|I1 − I2|",
     "o TC de um lado está ligado ao contrário"),
)
#:
#: Conferido nos manuais em 22/10/2026 (consulta, não teste de campo):
#: SEL-787 (IM 20251212, p. 4.17, «summation of all current magnitudes») e
#: SEL-487E (IM 20260730, Eq. 3.8) somam os módulos — e o manual do 787 avisa
#: que o 387/587 usavam a METADE disso (p. 4.23); GE T60 (5-346, Eq. 5-32) usa
#: o MAIOR dos compensados; Schneider P632 (3-135) usa `0,5·|Ia − Ib|`;
#: Siemens SIPROTEC 5 7UT8x (manual C53000-G5040-C016-R, 6.3.3.6) usa também o
#: MAIOR — «the currents of that measuring point whose RMS value is the
#: largest» — e o próprio manual avisa que mudou em relação ao SIPROTEC 4
#: (7UT6x), cujo manual ainda não temos. ABB série 615/620, função TR2PTDF
#: (manual técnico 1MRS757644 J, Eq. 69 e 70): `|IW1 − IW2| / 2`, a mesma
#: do P632. ABB RET670 (manual técnico 1MRK504164-UEN V, 8.1.8.4): a MAIOR
#: contribuição de todos os enrolamentos E de todas as fases, a mesma para as
#: três fases — a restrição «comum».
EQUACOES_IRT = (
    ("soma", "|I1| + |I2|", "SEL 787 e 487E"),
    ("media", "(|I1| + |I2|) / 2", "Ingeteam PD300 · SEL 387/587, os antigos"),
    ("maximo", "máx(|I1|, |I2|)", "GE T60 · Siemens SIPROTEC 5 (7UT8x)"),
    ("meia", "|I1 − I2| / 2", "Schneider P632 · ABB 615/620 (TR2PTDF)"),
    ("comum", "máx de |I1| e |I2| nas TRÊS fases", "ABB RET670"),
)
#: A Irt sugerida por fabricante, das linhas acima.
IRT_DO_FABRICANTE = {"SEL": "soma", "GE": "maximo", "Schneider": "meia",
                     "Siemens": "maximo", "ABB": "meia",
                     # PD300 User Manual, Apêndice I (p. 77–78): Idif = |Σ I·C/Tap|
                     # e I restraint = (|I1·C1/Tap1| + |I2·C2/Tap2|) / 2.
                     "Ingeteam": "media"}

#: As FORMAS da característica, conferidas nos manuais em 22/10/2026:
#: `[chave, nome, quem usa, ajustes que ela exige]`. Os slopes são sempre
#: `Slope 1` e `Slope 2` aqui; o nome de cada fabricante para eles está na
#: dica (a ABB chama de `SlopeSection2/3`, a Schneider de `m1/m2`).
FORMAS = (
    ("origem_quebra", "dois slopes pela origem, quebra no BP1",
     "SEL 787 (IM p. 4.16)", ("pickup", "slp1")),
    ("origem", "um slope pela origem",
     "SEL 487E (o SLP2 só vale com falta externa detectada)", ("pickup", "slp1")),
    ("origem_dupla", "dois slopes pela origem, transição entre BP1 e BP2",
     "GE T60 (5-347)", ("pickup", "slp1", "bp1", "slp2", "bp2")),
    ("tres_trechos", "plana até BP1, Slope 1 até BP2, Slope 2 depois",
     "Siemens SIPROTEC 5 · ABB 615/620 e RET670 · Ingeteam PD300/PD500",
     ("pickup", "slp1", "bp1", "slp2", "bp2")),
    ("p632", "plana até ½·pickup, m1 até IR,m2, m2 depois",
     "Schneider P632 (3-135)", ("pickup", "slp1", "slp2", "bp2")),
)
FORMA_DO_FABRICANTE = {"SEL": "origem_quebra", "GE": "origem_dupla",
                       "Siemens": "tres_trechos", "ABB": "tres_trechos",
                       # Catálogos PD300 p.6 e PD500 p.5: «Sensibilidad» plana
                       # até «I paso 1», α1 até «I paso 2», α2 depois.
                       "Ingeteam": "tres_trechos",
                       "Schneider": "p632"}
_FORMA = {f[0]: f for f in FORMAS}

#: As opções de compensação (grupo de ligação): `0` a `12`, em passos de 30°.
OPCOES_DE_COMPENSACAO = tuple(
    (str(m), "0 — sem compensação" if m == 0 else f"{m} — {m * 30}°"
     + (" (só tira a zero)" if m == 12 else ""))
    for m in range(13))

#: Os ajustes, na ordem da caixa. `sel` é a variável na SEL (787/487E). A
#: Siemens não grava ajuste no COMTRADE, então não há coluna dela: tudo a
#: digitar. Onde não há certeza do nome da variável, ele fica vazio.
AJUSTES = (
    # id, grupo, rótulo técnico, unidade, tipo, mínimo, máximo, sel, dica
    ("mva", "compensação", "Potência nominal", "MVA", "num", 0.5, 2000.0, "MVA",
     "Potência nominal do trafo: a base do TAP."),
    ("v1", "compensação", "V nominal 1", "kV", "num", 0.2, 800.0, "VWDG1",
     "Tensão nominal do lado 1, fase-fase."),
    ("v2", "compensação", "V nominal 2", "kV", "num", 0.2, 800.0, "VWDG2",
     "Tensão nominal do lado 2, fase-fase."),
    ("rtc1", "compensação", "RTC 1", "", "num", 1.0, 10000.0, "CTR1",
     "Relação do TC do lado 1 (200/5 = 40)."),
    ("rtc2", "compensação", "RTC 2", "", "num", 1.0, 10000.0, "CTR2",
     "Relação do TC do lado 2."),
    ("con1", "compensação", "Conexão do TC 1", "", "op", None, None, "W1CT",
     "Em delta, o TAP ganha √3."),
    ("con2", "compensação", "Conexão do TC 2", "", "op", None, None, "W2CT",
     "Em delta, o TAP ganha √3."),
    ("ctc1", "compensação", "Grupo de ligação / compensação 1", "", "op", None,
     None, "W1CTC", "Quanto este lado gira, em passos de 30°; diferente de 0 "
     "também tira a sequência zero."),
    ("ctc2", "compensação", "Grupo de ligação / compensação 2", "", "op", None,
     None, "W2CTC", "Num Dyn1, o lado 2 gira 30° a mais que o lado 1."),
    ("tap1", "compensação", "TAP 1", "A", "num", 0.1, 50.0, "TAP1",
     "Corrente nominal do trafo vista no secundário do TC 1."),
    ("tap2", "compensação", "TAP 2", "A", "num", 0.1, 50.0, "TAP2",
     "O mesmo, lado 2."),
    ("forma", "característica", "Forma da característica", "", "op", None,
     None, "", "O desenho da curva muda de fabricante para fabricante — ver o "
     "manual de cada um. A do relé do registro vem sugerida."),
    ("pickup", "característica", "Pickup (Idiff>)", "pu", "num", 0.05, 1.0,
     "O87P", "Abaixo disto a diferencial nunca opera."),
    ("slp1", "característica", "Slope 1", "%", "num", 5.0, 90.0, "SLP1",
     "Primeiro slope da característica."),
    ("bp1", "característica", "Breakpoint 1", "pu", "num", 0.1, 20.0, "IRS1",
     "Fim do primeiro trecho da curva."),
    ("slp2", "característica", "Slope 2", "%", "num", 5.0, 150.0, "SLP2",
     "Segundo slope: falta externa forte, TC saturando."),
    ("bp2", "característica", "Breakpoint 2", "pu", "num", 0.5, 40.0, "",
     "Onde começa o último trecho (GE, Siemens, ABB, Schneider)."),
    ("u87", "característica", "Pickup sem restrição (87U)", "pu", "num", 3.0,
     40.0, "U87P", "Opera acima disto sem olhar curva nem harmônica."),
    ("u87h", "característica", "Pickup que ignora harmônica", "pu", "num", 1.0,
     40.0, "", "Opcional. Acima disto a harmônica não bloqueia, mas a curva "
     "continua valendo — o Idiff>> do P632. O de cima é o Idiff>>>."),
    ("pct2", "harmônicas", "Bloqueio 2ª harmônica", "%", "num", 0.0, 50.0,
     "PCT2", "2ª da corrente diferencial que bloqueia (energização). 0 desliga."),
    ("pct5", "harmônicas", "Bloqueio 5ª harmônica", "%", "num", 0.0, 80.0,
     "PCT5", "5ª que bloqueia (sobre-excitação). 0 desliga."),
    ("ordens", "harmônicas", "Ordens do bloqueio de inrush", "", "op", None,
     None, "", "Só a 2ª, ou a 2ª e a 4ª juntas (√(I2² + I4²)) — opção do PD300."),
    ("lim_harm", "harmônicas", "Diferencial mínima para bloquear", "pu", "num",
     0.05, 2.0, "", "Opcional. Abaixo disto a harmônica não bloqueia — o "
     "«Differential threshold» do PD300."),
    ("max5", "harmônicas", "Diferencial máxima da 5ª", "pu", "num", 1.0, 40.0,
     "", "Opcional. Acima disto a 5ª deixa de bloquear — o P632 só bloqueia "
     "abaixo de 4·Iref."),
    ("modo", "harmônicas", "Modo de bloqueio (cross-blocking)", "", "op", None,
     None, "HBLK", "Só a fase com harmônica, as três (cruzado), ou a harmônica "
     "somada à restrição."),
    ("iop", "cálculo", "Equação da Iop", "", "op", None, None, "",
     "Como se somam as correntes dos dois lados."),
    ("irt", "cálculo", "Equação da Irt", "", "op", None, None, "",
     "Como se forma a corrente de restrição. Cada fabricante usa uma."),
)
#: As opções de cada ajuste de escolha: `[valor, rótulo]`.
OPCOES = {
    "con1": (("Y", "estrela (Y)"), ("D", "delta (Δ)")),
    "con2": (("Y", "estrela (Y)"), ("D", "delta (Δ)")),
    "ctc1": OPCOES_DE_COMPENSACAO,
    "ctc2": OPCOES_DE_COMPENSACAO,
    "forma": tuple((c, f"{r} — {q}") for c, r, q, _ in FORMAS),
    "ordens": (("2", "só a 2ª"), ("24", "2ª + 4ª")),
    "modo": (("fase", "por fase"), ("cruzado", "cruzado (cross-blocking)"),
             ("restricao", "restrição harmônica")),
    "iop": tuple((c, f"{f} — {q}") for c, f, q in EQUACOES_IOP),
    "irt": tuple((c, f"{f} — {q}") for c, f, q in EQUACOES_IRT),
}
#: Os que nascem DEDUZIDOS quando ninguém os deu. A conexão de TC em estrela
#: é o caso de quase todo trafo da distribuição, mas é palpite: entra como
#: deduzido, com a frase dizendo isso.
_POR_ID = {a[0]: a for a in AJUSTES}


def trincas_de_corrente(registro: Record) -> list:
    """As trincas de corrente, as COM sinal primeiro.

    Diferente do plano alfa, a trinca SEM sinal entra (no fim da lista): na
    energização o lado 2 está aberto e passa o registro inteiro em zero — e é
    exatamente o caso que o bloqueio por 2ª harmônica existe para resolver.
    Tirá-la deixaria o painel sem o segundo lado justo ali.
    """
    todas = [c for c in conjuntos.de_registro(registro)
             if c.grandeza == "I" and not c.e_de_linha]
    return ([c for c in todas if not c.sem_sinal]
            + [c for c in todas if c.sem_sinal])


# ---------------------------------------------------------------------------
# Os ajustes
# ---------------------------------------------------------------------------

def manuais_de(cru) -> dict:
    """O que a tela mandou: `{"valores": {id: valor}, "aceitos": [id, …]}`.

    Peneirado aqui, porque dado da tela o servidor não aceita de olhos
    fechados: id desconhecido some, número que não é número some, opção que
    não existe some.
    """
    if not isinstance(cru, dict):
        return {"valores": {}, "aceitos": []}
    valores = {}
    for chave, valor in (cru.get("valores") or {}).items():
        definicao = _POR_ID.get(str(chave))
        if definicao is None or valor is None or valor == "":
            continue
        if definicao[4] == "num":
            numero = _numero(valor)
            if numero is not None:
                valores[definicao[0]] = numero
        elif str(valor) in {v for v, _ in OPCOES[definicao[0]]}:
            valores[definicao[0]] = str(valor)
    aceitos = [str(x) for x in (cru.get("aceitos") or []) if str(x) in _POR_ID]
    return {"valores": valores, "aceitos": aceitos}


def _numero(cru) -> float | None:
    try:
        valor = float(str(cru).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return valor if math.isfinite(valor) else None


def fabricante(registro: Record, lidos: dict) -> str:
    """`SEL`, `Siemens`, `GE`, `Schneider`, `ABB` ou `""`, pelo que o
    arquivo diz de si mesmo."""
    texto = " ".join([registro.device_id or "", registro.station or "",
                      registro.format_name or ""]).upper()
    if "SEL" in texto or registro.format_name.lower() == "cev":
        return "SEL"
    if any(v[7] and v[7] in lidos for v in AJUSTES):
        return "SEL"
    if "SIPROTEC" in texto or "SIEMENS" in texto or "7UT" in texto:
        return "Siemens"
    if "MICOM" in texto or "P63" in texto or "SCHNEIDER" in texto:
        return "Schneider"
    if "T60" in texto or "T35" in texto or "MULTILIN" in texto or " GE " in f" {texto} ":
        return "GE"
    if "INGETEAM" in texto or "INGEPAC" in texto or "PD300" in texto or "PD500" in texto:
        return "Ingeteam"
    if "ABB" in texto or "RET6" in texto or "REF6" in texto or "RET5" in texto:
        return "ABB"
    return ""


def lidos_do_arquivo(ajustes: dict | None) -> dict:
    """`{NOME: texto bruto}` do bloco de ajustes que `formats/ajustes` leu."""
    saida = {}
    for par in (ajustes or {}).get("ajustes") or ():
        if len(par) >= 2:
            saida[str(par[0]).strip().upper()] = str(par[1]).strip()
    return saida


def lidos_de_texto(texto: str) -> dict:
    """O mesmo, de um texto `NOME := VALOR` solto (o `.hdr` colado)."""
    return {nome: valor for nome, valor in ajustes_mod.pares(texto)}


def _interpretar(id_: str, bruto: str):
    """O valor que um texto lido do relé quer dizer, ou `None`."""
    texto = bruto.strip().strip('"').upper()
    if id_ in ("con1", "con2"):
        if texto.startswith(("Y", "W")):
            return "Y"
        if texto.startswith("D"):
            return "D"
        return None
    if id_ in ("ctc1", "ctc2"):
        numero = _numero(texto)
        if numero is None or numero != int(numero) or not 0 <= numero <= 12:
            return None
        return str(int(numero))
    if id_ == "modo":
        # HBLK do SEL-787: `Y` liga o bloqueio COMUM (cross-phase) pela 2ª e
        # pela 4ª (IM 787, p. 4.21). `N` não diz o modo — pode ser que só a
        # restrição harmônica (HRSTR) esteja ligada —, então não vira valor.
        return "cruzado" if texto.startswith("Y") else None
    if id_ in ("pct2", "pct5") and texto == "OFF":
        return 0.0                         # o relé escreve OFF; aqui é 0
    return _numero(texto)


def tap_calculado(mva, kv, rtc, conexao) -> float | None:
    """`MVA·1000 / (√3·kV·RTC)`, vezes √3 com TC em delta."""
    if not (mva and kv and rtc) or mva <= 0 or kv <= 0 or rtc <= 0:
        return None
    tap = mva * 1000.0 / (math.sqrt(3.0) * kv * rtc)
    return tap * math.sqrt(3.0) if conexao == "D" else tap


def _relacao_da_trinca(registro: Record, trinca) -> float:
    """A relação de TC declarada no arquivo, ou 0.

    `1/1` não é declaração de relação nenhuma: é o arquivo dizendo que o
    valor gravado já é o primário (o `.CEV` da SEL faz isso). Tomá-la como
    RTC acusaria de suspeito todo ajuste lido.
    """
    if not trinca:
        return 0.0
    canais = {c.index: c for c in registro.analog_channels}
    razao = conversao.relacao(canais[trinca.abc[0]])
    return razao if razao > 1.0 else 0.0


def nomes_por_terminal(lidos: dict) -> dict[str, str]:
    """Os nomes do SEL-487E, que ajusta POR TERMINAL e não por lado.

    O `E87` diz quais terminais entram no diferencial (`S,T`; no `.CEV` vem
    entre aspas), e na ordem em que entram: o primeiro é o lado 1, o segundo o
    lado 2. Daí `VTERMS`, `CTRS`, `CTCONS`, `TSCTC` e `TAPS` são do lado 1 —
    levantamento dos 27 registros de 487E do parque, 24/10/2026. Sem `E87`
    (o 787, que escreve `CTR1`, `TAP1`…), devolve vazio e vale a coluna `sel`.

    O bloqueio por harmônica do 487E é sempre comum às fases quando ligado
    (`E87HB`), pelo levantamento do manual; por isso ele responde pelo modo.
    """
    bruto = str(lidos.get("E87", "")).replace('"', "").strip().upper()
    terminais = [x.strip() for x in bruto.split(",") if x.strip()]
    if len(terminais) < 2 or not all(len(x) == 1 and x.isalpha() for x in terminais):
        return {}
    um, dois = terminais[0], terminais[1]
    return {"v1": f"VTERM{um}", "v2": f"VTERM{dois}",
            "rtc1": f"CTR{um}", "rtc2": f"CTR{dois}",
            "con1": f"CTCON{um}", "con2": f"CTCON{dois}",
            "ctc1": f"T{um}CTC", "ctc2": f"T{dois}CTC",
            "tap1": f"TAP{um}", "tap2": f"TAP{dois}",
            "modo": "E87HB"}


def resolver(registro: Record, lidos: dict, manuais: dict, fab: str,
             lado1=None, lado2=None) -> list[dict]:
    """Cada ajuste com o valor que vale, o estado e o porquê.

    A ordem de quem manda: o DIGITADO, depois o LIDO (que vira SUSPEITO se não
    fecha com o registro e ninguém aceitou), depois o DEDUZIDO, e por fim
    FALTA.
    """
    valores = manuais.get("valores") or {}
    aceitos = set(manuais.get("aceitos") or ())
    relacoes = {"rtc1": _relacao_da_trinca(registro, lado1),
                "rtc2": _relacao_da_trinca(registro, lado2)}
    por_terminal = nomes_por_terminal(lidos) if fab == "SEL" else {}
    campos: dict[str, dict] = {}

    def vale(id_):
        return campos[id_]["valor"] if id_ in campos else None

    for (id_, grupo, rotulo, unidade, tipo, minimo, maximo, var_sel,
         dica) in AJUSTES:
        campo = {"id": id_, "grupo": grupo, "rotulo": rotulo,
                 "unidade": unidade, "tipo": tipo, "dica": dica,
                 "minimo": minimo, "maximo": maximo,
                 "opcoes": [list(o) for o in OPCOES.get(id_, ())],
                 "valor": None, "estado": FALTA, "variavel": "", "bruto": "",
                 "motivo": "", "como": "", "sugestao": None}
        variavel = por_terminal.get(id_, var_sel) if fab == "SEL" else ""
        if id_ in valores:
            campo.update(valor=valores[id_], estado=DIGITADO)
        elif variavel and variavel in lidos:
            interpretado = _interpretar(id_, lidos[variavel])
            if interpretado is not None:
                campo.update(valor=interpretado, estado=COLETADO,
                             variavel=variavel,
                             bruto=f"{variavel} := {lidos[variavel]}")
        campos[id_] = campo

    # O 487E diz o modo em DOIS ajustes: `E87HB` (bloqueio, comum às fases) e
    # `E87HR` (restrição harmônica). Com o bloqueio desligado e a restrição
    # ligada — 4 dos 27 registros de 487E do parque —, o modo é a restrição;
    # lendo só o `E87HB`, o painel ficava sem curva por «falta o modo».
    if (por_terminal and campos["modo"]["estado"] == FALTA
            and str(lidos.get("E87HB", "")).strip().upper().startswith("N")
            and str(lidos.get("E87HR", "")).strip().upper().startswith("Y")):
        campos["modo"].update(valor="restricao", estado=COLETADO, variavel="E87HR",
                              bruto=f"E87HB := {lidos['E87HB']}, E87HR := {lidos['E87HR']}")

    # Deduzidos, na ordem em que um depende do outro.
    for id_, como in (("con1", "estrela — o caso usual; o arquivo não disse"),
                      ("con2", "estrela — o caso usual; o arquivo não disse")):
        if campos[id_]["estado"] == FALTA:
            campos[id_].update(valor="Y", estado=DEDUZIDO, como=como)
    for lado in ("1", "2"):
        rtc = campos["rtc" + lado]
        if rtc["estado"] == FALTA and relacoes["rtc" + lado] > 0:
            rtc.update(valor=relacoes["rtc" + lado], estado=DEDUZIDO,
                       como="a relação declarada no arquivo")
        tap = campos["tap" + lado]
        calculado = tap_calculado(vale("mva"), vale("v" + lado),
                                  vale("rtc" + lado), vale("con" + lado))
        if tap["estado"] == FALTA and calculado:
            tap.update(valor=round(calculado, 4), estado=DEDUZIDO,
                       como=f"= Potência nominal·1000 / (√3 · V nominal {lado}"
                            f" · RTC {lado})"
                            + (" · √3" if vale("con" + lado) == "D" else ""))
    if campos["iop"]["estado"] == FALTA:
        campos["iop"].update(valor="entrando", estado=DEDUZIDO,
                             como="a convenção usual: os TCs medem a corrente "
                                  "entrando no trafo")
    if campos["ordens"]["estado"] == FALTA:
        campos["ordens"].update(valor="2", estado=DEDUZIDO,
                                como="só a 2ª, o caso comum")
    if campos["max5"]["estado"] == FALTA and fab == "Schneider":
        campos["max5"].update(valor=4.0, estado=DEDUZIDO,
                              como="o P632 só bloqueia pela 5ª abaixo de "
                                   "4·Iref (manual, p. 3-141)")
    if campos["forma"]["estado"] == FALTA:
        forma = FORMA_DO_FABRICANTE.get(fab, "origem_quebra")
        if fab == "SEL" and "487" in (registro.device_id or ""):
            forma = "origem"
        campos["forma"].update(
            valor=forma, estado=DEDUZIDO,
            como=(f"a de {_FORMA[forma][2]}" if fab
                  else "sem fabricante identificado: a do SEL 787"))
    if campos["irt"]["estado"] == FALTA:
        sugerida = IRT_DO_FABRICANTE.get(fab, "soma")
        if fab == "ABB" and "670" in (registro.device_id or ""):
            sugerida = "comum"
        campos["irt"].update(
            valor=sugerida, estado=DEDUZIDO,
            como=(f"a de {fab}, conferida no manual"
                  + (" do SIPROTEC 5 — no SIPROTEC 4 pode ser outra"
                     if fab == "Siemens" else
                     (" do RET670" if sugerida == "comum"
                      else " da série 615/620 — no RET670 é a comum")
                     if fab == "ABB" else "") if fab
                  else "sem fabricante identificado: a soma"))

    # As conferências contra o próprio registro: só no que veio do ARQUIVO.
    for id_, campo in campos.items():
        if campo["estado"] not in (COLETADO, DIGITADO):
            continue
        motivo, sugestao = _conferir(id_, campo, campos, relacoes)
        if not motivo:
            continue
        if campo["estado"] == DIGITADO:
            # Digitado não vira suspeito — foi alguém que escreveu —, mas o
            # aviso vai junto.
            campo["motivo"] = motivo
            continue
        campo["motivo"] = motivo
        campo["sugestao"] = sugestao
        if id_ not in aceitos:
            campo["estado"] = SUSPEITO
    return [campos[a[0]] for a in AJUSTES]


def _conferir(id_, campo, campos, relacoes) -> tuple[str, dict | None]:
    """`(motivo, sugestão)`: o que não fecha com o registro, ou `("", None)`."""
    valor = campo["valor"]
    if campo["tipo"] == "num":
        minimo, maximo = campo["minimo"], campo["maximo"]
        if id_ in ("pct2", "pct5") and valor == 0:
            return "", None
        if valor < minimo or valor > maximo:
            return (f"fora da faixa usual ({minimo:g} a {maximo:g} "
                    f"{campo['unidade']})".replace(" )", ")"), None)
    if id_ in ("rtc1", "rtc2") and relacoes[id_] > 0:
        declarada = relacoes[id_]
        if abs(valor / declarada - 1.0) > TOLERANCIA_DO_RTC:
            return (f"o arquivo declara a relação {declarada:g}",
                    {"valor": declarada, "texto": f"usar {declarada:g} (do arquivo)"})
    if id_ in ("tap1", "tap2"):
        lado = id_[-1]
        calculado = tap_calculado(
            campos["mva"]["valor"], campos["v" + lado]["valor"],
            campos["rtc" + lado]["valor"], campos["con" + lado]["valor"])
        if calculado and abs(valor / calculado - 1.0) > TOLERANCIA_DO_TAP:
            return (f"difere {100 * (valor / calculado - 1):+.0f} % do calculado "
                    f"por Potência nominal, V nominal e RTC ({calculado:.3g} A)",
                    {"valor": round(calculado, 4),
                     "texto": f"usar {calculado:.3g} (calculado)"})
    return "", None


def placar(campos: list[dict]) -> dict:
    """Quantos ajustes em cada estado."""
    contagem = {e: 0 for e in ESTADOS}
    for c in campos:
        contagem[c["estado"]] += 1
    return contagem


#: Na forma do SEL 787 o segundo slope é OPCIONAL, os dois juntos: há relé
#: de um slope só, e obrigá-lo a digitar um Slope 2 igual ao 1 seria pedir um
#: ajuste que ele não tem. Um sem o outro não fecha a característica — aí os
#: dois faltam.
OPCIONAIS = ("bp1", "slp2")
#: Os ajustes da característica, que entram ou não conforme a forma.
DA_CARACTERISTICA = ("pickup", "slp1", "bp1", "slp2", "bp2")


def _forma_de(campos: list[dict]) -> str:
    por_id = {c["id"]: c for c in campos}
    forma = por_id["forma"]["valor"] if "forma" in por_id else None
    return forma if forma in _FORMA else "origem_quebra"


def um_slope(campos: list[dict]) -> bool:
    """A curva desenhada é de UM slope: a do 487E, ou a do 787 com Breakpoint
    1 e Slope 2 em branco."""
    forma = _forma_de(campos)
    if forma == "origem":
        return True
    por_id = {c["id"]: c for c in campos}
    return forma == "origem_quebra" and all(
        por_id[i]["estado"] == FALTA for i in OPCIONAIS)


def nao_usados(campos: list[dict]) -> set:
    """Os ajustes da característica que a forma escolhida NÃO usa."""
    forma = _forma_de(campos)
    usados = set(_FORMA[forma][3])
    if forma == "origem_quebra" and not um_slope(campos):
        usados |= set(OPCIONAIS)
    return set(DA_CARACTERISTICA) - usados


#: Ajustes que só alguns relés têm: em branco, simplesmente não entram.
SEMPRE_OPCIONAIS = ("u87h", "lim_harm", "max5")


def faltam(campos: list[dict]) -> list[dict]:
    """Os ajustes sem valor que valha: os que faltam e os suspeitos não aceitos."""
    pular = nao_usados(campos) | set(SEMPRE_OPCIONAIS)
    return [{"id": c["id"], "rotulo": c["rotulo"], "estado": c["estado"]}
            for c in campos
            if c["estado"] in (FALTA, SUSPEITO) and c["id"] not in pular]


# ---------------------------------------------------------------------------
# A conta
# ---------------------------------------------------------------------------

def matriz_de_compensacao(m: int) -> np.ndarray:
    """A matriz SEL/IEEE `m` (0 a 12). Ver o cabeçalho do módulo."""
    if m == 0:
        return np.eye(3)
    i = np.arange(3)[:, None]
    j = np.arange(3)[None, :]
    return (2.0 / 3.0) * np.cos(np.radians(m * 30.0 - (i - j) * 120.0))


def limiar(irt: np.ndarray, pickup: float, slp1: float, bp1: float | None,
           slp2: float | None, forma: str = "origem_quebra",
           bp2: float | None = None) -> np.ndarray:
    """O limiar de operação para cada `Irt`, na FORMA de cada fabricante.

    `slp1`/`slp2` em %. As cinco formas:

    * `origem_quebra` (SEL 787): `S1·Irt` até BP1, depois `S2` a partir do
      ponto da quebra; sem BP1 ou sem S2, um slope só. Pickup por baixo.
    * `origem` (SEL 487E): `S1·Irt`, um slope só. O S2 do 487E só entra com
      falta externa detectada pelo relé — lógica interna dele, que o arquivo
      não traz.
    * `origem_dupla` (GE T60): `S1·Irt` até BP1, `S2·Irt` a partir de BP2, e
      entre os dois a transição. O manual diz «cubic spline»; aqui é a cúbica
      de Hermite que casa valor e inclinação nas duas pontas — a mesma ideia,
      sem os coeficientes internos do relé.
    * `tres_trechos` (Siemens SIPROTEC 5, ABB 615/620 e RET670): o pickup
      plano até BP1, `S1` dali até BP2, `S2` depois.
    * `p632` (Schneider): plano até `½·pickup`, `m1` (S1) até IR,m2 (BP2),
      `m2` (S2) depois — as equações da p. 3-135 do manual.
    """
    irt = np.asarray(irt, dtype=np.float64)
    s1 = slp1 / 100.0
    s2 = None if slp2 is None else slp2 / 100.0
    if forma == "origem" or (forma == "origem_quebra" and (bp1 is None or s2 is None)):
        return np.maximum(pickup, s1 * irt)
    if forma == "origem_quebra":
        rampa = np.where(irt <= bp1, s1 * irt, s1 * bp1 + s2 * (irt - bp1))
        return np.maximum(pickup, rampa)
    if forma == "origem_dupla":
        y1, y2 = s1 * bp1, s2 * bp2
        largura = max(bp2 - bp1, 1e-9)
        u = np.clip((irt - bp1) / largura, 0.0, 1.0)
        h00, h10 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u
        h01, h11 = -2 * u**3 + 3 * u**2, u**3 - u**2
        meio = h00 * y1 + h10 * largura * s1 + h01 * y2 + h11 * largura * s2
        rampa = np.where(irt <= bp1, s1 * irt, np.where(irt >= bp2, s2 * irt, meio))
        return np.maximum(pickup, rampa)
    if forma == "p632":
        bp1 = 0.5 * pickup
    rampa = np.where(irt <= bp1, pickup,
                     np.where(irt <= bp2, pickup + s1 * (irt - bp1),
                              pickup + s1 * (bp2 - bp1) + s2 * (irt - bp2)))
    return np.maximum(pickup, rampa)


def _harmonica(x: np.ndarray, trechos, frequencia: float, h: int) -> np.ndarray:
    """O fasor da harmônica `h` em cada amostra, janela de UM ciclo.

    A mesma conta de `envoltoria.fasores`, girando `h` vezes mais depressa —
    e sem o estimador cosseno, que é de fundamental.
    """
    saida = np.full(x.shape, np.nan + 0j, dtype=np.complex128)
    for trecho in trechos:
        n = ciclo_em_amostras(trecho.taxa_hz, frequencia)
        fatia = (..., slice(trecho.inicio, trecho.fim))
        pedaco = x[fatia]
        if n < 4 or pedaco.shape[-1] < n + 2:
            continue
        k = np.arange(pedaco.shape[-1], dtype=np.float64)
        giro = np.exp(-2j * np.pi * h * k / n)
        saida[fatia] = 2.0 * np.conj(giro) * envoltoria.media_do_ciclo(
            pedaco.astype(np.complex128) * giro, n)
    return saida


def _ondas_do_lado(registro: Record, trinca, rtc: float) -> tuple[np.ndarray, bool]:
    """As três ondas do lado em AMPÈRE SECUNDÁRIO, e se alguma estava em
    primário (e foi dividida pelo RTC do ajuste)."""
    canais = {c.index: c for c in registro.analog_channels}
    linhas = []
    do_primario = False
    for indice in trinca.abc:
        valores = np.asarray(registro.analog[indice], dtype=np.float64)
        if canais[indice].is_primary:
            valores = valores / float(rtc)
            do_primario = True
        linhas.append(valores)
    return np.vstack(linhas), do_primario


def calcular(registro: Record, lado1, lado2, valor: dict) -> dict:
    """Iop, Irt, limiar, 2ª, 5ª e decisão de cada fase, em cada amostra."""
    trechos = registro.trechos
    f = registro.line_frequency
    x1, prim1 = _ondas_do_lado(registro, lado1, valor["rtc1"])
    x2, prim2 = _ondas_do_lado(registro, lado2, valor["rtc2"])
    c1 = matriz_de_compensacao(int(valor["ctc1"])) @ x1 / float(valor["tap1"])
    c2 = matriz_de_compensacao(int(valor["ctc2"])) @ x2 / float(valor["tap2"])
    sinal = -1.0 if valor["iop"] == "invertido" else 1.0
    d = c1 + sinal * c2

    raiz2 = math.sqrt(2.0)
    f1 = envoltoria.calcular_fasores(c1, trechos, f) / raiz2
    f2 = envoltoria.calcular_fasores(c2, trechos, f) / raiz2
    fd = envoltoria.calcular_fasores(d, trechos, f) / raiz2
    iop = np.abs(fd)
    a, b = np.abs(f1), np.abs(f2)
    maior = np.maximum(a, b)
    irt = {"media": (a + b) / 2.0, "soma": a + b, "maximo": maior,
           "meia": np.abs(f1 - sinal * f2) / 2.0,
           # A do RET670: a maior das contribuições, em TODAS as fases, a
           # mesma para as três.
           "comum": np.broadcast_to(np.fmax.reduce(maior, axis=0),
                                    maior.shape)}[valor["irt"]]

    with np.errstate(invalid="ignore", divide="ignore"):
        medivel = iop >= IOP_MINIMA_PARA_HARMONICA
        h2 = np.where(medivel, 100.0 * np.abs(_harmonica(d, trechos, f, 2))
                      / raiz2 / iop, np.nan)
        h5 = np.where(medivel, 100.0 * np.abs(_harmonica(d, trechos, f, 5))
                      / raiz2 / iop, np.nan)
        if valor.get("ordens") == "24":
            # PD300 (p. 41): a 2ª e a 4ª somadas em quadratura.
            h4 = np.where(medivel, 100.0 * np.abs(_harmonica(d, trechos, f, 4))
                          / raiz2 / iop, np.nan)
            h2 = np.sqrt(h2 ** 2 + h4 ** 2)

    lim = limiar(irt, valor["pickup"], valor["slp1"], valor["bp1"], valor["slp2"],
                 valor.get("forma") or "origem_quebra", valor.get("bp2"))
    decisao = decidir(iop, lim, h2, h5, valor)
    return {"iop": iop, "irt": irt, "limiar": lim, "h2": h2, "h5": h5,
            "decisao": decisao, "do_primario": prim1 or prim2}


def decidir(iop, lim, h2, h5, valor) -> np.ndarray:
    """A decisão de cada fase (linhas) em cada amostra (colunas)."""
    pct2, pct5, u87 = valor["pct2"], valor["pct5"], valor["u87"]
    modo = valor["modo"]
    h2z = np.nan_to_num(h2, nan=0.0)
    h5z = np.nan_to_num(h5, nan=0.0)
    b2 = (pct2 > 0) & (h2z > pct2)
    b5 = (pct5 > 0) & (h5z > pct5)
    # A harmônica só bloqueia dentro da sua faixa de diferencial: acima de um
    # mínimo (PD300), a 5ª abaixo de um máximo (P632, 4·Iref), e nenhuma acima
    # do pickup que ignora harmônica (Idiff>> do P632).
    if valor.get("lim_harm"):
        b2 = b2 & (iop >= valor["lim_harm"])
        b5 = b5 & (iop >= valor["lim_harm"])
    if valor.get("max5"):
        b5 = b5 & (iop < valor["max5"])
    if valor.get("u87h"):
        b2 = b2 & ~(iop > valor["u87h"])
        b5 = b5 & ~(iop > valor["u87h"])
    existe = np.isfinite(iop) & np.isfinite(lim)
    passa = existe & (iop > lim)

    if modo == "restricao":
        reforco = iop * ((h2z / pct2 if pct2 > 0 else 0.0)
                         + (h5z / pct5 if pct5 > 0 else 0.0))
        passa_reforcado = passa & (iop > lim + reforco)
        bloq2 = passa & ~passa_reforcado & ((h2z / max(pct2, 1e-9))
                                            >= (h5z / max(pct5, 1e-9)))
        bloq5 = passa & ~passa_reforcado & ~bloq2
        opera = passa_reforcado
    else:
        if modo == "cruzado":
            # Uma fase com harmônica bloqueia as três, no mesmo instante.
            b2 = np.broadcast_to(b2.any(axis=0), b2.shape)
            b5 = np.broadcast_to(b5.any(axis=0), b5.shape)
        bloq2 = passa & b2
        bloq5 = passa & ~b2 & b5
        opera = passa & ~b2 & ~b5

    u87_opera = existe & (iop > u87)
    return np.select(
        [~existe, u87_opera, opera, bloq2, bloq5],
        ["", OPERA_87U, OPERA, BLOQUEADO_2, BLOQUEADO_5],
        default=RESTRINGE)


def _redondo(maximo: float) -> float:
    """O degrau «bonito» logo acima de `maximo` (1; 1,5; 2; 2,5; 3; 4; 5; 6; 8)."""
    if not (maximo > 0) or not math.isfinite(maximo):
        return 1.0
    dez = 10 ** math.floor(math.log10(maximo))
    for passo in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if passo * dez >= maximo:
            return passo * dez
    return 10 * dez


def _arredondar(valores) -> list:
    return [None if not math.isfinite(v) else float(f"{v:.5g}")
            for v in np.asarray(valores, dtype=np.float64).tolist()]


# ---------------------------------------------------------------------------
# O pacote
# ---------------------------------------------------------------------------

def montar(registro: Record, painel, ajustes: dict | None = None) -> dict:
    """O pacote de um painel diferencial: ajustes, curva e trajetórias."""
    escolhidos = [s for s in (painel.sinais or ()) if s in SINAIS]
    escolhidos = list(dict.fromkeys(escolhidos)) or list(SINAIS)

    lidos = lidos_do_arquivo(ajustes)
    fab = fabricante(registro, lidos)
    manuais = manuais_de(getattr(painel, "ajustes87", None))

    pacote = {
        "id": painel.id,
        "tipo": TIPO,
        "nome": painel.nome or "Diferencial percentual",
        "do_padrao": painel.do_padrao,
        "sinais": [{"id": s, "sinal": NOMES[s], "cor": CORES[s]}
                   for s in escolhidos],
        "fabricante": fab,
        "lado1": None,
        "lado2": None,
        "trincas": [],
        "falta": "",
        "ajustes": [],
        "placar": {e: 0 for e in ESTADOS},
        "faltam": [],
        "slopes": 2,
        "nao_usados": [],
        "pronto": False,
        "equacoes": {"iop": "", "irt": ""},
        "curva": {"irt": [], "iop": []},
        "eixos": {"irt": 1.0, "iop": 1.0},
        "marcas": {},
        "pontos": {"n": [], "t": []},
        "passo": 1,
        "trajetorias": {},
        "rodape": [],
        "nota": "",
    }

    trincas = trincas_de_corrente(registro)
    pacote["trincas"] = [{"rotulo": c.rotulo, "nome": c.nome} for c in trincas]
    lado1 = _escolher(trincas, getattr(painel, "local", "") or "")
    lado2 = _escolher(trincas, getattr(painel, "remoto", "") or "",
                      fora=lado1.rotulo if lado1 else "")
    if lado1 is not None:
        pacote["lado1"] = {"rotulo": lado1.rotulo, "nome": lado1.nome}
    if lado2 is not None:
        pacote["lado2"] = {"rotulo": lado2.rotulo, "nome": lado2.nome}

    campos = resolver(registro, lidos, manuais, fab, lado1, lado2)
    pacote["ajustes"] = campos
    pacote["placar"] = placar(campos)
    pacote["faltam"] = faltam(campos)
    pacote["slopes"] = 1 if um_slope(campos) else 2
    pacote["nao_usados"] = sorted(nao_usados(campos))
    pacote["opcionais"] = list(SEMPRE_OPCIONAIS)
    valor = {c["id"]: c["valor"] for c in campos}
    iop_eq = dict((c, f) for c, f, _ in EQUACOES_IOP).get(valor["iop"], "")
    irt_eq = dict((c, f) for c, f, _ in EQUACOES_IRT).get(valor["irt"], "")
    pacote["equacoes"] = {"iop": f"Iop = {iop_eq}", "irt": f"Irt = {irt_eq}"}
    if fab == "SEL" and str(lidos.get("E87", "")).strip().upper().startswith("N"):
        pacote["nota"] = ("E87 := N — o diferencial está DESLIGADO neste relé: "
                          "o arquivo não traz os ajustes da característica, e "
                          "o que se desenhar é estudo, não o que o relé fez.")

    if lado1 is None or lado2 is None:
        pacote["falta"] = ("Este registro tem uma trinca de corrente só: o "
                           "diferencial precisa da corrente dos DOIS lados do "
                           "trafo.")
        return pacote
    if pacote["faltam"]:
        return pacote

    conta = calcular(registro, lado1, lado2, valor)
    n = registro.n_samples
    passo = max(1, math.ceil(n / MAXIMO_DE_PONTOS)) if n else 1
    indices = np.arange(0, n, passo, dtype=np.int64)

    trajetorias = {}
    maior_irt = maior_iop = 0.0
    fases = {"A": 0, "B": 1, "C": 2}
    for s in escolhidos:
        k = fases[s]
        iop = conta["iop"][k][indices]
        irt = conta["irt"][k][indices]
        for vetor, nome in ((irt, "irt"), (iop, "iop")):
            finitos = vetor[np.isfinite(vetor)]
            if finitos.size:
                if nome == "irt":
                    maior_irt = max(maior_irt, float(finitos.max()))
                else:
                    maior_iop = max(maior_iop, float(finitos.max()))
        trajetorias[s] = {
            "iop": _arredondar(iop),
            "irt": _arredondar(irt),
            "limiar": _arredondar(conta["limiar"][k][indices]),
            "h2": _arredondar(conta["h2"][k][indices]),
            "h5": _arredondar(conta["h5"][k][indices]),
            "decisao": conta["decisao"][k][indices].tolist(),
        }

    # Os eixos: cabe a trajetória inteira e o breakpoint com folga.
    forma = valor.get("forma") or "origem_quebra"
    usados = set(DA_CARACTERISTICA) - nao_usados(campos)
    bp1 = valor["bp1"] if "bp1" in usados else None
    bp2 = valor["bp2"] if "bp2" in usados else None
    eixo_irt = _redondo(max(1.15 * maior_irt, 1.5 * (bp2 or bp1 or 0.0), 2.0))
    curva_irt = np.linspace(0.0, eixo_irt, 241)
    curva_iop = limiar(curva_irt, valor["pickup"], valor["slp1"], valor["bp1"],
                       valor["slp2"], forma, valor.get("bp2"))
    eixo_iop = _redondo(max(1.15 * maior_iop, 1.1 * float(curva_iop.max()), 1.0))

    pacote.update({
        "pronto": True,
        "curva": {"irt": _arredondar(curva_irt), "iop": _arredondar(curva_iop)},
        "eixos": {"irt": eixo_irt, "iop": eixo_iop},
        "marcas": {"bp1": bp1, "bp2": bp2, "u87": valor["u87"],
                   "pickup": valor["pickup"]},
        "passo": int(passo),
        "pontos": {"n": indices.tolist(),
                   "t": [round(float(x), 9) for x in registro.time[indices]]},
        "trajetorias": trajetorias,
    })
    canais = registro.analog_channels
    rodape = [
        f"lado 1 {lado1.rotulo} — "
        + ", ".join(f'"{canais[i].name}"' for i in lado1.abc),
        f"lado 2 {lado2.rotulo} — "
        + ", ".join(f'"{canais[i].name}"' for i in lado2.abc),
        f"diferencial PERCENTUAL (com restrição): {_FORMA[forma][1]} — "
        f"{_FORMA[forma][2]}",
    ]
    if conta["do_primario"]:
        rodape.append("canais gravados em primário: levados ao secundário pelo "
                      "RTC do ajuste, como o relé faz")
    if passo > 1:
        rodape.append(f"registro longo: um ponto a cada {passo} amostras")
    pacote["rodape"] = rodape
    return pacote
