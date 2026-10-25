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

def test_todo_conjunto_ganha_NOME_DE_GRUPO_mesmo_sozinho():
    """Já foi condicional: com uma trinca só, o nome saía limpo (`3I0`, `IN`) e
    o apelido seria barulho. Deixou de ser quando o grupo virou objeto que o
    usuário EDITA — o editor de grupos chama aquilo de `G1`, o rodapé do
    gráfico cita `G1`, e um sinal chamado `3I0` sem grupo no nome obrigaria
    quem lê a descobrir de qual deles ele saiu.

    O preço é este: num alimentador o nome é `3I0 G1` onde antes era `3I0`."""
    achados = conjuntos.de_registro(registro(
        canal(0, "Current IA"), canal(1, "Current IB"), canal(2, "Current IC")))
    assert achados[0].rotulo == "G1"
    assert achados[0].origem_do_rotulo == conjuntos.OrigemDoRotulo.NUMERO


def test_o_NIVEL_DE_TENSAO_nao_decide_mais_o_lado():
    """O programa não diz mais alta nem baixa, nem tendo o nível no nome.

    `AT`/`BT` afirmava duas coisas: que há um transformador ali, e qual lado é
    qual. A segunda saía da primeira, e a primeira nunca era verificada — um
    relé que grava uma linha de 138 kV e o serviço auxiliar de 13,8 kV tem dois
    níveis e nenhum transformador no meio. Quem sabe é quem abriu o arquivo.
    """
    achados = conjuntos.de_registro(registro(
        canal(0, "TC 13.8kV:I A"), canal(1, "TC 13.8kV:I B"), canal(2, "TC 13.8kV:I C"),
        canal(3, "TC 138kV:I A"), canal(4, "TC 138kV:I B"), canal(5, "TC 138kV:I C"),
    ))
    por_rotulo = {c.rotulo: c.abc for c in achados}
    assert por_rotulo == {"G1": (0, 1, 2), "G2": (3, 4, 5)}
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.NUMERO
               for c in achados)


def test_tres_enrolamentos_tambem_sao_numerados():
    achados = conjuntos.de_registro(registro(
        *[canal(i, f"TC {kv}:I {f}") for i, (kv, f) in enumerate(
            [(nivel, fase) for nivel in ("230kV", "69kV", "13.8kV")
             for fase in "ABC"])]))
    assert [c.rotulo for c in sorted(achados, key=lambda c: c.abc)] == [
        "G1", "G2", "G3"]


def test_a_contagem_do_GRUPO_e_do_arquivo_e_nao_da_grandeza():
    """`G1` tem que apontar para um grupo só, porque o usuário vai editá-lo por
    esse nome. Então a trinca de corrente é `G1` e a de tensão é `G2` — e não
    `G1` as duas, cada uma contada dentro da sua grandeza.

    A posição DENTRO da grandeza continua existindo, em `ordem`: é ela que diz
    que a primeira corrente e a primeira tensão são do mesmo lado do
    equipamento, e é o que intercala os painéis na abertura. Ver
    `plot/paineis.py`."""
    achados = conjuntos.de_registro(registro(
        canal(0, "IA", "A"), canal(1, "IB", "A"), canal(2, "IC", "A"),
        canal(3, "VA", "V"), canal(4, "VB", "V"), canal(5, "VC", "V"),
    ))
    assert [c.rotulo for c in achados] == ["G1", "G2"]
    assert [c.ordem for c in achados] == [1, 1]


def test_sem_nivel_de_tensao_o_apelido_e_um_NUMERO():
    """`IAW` e `IAX` são os terminais W e X de um SEL. O terminal é o nome que
    o relé dá ao borne dele, e **não diz de que lado do equipamento aquilo
    está** — quem lê `IA W` não sabe mais que quem lê `IA G1`, e corre o risco
    de achar que sabe. O nome do arquivo continua ao lado do nosso na tela.
    """
    achados = conjuntos.de_registro(registro(
        canal(0, "IAW"), canal(1, "IBW"), canal(2, "ICW"),
        canal(3, "IAX"), canal(4, "IBX"), canal(5, "ICX"),
    ))
    por_rotulo = {c.rotulo: c.abc for c in achados}
    assert por_rotulo == {"G1": (0, 1, 2), "G2": (3, 4, 5)}
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.NUMERO
               for c in achados)


def test_mesma_tensao_nos_dois_nao_vira_AT_e_BT():
    """Dois vãos de linha no mesmo 69 kV não são alta e baixa de nada."""
    achados = conjuntos.de_registro(registro(
        canal(0, "TC LINHA 1 69kV:I A"), canal(1, "TC LINHA 1 69kV:I B"),
        canal(2, "TC LINHA 1 69kV:I C"),
        canal(3, "TC LINHA 2 69kV:I A"), canal(4, "TC LINHA 2 69kV:I B"),
        canal(5, "TC LINHA 2 69kV:I C"),
    ))
    assert {c.rotulo for c in achados} == {"G1", "G2"}
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.NUMERO
               for c in achados)


@pytest.mark.parametrize("texto,volts", [
    ("TC BUC 69kV:I A", 69_000.0), ("TC 13.8 kV:I B", 13_800.0),
    ("TC 13,8kV", 13_800.0), ("BARRA 500V", 500.0), ("IAW", None),
    # A Siemens escreve `34-5kV` para 34,5 kV: o ponto decimal não cabe no
    # nome do canal dela. Lido como `5 kV`, errava por um fator de sete.
    ("TC EXT 34-5kV:I A", 34_500.0),
    # E o pior de todos: `L1V` NÃO é "1 volt". Lido assim, as duas linhas de
    # um TWFL — as duas no mesmo nível — apareciam com tensões diferentes, e
    # daí a alta e a baixa de um transformador que não existe.
    ("L1VA", None), ("L2VA", None), ("J2 Van", None),
])
def test_le_o_nivel_de_tensao_escrito_no_nome(texto, volts):
    assert conjuntos.nivel_de_tensao(texto) == volts


def test_niveis_PARECIDOS_DEMAIS_nao_viram_alta_e_baixa():
    """Dois vãos de 230 kV com um dígito trocado na digitação não são alta e
    baixa de coisa nenhuma. Errar o lado num laudo só aparece tarde."""
    achados = conjuntos.de_registro(registro(
        canal(0, "TC 230kV:I A"), canal(1, "TC 230kV:I B"), canal(2, "TC 230kV:I C"),
        canal(3, "TC 230.1kV:I A"), canal(4, "TC 230.1kV:I B"),
        canal(5, "TC 230.1kV:I C"),
    ))
    assert {c.rotulo for c in achados} == {"G1", "G2"}


def test_as_duas_linhas_de_um_TWFL_nao_viram_alta_e_baixa():
    """`L1VA` e `L2VA` são a linha 1 e a linha 2, no MESMO nível de tensão.
    Enquanto o `1` e o `2` eram lidos como volts, elas viravam `AT` e `BT`."""
    # O `ph` vem preenchido, como no arquivo real do TWFL.
    achados = conjuntos.de_registro(registro(
        canal(0, "L1VA", "kV", "A"), canal(1, "L1VB", "kV", "B"),
        canal(2, "L1VC", "kV", "C"),
        canal(3, "L2VA", "kV", "A"), canal(4, "L2VB", "kV", "B"),
        canal(5, "L2VC", "kV", "C"),
    ))
    assert {c.rotulo for c in achados} == {"G1", "G2"}
    assert all(c.origem_do_rotulo == conjuntos.OrigemDoRotulo.NUMERO
               for c in achados)


def test_tres_trincas_vivas_sao_TODAS_numeradas():
    """Com três, não há nomenclatura de lado que se aplique — e inventar uma
    seria afirmar do equipamento o que o arquivo não diz."""
    achados = conjuntos.de_registro(registro(
        *[canal(i, f"I{f}{t}") for i, (t, f) in enumerate(
            [(term, fase) for term in ("W", "X", "Y") for fase in "ABC"])]))
    assert [c.rotulo for c in sorted(achados, key=lambda c: c.abc)] == [
        "G1", "G2", "G3"]


def test_canal_que_nao_e_corrente_nem_tensao_fica_de_fora():
    achados = conjuntos.de_registro(registro(
        canal(0, "FREQ", "Hz"), canal(1, "POT A", "MW"), canal(2, "POT B", "MW")))
    assert achados == ()


def test_ccbm_SO_DE_DIGITOS_nao_e_nome_de_equipamento():
    """O SIPROTEC da Siemens escreve o NÚMERO do canal no `ccbm`: `1`, `2`, `3`
    para IA, IB, IC.

    O `ccbm` da norma é o equipamento vigiado, e por definição é o mesmo nas
    três fases. Acreditar num número põe cada fase num conjunto só dela — e o
    registro de um transformador de verdade ficou por todo o marco 0.4 sem
    componente simétrica nenhuma, com dois canais chamados `IA` na mesma tela,
    sem erro nenhum.
    """
    achados = conjuntos.de_registro(registro(
        canal(0, "TC 69kV:I A", ccbm="1"), canal(1, "TC 69kV:I B", ccbm="2"),
        canal(2, "TC 69kV:I C", ccbm="3"),
        canal(3, "TC 13.8kV:I A", ccbm="1"), canal(4, "TC 13.8kV:I B", ccbm="2"),
        canal(5, "TC 13.8kV:I C", ccbm="3"),
    ))
    assert len(achados) == 2
    assert {c.rotulo for c in achados} == {"G1", "G2"}


def test_ccbm_de_verdade_continua_mandando():
    """A correção acima não pode derrubar o campo quando ele vem preenchido do
    jeito que a norma manda."""
    achados = conjuntos.de_registro(registro(
        canal(0, "IA", ccbm="TRAFO T1"), canal(1, "IB", ccbm="TRAFO T1"),
        canal(2, "IC", ccbm="TRAFO T1"),
    ))
    assert len(achados) == 1
    assert achados[0].origem == conjuntos.OrigemDoConjunto.DECLARADA


# ---------------------------------------------------------------------------
# A trinca em DELTA: o relé mediu entre fases
# ---------------------------------------------------------------------------
#
# O que se amarra aqui é a diferença que não aparece olhando a onda. `VAB` e
# `VA` são duas senoides; qual das duas está no arquivo só se sabe pelo nome do
# canal, e errar isso produz `3V0 = 0` sempre e `V1` 73 % maior — tudo na
# unidade certa, sem aviso nenhum.

def _lacos(a, b, c):
    """As três diferenças, na ordem AB, BC, CA."""
    return (a - b, b - c, c - a)


def test_de_lacos_recupera_a_positiva_e_a_negativa_exatas():
    """O coração da conta: desfazer o √3∠±30° devolve o valor DE FASE.

    Com desequilíbrio, que é quando alguém olha. Equilibrado, a negativa é
    zero e o teste passaria com a rotação errada.
    """
    a, b, c = V, 0.4 * V * giro(-150), 0.8 * V * giro(95)
    _, p_fase, n_fase = simetricas.de_fasores(a, b, c)
    _, p_laco, n_laco = simetricas.de_lacos(*_lacos(a, b, c))

    assert p_laco == pytest.approx(p_fase, rel=1e-12)
    assert n_laco == pytest.approx(n_fase, rel=1e-12)


def test_de_lacos_recusa_a_sequencia_zero():
    """`VAB + VBC + VCA ≡ 0`. Devolver esse zero como `3V0` seria afirmar
    «não há falta à terra» a partir de uma identidade algébrica."""
    # Uma falta à terra franca na fase A: há MUITO 3V0 de verdade.
    a, b, c = 0.0, V * giro(-120), V * giro(120)
    zero_de_fase, _, _ = simetricas.de_fasores(a, b, c)
    assert abs(zero_de_fase) == pytest.approx(V, rel=1e-12)

    zero, _, _ = simetricas.de_lacos(*_lacos(a, b, c))
    assert cmath.isnan(zero)


def test_sem_desfazer_o_giro_o_erro_seria_de_73_por_cento():
    """O tamanho do erro que esta função existe para impedir — escrito.

    Se alguém um dia simplificar `de_lacos` para chamar `de_fasores` direto,
    este número é o que muda na tela de quem está analisando uma falta.
    """
    a, b, c = V, V * giro(-120), V * giro(120)
    _, cru, _ = simetricas.de_fasores(*_lacos(a, b, c))
    assert abs(cru) / V == pytest.approx(math.sqrt(3.0), rel=1e-12)


def test_canais_entre_fases_formam_uma_trinca_em_delta():
    """`VAB`, `VBC`, `VCA` viram UMA trinca, marcada como de linha.

    Antes eles nem viravam trinca: `_normalizar` só conhecia A, B e C, e os
    três canais ficavam soltos — sem `V1`, sem `V2` e sem grupo.
    """
    achados = conjuntos.de_registro(registro(
        canal(0, "VAB", "kV", fase="AB"),
        canal(1, "VBC", "kV", fase="BC"),
        canal(2, "VCA", "kV", fase="CA"),
    ))
    assert len(achados) == 1
    assert achados[0].e_de_linha
    assert achados[0].base == conjuntos.LINHA
    assert achados[0].abc == (0, 1, 2)
    assert achados[0].rotulos == ("AB", "BC", "CA")


def test_fase_e_delta_no_mesmo_nome_nao_viram_trinca_misturada():
    """Volt de fase somado com volt de linha dá três números plausíveis e sem
    significado. A base completa vence; com as duas, vence a de fase."""
    achados = conjuntos.de_registro(registro(
        canal(0, "VA", "kV", fase="A"), canal(1, "VB", "kV", fase="B"),
        canal(2, "VC", "kV", fase="C"), canal(3, "VAB", "kV", fase="AB"),
    ))
    assert len(achados) == 1
    assert achados[0].base == conjuntos.FASE
    assert achados[0].abc == (0, 1, 2)


def test_o_nome_do_conjunto_tira_as_DUAS_letras_do_laco():
    """`sem_a_fase` tirava um caractere só: `IAB` virava `I*B` contra o `I*C`
    de `IBC` — três conjuntos de um canal cada, onde há uma trinca."""
    assert conjuntos.sem_a_fase("IAB", "AB") == "I*"
    assert conjuntos.sem_a_fase("IBC", "BC") == "I*"
    assert conjuntos.sem_a_fase("ICA", "CA") == "I*"
    assert conjuntos.sem_a_fase("IAW", "A") == "I*W"


@pytest.mark.parametrize("fase", ["A", "B", "C"])
def test_sem_as_marcas_tira_a_letra_solta_e_nao_a_da_palavra(fase):
    """O religador escreve `T1 Phase C Current`: a ÚLTIMA ocorrência do C é a
    de `CURRENT`. A segunda tentativa tira a letra onde ela é marca de fase."""
    assert (conjuntos._sem_as_marcas(f"T1 Phase {fase} Current", fase)
            == "T1 PHASE * CURRENT")
    assert (conjuntos._sem_as_marcas(f"T0 Phase {fase} Voltage Res.Sensor", fase)
            == "T0 PHASE * VOLTAGE RES.SENSOR")
    # O PL300 escreve a fase DUAS vezes; as duas saem.
    assert (conjuntos._sem_as_marcas(f"I{fase}-Int.Fase {fase}", fase)
            == "I*-INT.FASE *")


def test_a_chave_principal_nao_mudou():
    assert conjuntos.sem_a_fase("BARRA A", "A") == "BARRA *"
    assert conjuntos.sem_a_fase("TC BUC 69kV:I A", "A") == "TC BUC 69KV:I *"
    assert conjuntos.sem_a_fase("Current IA", "A") == "CURRENT I*"
    assert conjuntos.sem_a_fase("Voltage A-G", "A") == "VOLTAGE *-G"
    assert conjuntos.sem_a_fase("IAW1", "A") == "I*W1"
    # O `IC` do começo é o nome do equipamento, não a fase.
    assert conjuntos.sem_a_fase("IC 13.8kV:I C", "C") == "IC 13.8KV:I *"


def _so_nomes(nomes) -> Record:
    canais = tuple(AnalogChannel(index=i, name=n, unit="A", phase="")
                   for i, n in enumerate(nomes))
    return Record(source=None, format_name="teste", station="", line_frequency=60.0,
                  start_time=None, analog_channels=canais,
                  analog=np.zeros((len(nomes), 10)), time=np.arange(10) / 1200.0)


@pytest.mark.parametrize("molde", ["T1 Phase {} Current", "I{}-Int.Fase {}"])
def test_a_trinca_do_religador_e_do_pl300_fecha(molde):
    r = _so_nomes([molde.format(f, f) for f in "ABC"])
    achados = conjuntos.de_registro(r)
    assert len(achados) == 1 and achados[0].abc == (0, 1, 2)


def test_a_segunda_tentativa_nao_rouba_canal_de_trinca_que_ja_fechou():
    r = _so_nomes(["IC 13.8kV:I A", "IC 13.8kV:I B", "IC 13.8kV:I C",
                   "IC 138kV:I A", "IC 138kV:I B", "IC 138kV:I C"])
    assert [c.abc for c in conjuntos.de_registro(r)] == [(0, 1, 2), (3, 4, 5)]


def test_ccbm_com_o_nome_do_rele_em_todo_canal_nao_junta_os_terminais():
    """O 487E (e o nosso leitor de `.CEV`) escreve o mesmo `ccbm` em todo
    canal — o nome do RELÉ. Juntar por ele punha os terminais S e T num grupo
    só, e o T sumia: 23 dos 28 registros de trafo ficavam sem diferencial."""
    nomes = ["IAS", "IBS", "ICS", "IAT", "IBT", "ICT"]
    rele = "ALTA TR01_UPC1"
    canais = tuple(AnalogChannel(index=i, name=n, unit="A", phase="", component=rele)
                   for i, n in enumerate(nomes))
    r = Record(source=None, format_name="teste", station="", line_frequency=60.0,
               start_time=None, analog_channels=canais,
               analog=np.zeros((6, 10)), time=np.arange(10) / 1200.0)
    assert sorted(c.abc for c in conjuntos.de_registro(r)) == [(0, 1, 2), (3, 4, 5)]


def test_ccbm_que_e_mesmo_de_equipamento_continua_valendo():
    canais = tuple(AnalogChannel(index=i, name=f"I{f}", unit="A", phase=f, component="TC BUC")
                   for i, f in enumerate("ABC"))
    r = Record(source=None, format_name="teste", station="", line_frequency=60.0,
               start_time=None, analog_channels=canais,
               analog=np.zeros((3, 10)), time=np.arange(10) / 1200.0)
    (unico,) = conjuntos.de_registro(r)
    assert unico.nome == "TC BUC" and unico.origem == conjuntos.OrigemDoConjunto.DECLARADA
