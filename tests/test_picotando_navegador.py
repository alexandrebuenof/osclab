"""O digital que PICOTA, NUM NAVEGADOR DE VERDADE (Chrome sem janela).

Sobe o servidor num acervo TEMPORÁRIO com um registro sintético de um trip e
um digital que liga e desliga a cada amostra depois da falta, até o fim, e
roda `tests/navegador/picotando.mjs`: o picotando fica fora do gráfico
padrão, aparece no bloco «picotando» do «+ sinal» com a contagem ao lado, e
um clique o põe no gráfico.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do domínio.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest

from tests import casos_calculadora as cc
from tests.test_calculadora_navegador import CHROMES, RAIZ, _porta_livre


def _registro(pasta: Path) -> Path:
    n = 700
    t = np.arange(n) / cc.TAXA
    canais = [
        ("Current IA", "", "A", cc.onda(t, [(0, cc.polar(2.0, 0)), (0.1, cc.polar(20.0, -70))]),
         600, 5),
        ("Current IB", "", "A", cc.onda(t, [(0, cc.polar(2.0, -120))]), 600, 5),
        ("Current IC", "", "A", cc.onda(t, [(0, cc.polar(2.0, 120))]), 600, 5),
    ]
    trip = ((t >= 0.14) & (t < 0.2)).astype(int)
    picota = np.where(t >= 0.1, np.arange(n) % 2, 0)
    return cc.escrever(pasta, "PICOTANDO", "SE TESTE", "LT01", canais,
                       [("TRIP", trip), ("ENX", picota)], n)


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_o_picotando_fica_no_bloco_proprio_do_mais_sinal(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    pasta = tmp_path / "registro"
    pasta.mkdir()
    cfg = _registro(pasta)
    dat = cfg.with_suffix(".dat")
    sha = acervo.guardar([(cfg.name, cfg.read_bytes()),
                          (dat.name, dat.read_bytes())]).aceitos[0].sha

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            ["node", str(RAIZ / "tests" / "navegador" / "picotando.mjs"),
             f"http://127.0.0.1:{porta}", sha, fotos, str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
