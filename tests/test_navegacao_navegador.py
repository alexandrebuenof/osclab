"""A navegação NUM NAVEGADOR DE VERDADE, com o servidor LENTO (12/11/2026:
«estou sentindo meio travado nas oscilografias maiores»).

Sobe o servidor num acervo TEMPORÁRIO com um sintético de 210 digitais que
mudam (o painel de tiras fica muitas vezes mais alto que a janela, como num
SEL-411L) e roda dois roteiros, que atrasam as respostas de propósito:

* `tests/navegador/navegacao.mjs` — dois arrastos com o primeiro pedido em
  voo andam os dois; seis toques de seta com a leitura lenta andam seis
  amostras; o pacote seguinte não repete a lista de todos os digitais; a
  última tira é pintada ao rolar até ela; vinte recargas não acumulam
  ouvintes;
* `tests/navegador/combinacoes.mjs` — as COMBINAÇÕES de gestos (roda e
  arrasto um com o outro em voo, roda no meio do arrasto, faixa logo depois
  da roda, botão direito no meio da fila, setas entre eles), com as
  respostas fora de ordem: a janela final é a composição dos gestos, gesto
  a gesto, e nunca volta a uma já deixada.

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

sem_navegador = pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)


def _rodar(roteiro: str, tmp_path, monkeypatch) -> None:
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
            ["node", str(RAIZ / "tests" / "navegador" / roteiro),
             f"http://127.0.0.1:{porta}", sha, fotos, str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]


@sem_navegador
def test_a_navegacao_com_o_servidor_lento(tmp_path, monkeypatch):
    _rodar("navegacao.mjs", tmp_path, monkeypatch)


@sem_navegador
def test_as_combinacoes_de_gestos_com_o_servidor_lento(tmp_path, monkeypatch):
    _rodar("combinacoes.mjs", tmp_path, monkeypatch)
