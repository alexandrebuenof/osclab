"""O acervo de arquivos do usuário, endereçado por conteúdo.

Padrão herdado da PAC CT, e pela mesma razão prática: o arquivo entra por UM
lugar só e cada tela escolhe do acervo em vez de pedir upload de novo. Guardado
por sha256, dois envios do mesmo arquivo são uma leitura só.

Ver `acervo.py` para o funcionamento.
"""

from osclab.library.acervo import (
    Item,
    Resultado,
    agrupar,
    aguardando,
    caminho_principal,
    esquecer_aguardando,
    guardar,
    ler,
    listar,
    obter,
    remover,
)

__all__ = [
    "Item",
    "Resultado",
    "aguardando",
    "agrupar",
    "caminho_principal",
    "esquecer_aguardando",
    "guardar",
    "ler",
    "listar",
    "obter",
    "remover",
]
