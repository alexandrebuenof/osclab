"""Bruto × filtrado: o veredito que trava o botão do filtro.

Estes testes existem porque o veredito tem **consequência**: dizer `filtrado`
tranca a tela, e trancar errado impede o usuário de filtrar um registro que
precisava ser filtrado. Por isso quase todo teste aqui está checando o lado
conservador — que na dúvida a resposta seja `desconhecido`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from osclab.analysis import filtragem
from osclab.formats.base import Filtering, FilteringSource, Record, SampleRate

POR_CICLO = 20
TAXA = 1200.0
N = 24 * POR_CICLO

t = np.arange(N) / POR_CICLO                      # em ciclos
onda = np.cos(2 * np.pi * t)
#: Amplitude que dá um degrau no meio — todo registro de falta tem um.
degrau = np.where(t < 8, 1.0, 18.0)

#: Os harmônicos que uma rede real de distribuição sempre tem. Não são
#: inventados: são os do registro que serviu de gabarito (0,4 % de 2ª, 2,1 % de
#: 3ª, 0,6 % de 5ª — 2,2 % de distorção no total).
sujeira = (0.004 * np.cos(2 * np.pi * 2 * t)
           + 0.021 * np.cos(2 * np.pi * 3 * t)
           + 0.006 * np.cos(2 * np.pi * 5 * t))


def registro(*canais: np.ndarray) -> Record:
    r = Record(source=Path("sintetico"), format_name="teste", line_frequency=60.0)
    r.analog = np.vstack(canais)
    r.time = np.arange(N) / TAXA
    r.sample_rates = (SampleRate(rate_hz=TAXA, last_sample=N),)
    return r


def veredito(*canais: np.ndarray) -> Filtering:
    return filtragem.diagnosticar(registro(*canais))[0]


# ---------------------------------------------------------------------------
# O que ele acerta
# ---------------------------------------------------------------------------

def test_harmonico_presente_prova_que_ninguem_filtrou():
    """A inferência forte: um filtro de 60 Hz teria removido os harmônicos.
    Se eles estão lá, o sinal não passou por filtro nenhum."""
    canal = degrau * (onda + sujeira)
    assert veredito(canal, canal, canal) == Filtering.BRUTO


def test_so_60hz_e_reconhecido_como_filtrado():
    canal = degrau * onda
    assert veredito(canal, canal, canal) == Filtering.FILTRADO


def test_o_ruido_de_quantizacao_nao_desmente_o_filtrado():
    """Um conversor de 16 bits deixa resíduo; ele não é harmônico."""
    acaso = np.random.default_rng(20260919)
    canais = [degrau * onda + 18 * 2**-15 * acaso.normal(size=N) for _ in range(3)]
    assert veredito(*canais) == Filtering.FILTRADO


def test_inrush_de_trafo_e_bruto():
    """Segundo harmônico forte: o caso em que o relé segura o disparo."""
    canal = degrau * (onda + 0.20 * np.cos(2 * np.pi * 2 * t))
    assert veredito(canal, canal, canal) == Filtering.BRUTO


# ---------------------------------------------------------------------------
# O que ele se recusa a afirmar — que é o mais importante
# ---------------------------------------------------------------------------

def test_injecao_de_mala_de_teste_nao_vira_filtrado():
    """Mala de teste sintetiza uma senoide quase pura: 0,2 % de distorção.

    Limpa demais para ser rede, suja demais para ser filtro. Chamar de
    `filtrado` trancaria o botão num registro bruto — o erro mais caro que
    este módulo pode cometer.
    """
    canal = degrau * (onda + 0.002 * np.cos(2 * np.pi * 3 * t))
    assert veredito(canal, canal, canal) == Filtering.DESCONHECIDO


def test_registro_curto_demais_nao_opina():
    """Sem alguns ciclos de amplitude parada, a medida seria um acidente."""
    curto = np.cos(2 * np.pi * np.arange(30) / POR_CICLO)
    r = registro(curto)
    r.time = np.arange(30) / TAXA
    assert filtragem.diagnosticar(r)[0] == Filtering.DESCONHECIDO


def test_registro_sem_canal_analogico_nao_opina():
    r = Record(source=Path("x"), format_name="teste", line_frequency=60.0)
    assert filtragem.diagnosticar(r)[0] == Filtering.DESCONHECIDO


def test_sem_frequencia_nominal_nao_opina():
    """Sem frequência não há ciclo, e sem ciclo não há janela que se meça."""
    r = registro(degrau * onda)
    r.line_frequency = 0.0
    assert filtragem.diagnosticar(r)[0] == Filtering.DESCONHECIDO


def test_um_canal_morto_nao_decide_pelo_registro():
    """Canal só com offset do conversor entra em qualquer oscilografia. Ele não
    pode arrastar o veredito — daí a mediana, e não a média."""
    vivo = degrau * (onda + sujeira)
    morto = np.full(N, 0.1536)
    assert veredito(vivo, morto, vivo) == Filtering.BRUTO


# ---------------------------------------------------------------------------
# Quem manda em quem
# ---------------------------------------------------------------------------

def test_o_que_o_arquivo_declara_nunca_e_sobreposto():
    """Dedução é o que se faz na falta de declaração, nunca por cima dela."""
    r = registro(degrau * (onda + sujeira))          # as amostras dizem "bruto"
    r.filtering = Filtering.FILTRADO
    r.filtering_source = FilteringSource.DECLARADO
    assert filtragem.diagnosticar(r) == (Filtering.FILTRADO, FilteringSource.DECLARADO)


def test_o_veredito_se_declara_como_deducao():
    """A tela precisa poder escrever "(deduzido)" — e ela escreve."""
    _, origem = filtragem.diagnosticar(registro(degrau * (onda + sujeira)))
    assert origem == FilteringSource.DEDUZIDO


def test_aplicar_grava_no_registro_e_devolve_ele():
    r = registro(degrau * (onda + sujeira))
    assert filtragem.aplicar(r) is r
    assert r.filtering == Filtering.BRUTO


def test_todo_formato_herda_o_diagnostico(tmp_path):
    """Está em `formats.registry.read`, não dentro de cada leitor: leitor novo
    ganha o diagnóstico sem saber que ele existe, e nenhum pode esquecê-lo."""
    from osclab.formats import registry
    from tests.fabrica import escrever_comtrade

    r = registry.read(escrever_comtrade(tmp_path, na=3, n=512, taxa=TAXA))
    assert r.filtering in tuple(Filtering)
    assert r.filtering_source == FilteringSource.DEDUZIDO


# ---------------------------------------------------------------------------
# O transitório, que foi o que derrubou a primeira ideia
# ---------------------------------------------------------------------------

def test_o_transitorio_sozinho_nao_pode_decidir_nada():
    """A medição que mudou o projeto deste módulo.

    Uma janela de um ciclo que pega uma MUDANÇA de amplitude não é senoide, por
    mais filtrado que o sinal esteja: num degrau de 60 Hz puro a distorção
    aparente chega a 189 %, igual à de uma falta bruta. Por isso o veredito só
    olha trechos de amplitude parada — e aqui se confere que olhar o
    transitório levaria à resposta errada.
    """
    puro = degrau * onda
    f = filtragem._distorcoes_em_regime(puro, POR_CICLO)
    assert f.size > 0
    assert np.median(f) < filtragem.RUIDO_DE_QUANTIZACAO      # em regime: zero

    # E no registro inteiro, sem o recorte de regime, o transitório domina:
    from osclab.dsp import envoltoria
    fu, rm = envoltoria.fundamental(puro, POR_CICLO), envoltoria.rms(puro, POR_CICLO)
    vale = np.isfinite(fu) & (fu > 0)
    tudo = 100 * np.sqrt(np.maximum(rm[vale]**2 - fu[vale]**2, 0)) / fu[vale]
    assert tudo.max() > 100.0
