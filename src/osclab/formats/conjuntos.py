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
    """De onde saiu o nome curto do conjunto — hoje só a numeração."""

    #: A posição do conjunto no arquivo: `G1`, `G2`. Todo conjunto tem nome,
    #: sempre — ver `rotular` para por que deixou de ser condicional.
    NUMERO = "numero"


#: `138kV`, `13.8 kV`, `69KV`, `34-5kV` — o nível de tensão escrito no nome.
#:
#: O `(?<![A-Za-z0-9])` na frente é o que impede o desastre. Sem ele, `L1V`
#: virava "1 volt" e `L2V` virava "2 volts": as duas linhas de um TWFL, ambas
#: no mesmo nível, apareciam com tensões DIFERENTES — e daí a alta e a baixa
#: de um transformador que não existe.
#:
#: O `-` entre os dígitos é porque a Siemens escreve `34-5kV` para 34,5 kV: o
#: ponto decimal não cabe no nome do canal dela. Sem isso, `TC EXT 34-5kV`
#: lia-se como 5 kV — errado por um fator de sete, e acertando o lado por
#: acidente só porque o outro enrolamento era 69 kV.
_NIVEL = re.compile(r"(?<![A-Za-z0-9])(\d+(?:[.,-]\d+)?)\s*([MK]?)V\b",
                    re.IGNORECASE)

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
    #: O NOME do grupo trifásico: `G1`, `G2`, `G3` — a posição do conjunto no
    #: arquivo, contada entre TODOS os conjuntos e não dentro da grandeza, para
    #: que `G1` signifique uma coisa só na tela. É o que o editor de grupos
    #: mostra, o que o rodapé do gráfico cita e o que entra no nome dos sinais
    #: que saem daqui (`3I0 G1`, `IN G1`).
    rotulo: str = ""
    origem_do_rotulo: OrigemDoRotulo = OrigemDoRotulo.NUMERO
    #: A posição DENTRO da grandeza, começando em 1. Não vai para a tela: é o
    #: que `plot/paineis.py` usa para dizer que a primeira trinca de corrente e
    #: a primeira de tensão são do mesmo lado do equipamento e merecem painéis
    #: intercalados. Antes esse papel era do próprio `rotulo`, que era ordinal
    #: por grandeza; com `G1` global os dois usos deixaram de caber num campo.
    ordem: int = 0
    #: As três fases estão lendo o próprio ruído: entrada do relé que ninguém
    #: cabeou. Ver `analysis/presenca.py` para como se mede, e `rotular` para o
    #: que isso muda no nome dos canais VIVOS.
    sem_sinal: bool = False

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
    """Onde este canal mora: `(nome do conjunto, unidade, de onde veio)`.

    **Um `ccbm` só de dígitos não é nome de equipamento.** O `ccbm` da norma é o
    *circuit component being monitored* — o equipamento que o canal vigia —, e
    por definição ele é o MESMO nas três fases. O SIPROTEC da Siemens escreve
    ali o número do canal: `1`, `2`, `3` para IA, IB, IC. Acreditar nisso põe
    cada fase num conjunto só dela, nenhum conjunto fecha as três, e o registro
    de um transformador fica **sem componente simétrica nenhuma** e com dois
    canais chamados `IA` na mesma tela — sem erro, sem aviso, sem nada.

    Foi assim por todo o marco 0.4 e só apareceu quando as trincas passaram a
    decidir o nome dos canais.
    """
    declarado = (getattr(canal, "component", "") or "").strip()
    if declarado and not declarado.isdigit():
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
        valor = float(achado.group(1).replace(",", ".").replace("-", "."))
    except ValueError:
        return None
    return valor * _ESCALA_DA_TENSAO.get(achado.group(2).upper(), 1.0)


#: O nome de um grupo trifásico: a letra G e a posição dele no arquivo.
_ORDINAL = re.compile(r"^G(\d+)$")


def _numerada(posicao: int) -> str:
    """O nome do grupo: `G1`, `G2`, `G3`.

    **Ordinal, e de proposito.** Ja foi apostrofo e ja foi a letra do terminal
    tirada do nome do arquivo (`IA S`, `IA 69kV`). O apostrofo era curto e nao
    dizia nada; a letra do terminal dizia alguma coisa, mas so funcionava
    porque a SEL e a Siemens tem o costume de escrever assim -- um rele que
    ninguem aqui viu nao tem essa obrigacao, e a ferramenta precisa servir a
    outra distribuidora com outro parque.

    "O primeiro conjunto trifasico do arquivo" existe em todo arquivo que
    existe. E a unica regra que nao depende de fabricante, e a origem -- de
    que canais aquilo saiu -- esta escrita na tela: no rodape do grafico, no
    editor de grupos e na coluna da direita do catalogo.

    **O numero e posicao dentro DAQUELE arquivo.** Dois registros do mesmo
    rele mantem a ordem; entre modelos diferentes, `G1` pode nao ser a mesma
    coisa. Nao e identidade estavel entre arquivos.

    **Conta TODOS os conjuntos, nao os da grandeza.** Num trafo com duas
    trincas de corrente e duas de tensao a numeracao sai `G1 G2 G3 G4`, e nao
    `G1 G2` duas vezes: o nome de um grupo tem que apontar para um grupo so,
    porque o usuario vai edita-lo por esse nome.
    """
    return f"G{posicao}"


def ordinal(rotulo: str) -> int | None:
    """O numero de um nome de grupo `G3`, ou `None` quando nao e um deles."""
    achado = _ORDINAL.match((rotulo or "").strip())
    return int(achado.group(1)) if achado else None


def juntar(nome: str, rotulo: str) -> str:
    """`3I0` + `G1` vira `3I0 G1`; sem nome de grupo, o nome sai inteiro."""
    return f"{nome} {rotulo}" if rotulo else nome


def _solto_numerado(posicao: int) -> str:
    """O apelido de um residual FORA de trinca: `[1]`, `[2]`.

    Colchete e nao `G`: `G1` passou a significar um grupo trifasico, e um `IG`
    solto nao e um grupo -- prometer que e' seria mentir no nome. O colchete
    existe por um caso real: o GE grava dois `IG` no mesmo arquivo, e os dois
    se chamariam `IN` sem nada que os separasse.

    So aparece quando ha MAIS DE UM na mesma grandeza. Com um so, o apelido
    nao distinguiria de nada, e inventaria uma ordem onde nao ha ordem.
    """
    return f"[{posicao}]"


def rotular(achados: list[Conjunto]) -> list[Conjunto]:
    """Da a cada conjunto o nome do grupo dele: `G1`, `G2`, `G3`.

    A regra inteira: a posicao no arquivo, contando TODOS os conjuntos na ordem
    em que chegaram -- correntes e tensoes na mesma contagem. `ordem` guarda à
    parte a posicao dentro da grandeza, que e' outra pergunta; ver o campo.

    **Todo conjunto tem nome, sempre.** Ja foi condicional: com uma trinca de
    corrente e uma de tensao o arquivo nao precisava de apelido e os nomes
    saiam limpos (`3I0`, `IN`). Deixou de ser quando o grupo virou objeto que o
    usuario EDITA: o editor de grupos chama aquilo de `G1`, o rodape do grafico
    cita `G1`, e um sinal chamado `3I0` sem grupo no nome obrigaria quem le a
    descobrir de qual deles ele saiu. Duas formas de chamar a mesma trinca era
    exatamente o que se estava evitando.

    O preco esta medido e aceito: num alimentador, que tem uma trinca de cada,
    o nome fica `3I0 G1` onde antes era `3I0`. Se um dia isso incomodar, o
    lugar de suprimir e' aqui -- e nao no nome do sinal, que tem que ser um so.

    **Ter sinal ou nao, nao muda o nome.** Um terminal que ninguem cabeou e uma
    trinca como as outras e recebe o proximo numero; o que ele nao faz e
    aparecer no grafico de abertura, e disso quem cuida e `plot/paineis.py`.
    """
    dentro_da_grandeza: dict[str, int] = {}
    saida: list[Conjunto] = []
    # A ORDEM recebida é preservada: ela é a posição que o `q{i}` dos arranjos
    # salvos usa. Ver `_completos`.
    for posicao, c in enumerate(achados, start=1):
        dentro = dentro_da_grandeza.get(c.grandeza, 0) + 1
        dentro_da_grandeza[c.grandeza] = dentro
        saida.append(replace(c, rotulo=_numerada(posicao),
                             origem_do_rotulo=OrigemDoRotulo.NUMERO,
                             ordem=dentro))
    return saida


def _pendurados(registro: Record, achados: list[Conjunto]) -> dict[int, int]:
    """Canal residual fora de trinca → a POSIÇÃO da trinca a que ele pertence.

    O `IG` de um SEL e o `3I0` de um Siemens medem a corrente de neutro no
    ferro e não entram na trinca porque o nome deles não sai do nome das fases
    trocando uma letra. Mas são do mesmo vão, e num evento à terra são a
    primeira coisa que se procura — tanto no gráfico de abertura quanto no
    NOME: sem isto, um painel do Siemens abria com o resíduo `IN` sem grupo
    nenhum no meio dos sinais de `G1`.

    Com mais de uma trinca da mesma unidade, só entra quando o nível de tensão
    do nome casa com o de uma delas. Sem isso seria adivinhar de que lado do
    transformador é o residual — e pendurá-lo no lado errado é pior que
    deixá-lo solto. É por isso que o `TC BUC 69kV:3I0` entra e o
    `TC H0 NEUTRO:Ix`, que não traz nível nenhum no nome, fica de fora.
    """
    usados = {i for c in achados for i in c.canais.values()}

    destino: dict[int, int] = {}
    for canal in registro.analog_channels:
        if canal.index in usados:
            continue
        if fases.grandeza_da_unidade(canal.unit) not in ("I", "V"):
            continue
        fase, _ = fases.da_canal(canal)
        if fase != "N":
            continue

        unidade = canal.unit.strip()
        candidatas = [i for i, c in enumerate(achados) if c.unidade == unidade]
        if len(candidatas) == 1:
            destino[canal.index] = candidatas[0]
            continue
        nivel = nivel_de_tensao(canal.name)
        iguais = [i for i in candidatas
                  if nivel is not None
                  and nivel_de_tensao(achados[i].nome) == nivel]
        if len(iguais) == 1:
            destino[canal.index] = iguais[0]
    return destino


def residuais_soltos(registro: Record) -> dict[int, int]:
    """`_pendurados` a partir do registro. Ver lá."""
    return _pendurados(registro, _completos(registro))


def _avulsos(registro: Record, achados: list[Conjunto],
             pendurados: dict[int, int]) -> dict[int, str]:
    """Canal residual que não achou trinca nenhuma → a grandeza dele.

    São o `J1 -IG` e o `J1 Ig` do GE e os dois `NEUTRO:Ix` do SIPROTEC: neutro
    de verdade, num arquivo com mais de uma trinca da mesma unidade e sem nada
    com que decidir de qual delas eles são. Cada um vale por um conjunto na
    hora de numerar — senão os dois do GE se chamariam os dois `IN`.
    """
    usados = {i for c in achados for i in c.canais.values()}
    saida: dict[int, str] = {}
    for canal in registro.analog_channels:
        if canal.index in usados or canal.index in pendurados:
            continue
        grandeza = fases.grandeza_da_unidade(canal.unit)
        if grandeza not in ("I", "V"):
            continue
        fase, _ = fases.da_canal(canal)
        if fase == "N":
            saida[canal.index] = grandeza
    return saida


def _por_grandeza(avulsos: dict[int, str]) -> dict[str, list[int]]:
    """`{grandeza: [índices de canal, em ordem de arquivo]}`."""
    saida: dict[str, list[int]] = {}
    for indice in sorted(avulsos):
        saida.setdefault(avulsos[indice], []).append(indice)
    return saida


def rotulos_por_canal(registro: Record) -> dict[int, str]:
    """Índice do canal → apelido do conjunto dele. Vazio para quem não tem.

    É o que o nome do sinal consulta: sem isto, um registro de trafo teria dois
    canais chamados `IA` e a tela não diria qual é qual.

    O residual pendurado leva o nome do grupo da trinca dele — ele é do mesmo
    vão. O residual avulso não é grupo nenhum e só ganha apelido quando há mais
    de um da mesma grandeza para desempatar. Ver `_pendurados`, `_avulsos` e
    `_solto_numerado`.
    """
    achados = _completos(registro)
    pendurados = _pendurados(registro, achados)
    avulsos = _avulsos(registro, achados, pendurados)
    soltos = _por_grandeza(avulsos)
    todos = rotular(achados)

    saida: dict[int, str] = {}
    for c in todos:
        for indice in c.canais.values():
            saida[indice] = c.rotulo
    for solto, alvo in pendurados.items():
        if 0 <= alvo < len(todos):
            saida[solto] = todos[alvo].rotulo

    for canais in soltos.values():
        if len(canais) < 2:
            saida.update(dict.fromkeys(canais, ""))
            continue
        for i, indice in enumerate(sorted(canais), start=1):
            saida[indice] = _solto_numerado(i)
    return saida


def _agrupar(registro: Record) -> list[dict]:
    """As trincas completas do registro, ainda sem apelido e sem veredito."""
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

    return [d for d in juntando.values()
            if all(f in d["canais"] for f in NECESSARIAS)]


def canais_sem_sinal(registro: Record) -> frozenset[int]:
    """Os canais que a tela pode deixar de desenhar por padrão.

    **Só some TRINCA INTEIRA.** Um canal solto em zero pode ser a informação: a
    tensão residual `VNG` de um Schneider marca 0,14 V porque não há falta à
    terra, e esse zero é a resposta que alguém foi procurar no arquivo. Já uma
    trinca inteira em zero é entrada de relé que ninguém cabeou — o SEL-487E
    tem cinco terminais de TC e três estão livres.

    E é tudo ou nada dentro da trinca: se só duas das três fases dessem o
    veredito de morta, esconder as duas seria pior que não esconder nenhuma —
    sobraria uma fase solta na tela, com cara de que as outras não existem.
    Aconteceu de verdade no 487E, onde o `ICU` passou raspando do limiar.
    """
    # Import adiado: `analysis` conversa com `formats`, e importá-lo no topo
    # fecharia um ciclo. Mesmo motivo de `formats/registry.py`.
    from osclab.analysis import presenca

    crus = presenca.sem_sinal(registro)
    if not crus:
        return frozenset()

    mortos: set[int] = set()
    for grupo in _agrupar(registro):
        indices = set(grupo["canais"].values())
        if indices <= crus:
            mortos |= indices
    return frozenset(mortos)


def _escolhidos(canais: dict[str, int], escolha) -> dict[str, int]:
    """Os canais da trinca com a correção do usuário por cima.

    Só A, B e C se corrigem — são os que entram na transformação de Fortescue.
    O residual acompanha a trinca e não entra na conta; quem o pendura é
    `_pendurados`, pelo nome.
    """
    if not isinstance(escolha, dict):
        return canais
    saida = dict(canais)
    for fase in NECESSARIAS:
        valor = escolha.get(fase)
        if isinstance(valor, int) and valor >= 0:
            saida[fase] = valor
    return saida


def _completos(registro: Record) -> list[Conjunto]:
    """As trincas do registro, ainda SEM apelido, na ordem em que saem na tela.

    Já vem ordenada porque `_pendurados` devolve POSIÇÃO nesta lista, e quem
    consulta a posição depois consulta a lista já rotulada — se as duas não
    estivessem na mesma ordem, o residual seria pendurado na trinca errada.

    **A ordem sai dos canais DEDUZIDOS, não dos corrigidos.** A posição na
    lista é o `q{i}` dos arranjos já salvos; se corrigir uma trinca a fizesse
    trocar de lugar com outra, um gráfico salvo passaria a desenhar a corrente
    de outro equipamento, sem erro nenhum na tela.
    """
    mortos = canais_sem_sinal(registro)
    escolhas = getattr(registro, "trincas_escolhidas", None) or {}
    completos = []
    for d in _agrupar(registro):
        canais = _escolhidos(d["canais"], escolhas.get(d["nome"]))
        completos.append((
            min(d["canais"].values()),
            Conjunto(nome=d["nome"], grandeza=d["grandeza"],
                     unidade=d["unidade"], canais=canais, origem=d["origem"],
                     sem_sinal=bool(set(canais.values()) <= mortos) if mortos
                     else False),
        ))
    return [c for _, c in sorted(completos, key=lambda x: x[0])]


def de_registro(registro: Record) -> tuple[Conjunto, ...]:
    """Os conjuntos trifásicos completos do registro, já com nome de grupo."""
    return tuple(rotular(_completos(registro)))
