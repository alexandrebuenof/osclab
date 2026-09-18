"""A comparação de versões decide se um pacote baixado substitui o que está
rodando. Um erro aqui é um programa que se auto-atualiza para trás."""

import pytest

from osclab import version


def test_le_a_versao_do_arquivo():
    assert version.parse(version.read()) is not None, (
        "o arquivo VERSION tem que conter um X.Y.Z limpo"
    )


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1.2.3", (1, 2, 3)),
        ("0.1.0", (0, 1, 0)),
        ("  2.0.0  ", (2, 0, 0)),
        ("10.20.30", (10, 20, 30)),
    ],
)
def test_parse_aceita_semver(texto, esperado):
    assert version.parse(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "1.2",             # incompleta
        "1.2.3.4",         # demais
        "v1.2.3",          # prefixo
        "1.2.3-rc1",       # pré-release
        "0.2.0.dev3+g1a2b", # instantâneo de desenvolvimento
        "",
        "abc",
    ],
)
def test_parse_recusa_o_que_nao_e_publicavel(texto):
    """Só X.Y.Z é versão publicável — o resto nunca é oferecido como atualização."""
    assert version.parse(texto) is None


@pytest.mark.parametrize(
    "candidata,atual",
    [
        ("1.2.4", "1.2.3"),
        ("1.3.0", "1.2.9"),
        ("2.0.0", "1.99.99"),
        ("0.2.0", "0.1.0"),
    ],
)
def test_reconhece_versao_mais_nova(candidata, atual):
    assert version.is_newer(candidata, atual)


@pytest.mark.parametrize(
    "candidata,atual",
    [
        ("1.2.3", "1.2.3"),   # igual não é mais nova
        ("1.2.2", "1.2.3"),   # mais velha
        ("1.9.0", "2.0.0"),
    ],
)
def test_nao_atualiza_para_tras(candidata, atual):
    assert not version.is_newer(candidata, atual)


@pytest.mark.parametrize(
    "candidata,atual",
    [
        ("1.2.3-rc1", "1.0.0"),
        ("0.2.0.dev3+g1a2b", "0.1.0"),
        ("1.2.3", "sei-la"),
        ("", "1.0.0"),
    ],
)
def test_na_duvida_nao_atualiza(candidata, atual):
    """Versão que não é X.Y.Z limpo nunca vale como atualização.

    Uma atualização que não deveria ter acontecido custa muito mais caro do que
    uma que deixou de acontecer.
    """
    assert not version.is_newer(candidata, atual)
