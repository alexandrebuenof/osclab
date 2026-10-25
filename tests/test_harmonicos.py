"""O painel de harmônicos: quem entra, até que ordem, e se as barras fecham.

O que se testa aqui é o que é NOVO. O Fourier em si já é o de `dsp/fasor.py`,
que tem os testes dele contra o SIGRA e contra os relés — e o primeiro teste
deste arquivo é justamente o que amarra uma coisa na outra: a primeira raia do
espectro TEM que ser, dígito a dígito, a fundamental daquela mesma janela.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.dsp import fasor
from osclab.plot import harmonicos, janela, leitura, paineis
from tests import arranjo
from tests.test_catalogo import PICO, trifasico


def _onda(amplitudes: dict[int, float], por_ciclo: float = 2000.0 / 60.0,
          n: int = 400, fases_: dict[int, float] | None = None) -> np.ndarray:
    """Uma onda com as amplitudes EFICAZES pedidas por ordem de harmônico."""
    t = np.arange(n) / (por_ciclo * 60.0)
    y = np.zeros(n)
    for ordem, eficaz in amplitudes.items():
        giro = (fases_ or {}).get(ordem, 0.0)
        y += eficaz * math.sqrt(2.0) * np.sin(2 * np.pi * 60.0 * ordem * t + giro)
    return y


def _janela_no_fim(y: np.ndarray, por_ciclo: float):
    pesos = fasor.pesos_do_ciclo(por_ciclo)
    return y[y.size - pesos.size:], pesos


# --- o Fourier -------------------------------------------------------------

def test_a_primeira_raia_do_espectro_E_a_fundamental_da_mesma_janela():
    """Duas contas do mesmo número é como o desenho e a tabela discordariam."""
    por_ciclo = 2000.0 / 60.0
    y = _onda({1: 100.0, 2: 40.0, 3: 15.0}, por_ciclo,
              fases_={2: 0.7, 3: -1.2})
    corte, pesos = _janela_no_fim(y, por_ciclo)
    raias = fasor.espectro(corte, por_ciclo, pesos)
    f = fasor.de_janela(corte, por_ciclo, pesos)
    assert raias[0] == pytest.approx(f.fundamental, rel=1e-9)


def test_o_espectro_devolve_o_eficaz_de_cada_ordem():
    por_ciclo = 2000.0 / 60.0
    y = _onda({1: 100.0, 2: 40.0, 3: 15.0}, por_ciclo,
              fases_={2: 0.7, 3: -1.2})
    corte, pesos = _janela_no_fim(y, por_ciclo)
    raias = fasor.espectro(corte, por_ciclo, pesos)
    assert raias[0] == pytest.approx(100.0, rel=2e-3)
    assert raias[1] == pytest.approx(40.0, rel=2e-3)
    assert raias[2] == pytest.approx(15.0, rel=2e-3)
    # As raias que não existem ficam no PISO DA MEDIDA, que nesta taxa
    # fracionária é de meio por cento — ver `fasor.espectro`.
    assert max(raias[3:]) < 0.6


def test_o_THD_das_barras_fecha_com_a_raiz_da_soma_dos_quadrados():
    por_ciclo = 2000.0 / 60.0
    y = _onda({1: 100.0, 2: 40.0, 3: 15.0}, por_ciclo)
    corte, pesos = _janela_no_fim(y, por_ciclo)
    raias = fasor.espectro(corte, por_ciclo, pesos)
    esperado = 100.0 * math.sqrt(40.0**2 + 15.0**2) / 100.0
    assert fasor.distorcao_do_espectro(raias) == pytest.approx(esperado, rel=3e-3)


@pytest.mark.parametrize("por_ciclo,piso", [
    (20.0, 1e-9),             # taxa INTEIRA: o espectro é exato
    (32.0, 1e-9),
    (2000.0 / 60.0, 0.6),     # fracionária: meio por cento de vazamento
])
def test_senoide_pura_nao_tem_harmonico(por_ciclo, piso):
    """E o piso de quem não tem é a medida do método, não um número solto.

    Com taxa inteira a janela fecha e o espectro é exato. Com a fracionária do
    SEL a 2000 Hz sobra 0,55 % — medido, e é de onde sai o `RUIDO_DA_BARRA` da
    tela. Ver `fasor.espectro`.
    """
    corte, pesos = _janela_no_fim(_onda({1: 100.0}, por_ciclo, n=400), por_ciclo)
    raias = fasor.espectro(corte, por_ciclo, pesos)
    assert fasor.distorcao_do_espectro(raias) == pytest.approx(0.0, abs=piso)


@pytest.mark.parametrize("por_ciclo,teto", [
    (2000.0 / 60.0, 16),      # SEL a 2000 Hz: 33,3 amostras/ciclo
    (20.0, 10),               # MiCOM a 1200 Hz
    (4.0, 2),                 # um `.CEV` de quatro amostras por ciclo
    (166.667, 83),            # 10 kHz
])
def test_o_teto_de_ordens_e_o_Nyquist_da_janela(por_ciclo, teto):
    assert fasor.ordens_mediveis(por_ciclo) == teto


def test_o_espectro_nunca_passa_do_teto_mesmo_se_pedirem():
    """Além do Nyquist não há zero — há aliasing, que é pior: uma barra
    plausível na ordem errada."""
    por_ciclo = 20.0
    corte, pesos = _janela_no_fim(_onda({1: 100.0}, por_ciclo, n=200), por_ciclo)
    raias = fasor.espectro(corte, por_ciclo, pesos, ate=40)
    assert raias.size == 10


def test_sem_janela_inteira_nao_ha_espectro():
    """Meia janela daria um espectro plausível e errado — a pior espécie."""
    assert fasor.espectro(np.ones(2), 20.0) is None
    assert fasor.espectro(np.array([1.0, np.nan, 2.0, 3.0, 4.0]), 5.0) is None


# --- o painel --------------------------------------------------------------

def _pacote(registro, sinais, lado="arquivo"):
    pacote = janela.montar(registro, colunas=200, lado=lado,
                           layout=[arranjo.harmonicos(sinais)])
    return pacote["paineis"][0]


def test_entra_canal_e_residuo_mas_NAO_componente_de_sequencia():
    """Fortescue é definido sobre fasores de UMA frequência: não existe "5º
    harmônico do I1" a partir do número que o painel tem."""
    r = trifasico()
    painel = _pacote(r, ["c0:instantaneo", "q0:n:instantaneo", "q0:0:rms",
                         "q0:1:rms", "v0:rms", "inexistente"])
    assert [s["id"] for s in painel["sinais"]] == ["c0:instantaneo",
                                                   "q0:n:instantaneo"]


def test_o_tipo_harmonicos_sobrevive_a_ida_e_volta_pela_tela():
    lido = paineis.de_json([{"id": "h1", "tipo": "harmonicos", "nome": "H",
                             "sinais": ["c0:instantaneo"]}])
    assert lido[0].tipo == paineis.HARMONICOS
    assert lido[0].sinais == ("c0:instantaneo",)


def test_o_painel_anuncia_o_teto_do_registro():
    r = trifasico()
    painel = _pacote(r, ["c0:instantaneo"])
    esperado = fasor.ordens_mediveis(
        min(t.taxa_hz for t in r.trechos) / r.line_frequency)
    assert painel["teto"] == esperado


def test_o_painel_avisa_quando_o_registro_ja_veio_filtrado():
    r = trifasico()
    painel = _pacote(r, ["c0:instantaneo"])
    assert painel["ja_filtrado"] == (str(r.filtering) == "filtrado")


# --- a leitura do cursor ---------------------------------------------------

def _leitura(registro, layout, t=None):
    if t is None:
        t = float(registro.time[-1])
    return leitura.em(registro, [(t, 0, 0.0), (None, 0, 0.0)], layout=layout)


def test_a_leitura_traz_as_raias_so_para_quem_esta_num_painel_de_harmonicos():
    """Vinte e cinco DFTs por canal a cada movimento do cursor, para jogar
    fora, é o que esta peneira evita."""
    r = trifasico()
    lido = _leitura(r, [arranjo.analogico(["c0:instantaneo"]),
                        arranjo.harmonicos(["c1:instantaneo"],
                                           identidade="ph")])
    sinais = lido["cursores"][0]["sinais"]
    assert sinais["c1:instantaneo"]["harmonicos"]
    assert "harmonicos" not in sinais["c0:instantaneo"]


def test_a_primeira_raia_da_leitura_bate_com_a_fundamental_da_leitura():
    r = trifasico()
    lido = _leitura(r, [arranjo.harmonicos(["c0:instantaneo"])])
    linha = lido["cursores"][0]["sinais"]["c0:instantaneo"]
    assert linha["harmonicos"][0] == pytest.approx(linha["fundamental"],
                                                   rel=1e-6)


def test_o_residuo_tambem_tem_espectro():
    r = trifasico()
    lido = _leitura(r, [arranjo.harmonicos(["q0:n:instantaneo"])])
    linha = lido["cursores"][0]["sinais"]["q0:n:instantaneo"]
    assert linha["harmonicos"] is not None
    assert linha["teto"] >= 1


def test_as_raias_acompanham_a_conversao_de_primario_e_secundario():
    """O espectro é multiplicado por escalar como o fasor — e tem que mudar
    junto com ele, senão a barra e a tabela falam de lados diferentes."""
    r = trifasico()
    layout = [arranjo.harmonicos(["c0:instantaneo"])]
    um = _leitura(r, layout, t=float(r.time[-1]))
    outro = leitura.em(r, [(float(r.time[-1]), 0, 0.0), (None, 0, 0.0)],
                       lado="primario", layout=layout)
    a = um["cursores"][0]["sinais"]["c0:instantaneo"]
    b = outro["cursores"][0]["sinais"]["c0:instantaneo"]
    razao_fasor = b["fundamental"] / a["fundamental"]
    razao_raia = b["harmonicos"][0] / a["harmonicos"][0]
    assert razao_raia == pytest.approx(razao_fasor, rel=1e-9)


# --- o Fourier do TRECHO entre os cursores ---------------------------------

def test_a_janela_de_N_ciclos_mede_as_mesmas_raias_de_um_ciclo():
    """Mais ciclos dão mais resolução, não outro resultado — e, de quebra,
    matam o vazamento da taxa fracionária."""
    pc = 2000.0 / 60.0
    for ciclos, piso in ((1, 0.6), (7, 0.1), (12, 1e-6)):
        n_janela = ciclos * pc
        pesos = fasor.pesos_do_ciclo(n_janela)
        y = _onda({1: 100.0, 2: 40.0}, pc, n=pesos.size)
        raias = fasor.espectro(y, n_janela, pesos, ciclos=ciclos)
        assert raias[0] == pytest.approx(100.0, rel=2e-3)
        assert raias[1] == pytest.approx(40.0, rel=2e-3)
        assert max(raias[2:]) < piso


def test_o_teto_de_ordens_nao_cresce_com_a_janela():
    """Janela longa dá RESOLUÇÃO, não Nyquist: quem limita é a taxa."""
    pc = 20.0
    for ciclos in (1, 5, 12):
        n_janela = ciclos * pc
        pesos = fasor.pesos_do_ciclo(n_janela)
        y = _onda({1: 100.0}, pc, n=pesos.size)
        assert fasor.espectro(y, n_janela, pesos, ciclos=ciclos).size == 10


def test_o_trecho_e_cortado_em_ciclos_INTEIROS():
    """Num pedaço quebrado a fundamental escorre para as vizinhas: medido,
    uma senoide pura aparece com 4,7 % de THD em 7,3 ciclos."""
    r = trifasico()
    layout = [arranjo.harmonicos(["c0:instantaneo"])]
    pc = r.trechos[0].taxa_hz / r.line_frequency
    # Um trecho de ~5,4 ciclos: tem que medir 5.
    t0 = float(r.time[0])
    t1 = float(r.time[min(int(round(5.4 * pc)), r.n_samples - 1)])
    lido = leitura.em(r, [(t0, 0, 0.0), (t1, 0, 0.0)], layout=layout)
    entre = lido["espectro_entre"]
    assert entre["ciclos"] == 5
    assert entre["ciclos_pedidos"] == pytest.approx(5.4, abs=0.1)
    assert entre["sinais"]["c0:instantaneo"]["harmonicos"]


def test_menos_de_um_ciclo_entre_os_cursores_nao_tem_espectro():
    r = trifasico()
    layout = [arranjo.harmonicos(["c0:instantaneo"])]
    lido = leitura.em(r, [(float(r.time[0]), 0, 0.0),
                          (float(r.time[3]), 0, 0.0)], layout=layout)
    entre = lido["espectro_entre"]
    assert entre["sinais"] == {}
    assert "menos de um ciclo" in entre["erro"]


def test_sem_painel_de_harmonicos_nao_se_calcula_espectro_de_trecho():
    r = trifasico()
    lido = leitura.em(r, [(float(r.time[0]), 0, 0.0),
                          (float(r.time[-1]), 0, 0.0)],
                      layout=[arranjo.analogico(["c0:instantaneo"])])
    assert lido["espectro_entre"] is None


# --- a janela fora de regime -----------------------------------------------

def test_a_janela_fora_de_regime_apaga_depois_da_transicao():
    """O aviso tem que APAGAR. A primeira versão comparava as duas metades da
    mesma janela e, num inrush (corrente unipolar), ficava aceso do começo ao
    fim do registro — ver `fasor.regime_da_janela`.
    """
    import numpy as np
    from osclab.dsp import fasor

    por_ciclo = 32
    t = np.arange(por_ciclo * 40) / (60.0 * por_ciclo)
    pesos = fasor.pesos_do_ciclo(por_ciclo)
    L = pesos.size

    def em(x, ciclo):
        i = int(por_ciclo * ciclo)
        return fasor.regime_da_janela(x[i - L:i], x[i - L - por_ciclo:i - por_ciclo])

    # Inrush com constante de tempo LONGA: é o caso que a versão antiga nunca
    # deixava apagar.
    env = np.where(t < 4 / 60.0, 0.0, np.exp(-(t - 4 / 60.0) / 0.5))
    inrush = np.where(t < 4 / 60.0, 0.0,
                      env + (1 + 0.5 * env) * np.sin(2 * np.pi * 60.0 * t)
                      + 0.35 * env * np.sin(2 * np.pi * 120.0 * t))
    assert em(inrush, 5) > fasor.LIMIAR_DE_REGIME        # a janela toca o evento
    for ciclo in (6, 10, 20, 30):
        assert em(inrush, ciclo) < fasor.LIMIAR_DE_REGIME, ciclo

    # E o aviso não confunde distorção verdadeira com transição.
    sujo = (np.sin(2 * np.pi * 60.0 * t) + 0.4 * np.sin(2 * np.pi * 180.0 * t)
            + 0.2 * np.sin(2 * np.pi * 300.0 * t))
    for ciclo in (5, 10, 30):
        assert em(sujo, ciclo) < 0.05, ciclo


def test_sem_ciclo_anterior_nao_ha_aviso():
    """No primeiro ciclo do arquivo não há com o que comparar. Avisar por falta
    de dado seria pior que calar."""
    import numpy as np
    from osclab.dsp import fasor
    assert fasor.regime_da_janela(np.ones(32), None) == 0.0
    assert fasor.regime_da_janela(np.zeros(32), np.zeros(32)) == 0.0
    assert fasor.regime_da_janela(np.ones(2), np.ones(2)) == 0.0
