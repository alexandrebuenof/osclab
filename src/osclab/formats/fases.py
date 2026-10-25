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
import unicodedata
from enum import StrEnum

from osclab.formats.base import AnalogChannel, StatusChannel


class OrigemDaFase(StrEnum):
    ESCOLHIDA = "escolhida"   # o usuário corrigiu o que o programa deduziu
    DECLARADA = "declarada"   # o campo `ph` do arquivo veio preenchido
    DEDUZIDA = "deduzida"     # tirada do nome do canal
    DESCONHECIDA = "desconhecida"


#: Como cada fabricante chama o neutro/residual. Tudo vira "N".
_NEUTRO = {"N", "G", "E", "0"}

#: As três fases, quando o canal mede contra o neutro.
FASES = ("A", "B", "C")

#: Os três LAÇOS, quando o canal mede entre duas fases.
#:
#: `VAB` não é "a fase A": é a diferença entre duas fases, e tratá-lo como
#: fase A é o erro que faz o resíduo dar zero por identidade (VAB+VBC+VCA ≡ 0)
#: e o 3V0 sair como um número que parece medido e não é.
#:
#: Existem em corrente também: um TC de delta fechado mede `IAB`.
LACOS = ("AB", "BC", "CA")

#: Para cada laço, o par de fases que ele liga — na ordem em que o nome diz.
PARES_DO_LACO = {"AB": ("A", "B"), "BC": ("B", "C"), "CA": ("C", "A")}


def e_de_linha(fase: str) -> bool:
    """Se este vínculo é um LAÇO (entre fases) e não uma fase contra o neutro."""
    return (fase or "").strip().upper() in LACOS

#: Quantos caracteres o TERMINAL pode ter depois da letra da fase.
#:
#: Era 1 (`IAW`, `VBY`, `ICX` — o padrão de terminal único da SEL) e o `.CEV`
#: do SEL-787 do parque mostrou que não basta: um diferencial de transformador
#: nomeia os enrolamentos `IAW1` e `IAW2`, com DOIS. Com o limite em 1, as duas
#: trincas de corrente daquele arquivo simplesmente não existiam — e nada na
#: tela dizia isso: os canais apareciam, desenhavam, e só 3I0, I1, I2 e a
#: localização de falta é que não existiam.
#:
#: **Dois, e não `*`.** Com sufixo livre, `VALOR` viraria fase A. O limite é o
#: que separa "terminal de relé" de "palavra qualquer".
_TERMINAL = "[A-Z0-9]{0,2}"

#: `IAW`, `VBY`, `ICX`, `IAW1` — o padrão da SEL: grandeza, fase, enrolamento.
_SEL = re.compile(rf"^[IVU]([ABC]){_TERMINAL}$", re.IGNORECASE)

#: `Current IA`, `J1 -IC`, `Voltage VB` — grandeza colada na fase.
_GRANDEZA = re.compile(
    rf"(?:^|[^A-Z0-9])[IVU]([ABC]){_TERMINAL}(?:[^A-Z0-9]|$)", re.IGNORECASE)

#: `Voltage A-G`, `...fase B` — a letra da fase sozinha, cercada de não-letras.
_FIM = re.compile(r"(?:^|[^A-Z0-9])([ABC])(?:[^A-Z0-9]|$)", re.IGNORECASE)

#: `Voltage N-G` — a letra do neutro sozinha. Só vale como último recurso: ver
#: a ordem em `deduzir`.
_NEUTRO_SOZINHO = re.compile(r"(?:^|[^A-Z0-9])([NGE])(?:[^A-Z0-9]|$)",
                             re.IGNORECASE)

#: `3I0`, `3V0`, `IN`, `VNG`, `Ix`, `IG` — residual ou neutro.
#: O `{1,2}` é por causa do `VNG`: neutro-terra escrito com as duas letras.
#: O `{_TERMINAL}` do fim é pelo mesmo motivo do `_SEL`: o SEL-787 escreve o
#: neutro de cada enrolamento como `IGW1` e `IGW2`, e o de outro ponto como
#: `IN1`. Sem ele, três canais de neutro ficavam sem fase nenhuma.
#: O ponto não fecha o residual: a Ingeteam abrevia intensidade como `Int.`
#: (`IA-Int.Fase A`), e `INT` + `.` casava como neutro de terminal `T` — as
#: três fases de todo PL300 do parque viravam `IN`, e trinca nenhuma fechava.
_RESIDUAL = re.compile(
    rf"(?:^|[^A-Z0-9])(3[IVU]0|[IVU][NGE]{{1,2}}|[IVU]X){_TERMINAL}"
    rf"(?:[^A-Z0-9.]|$)", re.IGNORECASE)


def _normalizar(bruta: str) -> str:
    """`G`, `E` e `0` viram `N`; o resto vira maiúscula ou some.

    Aceita também os LAÇOS `AB`, `BC` e `CA` — a medição entre duas fases.
    Ver `LACOS`: ela não é uma fase, e o programa inteiro precisa saber a
    diferença.
    """
    limpa = (bruta or "").strip().upper()
    if limpa in _NEUTRO:
        return "N"
    if limpa in LACOS:
        return limpa
    return limpa if limpa in FASES else ""


def deduzir(nome: str) -> str:
    """A fase que o NOME do canal sugere, ou `""`.

    A ordem das tentativas importa: `3I0` tem que ser reconhecido como residual
    ANTES de qualquer regra que procure uma letra solta, senão um canal chamado
    `3I0 BARRA A` viraria fase A.
    """
    # Sem acento: as fronteiras de palavra das expressões são `[^A-Z0-9]`, e
    # o `ó` de `Tensión` contava como fronteira — o `N` do fim ficava solto e
    # `VSIN-Tensión Sincronismo` (a tensão de sincronismo) virava neutro.
    limpo = unicodedata.normalize("NFKD", (nome or "").strip())
    limpo = limpo.encode("ascii", "ignore").decode("ascii")
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

    # Último recurso, e só depois de A/B/C terem falhado: a letra do neutro
    # sozinha. `Voltage N-G` não casa com `_RESIDUAL` (que espera o `V` colado,
    # como em `VNG`) e ficava sem fase nenhuma — um canal de tensão residual
    # fora de toda conta. `Voltage A-G` não chega aqui: o `A` já foi achado
    # acima, que é por isso que esta regra vem por último.
    if _NEUTRO_SOZINHO.search(pedaco):
        return "N"

    return ""


#: De que unidade sai cada letra de grandeza. O que não estiver aqui não ganha
#: nome padronizado: inventar um para um canal de frequência ou de potência
#: seria pior que não ter.
_GRANDEZAS = {
    "A": "I", "KA": "I", "MA": "I",
    "V": "V", "KV": "V", "MV": "V",
}


def grandeza_da_unidade(unidade: str) -> str:
    """`A`/`kA` → `I`; `V`/`kV` → `V`; o resto → `""`.

    A grandeza NÃO é palpite: vem da unidade que o arquivo declara. É a fase
    que se deduz do nome — e é só ela que o usuário precisa poder corrigir.
    """
    return _GRANDEZAS.get((unidade or "").strip().upper(), "")


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
    """A fase do canal e de onde ela veio.

    A ordem é a da confiança: o que o USUÁRIO escolheu vence tudo. Ele olhou o
    arquivo e o unifilar; a nossa expressão regular olhou um nome que cada
    fabricante escreve como quer. `"-"` é a escolha explícita de "este canal
    não é fase nenhuma", e por isso não cai na dedução.
    """
    escolhida = getattr(canal, "phase_escolhida", "") or ""
    if escolhida == "-":
        return "", OrigemDaFase.ESCOLHIDA
    if escolhida:
        normalizada = _normalizar(escolhida)
        if normalizada:
            return normalizada, OrigemDaFase.ESCOLHIDA

    declarada = _normalizar(getattr(canal, "phase", ""))
    if declarada:
        return declarada, OrigemDaFase.DECLARADA

    deduzida = deduzir(getattr(canal, "name", ""))
    if deduzida:
        return deduzida, OrigemDaFase.DEDUZIDA

    return "", OrigemDaFase.DESCONHECIDA
