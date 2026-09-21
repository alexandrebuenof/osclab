"""Componentes simétricas e o agrupamento trifásico, contra casos conhecidos.

Os casos aqui não são inventados: são as quatro situações que um engenheiro de
proteção reconhece de olho num registro. Se a conta estiver certa nelas, está
certa — e se estiver errada, o teste diz qual tipo de falta ela erra.
"""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest

from osclab.dsp import simetricas
from osclab.formats import conjuntos
from osclab.formats.base import AnalogChannel, Record

#: Uma fase de 100 V eficazes, ângulo zero. As outras giram a partir dela.
V = 100.0
def giro(graus: float) -> complex:
    """Um fasor unitário no ângulo pedido."""
    return cmath.exp(1j * math.radians(graus))


# ---------------------------------------------------------------------------
# A transformação, nos casos que se reconhece de olho
# ---------------------------------------------------------------------------

def test_sistema_equilibrado_so_tem_sequencia_positiva():
    """O caso que define a transformação: equilibrado é positiva pura."""
    a, b, c = V, V * giro(-120), V * giro(120)
    zero, positiva, negativa = simetricas.de_fasores(a, b, c)

    assert abs(positiva) == pytest.approx(V, rel=1e-12)
    assert abs(negativa) == pytest.approx(0.0, abs=1e-10)
    assert abs(zero) == pytest.approx(0.0, abs=1e-10)


def test_sequencia_invertida_e_negativa_pura():
    """Trocar B por C inverte o sentido de giro — e só sobra negativa.

    É o teste que pega um `a` e `a²` trocados na fórmula: com eles invertidos,
    este caso daria positiva pura e o equilibrado daria negativa pura, e os
    dois pareceriam plausíveis isoladamente.
    """
    a, b, c = V, V * giro(120), V * giro(-120)
    zero, positiva, negativa = simetricas.de_fasores(a, b, c)

    assert abs(negativa) == pytest.approx(V, rel=1e-12)
    assert abs(positiva) == pytest.approx(0.0, abs=1e-10)
    assert abs(zero) == pytest.approx(0.0, abs=1e-10)


def test_tres_fases_iguais_sao_sequencia_zero_pura():
    """`3I0` é a SOMA, não a média: três de 100 dão 300."""
    zero, positiva, negativa = simetricas.de_fasores(V, V, V)

    assert abs(zero) == pytest.approx(3 * V, rel=1e-12)
    assert abs(positiva) == pytest.approx(0.0, abs=1e-10)
    assert abs(negativa) == pytest.approx(0.0, abs=1e-10)


def test_falta_fase_terra_na_fase_A():
    """Tensão da fase A colapsada: aparecem as três sequências juntas.

    A soma das três (o `3V0`) é o que o relé de terra compara com o ajuste, e
    é exatamente a tensão que "faltou" na fase A.
    """
    a, b, c = 0.0, V * giro(-120), V * giro(120)
    zero, positiva, negativa = simetricas.de_fasores(a, b, c)

    assert abs(zero) == pytest.approx(V, rel=1e-12)          # = |0 + b + c| = V
    # A positiva cai para DOIS TERÇOS: é o que a proteção de distância enxerga
    # numa fase-terra, e é por isso que o alcance dela muda nesse tipo de falta.
    assert abs(positiva) == pytest.approx(2 * V / 3, rel=1e-12)
    assert abs(negativa) == pytest.approx(V / 3, rel=1e-12)


def test_falta_entre_fases_nao_gera_sequencia_zero():
    """B e C iguais (curto entre elas): há negativa e NÃO há zero.

    É esta ausência que distingue uma falta bifásica de uma bifásica-terra, e
    é por isso que `3I0` sozinho já classifica metade dos casos.
    """
    curto = (V * giro(-120) + V * giro(120)) / 2
    zero, _, negativa = simetricas.de_fasores(V, curto, curto)

    assert abs(zero) == pytest.approx(0.0, abs=1e-10)
    assert abs(negativa) > 0.1 * V


def test_as_tres_somadas_devolvem_a_fase_original():
    """A transformação é reversível: `Va = V0 + V1 + V2`. Se não fechar, a
    conta perdeu informação pelo caminho."""
    a, b, c = 37.0 * giro(11), 62.0 * giro(-133), 51.0 * giro(94)
    zero, positiva, negativa = simetricas.de_fasores(a, b, c)
    assert zero / 3 + positiva + negativa == pytest.approx(a, rel=1e-12)


def test_funciona_vetorizado_para_virar_curva():
    """A tela desenha 3I0 ao longo do tempo; não pode haver laço em Python."""
    n = 50
    a = np.full(n, V + 0j)
    b, c = np.full(n, V * giro(-120)), np.full(n, V * giro(120))
    zero, positiva, _ = simetricas.de_fasores(a, b, c)
    assert zero.shape == (n,)
    np.testing.assert_allclose(np.abs(positiva), V, rtol=1e-12)


def test_desequilibrio_e_a_razao_entre_negativa_e_positiva():
    assert simetricas.equilibrio(100 + 0j, 0j) == pytest.approx(0.0)
    assert simetricas.equilibrio(100 + 0j, 25 + 0j) == pytest.approx(25.0)
    # Sem positiva não há de que ser percentual — zero, nunca infinito.
    assert simetricas.equilibrio(0j, 10 + 0j) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Quem forma um conjunto
# ---------------------------------------------------------------------------

def registro(*canais: AnalogChannel) -> Record:
    r = Record(source=__import__("pathlib").Path("x"), format_name="teste")
    r.analog_channels = tuple(canais)
    r.analog = np.zeros((len(canais), 8))
    r.time = np.arange(8) / 1200.0
    return r


def canal(indice, nome, unidade="A", fase="", ccbm=""):
    return AnalogChannel(index=indice, name=nome, unit=unidade, phase=fase,
                         component=ccbm)


@pytest.mark.parametrize("nomes,unidade,grandeza", [
    (["Current IA", "Current IB", "Current IC"], "A", "I"),        # Schneider
    (["IAW", "IBW", "ICW"], "A", "I"),                             # SEL
    (["TC BUC 69kV:I A", "TC BUC 69kV:I B", "TC BUC 69kV:I C"], "A", "I"),
    (["Voltage A-G", "Voltage B-G", "Voltage C-G"], "V", "V"),
    (["BARRA A", "BARRA B", "BARRA C"], "kV", "V"),      # a letra repetida
])
def test_deduz_o_conjunto_pelo_nome(nomes, unidade, grandeza):
    """Os padrões dos fabricantes que já vimos, e o caso da letra repetida:
    `BARRA A` tem dois `A`, e só o último é a fase.

    A grandeza sai da UNIDADE, não do nome — um canal chamado `Voltage` mas
    declarado em ampères é corrente, porque a unidade é o que o arquivo
    afirma e o nome é o que alguém digitou.
    """
    achados = conjuntos.de_registro(registro(
        *[canal(i, n, unidade) for i, n in enumerate(nomes)]))
    assert len(achados) == 1
    assert achados[0].origem == conjuntos.OrigemDoConjunto.DEDUZIDA
    assert achados[0].grandeza == grandeza
    assert achados[0].abc == (0, 1, 2)


def test_dois_conjuntos_na_mesma_unidade_nao_se_misturam():
    """O erro que este módulo existe para impedir: somar IA de um TC com IB de
    outro dá um 3I0 sem sentido, com cara de número bom."""
    achados = conjuntos.de_registro(registro(
        canal(0, "Current IA"), canal(1, "Current IB"), canal(2, "Current IC"),
        canal(3, "TC BUC 69kV:I A"), canal(4, "TC BUC 69kV:I B"),
        canal(5, "TC BUC 69kV:I C"),
    ))
    assert len(achados) == 2
    assert {c.abc for c in achados} == {(0, 1, 2), (3, 4, 5)}


def test_o_campo_do_arquivo_ganha_da_deducao():
    """`ccbm` existe na norma exatamente para isto. Quando vem preenchido, não
    há o que deduzir — mesmo que os nomes sugiram outra coisa."""
    achados = conjuntos.de_registro(registro(
        canal(0, "Current IA", ccbm="LINHA 01"),
        canal(1, "Current IB", ccbm="LINHA 01"),
        canal(2, "Current IC", ccbm="LINHA 02"),      # nome igual, equipamento outro
    ))
    assert achados == ()          # nenhum dos dois tem as três fases


def test_conjunto_incompleto_nao_vira_componente_nenhuma():
    """Sem A, B e C não há Fortescue — há chute. Dois terços da informação não
    autorizam mostrar um número."""
    achados = conjuntos.de_registro(registro(
        canal(0, "Current IA"), canal(1, "Current IB")))
    assert achados == ()


def test_o_neutro_entra_junto_mas_nao_e_obrigatorio():
    achados = conjuntos.de_registro(registro(
        canal(0, "Current IA"), canal(1, "Current IB"),
        canal(2, "Current IC"), canal(3, "Current IN"),
    ))
    assert len(achados) == 1
    assert achados[0].canais["N"] == 3
    assert achados[0].abc == (0, 1, 2)


def test_corrente_e_tensao_nao_se_juntam():
    """Unidades diferentes são conjuntos diferentes, sempre."""
    achados = conjuntos.de_registro(registro(
        canal(0, "IA", "A"), canal(1, "IB", "A"), canal(2, "IC", "A"),
        canal(3, "VA", "V"), canal(4, "VB", "V"), canal(5, "VC", "V"),
    ))
    assert len(achados) == 2
    assert {c.grandeza for c in achados} == {"I", "V"}


# ---------------------------------------------------------------------------
# O apelido que distingue um conjunto do outro
# ---------------------------------------------------------------------------

def test_conjunto_unico_nao_ganha_apelido():
    """No registro de distribuição, com uma trinca só, `IA` continua `IA`.
    Sufixo que não distingue nada é ruído."""
    achados = conjuntos.de_registro(registro(
        canal(0, "Current IA"), canal(1, "Current IB"), canal(2, "Current IC")))
    assert achados[0].rotulo == ""
    assert achados[0].origem_do_rotulo == conjuntos.OrigemDoRotulo.UNICO


def test_rele_de_trafo_ganha_AT_e_BT_pelo_nivel_de_tensao():
    """Dois lados, e o de maior tensão é a alta. É a única forma de acertar o
    lado sem adivinhar — e inverter AT com BT num laudo só aparece tarde."""
    achados = conjuntos.de_registro(registro(
        canal(0, "TC 13.8kV:I A"), canal(1, "TC 13.8kV:I B"), canal(2, "TC 13.8kV:I C"),
        canal(3, "TC 138kV:I A"), canal(4, "TC 138kV:I B"), canal(5, "TC 138kV:I C"),
    ))
    por_rotulo = {c.rotulo: c.abc for c in achados}
    assert por_rotulo == {"BT": (0, 1, 2), "AT": (3, 4, 5)}
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.TENSAO for c in achados)


def test_tres_enrolamentos_viram_AT_MT_BT():
    achados = conjuntos.de_registro(registro(
        *[canal(i, f"TC {kv}:I {f}") for i, (kv, f) in enumerate(
            [(nivel, fase) for nivel in ("230kV", "69kV", "13.8kV")
             for fase in "ABC"])]))
    assert [c.rotulo for c in sorted(achados, key=lambda c: c.abc)] == ["AT", "MT", "BT"]


def test_sem_nivel_de_tensao_o_apelido_sai_do_que_DIFERE_nos_nomes():
    """`IAW` e `IAX` são enrolamentos W e X na nomenclatura da SEL. O programa
    não sabe o que é enrolamento — ele corta o que os nomes têm em comum e o
    que sobra distingue, que dá na mesma."""
    achados = conjuntos.de_registro(registro(
        canal(0, "IAW"), canal(1, "IBW"), canal(2, "ICW"),
        canal(3, "IAX"), canal(4, "IBX"), canal(5, "ICX"),
    ))
    por_rotulo = {c.rotulo: c.abc for c in achados}
    assert por_rotulo == {"W": (0, 1, 2), "X": (3, 4, 5)}
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.ARQUIVO
               for c in achados)


def test_mesma_tensao_nos_dois_nao_vira_AT_e_BT():
    """Dois vãos de linha no mesmo 69 kV não são alta e baixa de nada."""
    achados = conjuntos.de_registro(registro(
        canal(0, "TC LINHA 1 69kV:I A"), canal(1, "TC LINHA 1 69kV:I B"),
        canal(2, "TC LINHA 1 69kV:I C"),
        canal(3, "TC LINHA 2 69kV:I A"), canal(4, "TC LINHA 2 69kV:I B"),
        canal(5, "TC LINHA 2 69kV:I C"),
    ))
    assert {c.rotulo for c in achados} == {"1", "2"}
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.ARQUIVO
               for c in achados)


@pytest.mark.parametrize("texto,volts", [
    ("TC BUC 69kV:I A", 69_000.0), ("TC 13.8 kV:I B", 13_800.0),
    ("TC 13,8kV", 13_800.0), ("BARRA 500V", 500.0), ("IAW", None),
])
def test_le_o_nivel_de_tensao_escrito_no_nome(texto, volts):
    assert conjuntos.nivel_de_tensao(texto) == volts


def test_canal_que_nao_e_corrente_nem_tensao_fica_de_fora():
    achados = conjuntos.de_registro(registro(
        canal(0, "FREQ", "Hz"), canal(1, "POT A", "MW"), canal(2, "POT B", "MW")))
    assert achados == ()
