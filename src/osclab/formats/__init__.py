"""Leitura de oscilografia.

Um módulo por formato, todos devolvendo o mesmo `Record` (ver `base.py`).
`registry.py` é a única porta: chame `registry.read(caminho)`.

Quando um leitor novo nascer, ele é importado AQUI — é o import deste pacote
que o registra. Nada de descoberta automática por varredura de pasta: um import
explícito é o que o empacotador enxerga quando o programa virar um `.exe`.
"""

from osclab.formats import registry
from osclab.formats.base import (
    AnalogChannel,
    Filtering,
    FilteringSource,
    FormatError,
    Reader,
    Record,
    SampleRate,
    StatusChannel,
)

# --- leitores registrados ---------------------------------------------------
from osclab.formats.comtrade import ComtradeReader  # noqa: E402

registry.register(ComtradeReader())

__all__ = [
    "AnalogChannel",
    "ComtradeReader",
    "Filtering",
    "FilteringSource",
    "FormatError",
    "Reader",
    "Record",
    "SampleRate",
    "StatusChannel",
    "registry",
]
