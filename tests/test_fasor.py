"""A matemática do fasor, contra respostas conhecidas.

Um fasor errado não dá erro nenhum: ele devolve um número plausível, com a
unidade certa, e some dentro do relatório. Por isso cada teste aqui monta um
sinal de resposta SABIDA e confere o número, em vez de comparar com outra
implementação — que poderia estar errada junto.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.dsp import fasor


def senoide(amplitude: float, graus: float, por_ciclo: int = 20,
            ciclos: int = 4, dc: float = 0.0) -> np.ndarray:
    """`amplitude * cos(ωt + fase) + dc`, amostrada em `por_ciclo`.

    A amostra do índice 0 fica em t=0, então o fasor do ciclo que termina na
    amostra `k` tem ângulo `graus` referido àquele instante.
    """
    n = por_ciclo * ciclos
    t = np.arange(n) / por_ciclo                       # em ciclos
    return amplitude * np.cos(2 * np.pi * t + math.radians(graus)) + dc


# ---------------------------------------------------------------------------
# O básico: amplitude e ângulo
# ---------------------------------------------------------------------------

def test_o_modulo_e_eficaz_e_nao_amplitude():
    """Conferido contra o SIGRA: a coluna "Fundamental" dele é eficaz.

    Implementar como amplitude daria √2 de diferença — erro que se procura por
    horas, porque o gráfico continua parecendo certo.
    """
    sinal = senoide(amplitude=100.0, graus=0.0)
    f = fasor.no_instante(sinal, i=len(sinal) - 1, por_ciclo=20)
    assert f.fundamental == pytest.approx(100.0 / math.sqrt(2.0), rel=1e-9)


@pytest.mark.parametrize("graus", [0.0, 30.0, 90.0, -120.0, 179.0, -179.0])
def test_o_angulo_sai_referido_ao_cursor(graus):
    """A referência do ângulo é o ÚLTIMO ponto da janela, não o primeiro.

    Sem isso, o ângulo dependeria do tamanho da janela — e um registro a 32
    amostras/ciclo discordaria de um a 20 no mesmo instante.
    """
    por_ciclo = 20
    sinal = senoide(100.0, graus, por_ciclo=por_ciclo)
    # A amostra 3*por_ciclo cai exatamente em t = 3 ciclos, ou seja, na mesma
    # posição da onda que t = 0: o ângulo tem que ser o mesmo.
    f = fasor.no_instante(sinal, i=3 * por_ciclo, por_ciclo=por_ciclo)
    assert fasor.em_relacao_a(f.angulo, 0.0) == pytest.approx(graus, abs=1e-6)


def test_o_angulo_anda_com_o_cursor():
    """Uma amostra adiante a 20 por ciclo são 18° a mais."""
    por_ciclo = 20
    sinal = senoide(100.0, 0.0, por_ciclo=por_ciclo)
    a = fasor.no_instante(sinal, i=2 * por_ciclo, por_ciclo=por_ciclo)
    b = fasor.no_instante(sinal, i=2 * por_ciclo + 1, por_ciclo=por_ciclo)
    assert fasor.em_relacao_a(b.angulo, a.angulo) == pytest.approx(18.0, abs=1e-6)


def test_defasagem_de_120_graus_entre_fases():
    """O caso que sustenta as componentes simétricas do 0.4b."""
    por_ciclo = 20
    i = 3 * por_ciclo
    fa = fasor.no_instante(senoide(100.0, 0.0), i, por_ciclo)
    fb = fasor.no_instante(senoide(100.0, -120.0), i, por_ciclo)
    fc = fasor.no_instante(senoide(100.0, 120.0), i, por_ciclo)

    assert fasor.em_relacao_a(fb.angulo, fa.angulo) == pytest.approx(-120.0, abs=1e-6)
    assert fasor.em_relacao_a(fc.angulo, fa.angulo) == pytest.approx(120.0, abs=1e-6)


# ---------------------------------------------------------------------------
# A janela termina no cursor
# ---------------------------------------------------------------------------

def test_a_janela_e_o_ciclo_que_ACABOU_de_passar():
    """O relé só conhece o passado: o módulo leva um ciclo inteiro para subir.

    Sinal de 10 A que vira 100 A na amostra 40. Meio ciclo depois do degrau, a
    janela ainda tem metade de cada nível — o módulo tem que estar no meio do
    caminho, nunca já no valor final.
    """
    por_ciclo = 20
    sinal = np.concatenate([senoide(10.0, 0.0, ciclos=2),
                            senoide(100.0, 0.0, ciclos=2)])

    antes = fasor.no_instante(sinal, i=39, por_ciclo=por_ciclo)
    meio = fasor.no_instante(sinal, i=49, por_ciclo=por_ciclo)
    depois = fasor.no_instante(sinal, i=59, por_ciclo=por_ciclo)

    assert antes.fundamental == pytest.approx(10.0 / math.sqrt(2), rel=1e-6)
    assert depois.fundamental == pytest.approx(100.0 / math.sqrt(2), rel=1e-6)
    # No meio: nem o antigo, nem o novo.
    assert antes.fundamental < meio.fundamental < depois.fundamental


def test_nao_ha_fasor_sem_um_ciclo_inteiro_antes():
    """Meia janela daria um número plausível e errado — a pior espécie."""
    sinal = senoide(100.0, 0.0, por_ciclo=20)
    assert fasor.no_instante(sinal, i=10, por_ciclo=20) is None
    assert fasor.no_instante(sinal, i=19, por_ciclo=20) is not None


# ---------------------------------------------------------------------------
# DC, harmônicos e o RMS verdadeiro
# ---------------------------------------------------------------------------

def test_a_dc_nao_contamina_a_fundamental():
    """Falta assimétrica tem DC de decaimento. A DFT de um ciclo inteiro a
    rejeita — e é por isso que a janela precisa ser de um ciclo EXATO."""
    sinal = senoide(100.0, 0.0, dc=40.0)
    f = fasor.no_instante(sinal, i=59, por_ciclo=20)
    assert f.fundamental == pytest.approx(100.0 / math.sqrt(2), rel=1e-9)
    assert f.dc == pytest.approx(40.0, rel=1e-9)


def test_a_dc_percentual_segue_a_convencao_do_sigra():
    """Conferido com o registro real: DC% é relativa à fundamental EFICAZ.

        Current IC C | Fundamental 2,3449 A | Extremum 3,7229 A | DC 16,9 %
        2,3449 × √2 = 3,316 de pico, + 16,9 % × 2,3449 = 3,712 ≈ 3,7229
    """
    eficaz = 2.3449
    sinal = senoide(eficaz * math.sqrt(2), 0.0, dc=0.169 * eficaz)
    f = fasor.no_instante(sinal, i=59, por_ciclo=20)
    assert f.dc_percentual == pytest.approx(16.9, abs=0.1)
    assert f.maximo == pytest.approx(3.71, abs=0.02)


def test_o_rms_verdadeiro_inclui_o_que_a_fundamental_nao_ve():
    """Em senoide pura os dois coincidem; com harmônico, não. A diferença é o
    aviso de que o fasor sozinho não conta a história."""
    puro = fasor.no_instante(senoide(100.0, 0.0), i=59, por_ciclo=20)
    assert puro.rms == pytest.approx(puro.fundamental, rel=1e-9)
    # A distorção é PERCENTUAL e sai de uma raiz de diferença de quadrados, que
    # amplifica o resíduo do ponto flutuante: 1e-4 % já é zero para qualquer uso.
    assert puro.distorcao == pytest.approx(0.0, abs=1e-4)

    # Fundamental de 100 com terceiro harmônico de 30 (30 %).
    t = np.arange(80) / 20.0
    com_harmonico = 100 * np.cos(2 * np.pi * t) + 30 * np.cos(2 * np.pi * 3 * t)
    f = fasor.no_instante(com_harmonico, i=59, por_ciclo=20)

    assert f.fundamental == pytest.approx(100.0 / math.sqrt(2), rel=1e-9)
    assert f.rms > f.fundamental
    assert f.distorcao == pytest.approx(30.0, abs=0.5)


def test_o_extremo_e_o_pico_real_da_janela():
    sinal = senoide(100.0, 0.0, dc=40.0)
    f = fasor.no_instante(sinal, i=59, por_ciclo=20)
    assert f.maximo == pytest.approx(140.0, rel=1e-6)
    assert f.minimo == pytest.approx(-60.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Bordas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("taxa,nominal,esperado", [
    (1200.0, 60.0, 20), (960.0, 60.0, 16), (1920.0, 60.0, 32),
    (5760.0, 60.0, 96), (1000.0, 50.0, 20), (0.0, 60.0, 0),
])
def test_amostras_por_ciclo(taxa, nominal, esperado):
    assert fasor.amostras_por_ciclo(taxa, nominal) == esperado


def test_janela_curta_demais_nao_vira_fasor():
    assert fasor.de_janela(np.array([1.0, 2.0])) is None


def test_janela_com_buraco_nao_vira_fasor():
    """Canal saturado ou amostra perdida: melhor não responder."""
    ruim = senoide(100.0, 0.0)[:20].copy()
    ruim[5] = np.nan
    assert fasor.de_janela(ruim) is None


def test_sinal_zerado_nao_divide_por_zero():
    f = fasor.de_janela(np.zeros(20))
    assert f.fundamental == 0.0
    # Sem sinal não há de que ser percentual: traço, não zero. Zero afirmaria
    # "medi, e a DC é nula"; o traço diz "não há como medir isto aqui".
    assert f.dc_percentual is None
    assert f.distorcao is None


# ---------------------------------------------------------------------------
# Percentual de coisa nenhuma
# ---------------------------------------------------------------------------

def test_sem_fundamental_nao_ha_percentual():
    """O caso real que motivou a guarda.

    Canal de corrente depois de o disjuntor abrir: 0,15 A de offset parado do
    conversor A/D e nada de 60 Hz. A tela mostrava `DC 5.484,9 %` — conta certa,
    informação lixo. Quem lesse aquilo procuraria um defeito que não existe.
    """
    quase_nada = np.full(20, 0.1536) + 0.0028 * np.cos(2 * np.pi * np.arange(20) / 20)
    f = fasor.de_janela(quase_nada)

    # As MEDIDAS continuam valendo: têm unidade e não dependem de denominador.
    assert f.dc == pytest.approx(0.1536, rel=1e-6)
    assert f.rms == pytest.approx(0.1536, abs=0.001)
    # Os PERCENTUAIS, não.
    assert f.serve_de_referencia is False
    assert f.dc_percentual is None
    assert f.distorcao is None


def test_falta_assimetrica_de_verdade_continua_mostrando():
    """A guarda não pode comer o número que interessa.

    Uma falta com 60 % de DC é assimetria de livro — é exatamente o que satura
    TC e atrasa o relé, e tem que aparecer.
    """
    eficaz = 100.0
    sinal = senoide(eficaz * math.sqrt(2), 0.0, dc=0.60 * eficaz)
    f = fasor.no_instante(sinal, i=59, por_ciclo=20)

    assert f.serve_de_referencia is True
    assert f.dc_percentual == pytest.approx(60.0, abs=0.1)


@pytest.mark.parametrize("fracao,esperado", [
    (0.90, True),    # senoide quase limpa
    (0.50, True),    # bem distorcida, mas ainda é um sinal de 60 Hz
    (0.10, False),   # o que não é fundamental supera a fundamental em 10x
    (0.02, False),   # ruído
])
def test_o_limite_e_a_fundamental_sobre_o_rms_da_janela(fracao, esperado):
    """A regra olha a própria janela: que fração dela é 60 Hz.

    Monta-se uma janela com a fundamental valendo `fracao` do RMS total, o
    resto em harmônico. É o critério inteiro, num teste só.
    """
    n = 20
    t = np.arange(n) / n
    resto = math.sqrt(max(1.0 - fracao**2, 0.0))
    janela = (fracao * np.cos(2 * np.pi * t)
              + resto * np.cos(2 * np.pi * 7 * t))
    assert fasor.de_janela(janela).serve_de_referencia is esperado


@pytest.mark.parametrize("bruto,referencia,esperado", [
    (10.0, 0.0, 10.0),
    (190.0, 0.0, -170.0),
    (-190.0, 0.0, 170.0),
    (180.0, 0.0, 180.0),        # +180 fica +180, não vira -180
    (-180.0, 0.0, 180.0),
    (30.0, 120.0, -90.0),
    (0.0, None, 0.0),
])
def test_normalizacao_do_angulo(bruto, referencia, esperado):
    assert fasor.em_relacao_a(bruto, referencia) == pytest.approx(esperado)


# ---------------------------------------------------------------------------
# A janela de UM CICLO DE TEMPO — taxa que não fecha em amostra inteira
# ---------------------------------------------------------------------------

def test_os_pesos_do_ciclo_somam_o_ciclo():
    for n in (4.0, 16.0, 20.0, 2000 / 60, 10_000 / 60, 1000 / 60):
        assert fasor.pesos_do_ciclo(n).sum() == pytest.approx(n, rel=1e-12)


def test_com_taxa_QUE_FECHA_os_pesos_sao_todos_UM():
    """Aí a janela É um número inteiro de amostras e a conta é o Fourier de
    ciclo cheio de sempre — o mesmo que o relé roda por dentro.

    Isto é deliberado e não é detalhe: todo número já conferido contra o SIGRA
    e contra os relés saiu de arquivo com taxa inteira (MiCOM a 20 amostras por
    ciclo, `.CEV` a 4 e a 8). Mudar os pesos ali invalidaria a conferência.
    """
    for n in (4, 8, 16.0, 20, 96):
        pesos = fasor.pesos_do_ciclo(n)
        assert pesos.size == int(n)
        assert np.all(pesos == 1.0)


def test_a_taxa_de_2000_Hz_NAO_fecha_e_a_janela_cresce():
    """2000 Hz num sistema de 60 Hz dá 33,3333 amostras por ciclo — a taxa de
    quase todo COMTRADE do parque (SEL-451, SEL-487E, SIPROTEC)."""
    n = fasor.ciclo_em_amostras(2000.0, 60.0)
    assert n == pytest.approx(33.3333333, rel=1e-6)
    assert fasor.amostras_por_ciclo(2000.0, 60.0) == 33      # o arredondado
    assert fasor.pesos_do_ciclo(n).size == 35                # a janela de medida


def test_a_janela_de_um_ciclo_de_tempo_MATA_o_vazamento():
    """**O teste que dá razão a tudo isto.**

    A média de um ciclo de uma senoide é zero. Com a janela arredondada para
    33 amostras ela não é: sobra 1,01 % do pico, girando a 60 Hz. Isso vira
    ondulação de 1,01 % no RMS e na fundamental — e o GRÁFICO INTEIRO na
    componente contínua, cujo valor verdadeiro é zero.
    """
    n = 2000.0 / 60.0
    arredondada = 33

    pior_novo = pior_velho = 0.0
    for graus in range(0, 360, 5):
        # Senoide de período `n` amostras, com a janela terminando no fim.
        k = np.arange(40)
        x = np.cos(2 * np.pi * (k - 39) / n + math.radians(graus))
        pesos = fasor.pesos_do_ciclo(n)
        pior_novo = max(pior_novo,
                        abs(np.dot(x[-pesos.size:], pesos) / n))
        pior_velho = max(pior_velho, abs(np.mean(x[-arredondada:])))

    assert pior_velho > 0.01                 # 1 % do pico, o que se via na tela
    assert pior_novo < 0.0001                # e some


def test_a_curva_e_o_cursor_batem_TAMBEM_com_taxa_fracionaria():
    """A curva sai de uma passada sobre o registro inteiro e o cursor de uma
    janela só. Com a janela fracionária são duas implementações da mesma
    ponderação — exatamente onde elas divergiriam em silêncio."""
    from osclab.dsp import envoltoria

    n = 2000.0 / 60.0
    t = np.arange(600) / 2000.0
    x = (100 * np.cos(2 * np.pi * 60 * t + 0.7) + 37.0
         + 8 * np.cos(2 * np.pi * 180 * t))

    curva_f = envoltoria.fundamental(x, n)
    curva_r = envoltoria.rms(x, n)
    curva_d = envoltoria.continua(x, n)
    for i in (200, 301, 457, 599):
        f = fasor.no_instante(x, i, n)
        assert f is not None
        assert f.fundamental == pytest.approx(curva_f[i], rel=1e-12)
        assert f.rms == pytest.approx(curva_r[i], rel=1e-12)
        assert f.dc == pytest.approx(curva_d[i], rel=1e-12)


def test_com_taxa_fracionaria_a_leitura_fica_CERTA():
    """Resposta conhecida: 100 de pico e 37 de contínua, a 33,3333 am/ciclo."""
    from osclab.dsp import envoltoria

    n = 2000.0 / 60.0
    t = np.arange(800) / 2000.0
    x = 100 * np.cos(2 * np.pi * 60 * t) + 37.0

    janela = slice(200, 700)
    assert np.nanmean(envoltoria.continua(x, n)[janela]) == pytest.approx(37.0, abs=1e-3)
    assert np.nanmean(envoltoria.fundamental(x, n)[janela]) == pytest.approx(
        100 / math.sqrt(2.0), rel=1e-4)
    # A MÉDIA da janela arredondada também dá 37 — a ondulação se cancela ao
    # longo do registro. O que ela erra é AMOSTRA A AMOSTRA, que é o que se vê
    # na tela: a contínua desenha uma senoide de 60 Hz em vez de uma reta.
    ondula = envoltoria.continua(x, 33)[janela]
    assert (np.nanmax(ondula) - np.nanmin(ondula)) / 2 > 0.9      # ~1 % de 100
    certa = envoltoria.continua(x, n)[janela]
    assert (np.nanmax(certa) - np.nanmin(certa)) / 2 < 0.01
