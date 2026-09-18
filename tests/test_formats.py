"""O contrato dos formatos. Ainda não há leitor nenhum — o que se testa aqui é
que o registry falha de um jeito que o usuário entende, e que o `Record` calcula
certo os derivados de que todo o resto depende."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from osclab.formats import registry
from osclab.formats.base import (
    AnalogChannel,
    Filtering,
    FormatError,
    Record,
    SampleRate,
)


def test_arquivo_inexistente_diz_isso(tmp_path):
    with pytest.raises(FormatError, match="nao encontrado"):
        registry.read(tmp_path / "nao-existe.cfg")


def test_formato_desconhecido_lista_o_que_da_para_ler(tmp_path):
    """A mensagem tem que dizer o que o programa SABE ler — senão o usuário
    fica sem saber se o problema e' o arquivo ou a ferramenta."""
    arquivo = tmp_path / "qualquer.cfg"
    arquivo.write_text("conteudo que nao e' comtrade", encoding="utf-8")
    with pytest.raises(FormatError, match="Nao reconheci"):
        registry.read(arquivo)


def test_registry_vazio_explica_em_vez_de_dar_erro_seco(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_LEITORES", [])
    arquivo = tmp_path / "qualquer.cfg"
    arquivo.write_text("conteudo", encoding="utf-8")
    with pytest.raises(FormatError, match="Nenhum leitor"):
        registry.read(arquivo)


def _registro_sintetico(taxa_hz=1920.0, freq=60.0, n=192):
    """Um registro de mentira, só para exercitar os derivados do Record."""
    t = np.arange(n) / taxa_hz
    ia = 100.0 * np.sin(2 * np.pi * freq * t)
    inicio = datetime(2026, 9, 17, 15, 54, 0)
    return Record(
        source=__file__,
        format_name="sintetico",
        line_frequency=freq,
        start_time=inicio,
        trigger_time=inicio + timedelta(seconds=t[n // 2]),
        analog_channels=(AnalogChannel(index=0, name="IA", unit="A", phase="A"),),
        sample_rates=(SampleRate(rate_hz=taxa_hz, last_sample=n - 1),),
        analog=ia.reshape(1, -1),
        time=t,
        filtering=Filtering.BRUTO,
    )


def test_amostras_por_ciclo():
    """O número que mais diz sobre um registro: 4 só serve para dado filtrado."""
    r = _registro_sintetico(taxa_hz=1920.0, freq=60.0)
    assert r.samples_per_cycle == pytest.approx(32.0)


def test_amostras_por_ciclo_em_50_hz():
    r = _registro_sintetico(taxa_hz=1000.0, freq=50.0)
    assert r.samples_per_cycle == pytest.approx(20.0)


def test_taxa_deduzida_quando_o_arquivo_nao_declara():
    r = _registro_sintetico()
    r.sample_rates = ()
    assert r.base_rate_hz == pytest.approx(1920.0)


def test_indice_do_disparo_cai_no_meio():
    r = _registro_sintetico(n=192)
    assert r.trigger_index == 96


def test_registro_vazio_nao_explode():
    """Um Record recém-criado tem que responder aos derivados sem estourar."""
    r = Record(source=__file__, format_name="vazio")
    assert r.n_samples == 0
    assert r.duration == 0.0
    assert r.samples_per_cycle == 0.0
    assert r.trigger_index is None


def test_busca_canal_por_nome_ignora_caixa():
    r = _registro_sintetico()
    assert r.analog_by_name("ia").shape == (192,)
    with pytest.raises(KeyError):
        r.analog_by_name("IB")
