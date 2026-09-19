"""Descobrir a fase de um canal quando o arquivo não declara.

O COMTRADE tem um campo `ph` para isso, mas nem todo fabricante preenche. A
**Siemens SIPROTEC** deixa vazio e escreve a fase no fim do nome
(`TC BUC 69kV:I A`); o **GE** usa `G` onde a maioria usa `N`.

Isso não é detalhe estético: componentes simétricas (marco 0.4) precisam saber
quem é A, B e C. Sem o campo e sem a dedução, não há V1 nem V2.

A dedução devolve junto **de onde veio a resposta**, para a tela poder dizer
"deduzi isto do nome do canal" em vez de afirmar — a mesma regra do bruto ×
filtrado.
"""

from __future__ import annotations

import re
from enum import StrEnum

from osclab.formats.base import AnalogChannel, StatusChannel


class OrigemDaFase(StrEnum):
    DECLARADA = "declarada"   # o campo `ph` do arquivo veio preenchido
    DEDUZIDA = "deduzida"     # tirada do nome do canal
    DESCONHECIDA = "desconhecida"


#: Como cada fabricante chama o neutro/residual. Tudo vira "N".
_NEUTRO = {"N", "G", "E", "0"}

#: `IAW`, `VBY`, `ICX` — o padrão da SEL: grandeza, fase, enrolamento.
_SEL = re.compile(r"^[IVU]([ABC])[A-Z0-9]?$", re.IGNORECASE)

#: `Current IA`, `J1 -IC`, `Voltage VB` — grandeza colada na fase.
_GRANDEZA = re.compile(r"(?:^|[^A-Z0-9])[IVU]([ABC])[A-Z0-9]?(?:[^A-Z0-9]|$)",
                       re.IGNORECASE)

#: `Voltage A-G`, `...fase B` — a letra da fase sozinha, cercada de não-letras.
_FIM = re.compile(r"(?:^|[^A-Z0-9])([ABC])(?:[^A-Z0-9]|$)", re.IGNORECASE)

#: `3I0`, `3V0`, `IN`, `VNG`, `Ix`, `IG` — residual ou neutro.
#: O `{1,2}` é por causa do `VNG`: neutro-terra escrito com as duas letras.
_RESIDUAL = re.compile(r"(?:^|[^A-Z0-9])(3[IVU]0|[IVU][NGE]{1,2}|[IVU]X)"
                       r"(?:[^A-Z0-9]|$)", re.IGNORECASE)


def _normalizar(bruta: str) -> str:
    """`G`, `E` e `0` viram `N`; o resto vira maiúscula ou some."""
    limpa = (bruta or "").strip().upper()
    if limpa in _NEUTRO:
        return "N"
    return limpa if limpa in ("A", "B", "C") else ""


def deduzir(nome: str) -> str:
    """A fase que o NOME do canal sugere, ou `""`.

    A ordem das tentativas importa: `3I0` tem que ser reconhecido como residual
    ANTES de qualquer regra que procure uma letra solta, senão um canal chamado
    `3I0 BARRA A` viraria fase A.
    """
    limpo = (nome or "").strip()
    if not limpo:
        return ""

    if _RESIDUAL.search(limpo):
        return "N"

    # O último pedaço depois de ':' costuma ser a parte que nomeia a grandeza:
    # "TC BUC 69kV:I A" -> "I A". O hífen NÃO serve para cortar: "Voltage A-G"
    # perderia justamente a letra da fase.
    pedaco = limpo.split(":")[-1].strip() or limpo

    m = _SEL.match(pedaco.replace(" ", ""))
    if m:
        return m.group(1).upper()

    m = _GRANDEZA.search(pedaco)
    if m:
        return m.group(1).upper()

    achados = _FIM.findall(pedaco)
    if len(achados) == 1:
        return achados[0].upper()

    return ""


#: De que unidade sai cada letra de grandeza. O que não estiver aqui não ganha
#: nome padronizado: inventar um para um canal de frequência ou de potência
#: seria pior que não ter.
_GRANDEZAS = {
    "A": "I", "KA": "I", "MA": "I",
    "V": "V", "KV": "V", "MV": "V",
}


def padrao(canal: AnalogChannel | StatusChannel) -> str:
    """O nome que o OscLab dá ao canal: `IA`, `VB`, `IN`, `VN`...

    ## Por que existe um nome nosso ao lado do nome do arquivo

    Cada fabricante nomeia como quer: a Schneider escreve `Current IA`, o
    Siemens `TC BUC 69kV:I A`, a SEL `IAW`. Analisar um evento com registros de
    dois terminais de fabricantes diferentes vira um exercício de tradução.

    O nome padronizado é **sempre o mesmo**, venha de onde vier — e é por ele
    que o resto do programa vai se referir aos canais quando calcular
    componentes simétricas, impedância e localização de falta.

    Fica **ao lado** do nome do arquivo, nunca no lugar dele: o nome original é
    o que o engenheiro reconhece e o que consta do relatório do relé. Este é a
    tradução, e a tela mostra os dois para deixar claro o que é qual.

    Devolve `""` quando não dá para nomear — grandeza fora de corrente e tensão,
    ou fase que não se conseguiu determinar. Melhor nada que um palpite.
    """
    grandeza = _GRANDEZAS.get((getattr(canal, "unit", "") or "").strip().upper())
    if not grandeza:
        return ""
    fase, _ = da_canal(canal)
    return f"{grandeza}{fase}" if fase else ""


def da_canal(canal: AnalogChannel | StatusChannel) -> tuple[str, OrigemDaFase]:
    """A fase do canal e de onde ela veio."""
    declarada = _normalizar(getattr(canal, "phase", ""))
    if declarada:
        return declarada, OrigemDaFase.DECLARADA

    deduzida = deduzir(getattr(canal, "name", ""))
    if deduzida:
        return deduzida, OrigemDaFase.DEDUZIDA

    return "", OrigemDaFase.DESCONHECIDA
