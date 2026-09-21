"""Os pontos em que o cursor gruda.

O que estes testes protegem não é a tela: é o NÚMERO que sai dela. Um ímã que
gruda no lugar errado não dá erro nenhum — ele põe o cursor num instante
plausível, a tabelinha mostra um tempo de trip plausível, e aquilo vai para o
laudo. Por isso cada detector aqui é conferido contra um evento que o teste
mesmo injetou, com a amostra exata conhecida de antemão.
"""

from __future__ import annotations

import numpy as np
import pytest

from osclab.formats import registry
from osclab.plot import imas, janela
from tests import arranjo
from tests.fabrica import escrever_comtrade


def _registro(tmp_path, **kw):
    return registry.read(escrever_comtrade(tmp_path, **kw))


# ---------------------------------------------------------------------------
# Transições de digital
# ---------------------------------------------------------------------------

def test_transicao_acha_TODAS_as_mudancas(tmp_path):
    """E não só a primeira, que é o que a tela guarda para ordenar as tiras.

    Um religamento tem trip, abertura, fechamento e às vezes um segundo trip.
    Um ímã que só conhecesse a primeira mudança serviria para medir o trip e
    seria inútil justamente para o resto da história.
    """
    r = _registro(tmp_path, na=1, nd=2, n=200)
    r.status = np.zeros((2, 200), dtype=np.int8)
    r.status[0, 50:80] = 1          # sobe em 50, desce em 80
    r.status[0, 120:] = 1           # sobe de novo em 120

    assert list(imas.transicoes(r, 0)) == [50, 80, 120]
    assert list(imas.transicoes(r, 1)) == []        # parado o registro inteiro


def test_digital_que_nao_existe_nao_quebra(tmp_path):
    r = _registro(tmp_path, na=1, nd=2, n=64)
    assert list(imas.transicoes(r, 99)) == []
    assert list(imas.transicoes(r, -1)) == []


# ---------------------------------------------------------------------------
# Picos
# ---------------------------------------------------------------------------

def test_pico_e_crista_E_vale():
    """Os dois na mesma lista: o pico negativo de uma corrente é tão pico
    quanto o positivo, e quem procura o pico da falta não sabe de antemão em
    qual dos dois ele caiu."""
    t = np.arange(240) / 1200.0
    onda = np.sin(2 * np.pi * 60 * t)          # 20 amostras por ciclo
    achados = imas.picos(onda)

    # 12 ciclos, dois extremos por ciclo — menos os das bordas, que não têm
    # vizinho dos dois lados para se comparar.
    assert 22 <= achados.size <= 24
    # O primeiro máximo de um seno amostrado a 20/ciclo cai na amostra 5, e os
    # extremos se alternam a cada meio ciclo.
    assert achados[0] == 5
    assert list(np.diff(achados[:6])) == [10, 10, 10, 10, 10]
    # Todos são extremo de verdade, de um lado ou do outro.
    assert all(abs(onda[k]) > 0.99 for k in achados)
    assert any(onda[k] > 0 for k in achados)
    assert any(onda[k] < 0 for k in achados)


# ---------------------------------------------------------------------------
# Passagens por zero
# ---------------------------------------------------------------------------

def test_a_passagem_por_zero_e_a_amostra_MAIS_PERTO_do_zero():
    """A passagem verdadeira cai entre duas amostras. Interpolar daria um
    instante mais exato no papel e um cursor apontando para onde não há
    medida — então fica a que menos mente das duas."""
    t = np.arange(120) / 1200.0
    onda = np.sin(2 * np.pi * 60 * t)
    achados = imas.passagens_por_zero(onda)

    # Duas por ciclo, seis ciclos.
    assert 11 <= achados.size <= 13
    assert list(np.diff(achados[:5])) == [10, 10, 10, 10]
    # E cada uma é mesmo a vizinha mais próxima do zero.
    for k in achados:
        assert abs(onda[k]) < 0.16          # a 20 amostras/ciclo, sen(18°)
        if 0 < k < onda.size - 1:
            assert abs(onda[k]) <= max(abs(onda[k - 1]), abs(onda[k + 1]))


def test_curva_que_nao_cruza_o_zero_nao_tem_passagem():
    """Uma envoltória de RMS não passa por zero. Oferecer um ponto ali seria
    inventar um."""
    assert imas.passagens_por_zero(np.full(60, 70.7)).size == 0
    t = np.arange(120) / 1200.0
    assert imas.passagens_por_zero(np.sin(2 * np.pi * 60 * t) + 2.0).size == 0


def test_amostra_exatamente_zero_e_a_propria_passagem():
    onda = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    assert list(imas.passagens_por_zero(onda)) == [2]


def test_trecho_sem_curva_nao_inventa_passagem():
    """A borda de um `NaN` não é cruzamento de nada."""
    onda = np.concatenate([np.full(20, np.nan),
                           np.sin(2 * np.pi * np.arange(60) / 20)])
    achados = imas.passagens_por_zero(onda)
    assert achados.size > 0
    assert all(a >= 20 for a in achados)


def test_topo_achatado_e_UM_pico_so():
    """Canal saturado tem o topo plano. Contar cada amostra do platô como um
    pico encheria o ímã de pontos no mesmo lugar."""
    onda = np.array([0.0, 1.0, 2.0, 3.0, 3.0, 3.0, 2.0, 1.0, 0.0])
    assert imas.picos(onda).size == 1


def test_trecho_sem_curva_nao_tem_pico():
    """O primeiro ciclo de uma envoltória vem sem valor. `NaN` não é pico de
    nada, e um ponto de atração ali poria o cursor onde não há medida."""
    onda = np.concatenate([np.full(20, np.nan),
                           np.sin(2 * np.pi * np.arange(60) / 20)])
    achados = imas.picos(onda)
    assert achados.size > 0
    assert all(a >= 20 for a in achados)


def test_curva_curta_demais_nao_tem_pico():
    assert imas.picos(np.array([1.0, 2.0])).size == 0


# ---------------------------------------------------------------------------
# Início da perturbação
# ---------------------------------------------------------------------------

def test_o_inicio_sai_na_amostra_em_que_a_onda_mudou(tmp_path):
    """A conta é a grandeza incremental: cada amostra contra a mesma amostra do
    ciclo anterior. Em regime permanente a diferença é zero; quando a rede muda
    de estado, ela salta."""
    r = _registro(tmp_path, na=3, n=600, taxa=1200.0)
    r.analog[:, 400:] *= 4.0
    assert imas.inicio_da_perturbacao(r) == 400


def test_registro_sem_perturbacao_nao_inventa_uma(tmp_path):
    """Uma senoide que se repete do começo ao fim não tem início de nada. Um
    ponto de atração aqui poria o cursor num instante sem significado — e quem
    confere acreditaria nele."""
    assert imas.inicio_da_perturbacao(_registro(tmp_path, na=3, n=600)) is None


def test_ruido_de_uma_amostra_so_nao_e_perturbacao(tmp_path):
    """Um pico isolado no conversor A/D não é o começo de uma falta. Só conta
    o degrau que se mantém."""
    r = _registro(tmp_path, na=1, n=600, taxa=1200.0)
    r.analog[0, 400] += 500.0                  # uma amostra, e só
    assert imas.inicio_da_perturbacao(r) is None


def test_sem_pre_falta_nao_ha_com_que_calibrar(tmp_path):
    """O limiar sai do ruído de regime permanente do próprio registro. Sem um
    pedaço antes do evento, não há ruído para medir — e responder mesmo assim
    seria chutar."""
    r = _registro(tmp_path, na=1, n=600, taxa=1200.0)
    r.trigger_time = r.start_time              # disparo na primeira amostra
    assert imas.inicio_da_perturbacao(r) is None


def test_registro_vazio_nao_quebra(tmp_path):
    r = _registro(tmp_path, na=1, n=8)
    assert imas.inicio_da_perturbacao(r) is None


# ---------------------------------------------------------------------------
# Afinar por coluna de pixel
# ---------------------------------------------------------------------------

def test_sobra_no_maximo_um_ponto_por_coluna():
    """Mira é feita com o mouse, e o mouse não distingue duas amostras no mesmo
    pixel. Oferecer as duas faria o ímã escolher por um critério invisível."""
    amostras = np.arange(0, 1000)
    assert len(imas.afinar(amostras, 0, 1000, 50)) == 50
    assert len(imas.afinar(amostras, 0, 1000, 5000)) == 1000


def test_afinar_respeita_a_janela():
    amostras = np.array([10, 20, 30, 40, 50])
    assert imas.afinar(amostras, 25, 45, 900) == [30, 40]
    assert imas.afinar(amostras, 100, 200, 900) == []
    assert imas.afinar(np.empty(0, dtype=np.int64), 0, 100, 900) == []


# ---------------------------------------------------------------------------
# O que chega à tela
# ---------------------------------------------------------------------------

def test_os_pontos_chegam_no_pacote_da_janela(tmp_path):
    """Os instantes nascem no Python, onde há teste. A tela só escolhe qual
    deles está mais perto do mouse — isso é mira, não conta."""
    r = _registro(tmp_path, na=3, nd=2, n=600, taxa=1200.0)
    r.analog[:, 400:] *= 4.0
    r.status = np.zeros((2, 600), dtype=np.int8)
    r.status[0, 420:] = 1

    pacote = janela.montar(r, layout=arranjo.padrao(r), colunas=900)

    assert pacote["inicio_da_perturbacao"] == pytest.approx(float(r.time[400]))

    analogico = next(p for p in pacote["paineis"] if p["tipo"] == "analogico")
    sinal = analogico["sinais"][0]
    assert sinal["picos"] and sinal["zeros"], \
        "todo canal desenhado leva os picos e as passagens por zero dele"
    # Pico não é passagem por zero: as duas listas não se cruzam.
    assert not set(sinal["picos"]) & set(sinal["zeros"])
    # Todo ponto oferecido é uma amostra de VERDADE do arquivo: o ímã nunca
    # interpola, pela mesma razão que o cursor sempre cai numa amostra.
    instantes = {round(float(x), 9) for x in r.time}
    assert all(t in instantes for t in sinal["picos"] + sinal["zeros"])

    digital = next(p for p in pacote["paineis"] if p["tipo"] == "digital")
    tira = next(t for t in digital["tiras"] if t["indice"] == 0)
    assert tira["transicoes"] == [pytest.approx(float(r.time[420]))]


def test_janela_recortada_so_leva_os_pontos_dela(tmp_path):
    """Ponto fora da janela não pode ser oferecido: o cursor saltaria para fora
    do que está desenhado."""
    r = _registro(tmp_path, na=1, n=600, taxa=1200.0)
    pacote = janela.montar(r, de=0.2, ate=0.3, layout=arranjo.padrao(r),
                           colunas=900)
    sinal = pacote["paineis"][0]["sinais"][0]
    assert sinal["picos"]
    assert all(0.2 <= t <= 0.3 for t in sinal["picos"] + sinal["zeros"])


def test_a_falta_ANTES_do_disparo_e_encontrada(tmp_path):
    """O defeito que este teste existe para impedir, e que passou despercebido
    porque todo sintético injetava a falta depois do disparo.

    O relé dispara **por causa** da falta: o início dela está no trecho de
    pré-falta que ele gravou, sempre. A primeira versão descartava qualquer
    candidato anterior ao disparo achando que era ruído — ou seja, jogava fora
    justamente a resposta certa em TODO registro de relé de verdade.
    """
    r = _registro(tmp_path, na=3, n=600, taxa=1200.0)
    disparo = imas._amostras_de_pre_falta(r)
    assert disparo > 30, "a fábrica precisa gravar pré-falta para este teste"

    antes = disparo - 20
    r.analog[:, antes:] *= 4.0
    assert imas.inicio_da_perturbacao(r) == antes


def test_o_inicio_e_a_PRIMEIRA_mudanca_e_nao_a_abertura(tmp_path):
    """Numa falta que o disjuntor extingue há duas descontinuidades: o começo
    e a abertura. A que interessa é a primeira."""
    r = _registro(tmp_path, na=3, n=720, taxa=1200.0)
    r.analog[:, 300:460] *= 4.0
    r.analog[:, 460:] = 0.0
    assert imas.inicio_da_perturbacao(r) == 300


def test_afundamento_de_tensao_sozinho_tambem_conta(tmp_path):
    """Nem toda perturbação levanta corrente. Um afundamento de 7 % já é
    descontinuidade, e um detector que só olhasse magnitude o perderia."""
    r = _registro(tmp_path, na=3, n=600, taxa=1200.0)
    r.analog[:, 300:] *= 0.93
    assert imas.inicio_da_perturbacao(r) == 300


def test_ruido_no_registro_inteiro_nao_vira_perturbacao(tmp_path):
    """O limiar sai da mediana de `|d|` do registro todo, então ruído de fundo
    sobe o limiar junto e continua não disparando."""
    r = _registro(tmp_path, na=3, n=600, taxa=1200.0)
    gerador = np.random.default_rng(7)
    r.analog += gerador.normal(0.0, 1.5, r.analog.shape)
    assert imas.inicio_da_perturbacao(r) is None

    # E com falta em cima do mesmo ruído, ele acha.
    r.analog[:, 300:] *= 4.0
    assert imas.inicio_da_perturbacao(r) == 300
