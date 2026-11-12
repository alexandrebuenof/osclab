"""A navegação NUM NAVEGADOR DE VERDADE, com o servidor LENTO (12/11/2026:
«estou sentindo meio travado nas oscilografias maiores»).

Sobe o servidor num acervo TEMPORÁRIO com um sintético de 210 digitais que
mudam (o painel de tiras fica muitas vezes mais alto que a janela, como num
SEL-411L) e roda `tests/navegador/navegacao.mjs`, que atrasa as respostas e
confere: dois arrastos com o primeiro pedido em voo andam os dois; seis
toques de seta com a leitura lenta andam seis amostras; o pacote seguinte
não repete a lista de todos os digitais; a última tira é pintada ao rolar
até ela; vinte recargas não acumulam ouvintes.

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

from tests.fabrica import escrever_comtrade
from tests.test_calculadora_navegador import CHROMES, RAIZ, _porta_livre


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_a_navegacao_com_o_servidor_lento(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    cfg = escrever_comtrade(tmp_path / "origem", nome="MUITOS_DIGITAIS", na=6, nd=210,
                            n=6000, taxa=2000.0, degraus=True)
    r = acervo.guardar([(p.name, p.read_bytes()) for p in (cfg, cfg.with_suffix(".dat"))])
    assert len(r.aceitos) == 1, r.problemas
    sha = r.aceitos[0].sha

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            ["node", str(RAIZ / "tests" / "navegador" / "navegacao.mjs"),
             f"http://127.0.0.1:{porta}", sha, fotos, str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
