"""O catálogo de sinais que se pode acrescentar a um gráfico.

## As duas listas: IED e OscLab

    IED       os canais do arquivo, com o nome que o fabricante deu
    OscLab    tudo que saiu de uma conta nossa

## As variáveis fundamentais, e por que elas ficam do lado do IED

`IA`, `IB`, `IC`, `IN`, `VA`, `VB`, `VC`, `VN` são as **fundamentais**: é delas
que sai todo o resto — `IA RMS`, `3I0`, `V1`, a localização de falta. E elas
não são um canal: são um **vínculo** que o programa deduziu, olhando o nome do
canal e decidindo que `Current IA` é a corrente da fase A.

Esse vínculo é a única coisa neste programa em que tudo o mais se apoia, e é
deduzido de um nome que cada fabricante escreve como quer (`Current IA`,
`IAW`, `TC BUC 69kV:I A`). Se ele estiver errado, todas as contas ficam
erradas **sem dar erro nenhum** — 3I0 sai na unidade certa, na ordem de
grandeza certa, e ninguém percebe.

Por isso a fundamental aparece ao lado do canal, na lista do IED: ali ela não
é um sinal a mais para desenhar, é a conferência do vínculo. Quem abre a lista
vê, numa passada, se o programa entendeu o arquivo — e um canal que ficou sem
fundamental aparece dizendo isso.

A lista do OscLab, então, não repete `IA`: ela traz o que o relé NÃO gravou —
`IA RMS`, `IA 60Hz`, `IA 60Hz RMS`, `3I0`, `I1`, `I2`.

## A grandeza é do SINAL, não do botão

Um sinal acrescentado à mão diz o que é no próprio nome: `IA RMS` é eficaz
verdadeiro, `IA 60Hz RMS` é a fundamental. O botão de filtro do cabeçalho
manda nos canais que abriram por padrão e não mexe neles — senão `IA RMS`
mudaria de significado com um clique em outro lugar da tela.

Num registro que o relé já gravou filtrado, as variantes `60Hz` não são
oferecidas: as amostras já SÃO a componente de 60 Hz, e filtrar de novo só
acrescentaria mais um ciclo de atraso.

## Por que nada entra sozinho

O programa sabe calcular 3I0, I1 e I2 desde que há três fases no arquivo. Ele
**não** põe nenhum deles na tela por conta própria, e isso é decisão tomada:
uma tela que se enche do que o programa sabe fazer vira um painel de números
que ninguém pediu, e o que importa some no meio. Quem analisa escolhe o que
olhar; o programa oferece.

Cada sinal escolhido é acrescentado a UM gráfico, por decisão de quem está
analisando.

## A identidade de um sinal cabe numa linha de texto

O navegador precisa dizer ao servidor "põe este sinal neste gráfico", e o
servidor precisa devolver o mesmo sinal com o mesmo nome. Um `id` de texto
resolve os dois lados e atravessa a URL sem ambiguidade:

    c3:instantaneo      o canal 3 do arquivo, cru, como o IED gravou
    v3:rms              o eficaz da janela de um ciclo daquele canal
    v3:fundamental      a componente de 60 Hz dele, em eficaz
    q0:1:rms            a sequência positiva do conjunto trifásico 0

O `q` é o índice do conjunto em `conjuntos.de_registro`, que é estável para um
mesmo arquivo. O `0`, `1`, `2` do meio são zero, positiva e negativa.

## Componente simétrica é fasor, e só existe em eficaz

`3I0` pode ser somado no tempo (é o resíduo, `ia+ib+ic` amostra a amostra), mas
`I1` e `I2` **não**: eles exigem girar `Ib` e `Ic` de 120°, e girar é
multiplicar por um complexo — operação que não existe sobre uma amostra
sozinha. Só existe sobre o fasor.

Por isso as componentes saem sempre como **módulo do fasor da janela de um
ciclo, em eficaz**, e as três seguem a mesma regra: oferecer 3I0 instantâneo e
I1 só em eficaz seria uma tela em que dois números com a mesma cara vieram de
definições diferentes. Um ciclo de atraso na subida vale para todas elas, como
vale para qualquer curva de envoltória.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from osclab.dsp import envoltoria, simetricas
from osclab.formats import conjuntos, fases
from osclab.formats.base import Record
from osclab.plot import conversao, sinais, unidades

#: Índice da componente no resultado de `simetricas.de_fasores`, e como ela se
#: chama. O `{g}` vira `I` ou `V`, conforme a grandeza do conjunto.
COMPONENTES = {
    "0": (0, "3{g}0", "sequência zero — o resíduo das três fases"),
    "1": (1, "{g}1", "sequência positiva"),
    "2": (2, "{g}2", "sequência negativa"),
}

#: O que o OscLab oferece a partir de UM canal: `(o que o sinal É, que conta
#: aplicar para chegar nele)`. Os dois são coisas diferentes, e a diferença
#: aparece justamente num registro já filtrado — ver o cabeçalho.
#:
#: Num registro BRUTO, as três contas são de verdade:
OFERTA_DE_BRUTO = (("rms", "rms"),
                   ("filtrado", "filtrado"),
                   ("fundamental", "fundamental"))

#: Num registro que o relé JÁ gravou filtrado, as amostras já SÃO a componente
#: de 60 Hz. Então `IA 60Hz` é o próprio canal (conta nenhuma), e o eficaz de
#: um ciclo dele já é o eficaz da fundamental. `IA RMS` — eficaz verdadeiro,
#: com harmônicos — não existe ali: não há harmônico para incluir, e oferecer
#: esse nome seria prometer uma medida que o arquivo não permite.
OFERTA_DE_FILTRADO = (("filtrado", "instantaneo"),
                      ("fundamental", "rms"))


@dataclass(frozen=True)
class Sinal:
    """Um sinal que se pode acrescentar a um gráfico."""

    id: str
    nome: str
    #: A unidade do ARQUIVO — é ela que diz a que grupo/gráfico o sinal
    #: pertence, e é a chave por onde a tela agrupa.
    unidade: str
    #: A unidade COM prefixo, que é a que a tela escreve (`kV`).
    unidade_mostrada: str
    #: `canal` (veio do arquivo) ou `calculado` (saiu de uma conta nossa).
    familia: str
    #: O que o sinal É: `instantaneo`, `rms`, `filtrado` ou `fundamental`. Vem
    #: no `id` e no nome, e NÃO muda com o botão de filtro.
    grandeza: str
    #: A conta que se aplica às amostras para chegar nele. Quase sempre igual a
    #: `grandeza` — e diferente num registro já filtrado, onde `IA 60Hz` é o
    #: próprio canal, sem conta nenhuma. Ver `OFERTA_DE_FILTRADO`.
    conta: str
    descricao: str
    #: Para `familia == "calculado"`: de que canal (ou canais) do IED ele saiu.
    origem: str = ""
    #: Só para `familia == "canal"`: a variável fundamental que o OscLab
    #: vinculou a este canal (`IA`), ou `""` quando não reconheceu. É a
    #: conferência do vínculo em que todas as contas se apoiam.
    fundamental: str = ""
    #: De onde veio esse vínculo: `escolhida` (o usuário corrigiu), `declarada`
    #: (o campo `ph` do arquivo), `deduzida` (do nome) ou `desconhecida`. A
    #: tela precisa disso para dizer "deduzi" em vez de afirmar.
    fundamental_origem: str = ""
    #: O índice do canal no registro, para a tela poder mandar a correção.
    canal: int = -1
    #: Só para `familia == "canal"`: `I` ou `V`, tirado da unidade. É o que
    #: permite a tela oferecer `IA, IB, IC, IN` na correção em vez das letras
    #: soltas — a grandeza não é palpite, vem da unidade do arquivo.
    grandeza_do_canal: str = ""


#: O que cada grandeza é, em uma linha, para o hover da lista.
_O_QUE_E = {
    "rms": "eficaz verdadeiro da janela de um ciclo — inclui harmônicos e DC",
    "filtrado": "só a componente de 60 Hz, no tempo — a saída do filtro do relé",
    "fundamental": "o eficaz da componente de 60 Hz — o número com que o relé "
                   "decide atuar",
}


def de_registro(registro: Record, lado: str = "arquivo") -> list[Sinal]:
    """Tudo que se pode acrescentar a um gráfico deste registro.

    A lista sai inteira, das duas famílias, e a tela separa em abas. O servidor
    monta porque o nome de um sinal é identidade e nasce no Python — ver
    `plot/sinais.py`.
    """
    escalas = unidades.por_unidade(registro, lado)
    rotulos = conjuntos.rotulos_por_canal(registro)
    ja_filtrado = str(registro.filtering) == "filtrado"

    saida: list[Sinal] = []

    # --- IED: o arquivo, cru, e o vínculo com a fundamental ---------------
    for canal in registro.analog_channels:
        unidade = canal.unit.strip()
        _, mostrada = escalas.get(unidade, (1.0, unidade))
        padrao = fases.padrao(canal)
        _, origem_da_fase = fases.da_canal(canal)
        saida.append(Sinal(
            id=f"c{canal.index}:instantaneo",
            nome=canal.name,
            unidade=unidade,
            unidade_mostrada=mostrada,
            familia="canal",
            grandeza="instantaneo",
            conta="instantaneo",
            descricao="a amostra como o IED gravou",
            grandeza_do_canal=fases.grandeza_da_unidade(unidade),
            fundamental=sinais.nome(padrao, "instantaneo",
                                    rotulos.get(canal.index, "")),
            fundamental_origem=str(origem_da_fase),
            canal=canal.index,
        ))

    # --- OscLab: o que o relé NÃO gravou ----------------------------------
    for canal in registro.analog_channels:
        unidade = canal.unit.strip()
        _, mostrada = escalas.get(unidade, (1.0, unidade))
        padrao = fases.padrao(canal)
        oferta = OFERTA_DE_FILTRADO if ja_filtrado else OFERTA_DE_BRUTO
        for grandeza, conta in oferta:
            nome = sinais.nome(padrao, grandeza, rotulos.get(canal.index, ""))
            saida.append(Sinal(
                id=f"v{canal.index}:{grandeza}",
                # Canal que o programa não reconheceu não ganha nome nosso:
                # fica com o do arquivo mais o sufixo da conta.
                nome=nome or _sem_padrao(canal.name, grandeza),
                unidade=unidade,
                unidade_mostrada=mostrada,
                familia="calculado",
                grandeza=grandeza,
                conta=conta,
                descricao=_O_QUE_E[grandeza],
                origem=canal.name,
            ))

    nomes_de_canal = {c.index: c.name for c in registro.analog_channels}
    for i, conjunto in enumerate(conjuntos.de_registro(registro)):
        _, mostrada = escalas.get(conjunto.unidade, (1.0, conjunto.unidade))
        # De que canais do relé saiu a componente. O nome interno do conjunto
        # (`CURRENT I*`, com a letra da fase trocada por `*`) diz respeito ao
        # agrupamento e não a quem olha a tela: o que interessa ali é poder
        # conferir QUAIS três canais entraram na conta.
        origem = ", ".join(nomes_de_canal.get(x, f"#{x}") for x in conjunto.abc)
        for chave, (_, molde, descricao) in COMPONENTES.items():
            nome = molde.format(g=conjunto.grandeza)
            saida.append(Sinal(
                id=f"q{i}:{chave}:rms",
                nome=" ".join(x for x in (nome, conjunto.rotulo) if x),
                unidade=conjunto.unidade,
                unidade_mostrada=mostrada,
                familia="calculado",
                grandeza="fundamental",
                conta="fundamental",
                descricao=f"{descricao} — módulo do fasor de um ciclo, eficaz",
                origem=origem,
            ))

    return saida


def _sem_padrao(nome: str, grandeza: str) -> str:
    sufixo = sinais.SUFIXOS.get(grandeza, "")
    return f"{nome} {sufixo}".strip()


def por_id(registro: Record, lado: str = "arquivo") -> dict[str, Sinal]:
    return {s.id: s for s in de_registro(registro, lado)}


def de_texto(texto: str | None) -> dict[str, list[str]]:
    """Lê `A=c3:rms,q0:1:rms;kV=q1:0:rms` — o que a tela manda na URL.

    A chave é a unidade DO ARQUIVO do gráfico, que é como os grupos são
    formados. Tudo que não casar é ignorado em silêncio: a tela manda texto, e
    o servidor não confia nele.
    """
    saida: dict[str, list[str]] = {}
    for parte in (texto or "").split(";"):
        unidade, _, lista = parte.partition("=")
        unidade = unidade.strip()
        if not unidade:
            continue
        ids = [x.strip() for x in lista.split(",") if x.strip()]
        if ids:
            saida.setdefault(unidade, []).extend(ids)
    return saida


# ---------------------------------------------------------------------------
# A série de um sinal acrescentado
# ---------------------------------------------------------------------------

def _canal_por_indice(registro: Record) -> dict:
    return {c.index: c for c in registro.analog_channels}


def serie(registro: Record, sinal: Sinal, j0: int, i1: int, trechos,
          lado: str, escalas: dict) -> np.ndarray:
    """Os valores do sinal na janela `[j0, i1)`, já convertidos e escalados.

    `j0` traz o ciclo de história que as envoltórias precisam; quem chama
    recorta o começo depois. A conversão de TC/TP e o prefixo `k` são
    multiplicações por escalar, então podem vir antes ou depois da DFT — aqui
    vêm antes, porque para a componente simétrica as três fases precisam estar
    na mesma base antes de serem somadas.
    """
    divisor, _ = escalas.get(sinal.unidade, (1.0, sinal.unidade))

    if sinal.id[0] in ("c", "v"):
        canal = _canal_por_indice(registro).get(int(sinal.id[1:].split(":")[0]))
        if canal is None:
            return np.full(i1 - j0, np.nan)
        # A CONTA do sinal, não a grandeza que o nomeia: num registro já
        # filtrado `IA 60Hz` é o próprio canal, sem conta nenhuma.
        grandeza = sinal.conta
        bruto = envoltoria.calcular(registro.analog[canal.index, j0:i1],
                                    trechos, registro.line_frequency, grandeza)
        convertido, _, _ = conversao.converter(bruto, canal, lado)
        return convertido / divisor

    return _serie_de_componente(registro, sinal, j0, i1, trechos, lado, divisor)


def _serie_de_componente(registro: Record, sinal: Sinal, j0: int, i1: int,
                         trechos, lado: str, divisor: float) -> np.ndarray:
    _, chave, _ = sinal.id.split(":")
    posicao, _, _ = COMPONENTES[chave]
    conjunto = _conjunto_do(registro, sinal)
    if conjunto is None:
        return np.full(i1 - j0, np.nan)

    canais = _canal_por_indice(registro)
    fasores = []
    for indice in conjunto.abc:
        canal = canais.get(indice)
        if canal is None:
            return np.full(i1 - j0, np.nan)
        convertido, _, _ = conversao.converter(registro.analog[indice, j0:i1],
                                               canal, lado)
        fasores.append(envoltoria.calcular_fasores(convertido, trechos,
                                                   registro.line_frequency))

    # `de_fasores` é escrita com escalares e roda igual sobre vetores: as
    # operações são soma e multiplicação por complexo, que o numpy faz elemento
    # a elemento. Uma implementação, dois usos — é assim que elas não divergem.
    componentes = simetricas.de_fasores(*fasores)
    return np.abs(componentes[posicao]) / math.sqrt(2.0) / divisor


def _conjunto_do(registro: Record, sinal: Sinal):
    achados = conjuntos.de_registro(registro)
    i = int(sinal.id[1:].split(":")[0])
    return achados[i] if 0 <= i < len(achados) else None


def fasor_de_componente(registro: Record, sinal: Sinal, i: int, por_ciclo: int,
                        lado: str, divisor: float) -> tuple[float, float] | None:
    """Módulo (eficaz) e ângulo da componente no instante da amostra `i`.

    É o que a tabelinha do cursor mostra. Sai da MESMA conta da curva — as três
    fases viram fasor, a transformação de Fortescue combina os três — só que
    numa amostra só.
    """
    from osclab.dsp import fasor as dsp_fasor

    conjunto = _conjunto_do(registro, sinal)
    if conjunto is None:
        return None
    _, chave, _ = sinal.id.split(":")
    posicao, _, _ = COMPONENTES[chave]

    canais = _canal_por_indice(registro)
    fasores = []
    for indice in conjunto.abc:
        canal = canais.get(indice)
        if canal is None:
            return None
        f = dsp_fasor.no_instante(registro.analog[indice], i, por_ciclo)
        if f is None:
            return None
        razao = conversao.relacao(canal)
        lado_do_canal = "primario" if canal.is_primary else "secundario"
        fator = 1.0
        if lado != lado_do_canal and razao > 0:
            fator = razao if lado == "primario" else 1.0 / razao
        # Fasor de PICO, como em `envoltoria.fasores`: o eficaz sai no fim, uma
        # vez só, depois de somar.
        pico = f.fundamental * math.sqrt(2.0) * fator / divisor
        fasores.append(pico * np.exp(1j * math.radians(f.angulo)))

    x = simetricas.de_fasores(*fasores)[posicao]
    return (float(abs(x)) / math.sqrt(2.0), float(np.degrees(np.angle(x))))
