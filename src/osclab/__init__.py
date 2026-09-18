"""OscLab — leitor e analisador de oscilografia.

O mapa das pastas está no README.md. Em uma linha: `formats/` lê arquivo,
`dsp/` processa sinal, `analysis/` interpreta a perturbação, `faultloc/`
localiza a falta, `report/` escreve o relatório e `web/` apenas mostra.
"""

from osclab.version import read as __version_read

__version__ = __version_read()

__all__ = ["__version__"]
