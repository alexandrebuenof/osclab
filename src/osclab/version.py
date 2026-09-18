"""A versão do OscLab e a comparação entre versões.

A comparação existe por causa da atualização automática, que ainda não foi
implementada (ver o marco 0.1 no CLAUDE.md). Ela já está aqui, com teste, porque
é a peça que decide se um pacote baixado substitui o que está rodando — e essa
decisão não é lugar para ser escrita com pressa no dia da primeira release.

Regra que o resto do programa depende: **só `X.Y.Z` é uma versão publicável.**
Um `0.2.0.dev3+g1a2b3c` é um instantâneo de desenvolvimento e nunca é oferecido
como atualização, porque o commit que ele nomeia pode nunca virar release.
"""

from __future__ import annotations

import re

from osclab.paths import VERSION_FILE

#: `X.Y.Z` e nada mais. O `fullmatch` é o que recusa sufixos de desenvolvimento.
_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")

DESCONHECIDA = "0.0.0+desconhecida"


def read() -> str:
    """A versão que está no arquivo `VERSION`, como texto."""
    if not VERSION_FILE.is_file():
        return DESCONHECIDA
    return VERSION_FILE.read_text(encoding="utf-8").strip() or DESCONHECIDA


def parse(versao: str) -> tuple[int, int, int] | None:
    """`"1.2.3"` vira `(1, 2, 3)`. Qualquer outra coisa vira `None`.

    `None` significa "isto não é uma versão publicável" — e quem chama trata
    isso como recusa, nunca como zero.
    """
    m = _SEMVER.fullmatch(versao.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_newer(candidata: str, atual: str) -> bool:
    """`candidata` é mais nova que `atual`?

    Falso sempre que qualquer uma das duas não for um `X.Y.Z` limpo. Isso é
    deliberado: na dúvida, não atualiza. Uma atualização que não deveria ter
    acontecido custa muito mais caro do que uma que deixou de acontecer.
    """
    nova = parse(candidata)
    velha = parse(atual)
    if nova is None or velha is None:
        return False
    return nova > velha
