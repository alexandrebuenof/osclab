"""O plano alfa: `k = I_remoto / I_local`, a característica e o ponto de vista.

Os registros são sintéticos e trazem DUAS trincas de corrente — `IAW…` e
`IAX…` —, que é como o plano alfa enxerga o local e o remoto enquanto o
multi-registro não existe. O que se prende aqui é a conta do 87L: externa
perto de 1∠180°, interna perto de 0°, e a decisão que sai da coroa.
"""

from __future__ import annotations

import cmath
import math
from datetime import datetime

import numpy as np

from osclab.formats.base import AnalogChannel, Record, SampleRate
from osclab.plot import alfa, janela, paineis

TAXA = 1920.0
F0 = 60.0
CARGA = 200.0
FALTA = 3000.0
T_FALTA = 0.100
DURACAO = 0.250


def _registro(interna: bool, *, com_remoto: bool = True,
              relacao_remota: float = 120.0) -> Record:
    """Local `W` e remoto `X`; a falta em 100 ms, AG.

    Externa: a corrente que entra pelo local SAI pelo remoto — os dois TCs,
    olhando para dentro da linha, veem fasores opostos. Interna: os dois
    terminais alimentam a falta, e o remoto fica perto do local.
    """
    n = int(DURACAO * TAXA)
    t = np.arange(n) / TAXA
    w = 2 * math.pi * F0
    ang = {"A": 0.0, "B": -120.0, "C": 120.0}
    linhas = []
    for terminal in ("W", "X") if com_remoto else ("W",):
        for fase in ("A", "B", "C"):
            antes = cmath.rect(CARGA, math.radians(ang[fase] - 20))
            durante = antes
            if fase == "A":
                durante = cmath.rect(FALTA, math.radians(-80))
            if terminal == "X":
                antes = -antes
                durante = (durante * 0.9 * cmath.rect(1, math.radians(10))
                           if interna and fase == "A" else -durante)
            fasor = np.where(t >= T_FALTA, durante, antes)
            # Em SECUNDÁRIO, com a relação do terminal: o plano tem de
            # comparar em primário e desfazer a diferença das duas.
            razao = 120.0 if terminal == "W" else relacao_remota
            onda = (np.abs(fasor) * math.sqrt(2)
                    * np.sin(w * t + np.angle(fasor))) / razao
            linhas.append((f"I{fase}{terminal}", fase, onda, razao))
    canais = [AnalogChannel(index=i, name=nome, unit="A", phase=fase,
                            primary=razao * 5.0, secondary=5.0, scaling="S")
              for i, (nome, fase, _, razao) in enumerate(linhas)]
    return Record(
        source=None, format_name="teste", station="SE TESTE",
        line_frequency=F0, start_time=datetime(2026, 10, 22, 9, 0, 0),
        analog_channels=tuple(canais),
        sample_rates=(SampleRate(rate_hz=TAXA, last_sample=n),),
        analog=np.array([x[2] for x in linhas]), time=t,
    )


def _plano(sinais=("A", "B", "C"), **kw) -> paineis.Painel:
    return paineis.Painel(id="pa", tipo=paineis.ALFA, nome="", sinais=tuple(sinais),
                          **kw)


def _montado(registro, painel) -> dict:
    return janela.montar(registro, colunas=200, layout=[painel])["paineis"][0]


def _no_instante(p, sinal, t):
    """O ponto da trajetória mais perto do instante `t`."""
    k = int(np.argmin(np.abs(np.asarray(p["pontos"]["t"]) - t)))
    tr = p["trajetorias"][sinal]
    return {campo: tr[campo][k] for campo in tr}


def test_falta_externa_fica_em_1_a_180_graus_e_restringe():
    p = _montado(_registro(interna=False), _plano())
    assert p["tipo"] == "alfa"
    lido = _no_instante(p, "A", 0.200)
    assert abs(lido["modulo"] - 1.0) < 1e-3
    assert abs(abs(lido["angulo"]) - 180.0) < 0.1
    assert lido["decisao"] == alfa.RESTRINGE
    # A carga também atravessa: restringe nas três fases, antes da falta.
    for fase in ("A", "B", "C"):
        assert _no_instante(p, fase, 0.060)["decisao"] == alfa.RESTRINGE


def test_falta_interna_vira_para_perto_de_zero_e_opera():
    p = _montado(_registro(interna=True), _plano())
    lido = _no_instante(p, "A", 0.200)
    assert abs(lido["modulo"] - 0.9) < 1e-3
    assert abs(lido["angulo"] - 10.0) < 0.1
    assert lido["decisao"] == alfa.OPERA
    # As fases sãs continuam atravessando.
    assert _no_instante(p, "B", 0.200)["decisao"] == alfa.RESTRINGE


def test_trocar_o_ponto_de_vista_inverte_k():
    r = _registro(interna=True)
    local = _no_instante(_montado(r, _plano()), "A", 0.200)
    remoto = _no_instante(_montado(r, _plano(vista="remoto")), "A", 0.200)
    assert abs(remoto["modulo"] - 1.0 / local["modulo"]) < 1e-3
    assert abs(remoto["angulo"] + local["angulo"]) < 0.1


def test_k_compara_em_PRIMARIO_mesmo_com_relacoes_diferentes():
    """Um TC de 600/5 de um lado e 1200/5 do outro, comparados em
    secundário, dariam |k| = 0,5 numa externa — e isso se leria como outfeed."""
    p = _montado(_registro(interna=False, relacao_remota=240.0), _plano())
    assert abs(_no_instante(p, "A", 0.200)["modulo"] - 1.0) < 1e-3


def test_3I0_e_I2_saem_das_trincas():
    p = _montado(_registro(interna=False), _plano(("3I0", "I2")))
    for s in ("3I0", "I2"):
        lido = _no_instante(p, s, 0.200)
        assert abs(lido["modulo"] - 1.0) < 1e-3
        assert lido["decisao"] == alfa.RESTRINGE
    # Na carga equilibrada não há 3I0: sem corrente, sem ponto.
    antes = _no_instante(p, "3I0", 0.060)
    assert antes["decisao"] == alfa.SEM_CORRENTE
    assert antes["re"] is None


def test_com_uma_trinca_so_o_painel_avisa_e_nao_desenha():
    p = _montado(_registro(interna=False, com_remoto=False), _plano())
    assert p["falta"]
    assert p["trajetorias"] == {}
    assert p["remoto"] is None


def test_87LR_e_87LANG_mudam_a_decisao():
    r = _registro(interna=True)
    # |k| = 0,9 ∠ 10°: fora de qualquer setor em volta de 180°…
    assert _no_instante(_montado(r, _plano()), "A", 0.2)["decisao"] == alfa.OPERA
    # …a não ser que o setor se abra quase até ele.
    largo = _montado(r, _plano(ang87=270.0))
    assert _no_instante(largo, "A", 0.2)["decisao"] == alfa.OPERA
    # E na externa, um raio apertado demais faz a fase errar: com |k| = 1 ela
    # continua dentro de qualquer 87LR ≥ 1,5; o ângulo é que decide.
    estreito = _montado(_registro(interna=False), _plano(ang87=90.0))
    assert _no_instante(estreito, "A", 0.2)["decisao"] == alfa.RESTRINGE
    k = np.array([2.5 * cmath.rect(1, math.radians(180))])
    assert alfa.decidir(k, 3.0, 195.0)[0]
    assert not alfa.decidir(k, 2.0, 195.0)[0]
    k = np.array([cmath.rect(1, math.radians(250))])
    assert not alfa.decidir(k, 6.0, 120.0)[0]
    assert alfa.decidir(k, 6.0, 160.0)[0]


def test_no_maximo_tres_sinais():
    p = _montado(_registro(interna=False), _plano(("A", "B", "C", "3I0")))
    assert [s["id"] for s in p["sinais"]] == ["A", "B", "C"]


def test_os_ajustes_da_tela_sao_peneirados():
    lido = paineis.de_json([{"id": "x", "tipo": "alfa", "r87": "abc",
                             "ang87": 999, "vista": "remoto"}])[0]
    assert lido.r87 == 6.0
    assert lido.ang87 == 270.0
    assert lido.vista == "remoto"


def test_o_usuario_escolhe_qual_trinca_e_local_e_qual_e_remota():
    r = _registro(interna=True)
    padrao = _montado(r, _plano())
    assert len(padrao["trincas"]) == 2
    g1, g2 = (t["rotulo"] for t in padrao["trincas"])
    assert (padrao["local"]["rotulo"], padrao["remoto"]["rotulo"]) == (g1, g2)
    # Pôr a segunda como local troca os lados — o mesmo que inverter k.
    trocado = _montado(r, _plano(local=g2))
    assert (trocado["local"]["rotulo"], trocado["remoto"]["rotulo"]) == (g2, g1)
    a = _no_instante(padrao, "A", 0.200)
    b = _no_instante(trocado, "A", 0.200)
    assert abs(b["modulo"] - 1.0 / a["modulo"]) < 1e-3
