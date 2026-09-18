"""Testes do leitor COMTRADE com arquivos sintéticos.

Cada caso aqui corresponde a algo que apareceu num arquivo real do parque da
distribuidora — ver o cabeçalho de `fabrica.py`. Quando um leitor quebrar, o
nome do teste diz qual fabricante volta a dar problema.
"""

from __future__ import annotations

import numpy as np
import pytest

from osclab.formats import registry
from osclab.formats.base import FormatError
from tests.fabrica import (
    ESCALA,
    PICO,
    escrever_comtrade,
    esperado_analog,
    esperado_digital,
)

# ---------------------------------------------------------------------------
# O caso comum
# ---------------------------------------------------------------------------

def test_le_o_basico(tmp_path):
    cfg = escrever_comtrade(tmp_path, na=3, nd=4, n=128, taxa=960.0)
    r = registry.read(cfg)

    assert r.format_name == "comtrade-1999"
    assert r.station == "SE TESTE"
    assert r.device_id == "IED-TESTE"
    assert r.line_frequency == 60.0
    assert len(r.analog_channels) == 3
    assert len(r.status_channels) == 4
    assert r.n_samples == 128
    assert r.analog.shape == (3, 128)
    assert r.status.shape == (4, 128)


def test_os_metadados_dos_canais_chegam_inteiros(tmp_path):
    r = registry.read(escrever_comtrade(tmp_path, na=3))
    nomes = [c.name for c in r.analog_channels]
    fases = [c.phase for c in r.analog_channels]
    assert nomes == ["CH1", "CH2", "CH3"]
    assert fases == ["A", "B", "C"]
    assert all(c.unit == "A" for c in r.analog_channels)
    assert all(not c.is_primary for c in r.analog_channels)


def test_marca_canal_em_primario(tmp_path):
    r = registry.read(escrever_comtrade(tmp_path, escala_primaria=True))
    assert all(c.is_primary for c in r.analog_channels)


# ---------------------------------------------------------------------------
# A conversão para unidade de engenharia — o erro mais caro do formato
# ---------------------------------------------------------------------------

def test_aplica_o_fator_de_conversao(tmp_path):
    """Sem aplicar `a` e `b`, o gráfico sai com a forma certa e a amplitude
    errada — e ninguém percebe olhando."""
    cfg = escrever_comtrade(tmp_path, na=3, n=128, taxa=960.0)
    r = registry.read(cfg)
    esperado = esperado_analog(3, 128, 960.0, 60.0)
    np.testing.assert_allclose(r.analog, esperado, atol=ESCALA)


def test_a_amplitude_e_a_de_engenharia_nao_a_do_conversor(tmp_path):
    r = registry.read(escrever_comtrade(tmp_path, na=1, n=960, taxa=960.0))
    pico_lido = float(np.max(np.abs(r.analog[0])))
    assert pico_lido == pytest.approx(PICO, rel=0.01)


def test_desempacota_os_digitais_bit_a_bit(tmp_path):
    cfg = escrever_comtrade(tmp_path, nd=20, n=64)     # 20 canais = 2 palavras
    r = registry.read(cfg)
    np.testing.assert_array_equal(r.status, esperado_digital(20, 64))


# ---------------------------------------------------------------------------
# Tempo e taxa de amostragem
# ---------------------------------------------------------------------------

def test_taxa_e_amostras_por_ciclo(tmp_path):
    r = registry.read(escrever_comtrade(tmp_path, taxa=1920.0, freq=60.0, n=64))
    assert r.base_rate_hz == pytest.approx(1920.0)
    assert r.samples_per_cycle == pytest.approx(32.0)


def test_50_hz(tmp_path):
    r = registry.read(escrever_comtrade(tmp_path, taxa=1000.0, freq=50.0, n=64))
    assert r.line_frequency == 50.0
    assert r.samples_per_cycle == pytest.approx(20.0)


def test_sem_taxa_declarada_o_tempo_vem_do_carimbo(tmp_path):
    """`nrates = 0` é o que um GE 850 gera."""
    cfg = escrever_comtrade(tmp_path, nrates=0, taxa=960.0, n=128)
    r = registry.read(cfg)
    assert r.base_rate_hz == pytest.approx(960.0, rel=1e-3)
    assert r.samples_per_cycle == pytest.approx(16.0, rel=1e-3)
    assert any("carimbo" in n for n in r.notes)


def test_indice_do_disparo(tmp_path):
    # início 03:04:05.000000, disparo 03:04:05.050000 -> 50 ms a 960 Hz = 48
    r = registry.read(escrever_comtrade(tmp_path, taxa=960.0, n=128))
    assert r.trigger_index == 48


def test_duracao(tmp_path):
    r = registry.read(escrever_comtrade(tmp_path, taxa=1000.0, n=1001))
    assert r.duration == pytest.approx(1.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Os quatro tipos de dado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tipo", ["ASCII", "BINARY", "BINARY32", "FLOAT32"])
def test_todos_os_tipos_de_dado(tmp_path, tipo):
    cfg = escrever_comtrade(tmp_path, tipo=tipo, na=3, nd=4, n=96, taxa=960.0)
    r = registry.read(cfg)
    assert r.analog.shape == (3, 96)
    np.testing.assert_allclose(
        r.analog, esperado_analog(3, 96, 960.0, 60.0), atol=ESCALA * 2
    )
    np.testing.assert_array_equal(r.status, esperado_digital(4, 96))


# ---------------------------------------------------------------------------
# Esquisitices dos fabricantes
# ---------------------------------------------------------------------------

def test_edicao_que_nao_existe_e_lida_assim_mesmo(tmp_path):
    """Um MiCOM da Schneider escreve `2001` no campo da edição.

    Recusar o arquivo por isso seria transformar uma esquisitice do fabricante
    num arquivo ilegível.
    """
    r = registry.read(escrever_comtrade(tmp_path, revisao="2001"))
    assert r.format_name == "comtrade-2001"
    assert r.n_samples > 0
    assert any("2001" in n for n in r.notes)


def test_sem_a_linha_de_timemult(tmp_path):
    """A Schneider simplesmente não escreve a última linha."""
    r = registry.read(escrever_comtrade(tmp_path, timemult=False, n=64))
    assert r.n_samples == 64


def test_fim_de_linha_do_unix(tmp_path):
    """O GE grava o `.cfg` com LF, não CRLF."""
    r = registry.read(escrever_comtrade(tmp_path, crlf=False))
    assert r.station == "SE TESTE"


def test_acento_em_cp1252(tmp_path):
    """Nome de subestação com acento não vem em UTF-8."""
    cfg = escrever_comtrade(tmp_path, estacao="SE CUIABÁ", codec="cp1252")
    r = registry.read(cfg)
    assert r.station == "SE CUIABÁ"


def test_lixo_no_fim_do_dat_nao_atrapalha(tmp_path):
    """O `.dat` de um SEL-TWFL termina com 64 bytes 0x1A, do fim-de-arquivo do
    DOS. Não é erro — é enchimento de bloco."""
    cfg = escrever_comtrade(tmp_path, n=64, lixo_no_fim=64)
    r = registry.read(cfg)
    assert r.n_samples == 64


def test_campos_extras_da_edicao_2013(tmp_path):
    r = registry.read(escrever_comtrade(tmp_path, revisao="2013"))
    assert r.format_name == "comtrade-2013"
    assert r.time_quality == "0,-4"


def test_dat_em_maiusculas(tmp_path):
    """No Windows tanto faz; no Linux, `.DAT` e `.dat` são arquivos diferentes —
    e a distribuidora exporta dos dois jeitos."""
    cfg = escrever_comtrade(tmp_path, nome="maiusculo", n=32)
    (cfg.parent / "maiusculo.dat").rename(cfg.parent / "maiusculo.DAT")
    r = registry.read(cfg)
    assert r.n_samples == 32


# ---------------------------------------------------------------------------
# Quando dá errado, a mensagem tem que servir para alguém
# ---------------------------------------------------------------------------

def test_sem_o_dat_a_mensagem_explica_o_que_falta(tmp_path):
    cfg = escrever_comtrade(tmp_path, nome="sozinho")
    (cfg.parent / "sozinho.dat").unlink()
    with pytest.raises(FormatError, match="dois arquivos"):
        registry.read(cfg)


def test_dat_de_outro_registro_e_detectado(tmp_path):
    """O sintoma real de um `.cfg` e um `.dat` que não são do mesmo evento."""
    cfg = escrever_comtrade(tmp_path, nome="trocado", na=3, nd=4, n=64)
    (cfg.parent / "trocado.dat").write_bytes(b"\x00" * 100)
    with pytest.raises(FormatError, match="nao bate"):
        registry.read(cfg)


def test_tipo_de_dado_desconhecido(tmp_path):
    cfg = escrever_comtrade(tmp_path, nome="estranho")
    texto = cfg.read_text(encoding="utf-8").replace("BINARY", "XPTO")
    cfg.write_text(texto, encoding="utf-8")
    with pytest.raises(FormatError, match="XPTO"):
        registry.read(cfg)


def test_cfg_truncado(tmp_path):
    cfg = escrever_comtrade(tmp_path, nome="cortado", na=3, nd=4)
    linhas = cfg.read_text(encoding="utf-8").splitlines()
    cfg.write_text("\n".join(linhas[:4]), encoding="utf-8")
    with pytest.raises(FormatError, match="acaba antes"):
        registry.read(cfg)


def test_arquivo_que_nao_e_comtrade(tmp_path):
    outro = tmp_path / "qualquer.cfg"
    outro.write_text("isto aqui nao e' um comtrade\nnem de longe\n", encoding="utf-8")
    with pytest.raises(FormatError, match="Nao reconheci"):
        registry.read(outro)


# ---------------------------------------------------------------------------
# O registry escolhe pelo conteúdo, não pela extensão
# ---------------------------------------------------------------------------

def test_reconhece_mesmo_com_extensao_errada(tmp_path):
    cfg = escrever_comtrade(tmp_path, nome="disfarcado", n=32)
    novo = cfg.parent / "disfarcado.txt"
    cfg.rename(novo)
    # o .dat continua se chamando disfarcado.dat, que e' o que o leitor procura
    r = registry.read(novo)
    assert r.n_samples == 32


def test_o_leitor_esta_registrado():
    assert "comtrade" in [r.name for r in registry.readers()]
