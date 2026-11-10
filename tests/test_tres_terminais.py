"""As linhas de TRÊS TERMINAIS e o `linhas.csv` que não perde nada.

Pedido dele, 09/11/2026: a linha com derivação aparece UMA vez (A–B, com o
TAP dito), a conta usa o caminho A–B, os papéis se marcam e a marcação fica
gravada — e nenhum parâmetro da base se perde.
"""

from __future__ import annotations

import numpy as np
import pytest

from osclab.basedados import linhas
from osclab.basedados import tres_terminais as t3
from osclab.faultloc import ldl


class _Base:
    def __init__(self, pasta):
        self.pasta = pasta

    def gaveta(self, qual):
        destino = self.pasta / qual
        destino.mkdir(parents=True, exist_ok=True)
        return destino


#: Uma base como a montada do OnLiner: 23 colunas, trechos de uma derivação,
#: uma linha simples e uma linha AINDA SEM PARÂMETRO.
CABECALHO = ("codigo;trecho;nome;terminal_s;terminal_r;comprimento_km;r1_ohm;x1_ohm;r0_ohm;"
             "x0_ohm;b1_us;b0_us;tensao_kv;circuito;condutor;corrente_nominal_a;potencia_mva;"
             "topologia;regional;em_operacao_desde;ativo_sgm;guid_onliner;fonte\n")
#: Cada trecho: os dez campos do programa, depois os treze que ele ignora.
_R = ";;;138;1;{};;;radial;ME;;;{};onliner"
LINHAS = [
    "69LT70;1/2;LD VG - POCONE;VARZEA GRANDE;TAP 69LT70;20;4;10;8;30" + _R.format("DOVE", "g1"),
    "69LT70;2/2;LD VG - POCONE;TAP 69LT70;POCONE;60;12;20;24;60" + _R.format("LINNET", "g2"),
    "12LT1;1/2;LD CV - BF;CAMPO VERDE;INCOFIBRAS;10;2;5;6;18" + _R.format("DOVE", "g3"),
    "12LT1;2/2;LD CV - BF;INCOFIBRAS;BOM FUTURO;3;0,6;1,5;1,8;5,4" + _R.format("DOVE", "g4"),
    "01LT9;;LD ALFA - BETA;ALFA;BETA;30;3;12;9;36" + _R.format("DOVE", "g5"),
    "02LT9;;LD SEM DADO;GAMA;DELTA;;;;;;;;138;1;;;;;ME;;;;ldat",
]
TRES_T = ("codigo;nome;ponto;situacao;papeis;origem;nota;"
          "t1_nome;t1_barra;t1_papel;t1_km;t1_r1;t1_x1;t1_r0;t1_x0;"
          "t2_nome;t2_barra;t2_papel;t2_km;t2_r1;t2_x1;t2_r0;t2_x0;"
          "t3_nome;t3_barra;t3_papel;t3_km;t3_r1;t3_x1;t3_r0;t3_x0\n"
          "69LT70;LD VG - POCONE;BUS61;certo;deduzido;onliner;;"
          "VARZEA GRANDE;V.GRANDE138;A;20;4;10;8;30;"
          "POCONE;POCONE 138;B;60;12;20;24;60;"
          "CANGAS;CANGAS;TAP;3,3;0,8;1,7;2;7\n")


@pytest.fixture()
def base(tmp_path):
    b = _Base(tmp_path)
    (b.gaveta("linhas") / "linhas.csv").write_text(CABECALHO + "\n".join(LINHAS) + "\n",
                                                  encoding="utf-8")
    (b.gaveta("linhas") / "linhas-3t.csv").write_text(TRES_T, encoding="utf-8")
    return b


def test_gravar_pela_tela_nao_perde_coluna_nem_linha_sem_parametro(base):
    """A versão anterior reescrevia o arquivo só com as dez colunas que o
    programa conhece e só com as linhas legíveis: condutor, GUID, código e a
    linha ainda sem parâmetro sumiam na primeira gravação pela tela."""
    linhas.gravar(base, linhas.Linha("LD ALFA - BETA", "ALFA", "BETA", 3.1, 12.5, 30.0))
    linhas.gravar(base, linhas.Linha("LD NOVA", "X", "Y", 1.0, 4.0, 9.0))
    texto = (base.gaveta("linhas") / "linhas.csv").read_text(encoding="utf-8")
    assert texto.splitlines()[0] == CABECALHO.strip()
    assert "LD SEM DADO;GAMA;DELTA" in texto            # a linha sem parâmetro ficou
    assert "LINNET" in texto and ";g2;" in texto           # as colunas que o programa ignora
    alfa = next(x for x in texto.splitlines() if "LD ALFA - BETA" in x)
    assert alfa.startswith("01LT9;;LD ALFA - BETA;ALFA;BETA;30;3,1;12,5;9;36;")  # Z0 ficou
    assert alfa.endswith(";g5;onliner")
    assert texto.count("LD VG - POCONE") == 2              # trechos intocados
    assert texto.splitlines()[-1].startswith(";;LD NOVA;X;Y;9;1;4;")


def test_uma_entrada_por_linha_e_nenhum_trecho_some(base):
    ent = {x["nome"]: x for x in linhas.entradas(base)}
    assert set(ent) == {"LD VG - POCONE", "LD CV - BF", "LD ALFA - BETA"}
    vg = ent["LD VG - POCONE"]
    assert vg["tipo"] == "3t" and vg["tap"] == "CANGAS"
    assert (vg["terminal_s"], vg["terminal_r"]) == ("VARZEA GRANDE", "POCONE")
    assert vg["comprimento_km"] == pytest.approx(80) and vg["x1_ohm"] == pytest.approx(30)
    assert len(vg["trechos"]) == 2                          # escolhíveis um a um
    cv = ent["LD CV - BF"]
    assert cv["tipo"] == "trechos" and cv["pontos"] == ["INCOFIBRAS"]
    assert cv["comprimento_km"] == pytest.approx(13)
    assert ent["LD ALFA - BETA"]["tipo"] == "linha"


def test_a_busca_acha_o_circuito_pelas_pontas(base):
    """Nenhum TRECHO vai de Várzea Grande a Poconé; o circuito vai — e é
    UMA entrada na lista, não um trecho de cada vez."""
    achadas = linhas.buscar(base, "pocone")
    assert [x["nome"] for x in achadas] == ["LD VG - POCONE"]


def test_o_caminho_A_B_soma_as_pernas_e_diz_o_tap(base):
    cam = t3.caminho_de_circuito(t3.de_nome(base, "LD VG - POCONE"))
    assert cam["ok"] and (cam["r"], cam["x"], cam["km"]) == (16, 30, 80)
    assert (cam["r0"], cam["x0"]) == (32, 90)
    assert cam["tap"] == {"nome": "CANGAS", "km_de_a": 20, "km": 3.3}
    assert "CANGAS" in cam["aviso"] and "delta" in cam["aviso"]
    assert cam["perfil"] == [[0.0, 0.0], [20.0, pytest.approx(10 / 30)], [80.0, 1.0]]


def test_a_fracao_de_impedancia_vira_km_pelo_perfil():
    """Condutores diferentes: uma falta EM CIMA do TAP tem 1/3 da reatância e
    está a 20 km de 80 — tratar a linha como uniforme daria 26,7 km."""
    perfil = [[0.0, 0.0], [20.0, 1 / 3], [80.0, 1.0]]
    m = np.array([0.0, 1 / 3, 2 / 3, 1.0, 1.1, -0.1, np.nan])
    km = ldl.km_pelo_perfil(m, perfil, 80.0)
    assert km[:4] == pytest.approx([0, 20, 50, 80])
    assert km[4] == pytest.approx(80 + 0.1 * 60 / (2 / 3))   # fora: inclinação da ponta
    assert km[5] == pytest.approx(-0.1 * 20 / (1 / 3))
    assert np.isnan(km[6])
    assert ldl.km_pelo_perfil(np.array([0.5]), None, 80.0) == pytest.approx([40])


def test_marcar_os_papeis_grava_e_vence_a_deducao(base):
    t3.marcar(base, "LD VG - POCONE", ["A", "TAP", "B"])
    c = t3.de_nome(base, "LD VG - POCONE")
    assert c.papeis == "marcado" and [p.papel for p in c.pernas] == ["A", "TAP", "B"]
    cam = t3.caminho_de_circuito(c)
    assert cam["km"] == pytest.approx(23.3) and cam["tap"]["nome"] == "POCONE"
    with pytest.raises(ValueError, match="cada papel"):
        t3.marcar(base, "LD VG - POCONE", ["A", "A", "B"])
    # O linhas.csv não foi tocado.
    texto = (base.gaveta("linhas") / "linhas.csv").read_text(encoding="utf-8")
    assert texto == CABECALHO + "\n".join(LINHAS) + "\n"


def test_o_tap_que_o_onliner_nao_reconheceu_se_cadastra_a_mao_e_se_tira(base):
    c = t3.cadastrar(base, "LD CV - BF", 0, "INCOFIBRAS", 0.5)
    assert (c.origem, c.papeis, c.ponto) == ("manual", "marcado", "INCOFIBRAS")
    assert c.perna("A").km == 10 and c.perna("B").km == 3 and c.perna("TAP").km == 0.5
    ent = {x["nome"]: x for x in linhas.entradas(base)}
    assert ent["LD CV - BF"]["tipo"] == "3t"
    assert t3.resumo(base)["trechos_sem_tap"] == 0
    # O que veio do OnLiner não se tira por clique; o cadastrado à mão, sim.
    assert t3.remover_manual(base, "LD VG - POCONE") is False
    assert t3.remover_manual(base, "LD CV - BF") is True
    assert {x["nome"]: x for x in linhas.entradas(base)}["LD CV - BF"]["tipo"] == "trechos"
    with pytest.raises(ValueError):
        t3.cadastrar(base, "LD ALFA - BETA", 0, "X")        # um trecho só: sem ponto
    with pytest.raises(ValueError):
        t3.cadastrar(base, "LD CV - BF", 0, "")             # sem nome do TAP


def test_o_resumo_e_o_aviso_que_a_tela_mostra(base):
    assert t3.resumo(base) == {"tres_terminais": 1, "conferir": 0, "marcar": 0,
                               "sem_tap": 0, "seccionadas": 0, "trechos_sem_tap": 1}
    cam = t3.caminho_de_trechos(t3.trechos_de(base, "LD CV - BF"))
    assert cam["km"] == pytest.approx(13) and "INCOFIBRAS" in cam["aviso"]


def test_linha_em_trechos_conferida_sem_tap_ou_seccionada(base):
    """O que se conferiu no Caderno de Manobras: sem derivação no ponto do meio
    (dois terminais, sem aviso) ou subestação com disjuntor no meio (cada
    trecho é uma linha para a proteção)."""
    t3.conferir_trechos(base, "LD CV - BF", "sem-tap", "caderno FL.25: 12,08 km direto")
    cv = {x["nome"]: x for x in linhas.entradas(base)}["LD CV - BF"]
    assert cv["tipo"] == "trechos" and cv["conferido"] and "FL.25" in cv["nota"]
    cam = t3.caminho_de_trechos(t3.trechos_de(base, "LD CV - BF"), conferido=True)
    assert cam["aviso"] == "" and cam["km"] == pytest.approx(13)
    resumo = t3.resumo(base)
    assert (resumo["sem_tap"], resumo["trechos_sem_tap"], resumo["tres_terminais"]) == (1, 0, 1)

    t3.conferir_trechos(base, "LD CV - BF", "seccionada", "SE no meio com disjuntor")
    separadas = [x for x in linhas.entradas(base) if x["nome"] == "LD CV - BF"]
    assert [x["tipo"] for x in separadas] == ["linha", "linha"]
    assert {x["terminal_r"] for x in separadas} == {"INCOFIBRAS", "BOM FUTURO"}
    assert all(x["situacao"] == "seccionada" for x in separadas)
    assert t3.resumo(base)["seccionadas"] == 1

    # Desfazer: o registro foi feito à mão, então se tira.
    assert t3.remover_manual(base, "LD CV - BF") is True
    assert {x["nome"]: x for x in linhas.entradas(base)}["LD CV - BF"]["conferido"] is False
    with pytest.raises(ValueError):
        t3.conferir_trechos(base, "LD CV - BF", "talvez")
    # O linhas.csv continua intocado.
    texto = (base.gaveta("linhas") / "linhas.csv").read_text(encoding="utf-8")
    assert texto == CABECALHO + "\n".join(LINHAS) + "\n"
