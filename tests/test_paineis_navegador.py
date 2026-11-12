"""Os painéis NUM NAVEGADOR DE VERDADE (Chrome sem janela).

Sobe o servidor num acervo TEMPORÁRIO com os registros de
`tests/casos_calculadora.py` — o trafo (duas trincas de corrente, diferencial
sem ajustes) e o alimentador (uma trinca só: o alfa sem terminal remoto, o
localizador sem linha) — e roda `tests/navegador/paineis.mjs`, que confere:

* todo tipo de gráfico do «+ adicionar gráfico» tem a engrenagem;
* nenhum botão visível sai com a cara do botão do navegador, inclusive nos
  estados de «falta ajuste» e dentro das caixas das engrenagens;
* a caixa da engrenagem é larga e baixa e cabe na janela;
* o «falta o terminal remoto» do alfa é dito uma vez só;
* a roda no localizador: amplia proporcional ao deltaY dentro da moldura sem
  rolar a página, rola a página fora dela, e no piso não anda de lado.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do domínio.
As fotos ficam numa pasta temporária; `OSCLAB_FOTOS=<pasta>` as guarda.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tests import casos_calculadora as cc
from tests.test_calculadora_navegador import CHROMES, RAIZ, _porta_livre


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_engrenagem_botoes_estados_vazios_e_a_roda_do_localizador(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    monkeypatch.setattr(paths, "MODELOS_DA_CALCULADORA", tmp_path / "modelos.json")
    shas = []
    for fazer in (cc.trafo, cc.alimentador):
        pasta = tmp_path / fazer.__name__
        pasta.mkdir()
        cfg = fazer(pasta)
        dat = cfg.with_suffix(".dat")
        shas.append(
            acervo.guardar([(cfg.name, cfg.read_bytes()), (dat.name, dat.read_bytes())])
            .aceitos[0]
            .sha
        )

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            [
                "node",
                str(RAIZ / "tests" / "navegador" / "paineis.mjs"),
                f"http://127.0.0.1:{porta}",
                shas[0],
                shas[1],
                fotos,
                str(_porta_livre()),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=400,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
