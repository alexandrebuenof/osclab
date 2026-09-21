"""Quais canais formam um conjunto trifásico.

## O erro que este módulo existe para impedir

Componente simétrica é feita somando as três fases. Somar `IA` de um TC com
`IB` de outro dá um 3I0 sem sentido nenhum — **e ele sai com cara de número
bom**, na unidade certa, na ordem de grandeza certa. Ninguém percebe.

Um SEL-487E grava corrente de linha, de barra e de enrolamento no mesmo
arquivo, todas em ampères. Agrupar por unidade, que é o que a tela faz para
desenhar, juntaria as três famílias.

## De onde vem a resposta

**Primeiro o arquivo.** O COMTRADE tem o campo `ccbm` — *circuit component
being monitored*, o equipamento que aquele canal vigia. Foi criado exatamente
para isto. Quando vem preenchido (`LINHA 01`, `TRAFO T1`), ele manda e não há
o que deduzir.

**Depois o nome.** A maioria dos fabricantes deixa o `ccbm` vazio, então na
prática o caminho principal é: **tirar do nome a letra da fase e ver o que
sobra.** O resto é a identidade do conjunto.

    Current IA      →  Current I*      ┐
    Current IB      →  Current I*      ├ mesmo conjunto
    Current IC      →  Current I*      ┘
    Current IN      →  Current I*        e o neutro entra junto

    TC BUC 69kV:I A →  TC BUC 69kV:I *   outro conjunto
    Voltage A-G     →  Voltage *-G       outro ainda

Tira-se a **última** ocorrência da letra, não todas: em `BARRA A` a fase é o
segundo `A`, e apagar os dois daria `B*RR*` contra `*ARRA` da fase B — dois
conjuntos onde há um. A última ocorrência acerta os três padrões que já vimos
(SEL, Schneider, Siemens) e não depende de os canais estarem em ordem.

## Conjunto incompleto não vira componente nenhuma

Sem A, B e C não há transformação de Fortescue — há chute. Um registro com só
duas fases gravadas devolve zero conjuntos, e a tela mostra que não há
componentes, em vez de mostrar números tirados de dois terços da informação.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from osclab.formats import fases
from osclab.formats.base import Record

#: As três que a transformação exige. O neutro é bem-vindo e não é obrigatório:
#: ele não entra na conta, só acompanha o conjunto na tela.
NECESSARIAS = ("A", "B", "C")


class OrigemDoConjunto(StrEnum):
    DECLARADA = "declarada"   # o campo `ccbm` do arquivo veio preenchido
    DEDUZIDA = "deduzida"     # tirada do nome dos canais


class OrigemDoRotulo(StrEnum):
    """De onde saiu o apelido curto do conjunto — `AT`, `69kV`, `W`..."""

    UNICO = "unico"           # há um conjunto só: não precisa de apelido
    TENSAO = "tensao"         # deduzido do nível de tensão no nome
    ARQUIVO = "arquivo"       # o que o arquivo chama, sem interpretação


#: Como chamar os lados quando o nível de tensão de cada um é conhecido. Dois
#: enrolamentos são alta e baixa; três são alta, média e baixa. Acima disso não
#: há nomenclatura consagrada, e o programa volta a usar o nome do arquivo.
LADOS_POR_NIVEL = {2: ("AT", "BT"), 3: ("AT", "MT", "BT")}

#: `138kV`, `13.8 kV`, `69KV` — o nível de tensão escrito no nome do canal.
_NIVEL = re.compile(r"(\d+(?:[.,]\d+)?)\s*([MK]?)V\b", re.IGNORECASE)

#: Multiplicador de cada prefixo, para comparar 13.8kV com 138kV e com 500 V.
_ESCALA_DA_TENSAO = {"": 1.0, "K": 1e3, "M": 1e6}


@dataclass(frozen=True)
class Conjunto:
    """Três fases do mesmo equipamento, prontas para virar componentes."""

    #: Como chamar o conjunto na tela: o `ccbm`, ou o resto do nome.
    nome: str
    #: `I` ou `V` — decide se as componentes se chamam `3I0` ou `3V0`.
    grandeza: str
    #: A unidade do arquivo, que é por onde a tela agrupa os gráficos.
    unidade: str
    #: Fase → índice do canal no registro. Sempre tem A, B e C; N é opcional.
    canais: dict[str, int]
    origem: OrigemDoConjunto
    #: Apelido curto que distingue este conjunto dos outros da mesma grandeza:
    #: `AT`, `BT`, `69kV`, `W`. Vazio quando há um conjunto só — o caso comum,
    #: e o sufixo seria ruído.
    rotulo: str = ""
    origem_do_rotulo: OrigemDoRotulo = OrigemDoRotulo.UNICO

    @property
    def abc(self) -> tuple[int, int, int]:
        """Os índices de A, B e C, na ordem — como a conta os quer."""
        return (self.canais["A"], self.canais["B"], self.canais["C"])


def sem_a_fase(nome: str, fase: str) -> str:
    """O nome sem a última ocorrência da letra da fase.

    É a chave do conjunto. Ver o cabeçalho para por que a ÚLTIMA e não todas.
    """
    limpo = (nome or "").strip().upper()
    corte = limpo.rfind((fase or "").upper())
    if not fase or corte < 0:
        return limpo
    return f"{limpo[:corte]}*{limpo[corte + 1:]}"


def _chave(canal) -> tuple[str, str, OrigemDoConjunto]:
    """Onde este canal mora: `(nome do conjunto, unidade, de onde veio)`."""
    declarado = (getattr(canal, "component", "") or "").strip()
    if declarado:
        return declarado, declarado, OrigemDoConjunto.DECLARADA
    fase, _ = fases.da_canal(canal)
    resto = sem_a_fase(getattr(canal, "name", ""), fase)
    return resto, resto, OrigemDoConjunto.DEDUZIDA


def nivel_de_tensao(texto: str) -> float | None:
    """O nível de tensão escrito no nome, em volts, ou `None`.

    `TC BUC 69kV:I A` devolve 69 000. É o que permite dizer qual conjunto é o
    de alta sem adivinhar: o de maior tensão é a alta, e ponto.
    """
    achado = _NIVEL.search(texto or "")
    if not achado:
        return None
    try:
        valor = float(achado.group(1).replace(",", "."))
    except ValueError:
        return None
    return valor * _ESCALA_DA_TENSAO.get(achado.group(2).upper(), 1.0)


def _comum(nomes: list[str], do_fim: bool = False) -> int:
    """Quantos caracteres todos os nomes têm em comum, no começo ou no fim."""
    if not nomes:
        return 0
    pares = [n[::-1] if do_fim else n for n in nomes]
    for i in range(min(len(n) for n in pares)):
        if len({n[i] for n in pares}) > 1:
            return i
    return min(len(n) for n in pares)


def apelidos_do_arquivo(nomes: list[str]) -> list[str]:
    """O pedaço de cada nome que o DISTINGUE dos outros.

    Último recurso, quando não há nível de tensão para comparar. A ideia é
    simples: tudo que os nomes têm em comum não distingue nada, então corta-se
    o começo e o fim comuns e fica o miolo.

        I*W  e  I*X   →   W  e  X      (enrolamentos, na nomenclatura da SEL)

    Sai exatamente a letra do enrolamento, sem o programa precisar saber que
    existe tal coisa como enrolamento. Quando o corte deixa algo vazio — nomes
    idênticos, que não deviam chegar aqui — devolve o nome inteiro, porque um
    apelido vazio não distinguiria coisa alguma.
    """
    limpos = [" ".join((n or "").replace("*", " ").split()) for n in nomes]
    inicio, fim = _comum(limpos), _comum(limpos, do_fim=True)
    saida = []
    for nome in limpos:
        miolo = nome[inicio:len(nome) - fim].strip(" :-_")
        saida.append((miolo or nome)[:12])
    return saida


def rotular(achados: list[Conjunto]) -> list[Conjunto]:
    """Dá a cada conjunto o apelido que o distingue dos seus pares.

    Só rotula quando há **mais de um conjunto da mesma grandeza**: num registro
    de distribuição, com uma trinca de correntes só, `IA` continua `IA`, sem
    sufixo nenhum. Sufixo que não distingue nada é ruído.

    Quando todos os pares trazem o nível de tensão no nome e os níveis são
    diferentes, saem `AT`/`BT` (ou `AT`/`MT`/`BT`) **ordenados pela tensão** —
    o maior é a alta. Essa é a única forma de acertar o lado sem adivinhar:
    dois enrolamentos chamados `W` e `X` dizem que são diferentes e não dizem
    qual é o de cima.
    """
    saida: list[Conjunto] = []
    por_grandeza: dict[str, list[Conjunto]] = {}
    for c in achados:
        por_grandeza.setdefault(c.grandeza, []).append(c)

    for pares in por_grandeza.values():
        if len(pares) == 1:
            saida.extend(pares)
            continue

        niveis = [nivel_de_tensao(c.nome) for c in pares]
        lados = LADOS_POR_NIVEL.get(len(pares))
        # Todos precisam ter nível, e os níveis precisam ser distintos: dois
        # vãos de linha no mesmo 69 kV não são alta e baixa de nada.
        if lados and all(n is not None for n in niveis) and len(set(niveis)) == len(niveis):
            ordem = sorted(range(len(pares)), key=lambda i: niveis[i], reverse=True)
            for posicao, i in enumerate(ordem):
                saida.append(replace(pares[i], rotulo=lados[posicao],
                                     origem_do_rotulo=OrigemDoRotulo.TENSAO))
            continue

        for c, apelido in zip(pares, apelidos_do_arquivo([p.nome for p in pares]),
                              strict=True):
            saida.append(replace(c, rotulo=apelido,
                                 origem_do_rotulo=OrigemDoRotulo.ARQUIVO))

    return sorted(saida, key=lambda c: c.abc)


def rotulos_por_canal(registro: Record) -> dict[int, str]:
    """Índice do canal → apelido do conjunto dele. Vazio para quem não tem.

    É o que o nome do sinal consulta: sem isto, um registro de trafo teria dois
    canais chamados `IA` e a tela não diria qual é qual.
    """
    saida: dict[int, str] = {}
    for c in de_registro(registro):
        for indice in c.canais.values():
            saida[indice] = c.rotulo
    return saida


def de_registro(registro: Record) -> tuple[Conjunto, ...]:
    """Os conjuntos trifásicos completos do registro, já com apelido."""
    juntando: dict[tuple[str, str], dict] = {}

    for canal in registro.analog_channels:
        padrao = fases.padrao(canal)         # "IA", "VB"... já filtra grandeza
        if not padrao:
            continue
        fase = padrao[1:]
        if fase not in ("A", "B", "C", "N"):
            continue

        nome, _, origem = _chave(canal)
        unidade = canal.unit.strip()
        alvo = juntando.setdefault((nome, unidade), {
            "nome": nome, "grandeza": padrao[0], "unidade": unidade,
            "canais": {}, "origem": origem,
        })
        # Primeiro canal de cada fase vence. Dois `IA` no mesmo conjunto é
        # arquivo estranho, e escolher o segundo não seria mais certo que o
        # primeiro — só menos previsível.
        alvo["canais"].setdefault(fase, canal.index)

    completos = [
        Conjunto(nome=d["nome"], grandeza=d["grandeza"], unidade=d["unidade"],
                 canais=dict(d["canais"]), origem=d["origem"])
        for d in juntando.values()
        if all(f in d["canais"] for f in NECESSARIAS)
    ]
    return tuple(rotular(completos))
