"""O diferencial de transformador (87T): compensação, Iop × Irt e a decisão.

O trafo sintético é 25 MVA, 138/13,8 kV, Dyn1, com TC 200/5 (RTC 40) no lado 1
e 1200/5 (RTC 240) no lado 2 — o mesmo das maquetes. Os dois lados são
gravados em SECUNDÁRIO, com a relação declarada, como um relé grava. As
correntes são dadas em pu do TAP de cada lado; a do lado 2 é a que ENTRA no
trafo, então em carga ela é `−I1` girada de −30° (o lado de baixo do Dyn1
atrasa 30°).
"""

from __future__ import annotations

import cmath
import math
from datetime import datetime

import numpy as np

from osclab.formats.base import AnalogChannel, Record, SampleRate
from osclab.plot import diferencial, janela, paineis

TAXA = 1920.0
F0 = 60.0
DURACAO = 0.300
T_EVENTO = 0.100
RTC1, RTC2 = 40.0, 240.0
TAP1 = 25000 / (math.sqrt(3) * 138 * RTC1)
TAP2 = 25000 / (math.sqrt(3) * 13.8 * RTC2)
ANG = {"A": 0.0, "B": -120.0, "C": 120.0}

AJUSTES = {"mva": 25, "v1": 138, "v2": 13.8, "rtc1": RTC1, "rtc2": RTC2,
           "con1": "Y", "con2": "Y", "ctc1": "0", "ctc2": "1",
           "pickup": 0.3, "slp1": 25, "bp1": 3, "slp2": 50, "u87": 10,
           "pct2": 15, "pct5": 35, "modo": "fase", "iop": "entrando",
           "irt": "media"}


def _registro(caso: str) -> Record:
    """Os seis canais (lado W e lado X), com o evento em 100 ms."""
    n = int(DURACAO * TAXA)
    t = np.arange(n) / TAXA
    w = 2 * math.pi * F0
    linhas = []
    for lado, tap, rtc in (("W", TAP1, RTC1), ("X", TAP2, RTC2)):
        for fase in ("A", "B", "C"):
            carga = cmath.rect(0.8, math.radians(ANG[fase] - 20))
            i1 = np.full(n, carga, dtype=complex)
            h2 = np.zeros(n)
            depois = t >= T_EVENTO
            if caso == "externa":
                i1[depois] = cmath.rect(5.0, math.radians(ANG[fase] - 80))
            elif caso == "interna":
                i1[depois] = cmath.rect(4.0, math.radians(ANG[fase] - 80))
            elif caso in ("inrush", "u87"):
                modulo = 12.0 if (caso == "u87" and fase == "A") else 2.0
                i1[:] = 0
                i1[depois] = cmath.rect(modulo, math.radians(ANG[fase] - 60))
                h2[depois] = 0.30 if fase == "A" else 0.05
            if lado == "W":
                pu = i1
            elif caso in ("interna", "inrush", "u87"):
                # Só o lado 1 alimenta: falta interna ou energização.
                pu = np.where(depois, 0, -i1 * cmath.rect(1, math.radians(-30)))
                if caso in ("inrush", "u87"):
                    pu = np.zeros(n, dtype=complex)
            else:
                pu = -i1 * cmath.rect(1, math.radians(-30))
            onda = (np.abs(pu) * math.sqrt(2) * np.sin(w * t + np.angle(pu))
                    + (np.abs(pu) * math.sqrt(2) * h2
                       * np.sin(2 * w * t + np.angle(pu)) if lado == "W" else 0))
            linhas.append((f"I{fase}{lado}", fase, onda * tap, rtc))
    canais = [AnalogChannel(index=i, name=nome, unit="A", phase=fase,
                            primary=rtc * 5.0, secondary=5.0, scaling="S")
              for i, (nome, fase, _, rtc) in enumerate(linhas)]
    return Record(
        source=None, format_name="teste", station="SE TESTE",
        line_frequency=F0, start_time=datetime(2026, 10, 22, 9, 0, 0),
        analog_channels=tuple(canais),
        sample_rates=(SampleRate(rate_hz=TAXA, last_sample=n),),
        analog=np.array([x[2] for x in linhas]), time=t,
    )


def _painel(**ajustes) -> paineis.Painel:
    valores = {**AJUSTES, **ajustes}
    return paineis.Painel(id="pd", tipo=paineis.DIFERENCIAL, nome="",
                          sinais=("A", "B", "C"),
                          ajustes87={"valores": valores})


def _montado(registro, painel, ajustes=None) -> dict:
    return janela.montar(registro, colunas=200, layout=[painel],
                         ajustes=ajustes)["paineis"][0]


def _em(p, fase, t):
    k = int(np.argmin(np.abs(np.asarray(p["pontos"]["t"]) - t)))
    tr = p["trajetorias"][fase]
    return {campo: tr[campo][k] for campo in tr}


def test_a_matriz_1_e_a_CTC1_da_IEEE():
    esperada = np.array([[1, -1, 0], [0, 1, -1], [-1, 0, 1]]) / math.sqrt(3)
    assert np.allclose(diferencial.matriz_de_compensacao(1), esperada)
    # A 12 só tira a sequência zero; a 0 não mexe em nada.
    assert np.allclose(diferencial.matriz_de_compensacao(12),
                       np.eye(3) - np.ones((3, 3)) / 3)
    assert np.allclose(diferencial.matriz_de_compensacao(0), np.eye(3))


def test_carga_compensada_da_Iop_zero_e_restringe():
    p = _montado(_registro("carga"), _painel())
    assert p["pronto"]
    for fase in "ABC":
        lido = _em(p, fase, 0.200)
        assert lido["iop"] < 0.01
        assert abs(lido["irt"] - 0.8) < 0.01
        assert lido["decisao"] == diferencial.RESTRINGE


def test_falta_externa_restringe():
    p = _montado(_registro("externa"), _painel())
    lido = _em(p, "A", 0.250)
    assert lido["iop"] < 0.05
    assert abs(lido["irt"] - 5.0) < 0.05
    assert lido["decisao"] == diferencial.RESTRINGE


def test_falta_interna_opera():
    p = _montado(_registro("interna"), _painel())
    for fase in "ABC":
        lido = _em(p, fase, 0.250)
        assert abs(lido["iop"] - 4.0) < 0.05
        assert lido["decisao"] == diferencial.OPERA


def test_grupo_de_ligacao_errado_da_falsa_diferencial_em_carga():
    p = _montado(_registro("carga"), _painel(ctc2="0"))
    lido = _em(p, "A", 0.200)
    # |1 − e^(−j30°)| · 0,8 = 0,414 pu: acima do pickup de 0,3.
    assert abs(lido["iop"] - 0.8 * 2 * math.sin(math.radians(15))) < 0.01
    assert lido["decisao"] == diferencial.OPERA


def test_energizacao_bloqueia_pela_2a_por_fase_e_cruzado():
    r = _registro("inrush")
    por_fase = _montado(r, _painel())
    assert abs(_em(por_fase, "A", 0.250)["h2"] - 30.0) < 1.0
    assert _em(por_fase, "A", 0.250)["decisao"] == diferencial.BLOQUEADO_2
    assert _em(por_fase, "B", 0.250)["decisao"] == diferencial.OPERA
    cruzado = _montado(r, _painel(modo="cruzado"))
    for fase in "ABC":
        assert _em(cruzado, fase, 0.250)["decisao"] == diferencial.BLOQUEADO_2


def test_87U_opera_mesmo_com_2a_alta():
    p = _montado(_registro("u87"), _painel())
    lido = _em(p, "A", 0.250)
    assert lido["iop"] > 10
    assert lido["h2"] > 15
    assert lido["decisao"] == diferencial.OPERA_87U


def test_sem_ajustes_nao_desenha_e_diz_o_que_falta():
    painel = paineis.Painel(id="pd", tipo=paineis.DIFERENCIAL, nome="",
                            sinais=("A", "B", "C"))
    p = _montado(_registro("carga"), painel)
    assert not p["pronto"]
    assert p["trajetorias"] == {}
    faltam = {x["id"] for x in p["faltam"]}
    assert {"mva", "pickup", "slp1", "pct2"} <= faltam
    # A relação de TC declarada no arquivo vira RTC deduzido, e o TAP fica à
    # espera da potência e das tensões.
    campos = {c["id"]: c for c in p["ajustes"]}
    assert campos["rtc1"]["estado"] == diferencial.DEDUZIDO
    assert campos["rtc1"]["valor"] == RTC1
    assert campos["tap1"]["estado"] == diferencial.FALTA


def test_o_TAP_sai_deduzido_da_potencia_tensao_e_RTC():
    valores = {k: v for k, v in AJUSTES.items()}
    p = _montado(_registro("carga"), _painel())
    campos = {c["id"]: c for c in p["ajustes"]}
    assert "tap1" not in valores
    assert campos["tap1"]["estado"] == diferencial.DEDUZIDO
    assert abs(campos["tap1"]["valor"] - TAP1) < 1e-3


def test_ajustes_lidos_da_SEL_e_o_TAP_suspeito():
    texto = ("MVA := 25.00  VWDG1 := 138.00  VWDG2 := 13.80\n"
             "CTR1 := 40  CTR2 := 240  W1CT := Y  W2CT := Y\n"
             "W1CTC := 0  W2CTC := 1  TAP1 := 3.00  TAP2 := 4.36\n"
             "O87P := 0.30  SLP1 := 25  IRS1 := 3.0  SLP2 := 50\n"
             "U87P := 10.0  PCT2 := 15  PCT5 := OFF  HBLK := Y\n")
    lidos = diferencial.lidos_de_texto(texto)
    assert lidos["VWDG1"] == "138.00"
    r = _registro("carga")
    campos = {c["id"]: c for c in diferencial.resolver(
        r, lidos, {}, "SEL")}
    assert campos["mva"]["estado"] == diferencial.COLETADO
    assert campos["mva"]["bruto"] == "MVA := 25.00"
    assert campos["ctc2"]["valor"] == "1"
    assert campos["modo"]["valor"] == "cruzado"
    assert campos["pct5"]["valor"] == 0.0
    # A Irt da SEL é a SOMA dos módulos (IM 787 p. 4.17; 487E Eq. 3.8).
    assert campos["irt"]["valor"] == "soma"
    assert campos["tap1"]["estado"] == diferencial.SUSPEITO
    assert campos["tap1"]["sugestao"]["valor"] == round(TAP1, 4)
    assert campos["tap2"]["estado"] == diferencial.COLETADO
    # Aceito, o suspeito volta a valer — com o motivo guardado.
    aceito = {c["id"]: c for c in diferencial.resolver(
        r, lidos, {"aceitos": ["tap1"]}, "SEL")}
    assert aceito["tap1"]["estado"] == diferencial.COLETADO
    assert aceito["tap1"]["motivo"]


def test_RTC_lido_que_nao_bate_com_o_arquivo_e_suspeito():
    r = _registro("carga")
    trincas = diferencial.trincas_de_corrente(r)
    campos = {c["id"]: c for c in diferencial.resolver(
        r, {"CTR1": "60"}, {}, "SEL", trincas[0], trincas[1])}
    assert campos["rtc1"]["estado"] == diferencial.SUSPEITO
    assert campos["rtc1"]["sugestao"]["valor"] == RTC1


def test_a_equacao_da_Irt_muda_o_numero():
    r = _registro("carga")
    media = _em(_montado(r, _painel()), "A", 0.200)["irt"]
    soma = _em(_montado(r, _painel(irt="soma")), "A", 0.200)["irt"]
    assert abs(soma - 2 * media) < 0.01


def test_a_curva_sai_pronta_do_servidor():
    p = _montado(_registro("carga"), _painel())
    irt = np.asarray(p["curva"]["irt"])
    iop = np.asarray(p["curva"]["iop"])
    esperado = diferencial.limiar(irt, 0.3, 25, 3, 50)
    assert np.allclose(iop, esperado, rtol=1e-4)
    assert p["eixos"]["irt"] >= 4.5


def test_um_slope_so_desenha_sem_breakpoint_nem_slope_2():
    painel = paineis.Painel(
        id="pd", tipo=paineis.DIFERENCIAL, nome="", sinais=("A", "B", "C"),
        ajustes87={"valores": {k: v for k, v in AJUSTES.items()
                               if k not in ("bp1", "slp2")}})
    p = _montado(_registro("interna"), painel)
    assert p["pronto"]
    assert p["slopes"] == 1
    irt = np.asarray(p["curva"]["irt"])
    assert np.allclose(np.asarray(p["curva"]["iop"]),
                       np.maximum(0.3, 0.25 * irt), rtol=1e-4)
    assert _em(p, "A", 0.250)["decisao"] == diferencial.OPERA


def test_breakpoint_sem_slope_2_nao_fecha_e_falta():
    valores = {k: v for k, v in AJUSTES.items() if k != "slp2"}
    painel = paineis.Painel(id="pd", tipo=paineis.DIFERENCIAL, nome="",
                            sinais=("A",), ajustes87={"valores": valores})
    p = _montado(_registro("carga"), painel)
    assert not p["pronto"]
    assert [x["id"] for x in p["faltam"]] == ["slp2"]


def test_a_restricao_comum_do_RET670_e_a_mesma_nas_tres_fases():
    # Na «comum» as três fases restringem com o MESMO número: a maior
    # contribuição de todos os lados e fases (aqui, os 4 pu da falta).
    r = _registro("interna")
    p = _montado(r, _painel(irt="comum"))
    irt = [_em(p, f, 0.250)["irt"] for f in "ABC"]
    assert max(irt) - min(irt) < 1e-6
    assert abs(irt[0] - 4.0) < 0.05


def test_as_formas_da_caracteristica_seguem_os_manuais():
    irt = np.array([0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0])
    # Siemens / ABB: plana até BP1, depois S1 a partir dali, S2 depois do BP2.
    tres = diferencial.limiar(irt, 0.3, 30, 1.0, 70, "tres_trechos", 3.0)
    assert np.allclose(tres[:3], 0.3)
    assert abs(tres[4] - (0.3 + 0.3 * 2.0)) < 1e-9
    assert abs(tres[5] - (0.3 + 0.3 * 2.0 + 0.7 * 2.0)) < 1e-9
    # P632: plana até ½·pickup, e a reta m1 passa por (½·Idiff>, Idiff>).
    p632 = diferencial.limiar(np.array([0.1, 0.15, 1.0]), 0.3, 30, None, 70,
                              "p632", 4.0)
    assert np.allclose(p632[:2], 0.3)
    assert abs(p632[2] - (0.3 * 1.0 + 0.3 * (1 - 0.5 * 0.3))) < 1e-9
    # GE: S1·Ir antes de BP1, S2·Ir depois de BP2, contínua no meio.
    ge = diferencial.limiar(np.linspace(0, 10, 1001), 0.1, 25, 2.0, 90,
                            "origem_dupla", 8.0)
    assert abs(ge[200] - 0.5) < 1e-6 and abs(ge[900] - 8.1) < 1e-6
    assert np.max(np.abs(np.diff(ge))) < 0.02
    # SEL 487E: um slope só pela origem.
    um = diferencial.limiar(irt, 0.3, 30, 3.0, 60, "origem")
    assert np.allclose(um, np.maximum(0.3, 0.3 * irt))


def test_a_forma_vem_do_fabricante_e_diz_o_que_nao_usa():
    r = _registro("carga")
    sel = {c["id"]: c for c in diferencial.resolver(r, {}, {}, "SEL")}
    assert sel["forma"]["valor"] == "origem_quebra"
    siemens = diferencial.resolver(r, {}, {}, "Siemens")
    assert {c["id"]: c for c in siemens}["forma"]["valor"] == "tres_trechos"
    assert "bp2" in {x["id"] for x in diferencial.faltam(siemens)}
    p632 = diferencial.resolver(r, {}, {}, "Schneider")
    assert "bp1" in diferencial.nao_usados(p632)


def test_acima_do_pickup_que_ignora_harmonica_a_2a_nao_bloqueia():
    # Fase A com 2 pu e 30 % de 2ª: bloqueada; com o Idiff>> em 1,5 pu, opera.
    r = _registro("inrush")
    assert _em(_montado(r, _painel()), "A", 0.250)["decisao"] == diferencial.BLOQUEADO_2
    assert _em(_montado(r, _painel(u87h=1.5)), "A", 0.250)["decisao"] == diferencial.OPERA


def test_abaixo_da_diferencial_minima_a_harmonica_nao_bloqueia():
    r = _registro("inrush")
    p = _montado(r, _painel(lim_harm=2.5))
    assert _em(p, "A", 0.250)["decisao"] == diferencial.OPERA


def test_2a_mais_4a_soma_em_quadratura():
    r = _registro("inrush")
    so2 = _em(_montado(r, _painel()), "A", 0.250)["h2"]
    com4 = _em(_montado(r, _painel(ordens="24")), "A", 0.250)["h2"]
    assert com4 >= so2 - 1e-6


def test_o_P632_ganha_o_limite_de_4_Iref_na_5a():
    r = _registro("carga")
    campos = {c["id"]: c for c in diferencial.resolver(r, {}, {}, "Schneider")}
    assert campos["max5"]["valor"] == 4.0
    assert campos["max5"]["estado"] == diferencial.DEDUZIDO


def test_o_487e_ajusta_por_terminal_e_o_e87_diz_qual_e_o_lado():
    """O 487E não escreve `CTR1`/`TAP1`: escreve `CTRS`, `TAPS`, `TSCTC`… para
    os terminais que o `E87` lista. Números de um 487E do parque: o TAP lido
    fecha com o calculado (19 MVA, 138/13,8 kV, CTRS 40, CTRT 200)."""
    texto = ('E87 := "S,T"  MVA := 19  VTERMS := 138.00  VTERMT := 13.80\n'
             "CTRS := 40  CTRT := 200  CTCONS := Y  CTCONT := Y\n"
             "TSCTC := 12  TTCTC := 12  TAPS := 1.99  TAPT := 3.97\n"
             "O87P := 0.30  SLP1 := 30.00  SLP2 := 70.00  U87P := 10.00\n"
             "PCT2 := 15  PCT5 := 35  E87HB := Y\n")
    lidos = diferencial.lidos_de_texto(texto)
    campos = {c["id"]: c for c in diferencial.resolver(_registro("carga"), lidos, {}, "SEL")}
    for id_, variavel in (("v1", "VTERMS"), ("v2", "VTERMT"), ("rtc1", "CTRS"),
                          ("rtc2", "CTRT"), ("tap1", "TAPS"), ("tap2", "TAPT"),
                          ("ctc1", "TSCTC"), ("ctc2", "TTCTC"), ("modo", "E87HB")):
        assert campos[id_]["estado"] == diferencial.COLETADO, id_
        assert campos[id_]["variavel"] == variavel
    assert campos["v2"]["valor"] == 13.8 and campos["ctc2"]["valor"] == "12"
    assert campos["modo"]["valor"] == "cruzado"
    assert not campos["tap1"]["motivo"] and not campos["tap2"]["motivo"]


def test_sem_e87_valem_os_nomes_do_787():
    assert diferencial.nomes_por_terminal({"CTR1": "40"}) == {}
    assert diferencial.nomes_por_terminal({"E87": '"S,T,U"'})["tap2"] == "TAPT"
