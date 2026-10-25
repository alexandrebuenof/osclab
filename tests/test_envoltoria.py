"""A curva de fundamental e a de RMS, contra o cálculo ponto a ponto.

O teste que importa aqui não é contra uma resposta decorada: é contra
`fasor.no_instante`, que já foi conferido contra o SIGRA num registro real. A
envoltória é uma reescrita rápida da MESMA conta, e uma reescrita rápida só vale
se der exatamente o mesmo número.

É por isso que estes testes comparam amostra a amostra, e não só o máximo ou a
média: um erro de meio ciclo no deslocamento da janela passaria despercebido
numa comparação de máximos e apareceria imediatamente aqui.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.dsp import envoltoria, fasor
from osclab.formats.base import Trecho


def senoide(amplitude: float, graus: float = 0.0, por_ciclo: int = 20,
            ciclos: int = 6, dc: float = 0.0) -> np.ndarray:
    n = por_ciclo * ciclos
    t = np.arange(n) / por_ciclo
    return amplitude * np.cos(2 * np.pi * t + math.radians(graus)) + dc


def ponto_a_ponto(sinal: np.ndarray, por_ciclo: int, campo: str) -> np.ndarray:
    """A mesma curva, pelo caminho lento — a referência deste arquivo."""
    saida = np.full(sinal.size, np.nan)
    for i in range(sinal.size):
        f = fasor.no_instante(sinal, i, por_ciclo)
        if f is not None:
            saida[i] = getattr(f, campo)
    return saida


# ---------------------------------------------------------------------------
# A reescrita rápida dá o mesmo que a conta lenta
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("por_ciclo", [16, 20, 32, 96])
def test_a_fundamental_bate_com_o_calculo_ponto_a_ponto(por_ciclo):
    sinal = senoide(100.0, 30.0, por_ciclo=por_ciclo, ciclos=5, dc=25.0)
    rapido = envoltoria.fundamental(sinal, por_ciclo)
    lento = ponto_a_ponto(sinal, por_ciclo, "fundamental")
    np.testing.assert_allclose(rapido, lento, rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize("por_ciclo", [16, 20, 32])
def test_o_rms_bate_com_o_calculo_ponto_a_ponto(por_ciclo):
    sinal = senoide(100.0, -75.0, por_ciclo=por_ciclo, ciclos=5, dc=-12.0)
    np.testing.assert_allclose(envoltoria.rms(sinal, por_ciclo),
                               ponto_a_ponto(sinal, por_ciclo, "rms"),
                               rtol=1e-9, atol=1e-9)


def test_bate_tambem_num_degrau_de_falta():
    """O caso que separa uma janela deslocada de uma correta.

    Em senoide estacionária uma janela meio ciclo fora de lugar daria o mesmo
    número. Num degrau, não: a subida de um ciclo inteiro tem que cair
    exatamente nas mesmas amostras.
    """
    sinal = np.concatenate([senoide(10.0, ciclos=3), senoide(100.0, ciclos=3)])
    np.testing.assert_allclose(envoltoria.fundamental(sinal, 20),
                               ponto_a_ponto(sinal, 20, "fundamental"),
                               rtol=1e-9, atol=1e-9)


def test_vetorizado_da_o_mesmo_que_canal_a_canal():
    """A tela desenha oito canais de uma vez; não pode haver laço em Python."""
    canais = np.vstack([senoide(100.0, g, ciclos=4) for g in (0.0, -120.0, 120.0)])
    junto = envoltoria.fundamental(canais, 20)
    assert junto.shape == canais.shape
    for k in range(canais.shape[0]):
        np.testing.assert_allclose(junto[k], envoltoria.fundamental(canais[k], 20),
                                   rtol=1e-12, atol=1e-12)


# ---------------------------------------------------------------------------
# O que a curva diz e o que ela não diz
# ---------------------------------------------------------------------------

def test_o_primeiro_ciclo_nao_tem_curva():
    """Sem janela antes não há medida. NaN, nunca zero: zero é afirmação."""
    curva = envoltoria.fundamental(senoide(100.0), 20)
    assert np.all(np.isnan(curva[:19]))
    assert np.isfinite(curva[19])


def test_a_curva_leva_um_ciclo_inteiro_para_subir():
    """É assim no relé e é assim no SIGRA — e é por isso que esta curva não
    serve para achar o INSTANTE da falta, só o valor."""
    sinal = np.concatenate([senoide(10.0, ciclos=3), senoide(100.0, ciclos=3)])
    curva = envoltoria.fundamental(sinal, 20)
    antes = curva[59]                      # última amostra antes do degrau
    assert antes == pytest.approx(10.0 / math.sqrt(2), rel=1e-6)
    # Meio ciclo depois a janela tem metade de cada nível: nem um, nem outro.
    assert antes < curva[69] < curva[79]
    assert curva[79] == pytest.approx(100.0 / math.sqrt(2), rel=1e-6)


def test_o_rms_fica_acima_da_fundamental_quando_ha_dc():
    """A diferença entre as duas curvas é a assimetria da falta, à vista."""
    sinal = senoide(100.0, dc=40.0)
    f = envoltoria.fundamental(sinal, 20)
    r = envoltoria.rms(sinal, 20)
    assert np.all(r[19:] > f[19:])
    assert r[-1] == pytest.approx(math.sqrt(50.0**2 * 2 + 40.0**2), rel=1e-9)


def test_senoide_pura_tem_as_duas_curvas_iguais():
    sinal = senoide(100.0)
    np.testing.assert_allclose(envoltoria.fundamental(sinal, 20)[19:],
                               envoltoria.rms(sinal, 20)[19:], rtol=1e-9)


def test_o_rms_nunca_fica_abaixo_da_fundamental():
    """Não é observação, é lei — e por isso vira teste.

    A DFT decompõe a janela em componentes ORTOGONAIS, e Parseval diz que a
    energia total é a soma das energias de todas elas:

        RMS² = DC² + fundamental² + 2ª² + 3ª² + ...

    A fundamental é uma parcela dessa soma, e as outras são quadrados. Logo o
    RMS nunca fica abaixo dela, com igualdade só em senoide pura. Se alguma
    mudança futura quebrar esta desigualdade, a conta saiu do lugar — mesmo
    que os números continuem parecendo plausíveis.
    """
    acaso = np.random.default_rng(20260919)
    t = np.arange(400) / 20.0
    casos = {
        "senoide pura": senoide(100.0),
        "com DC": senoide(100.0, dc=55.0),
        "so' DC (canal morto)": np.full(400, 0.1536),
        "harmonico dominante": 5 * np.cos(2 * np.pi * t) + 90 * np.cos(2 * np.pi * 2 * t),
        "degrau de falta": np.concatenate([senoide(1.5, ciclos=3),
                                           senoide(25.0, ciclos=3)]),
        "ruido": acaso.normal(size=400),
        "zerado": np.zeros(400),
    }
    for nome, sinal in casos.items():
        f = envoltoria.fundamental(sinal, 20)
        r = envoltoria.rms(sinal, 20)
        vale = np.isfinite(f) & np.isfinite(r)
        # A folga de 1e-9 é do ponto flutuante, não do conceito.
        assert np.all(r[vale] + 1e-9 >= f[vale]), nome


# ---------------------------------------------------------------------------
# Bordas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("por_ciclo,n", [(2, 100), (20, 10), (0, 100)])
def test_sem_ciclo_que_caiba_devolve_tudo_nan(por_ciclo, n):
    curva = envoltoria.fundamental(np.ones(n), por_ciclo)
    assert curva.shape == (n,)
    assert np.all(np.isnan(curva))


def test_precisao_nao_se_perde_num_registro_longo():
    """Os expoentes usam `m % n`: sem isso, o argumento do seno chega a
    milhões de radianos e a fundamental erra no fim do registro."""
    sinal = senoide(100.0, por_ciclo=20, ciclos=25_000)     # 500 mil amostras
    curva = envoltoria.fundamental(sinal, 20)
    esperado = 100.0 / math.sqrt(2)
    assert curva[-1] == pytest.approx(esperado, rel=1e-10)
    assert curva[len(curva) // 2] == pytest.approx(esperado, rel=1e-10)


def um_trecho(n, taxa_hz=1200.0):
    return [Trecho(0, n, taxa_hz)]


def test_calcular_escolhe_a_curva_e_deixa_o_instantaneo_passar():
    sinal = senoide(100.0)
    t = um_trecho(sinal.size)
    np.testing.assert_allclose(envoltoria.calcular(sinal, t, 60.0, "instantaneo"),
                               sinal)
    np.testing.assert_allclose(envoltoria.calcular(sinal, t, 60.0, "rms"),
                               envoltoria.rms(sinal, 20))


# ---------------------------------------------------------------------------
# Taxa que muda no meio do registro
# ---------------------------------------------------------------------------

def test_cada_trecho_usa_a_propria_janela_de_um_ciclo():
    """O relé grava a falta a 96 amostras/ciclo e o resto a 16. Calcular tudo
    com a taxa do primeiro trecho daria uma curva confiante e errada na metade
    do registro — e nada na tela denunciaria."""
    a = senoide(100.0, por_ciclo=16, ciclos=8)        # 128 amostras a 960 Hz
    b = senoide(100.0, por_ciclo=96, ciclos=8)        # 768 amostras a 5760 Hz
    sinal = np.concatenate([a, b])
    trechos = [Trecho(0, a.size, 960.0), Trecho(a.size, sinal.size, 5760.0)]

    curva = envoltoria.calcular(sinal, trechos, 60.0, "fundamental")
    esperado = 100.0 / math.sqrt(2)
    # Cada trecho, depois do seu primeiro ciclo, acerta o mesmo valor.
    assert curva[a.size - 1] == pytest.approx(esperado, rel=1e-9)
    assert curva[-1] == pytest.approx(esperado, rel=1e-9)

    # E a conta de cada trecho é a mesma que a de um registro só com ele.
    np.testing.assert_allclose(curva[:a.size], envoltoria.fundamental(a, 16),
                               rtol=1e-9, atol=1e-9)


def test_nenhuma_janela_atravessa_a_fronteira_de_taxa():
    """Metade das amostras de um lado e metade do outro não é um ciclo de coisa
    nenhuma. O primeiro ciclo de CADA trecho fica sem curva, pela mesma razão
    que o primeiro ciclo do registro."""
    a = senoide(100.0, por_ciclo=16, ciclos=8)
    b = senoide(100.0, por_ciclo=96, ciclos=8)
    sinal = np.concatenate([a, b])
    trechos = [Trecho(0, a.size, 960.0), Trecho(a.size, sinal.size, 5760.0)]

    curva = envoltoria.calcular(sinal, trechos, 60.0, "rms")
    # 96 amostras por ciclo no segundo trecho: 95 sem curva, e a 96ª já tem.
    assert np.all(np.isnan(curva[a.size:a.size + 95]))
    assert np.isfinite(curva[a.size + 95])


def test_taxa_variavel_tambem_na_onda_filtrada():
    a = senoide(50.0, por_ciclo=20, ciclos=6)
    b = senoide(50.0, por_ciclo=40, ciclos=6)
    sinal = np.concatenate([a, b])
    trechos = [Trecho(0, a.size, 1200.0), Trecho(a.size, sinal.size, 2400.0)]
    curva = envoltoria.calcular(sinal, trechos, 60.0, "filtrado")
    np.testing.assert_allclose(curva[a.size + 39:], envoltoria.filtrada(b, 40)[39:],
                               rtol=1e-9, atol=1e-9)


# ---------------------------------------------------------------------------
# A componente contínua
# ---------------------------------------------------------------------------

def test_a_contINUA_de_uma_senoide_pura_e_zero():
    """Média de um ciclo inteiro de cosseno é zero, por definição. Se este
    teste falhar, a janela não está fechando um ciclo — e aí NENHUMA envoltória
    deste arquivo vale, porque todas usam a mesma janela."""
    curva = envoltoria.continua(senoide(100.0, por_ciclo=20, ciclos=6), 20)
    assert np.all(np.isnan(curva[:19]))
    np.testing.assert_allclose(curva[19:], 0.0, atol=1e-12)


def test_a_continua_devolve_o_deslocamento_que_foi_posto():
    """Resposta conhecida: senoide com 37 de offset tem contínua 37."""
    for offset in (37.0, -12.5, 0.0):
        curva = envoltoria.continua(
            senoide(100.0, por_ciclo=16, ciclos=6, dc=offset), 16)
        np.testing.assert_allclose(curva[15:], offset, atol=1e-12)


def test_a_continua_sai_COM_SINAL():
    """O SIGRA mostra a DC em módulo; nós mostramos com sinal, e isso está
    conferido contra ele nos oito canais de um registro real (ver `CLAUDE.md`).
    Tirar o sinal aqui esconderia de que lado a onda está deslocada — que é
    metade do que a assimetria conta."""
    curva = envoltoria.continua(senoide(10.0, por_ciclo=16, ciclos=4, dc=-5.0), 16)
    assert curva[20] < 0


def test_rms_ao_quadrado_e_fundamental_mais_continua_ao_quadrado():
    """As três curvas saem de contas independentes, e Parseval as amarra: sem
    harmônico, `rms² = fundamental² + dc²`.

    É o teste que pega as três de uma vez. Se alguém trocar um `/n` por um
    `/(n-1)`, ou esquecer um √2 na fundamental, a identidade abre — e nenhuma
    das três, olhada sozinha, denunciaria.
    """
    x = senoide(100.0, por_ciclo=32, ciclos=6, dc=40.0)
    ef = envoltoria.rms(x, 32)[40]
    fu = envoltoria.fundamental(x, 32)[40]
    dc = envoltoria.continua(x, 32)[40]
    assert ef**2 == pytest.approx(fu**2 + dc**2, rel=1e-12)


def test_a_continua_bate_com_a_do_cursor():
    """Curva e cursor são duas implementações da mesma identidade — a curva por
    soma móvel sobre o registro inteiro, o cursor por uma janela só. É assim
    que elas divergem, em silêncio, meses depois."""
    x = senoide(80.0, graus=33.0, por_ciclo=24, ciclos=6, dc=-17.0)
    np.testing.assert_allclose(envoltoria.continua(x, 24)[23:],
                               ponto_a_ponto(x, 24, "dc")[23:],
                               rtol=1e-9, atol=1e-9)


def test_a_continua_segue_os_trechos_de_taxa():
    """Mesma regra de todas: nenhuma janela atravessa a fronteira entre dois
    trechos, porque meia janela de cada lado não é um ciclo de coisa nenhuma."""
    a = senoide(50.0, por_ciclo=20, ciclos=6, dc=9.0)
    b = senoide(50.0, por_ciclo=40, ciclos=6, dc=9.0)
    sinal = np.concatenate([a, b])
    trechos = [Trecho(0, a.size, 1200.0), Trecho(a.size, sinal.size, 2400.0)]
    curva = envoltoria.calcular(sinal, trechos, 60.0, "dc")
    assert np.all(np.isnan(curva[a.size:a.size + 39]))
    np.testing.assert_allclose(curva[a.size + 39:], 9.0, atol=1e-9)


# --- NaN não contamina o resto -------------------------------------------

def test_nan_na_frente_nao_envenena_o_registro_inteiro():
    """`np.cumsum` faz um NaN contaminar tudo que vem depois dele.

    Não aparecia enquanto a envoltória só via canal do arquivo, que é finito
    de ponta a ponta. Apareceu quando a calculadora passou a alcançar as
    colunas derivadas: `[VAY] - [VAY · 60Hz]` tem o primeiro ciclo NaN por
    construção, e a envoltória DELA saía NaN no registro inteiro — quatro das
    cinco colunas do sinal, vazias.
    """
    import numpy as np
    from osclab.dsp import envoltoria

    por_ciclo = 32
    t = np.arange(por_ciclo * 40) / (60.0 * por_ciclo)
    onda = np.sqrt(2) * np.cos(2 * np.pi * 60.0 * t)

    limpo = envoltoria.media_do_ciclo(onda, por_ciclo)
    sujo = onda.copy()
    sujo[:por_ciclo] = np.nan
    saida = envoltoria.media_do_ciclo(sujo, por_ciclo)

    # Os dois ciclos da frente são desconhecidos — e só eles.
    assert np.isnan(saida[:2 * por_ciclo - 1]).all()
    assert np.isfinite(saida[2 * por_ciclo:]).all()
    # E o que sobrou vale o mesmo que sem o buraco.
    assert np.allclose(saida[2 * por_ciclo:], limpo[2 * por_ciclo:])


def test_buraco_no_meio_so_apaga_as_janelas_que_o_contem():
    """Depois de passar o buraco, a conta volta ao normal."""
    import numpy as np
    from osclab.dsp import envoltoria

    por_ciclo = 32
    t = np.arange(por_ciclo * 40) / (60.0 * por_ciclo)
    onda = np.sqrt(2) * np.cos(2 * np.pi * 60.0 * t)
    limpo = envoltoria.media_do_ciclo(onda, por_ciclo)

    sujo = onda.copy()
    sujo[500:503] = np.nan
    saida = envoltoria.media_do_ciclo(sujo, por_ciclo)

    # A última janela tocada pelo buraco termina em 502 + (largura - 1).
    fim = 502 + por_ciclo
    assert np.isnan(saida[500:fim]).all()
    assert np.allclose(saida[fim + 1:], limpo[fim + 1:])


def test_sinal_sem_furo_nao_muda_de_resultado():
    """A guarda não pode cobrar nada de quem não tem NaN — que é o caso de
    todo canal do arquivo."""
    import numpy as np
    from osclab.dsp import envoltoria

    por_ciclo = 20
    t = np.arange(por_ciclo * 30) / (60.0 * por_ciclo)
    onda = (np.sqrt(2) * np.cos(2 * np.pi * 60.0 * t)
            + 0.3 * np.cos(2 * np.pi * 180.0 * t) + 0.1)
    saida = envoltoria.media_do_ciclo(onda, por_ciclo)
    assert np.isfinite(saida[por_ciclo - 1:]).all()
    # A média de um ciclo de uma senoide com 0,1 de contínua é 0,1.
    assert saida[-1] == pytest.approx(0.1, abs=1e-9)
