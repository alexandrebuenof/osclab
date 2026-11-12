"""A janela «? métodos» do painel localizador NUM NAVEGADOR DE VERDADE
(variante 06, 12/11/2026: as equações desenhadas, lado a lado).

Sobe o servidor num acervo TEMPORÁRIO com os dois terminais de uma falta AG
do mini-EMTP (`tests/rede_de_falta.py`), abre a aba com as duas
oscilografias, põe o painel localizador com a linha DIGITADA e roda
`tests/navegador/metodos.mjs`, que confere:

* a lista à esquerda tem os quatro métodos, cada um com o km dele, e o
  «resultado e trecho» no fim;
* o método do resultado abre escolhido; clicar noutro troca o da direita;
* as equações são desenhadas (fração com traço) e «neste registro» é a conta
  com o mesmo km da lista;
* passar o mouse num símbolo acende o mesmo símbolo e mostra o que ele é;
* a janela fecha no clique fora e no Esc.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do domínio.
As fotos ficam numa pasta temporária; `OSCLAB_FOTOS=<pasta>` as guarda.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tests import rede_de_falta as rede
from tests.test_calculadora_navegador import CHROMES, RAIZ, _porta_livre
from tests.test_refino import _comtrade

KM = 100.0


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_a_janela_dos_metodos_lado_a_lado(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    cen = rede.Cenario(linha=rede.LT_100, m=0.615, tipo="AG", rf=4.0, delta=12.0)
    sim = rede.simular(cen, abre_s=0.062, abre_r=0.068)
    gravar = lambda lado, seed: rede.gravar(  # noqa: E731
        sim, lado, rede.Formato(tipo="comtrade", escala="S", taxa=2000.0, seed=seed),
        nome=f"SE {lado}")
    origem = tmp_path / "origem"
    origem.mkdir()
    r = acervo.guardar(_comtrade(origem, "LADO_A", gravar("S", 1))
                       + _comtrade(origem, "LADO_B", gravar("R", 2)))
    assert len(r.aceitos) == 2, r.problemas
    sha_a, sha_b = (x.sha for x in sorted(r.aceitos, key=lambda x: x.nome))
    z1, z0 = rede.LT_100.Z1, rede.LT_100.Z0
    manual = {"km": KM, "forma": "rx", "r": z1.real, "x": z1.imag, "r0": z0.real, "x0": z0.imag}

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            ["node", str(RAIZ / "tests" / "navegador" / "metodos.mjs"),
             f"http://127.0.0.1:{porta}", sha_a, sha_b, json.dumps(manual), fotos,
             str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
