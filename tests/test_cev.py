"""Testes do leitor CEV com arquivos sintéticos.

O CEV é onde a metade FILTRADA de uma oscilografia SEL vive, e ele tem três
armadilhas que não estão escritas em campo nenhum do arquivo — ver o cabeçalho
de `osclab/formats/cev.py`. Cada uma delas tem um teste com nome em maiúsculas
aqui: são as que passam despercebidas e estragam medição.

Os arquivos reais continuam sendo abertos por fora, em `test_comtrade_reais.py`.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.formats import registry
from osclab.formats.base import FormatError
from tests.fabrica import (
    DC1_CEV,
    RMS_CEV,
    escrever_cev,
    esperado_digital_cev,
)

RAIZ2 = math.sqrt(2.0)


def _por_nome(registro):
    return {c.name: registro.analog[c.index] for c in registro.analog_channels}


# ---------------------------------------------------------------------------
# O caso comum
# ---------------------------------------------------------------------------

def test_le_o_basico(tmp_path):
    r = registry.read(escrever_cev(tmp_path, por_ciclo=8, ciclos=4))

    assert r.format_name == "cev"
    assert r.station == "SE TESTE"
    assert r.device_id == "FID=SEL-000-TESTE"
    assert r.line_frequency == 60.0
    assert r.n_samples == 32
    assert r.base_rate_hz == 480.0
    assert r.samples_per_cycle == 8.0
    assert r.analog.shape == (len(r.analog_channels), 32)
    assert r.status.shape == (8, 32)


def test_o_nome_do_bay_vai_para_o_componente_do_canal(tmp_path):
    r = registry.read(escrever_cev(tmp_path))
    assert {c.component for c in r.analog_channels} == {"BAIA DE TESTE"}


def test_prim_val_yes_marca_os_canais_como_primario(tmp_path):
    r = registry.read(escrever_cev(tmp_path))
    assert all(c.is_primary for c in r.analog_channels)


# ---------------------------------------------------------------------------
# Armadilha 1: a amostra vem em EFICAZ
# ---------------------------------------------------------------------------

def test_a_amostra_EFICAZ_do_arquivo_vira_valor_INSTANTANEO(tmp_path):
    """O pico da coluna no arquivo é o eficaz; no `Record` tem que ser o pico.

    Sem esta multiplicação o registro filtrado aparece 41 % menor que o bruto
    do mesmo evento e o botão de RMS da tela devolve o valor dividido por
    raiz de 2 — tudo sem erro nenhum na tela.
    """
    r = registry.read(escrever_cev(tmp_path, por_ciclo=64, ciclos=4))
    canais = _por_nome(r)
    for nome in ("IA", "IB", "IC", "VA", "VB", "VC"):
        assert np.max(canais[nome]) == pytest.approx(RMS_CEV * RAIZ2, rel=1e-3)


def test_a_raiz_de_dois_NAO_vale_para_quem_nao_e_onda(tmp_path):
    """`FREQ(Hz)` está em hertz e `DC1` em volts contínuos: nenhum dos dois é
    uma senoide eficaz, e multiplicá-los seria inventar 41 % de erro."""
    r = registry.read(escrever_cev(tmp_path))
    canais = _por_nome(r)
    assert np.allclose(canais["FREQ"], 60.0)
    assert np.allclose(canais["DC1"], DC1_CEV)


def test_o_aviso_da_raiz_de_dois_aparece_na_tela(tmp_path):
    r = registry.read(escrever_cev(tmp_path))
    assert any("eficaz" in a for a in r.notes)


# ---------------------------------------------------------------------------
# Armadilha 2: a hora do cabeçalho é a do DISPARO
# ---------------------------------------------------------------------------

def test_a_hora_do_cabecalho_e_a_do_DISPARO_e_nao_a_da_PRIMEIRA_amostra(tmp_path):
    r = registry.read(escrever_cev(tmp_path, por_ciclo=8, ciclos=4, disparo=8))

    assert r.trigger_time is not None and r.start_time is not None
    assert r.trigger_time.strftime("%H:%M:%S.%f") == "10:20:30.500000"
    # 8 amostras a 480 Hz antes do disparo
    atraso = (r.trigger_time - r.start_time).total_seconds()
    assert atraso == pytest.approx(8 / 480.0, abs=1e-6)
    assert r.trigger_index == 8


def test_sem_a_marca_do_disparo_o_leitor_avisa_e_nao_chuta(tmp_path):
    r = registry.read(escrever_cev(tmp_path, disparo=None))
    assert r.start_time == r.trigger_time
    assert any("marca do disparo" in a for a in r.notes)


# ---------------------------------------------------------------------------
# Armadilha 3: as colunas ANAnn não são canais de onda
# ---------------------------------------------------------------------------

def test_a_coluna_ANA_ganha_o_nome_que_o_rele_deu_no_ERAQ(tmp_path):
    r = registry.read(escrever_cev(tmp_path))
    nomes = [c.name for c in r.analog_channels]
    assert "V1M" in nomes and "V1A" in nomes and "DC1" in nomes
    assert "ANA01" not in nomes


def test_a_coluna_ANA_sem_nome_e_sem_dado_fica_de_fora(tmp_path):
    """`ERAQ04` está em branco e `ANA04` não tem número nenhum: é vaga vazia do
    relatório, não canal mudo. Seis dessas enchem o buscador de sinais à toa."""
    r = registry.read(escrever_cev(tmp_path))
    assert "ANA04" not in [c.name for c in r.analog_channels]
    assert any("ficaram de fora" in a for a in r.notes)


def test_a_coluna_ANA_nao_declara_unidade(tmp_path):
    r = registry.read(escrever_cev(tmp_path))
    unidades = {c.name: c.unit for c in r.analog_channels}
    assert unidades["IA"] == "A"
    assert unidades["VA"] == "kV"
    assert unidades["FREQ"] == "Hz"
    assert unidades["V1M"] == ""


# ---------------------------------------------------------------------------
# Digitais
# ---------------------------------------------------------------------------

def test_o_bit_do_digital_segue_a_ORDEM_DOS_NOMES(tmp_path):
    """O padrão do sintético é uma diagonal: se a ordem dos bits estivesse
    espelhada, a diagonal apareceria ao contrário e este teste cairia."""
    r = registry.read(escrever_cev(tmp_path, por_ciclo=8, ciclos=4, nd=8))
    assert [c.name for c in r.status_channels] == [f"D0{j + 1}" for j in range(8)]
    np.testing.assert_array_equal(r.status, esperado_digital_cev(8, 32))


def test_digital_que_nao_enche_um_byte_inteiro(tmp_path):
    """Cinco digitais ocupam 5 bits de um byte de 8. Os 3 que sobram não podem
    virar canal nenhum."""
    r = registry.read(escrever_cev(tmp_path, nd=5))
    assert len(r.status_channels) == 5
    np.testing.assert_array_equal(r.status, esperado_digital_cev(5, 32))


# ---------------------------------------------------------------------------
# O que o arquivo real traz junto
# ---------------------------------------------------------------------------

def test_o_bloco_de_ajustes_no_fim_nao_entra_como_amostra(tmp_path):
    """Depois do marcador `SETTINGS` o arquivo deixa de ser CSV: é um campo só,
    com quebras de linha dentro. O leitor tem que parar ali."""
    com = registry.read(escrever_cev(tmp_path, nome="com", com_ajustes=True))
    sem = registry.read(escrever_cev(tmp_path, nome="sem", com_ajustes=False))
    assert com.n_samples == sem.n_samples == 32


def test_soma_de_verificacao_errada_avisa_mas_nao_recusa(tmp_path):
    r = registry.read(escrever_cev(tmp_path, soma_certa=False))
    assert r.n_samples == 32
    assert any("Soma de verificação" in a for a in r.notes)


def test_o_evento_que_o_rele_classificou_e_RELATO_e_nao_aviso(tmp_path):
    r = registry.read(escrever_cev(tmp_path))
    # Em `relatos`, não em `notes`: é informação do arquivo, não coisa que deu
    # errado. Carimbar triângulo nisso ensina a ignorar o triângulo.
    assert any('"AB T"' in a for a in r.relatos)
    assert not any("AB T" in a for a in r.notes)


def test_distancia_nao_calculada_nao_vira_numero(tmp_path):
    """O relé escreve `$$$$.$$` quando não localizou a falta. Isso é ausência
    de resposta, e não uma falta a zero quilômetro."""
    r = registry.read(escrever_cev(tmp_path))
    assert not any("LOCATION" in a for a in r.relatos)


# ---------------------------------------------------------------------------
# Variações e defeitos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("por_ciclo", [4, 8, 16])
def test_taxas_das_familias_que_usamos(tmp_path, por_ciclo):
    r = registry.read(escrever_cev(tmp_path, por_ciclo=por_ciclo))
    assert r.samples_per_cycle == float(por_ciclo)
    assert r.base_rate_hz == por_ciclo * 60.0


def test_50_hz(tmp_path):
    r = registry.read(escrever_cev(tmp_path, freq=50.0))
    assert r.line_frequency == 50.0
    assert r.base_rate_hz == 400.0


def test_fim_de_linha_do_unix(tmp_path):
    r = registry.read(escrever_cev(tmp_path, crlf=False))
    assert r.n_samples == 32


def test_sem_amostras_por_ciclo_a_mensagem_explica_o_que_falta(tmp_path):
    caminho = escrever_cev(tmp_path, sam_cyc=False)
    with pytest.raises(FormatError, match="SAM/CYC_A"):
        registry.read(caminho)


def test_arquivo_truncado_logo_depois_do_cabecalho(tmp_path):
    caminho = escrever_cev(tmp_path)
    # `read_text` traduz CRLF para LF sozinho; cortar por `splitlines` e gravar
    # em bytes e' o que garante que o arquivo REALMENTE ficou truncado.
    linhas = caminho.read_text(encoding="latin-1").splitlines()
    caminho.write_bytes(("\r\n".join(linhas[:6]) + "\r\n").encode("latin-1"))
    with pytest.raises(FormatError):
        registry.read(caminho)


def test_o_tempo_e_crescente_e_a_duracao_fecha(tmp_path):
    r = registry.read(escrever_cev(tmp_path, por_ciclo=8, ciclos=4))
    assert np.all(np.diff(r.time) > 0)
    assert r.duration == pytest.approx(31 / 480.0)


# ---------------------------------------------------------------------------
# O registry
# ---------------------------------------------------------------------------

def test_reconhece_mesmo_com_extensao_errada(tmp_path):
    """O leitor escolhe pelo conteúdo. Um CEV salvo como `.txt` abre igual."""
    r = registry.read(escrever_cev(tmp_path, extensao=".txt"))
    assert r.format_name == "cev"


def test_o_leitor_de_cev_nao_rouba_um_comtrade(tmp_path):
    from tests.fabrica import escrever_comtrade
    r = registry.read(escrever_comtrade(tmp_path))
    assert r.format_name.startswith("comtrade")


def test_o_leitor_esta_registrado():
    assert "cev" in {leitor.name for leitor in registry.readers()}
    assert ".cev" in {e for r in registry.readers() for e in r.extensions}


def test_um_CEV_de_4_ou_8_amostras_JA_ESTA_FILTRADO(tmp_path):
    """O relé grava o relatório filtrado a 4 ou 8 amostras por ciclo — não
    daria para gravar onda crua com tão pouco — e o bruto a 16 ou mais.

    Sem isto o botão do filtro ficava solto num registro já filtrado, e
    filtrar de novo acrescenta mais um ciclo de atraso em tudo que se lê. A
    dedução por harmônico não resolvia sozinha: ela foi calibrada para um
    COMTRADE binário de 16 bits, e o CEV imprime a corrente com três
    algarismos — essa precisão de impressão vira 0,46 % de distorção aparente
    e o veredito saía `desconhecido`.
    """
    from osclab.formats.base import Filtering, FilteringSource

    for por_ciclo in (4, 8):
        r = registry.read(escrever_cev(tmp_path, nome=f"f{por_ciclo}",
                                       por_ciclo=por_ciclo))
        assert r.filtering == Filtering.FILTRADO
        assert r.filtering_source == FilteringSource.DECLARADO


def test_um_CEV_de_taxa_ALTA_volta_a_ser_deduzido(tmp_path):
    """A SEL também sabe gravar o relatório BRUTO em CEV, e aí a taxa sobe.
    Declarar `filtrado` pela extensão seria afirmar do formato o que só a taxa
    diz."""
    from osclab.formats.base import FilteringSource

    r = registry.read(escrever_cev(tmp_path, por_ciclo=32, ciclos=4))
    assert r.filtering_source == FilteringSource.DEDUZIDO


# ---------------------------------------------------------------------------
# O segundo dialeto: CEV_VER 2.0.1 (SEL-787)
# ---------------------------------------------------------------------------

def test_le_o_dialeto_CEV_VER_do_SEL_787(tmp_path):
    """Um `.CEV` do parque não abria: o SEL-787 escreve outra primeira linha.

        SEL-451, sem versão:    "FID","RID","SID",<soma>
        SEL-787, CEV_VER 2.0.1: "FID","CEV_VER",<soma>

    A assinatura exigia a primeira forma, então o `sniff` recusava e nenhum
    leitor assumia o arquivo. **Quem achou foi o comissionamento** — um arquivo
    do acervo que o programa não lia, denunciado por um teste que roda sobre o
    acervo inteiro.

    O esqueleto dos dois é o mesmo; mudam os nomes de três campos.
    """
    r = registry.read(escrever_cev(tmp_path, dialeto="cev_ver"))
    assert r.format_name == "cev"
    assert len(r.analog_channels) == 10
    assert r.relatos == ('Relé classificou o evento como "ER Trigger"',)


def test_os_dois_dialetos_dao_o_MESMO_registro(tmp_path):
    """Só o cabeçalho muda: as amostras têm que sair idênticas.

    Se não saíssem, o dialeto novo estaria lendo as colunas de outro jeito — e
    um erro assim sai na unidade certa e na ordem de grandeza certa, sem nada
    na tela denunciando.
    """
    a = registry.read(escrever_cev(tmp_path / "a", dialeto="rid_sid"))
    b = registry.read(escrever_cev(tmp_path / "b", dialeto="cev_ver"))

    assert [c.name for c in a.analog_channels] == [c.name for c in b.analog_channels]
    assert [c.unit for c in a.analog_channels] == [c.unit for c in b.analog_channels]
    np.testing.assert_allclose(a.analog, b.analog, rtol=0, atol=0, equal_nan=True)
    np.testing.assert_array_equal(a.status, b.status)
    assert a.trigger_time == b.trigger_time
    assert a.sample_rates == b.sample_rates


def test_o_787_nao_tem_SID_e_a_estacao_fica_VAZIA(tmp_path):
    """E fica vazia mesmo: inventar um nome de subestação a partir do `FID`
    seria afirmar uma coisa que o arquivo não diz."""
    r = registry.read(escrever_cev(tmp_path, dialeto="cev_ver"))
    assert r.station == ""
    assert "SEL-787" in r.device_id


def test_um_arquivo_que_so_comeca_com_FID_nao_e_sequestrado(tmp_path):
    """A assinatura lista os DOIS dialetos na mão em vez de aceitar `"FID",.*`.

    Um `sniff` que assume demais tira arquivo dos outros leitores, e o erro
    aparece longe daqui — como formato lido errado, não como formato recusado.
    """
    from osclab.formats.cev import CevReader

    impostor = tmp_path / "impostor.cev"
    impostor.write_bytes(b'"FID","OUTRA_COISA","0000"\r\n1,2,"0000"\r\n')
    assert CevReader().sniff(impostor) is False
