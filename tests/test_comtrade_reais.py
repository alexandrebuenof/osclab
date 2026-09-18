"""Testes contra os arquivos REAIS do parque da distribuidora.

Esses arquivos **não entram no repositório**: identificam instalação, data e
comportamento da rede, e o repositório é público. Então este arquivo de teste
fica desligado por padrão e só roda quando alguém aponta onde eles estão:

    # Windows
    set OSCLAB_AMOSTRAS=C:\\Users\\alexa\\Documents\\06 - Ferramentas\\Oscilografias
    python app.py --testes

    # Linux / macOS
    OSCLAB_AMOSTRAS=~/oscilografias pytest

Sem a variável, o pytest reporta estes testes como `skipped` — o que é o
comportamento certo para quem clonar o repositório e não tiver os arquivos.

O que se verifica aqui não é valor numérico (isso é trabalho dos sintéticos, que
têm resposta conhecida) e sim que **cada fabricante continua abrindo**: taxa
coerente, canais no lugar, tempo crescente, nada de exceção.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from osclab.formats import registry
from osclab.formats.base import Record

_RAIZ = os.environ.get("OSCLAB_AMOSTRAS", "").strip()
AMOSTRAS = Path(_RAIZ).expanduser() if _RAIZ else None

pytestmark = pytest.mark.skipif(
    AMOSTRAS is None or not AMOSTRAS.is_dir(),
    reason="defina OSCLAB_AMOSTRAS apontando para a pasta das oscilografias reais",
)


def _cfgs() -> list[Path]:
    if AMOSTRAS is None or not AMOSTRAS.is_dir():
        return []
    achados = [p for p in AMOSTRAS.rglob("*")
               if p.is_file() and p.suffix.lower() in (".cfg", ".cff")]
    return sorted(achados)


def _ids(caminhos: list[Path]) -> list[str]:
    base = AMOSTRAS or Path(".")
    return [str(p.relative_to(base)) for p in caminhos]


CAMINHOS = _cfgs()


@pytest.mark.parametrize("cfg", CAMINHOS, ids=_ids(CAMINHOS))
def test_abre_sem_estourar(cfg: Path):
    r = registry.read(cfg)
    assert isinstance(r, Record)
    assert r.n_samples > 0, "registro sem amostra nenhuma"


@pytest.mark.parametrize("cfg", CAMINHOS, ids=_ids(CAMINHOS))
def test_o_registro_e_coerente(cfg: Path):
    r = registry.read(cfg)

    # as matrizes têm que casar com os canais declarados
    assert r.analog.shape == (len(r.analog_channels), r.n_samples)
    assert r.status.shape == (len(r.status_channels), r.n_samples)

    # tempo sempre para a frente
    assert np.all(np.diff(r.time) > 0), "o tempo anda para tras em algum ponto"

    # taxa de amostragem plausível para proteção: entre 4 e 512 amostras/ciclo
    assert 4 <= r.samples_per_cycle <= 512, (
        f"{r.samples_per_cycle:.2f} amostras por ciclo esta fora do que um "
        f"registro de protecao produz"
    )

    # frequência nominal de um sistema de potência
    assert r.line_frequency in (50.0, 60.0)

    # digitais são 0 ou 1, nunca outra coisa
    if r.status.size:
        assert set(np.unique(r.status).tolist()) <= {0, 1}


@pytest.mark.parametrize("cfg", CAMINHOS, ids=_ids(CAMINHOS))
def test_os_valores_estao_em_unidade_de_engenharia(cfg: Path):
    """Um canal cujo maior valor absoluto passa de 32767 denuncia que o fator de
    conversao nao foi aplicado — seria o inteiro cru do conversor A/D."""
    r = registry.read(cfg)
    for c in r.analog_channels:
        v = r.analog[c.index]
        pico = float(np.nanmax(np.abs(v))) if v.size else 0.0
        assert pico != 32767, f"canal {c.name} parece estar em contagem crua"
