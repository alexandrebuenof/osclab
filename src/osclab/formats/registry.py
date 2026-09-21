"""Quem abre este arquivo?

O registry é a única porta: o resto do programa chama `read(caminho)` e recebe um
`Record`, sem nunca saber qual formato estava na frente. Acrescentar um formato é
escrever o leitor e registrá-lo — nenhuma outra linha do projeto muda.

A escolha do leitor olha o CONTEÚDO (`sniff`), não a extensão. Extensão é
palpite: `.dat` é COMTRADE binário, COMTRADE ASCII e mais uma dúzia de coisas.
A extensão serve só para decidir a ORDEM das tentativas, o que economiza leituras
no caso comum sem nunca decidir sozinha.
"""

from __future__ import annotations

from pathlib import Path

from osclab.formats.base import FormatError, Reader, Record

_LEITORES: list[Reader] = []


def register(leitor: Reader) -> Reader:
    """Registra um leitor. Serve como decorador de classe."""
    _LEITORES.append(leitor)
    return leitor


def readers() -> tuple[Reader, ...]:
    """Os leitores registrados, na ordem em que entraram."""
    return tuple(_LEITORES)


def reader_for(path: Path) -> Reader:
    """O leitor que sabe abrir este arquivo.

    Tenta primeiro os que declaram a extensão do arquivo; depois todos os outros.
    """
    caminho = Path(path)
    if not caminho.is_file():
        raise FormatError(f"arquivo nao encontrado: {caminho}")

    ext = caminho.suffix.lower()
    provaveis = [r for r in _LEITORES if ext in r.extensions]
    resto = [r for r in _LEITORES if r not in provaveis]

    for leitor in (*provaveis, *resto):
        try:
            if leitor.sniff(caminho):
                return leitor
        except OSError:
            # Um leitor que não consegue nem ler o arquivo não é motivo para
            # derrubar a tentativa dos outros.
            continue

    if not _LEITORES:
        raise FormatError(
            "Nenhum leitor de formato foi registrado ainda.\n"
            "Esta e' a versao 0.1 do OscLab, que ainda nao le oscilografia — "
            "o leitor COMTRADE entra no marco 0.2."
        )
    conhecidos = ", ".join(sorted({e for r in _LEITORES for e in r.extensions}))
    raise FormatError(
        f"Nao reconheci o formato de {caminho.name}.\n"
        f"Formatos que este OscLab le hoje: {conhecidos}"
    )


def read(path: Path) -> Record:
    """Abre o arquivo com o leitor certo e devolve o registro.

    O diagnóstico de bruto × filtrado é aplicado AQUI, e não dentro de cada
    leitor: ele se deduz das amostras, não do formato. Todo leitor novo o herda
    sem precisar saber que ele existe — e nenhum leitor pode esquecer dele.
    """
    # Import adiado: `analysis` conversa com `formats`, e importá-lo no topo
    # fecharia um ciclo.
    from osclab.analysis import filtragem

    return filtragem.aplicar(reader_for(path).read(Path(path)))
