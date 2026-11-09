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

Quem fica sem trinca ganha uma segunda tentativa, sem todas as MARCAS de fase
(`_sem_as_marcas`): é o que fecha `T1 Phase C Current` (o C de `CURRENT` é a
última ocorrência) e `IA-Int.Fase A` (a fase escrita duas vezes).

## Conjunto incompleto não vira componente nenhuma

Sem A, B e C não há transformação de Fortescue — há chute. Um registro com só
duas fases gravadas devolve zero conjuntos, e a tela mostra que não há
componentes, em vez de mostrar números tirados de dois terços da informação.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np

from osclab.formats import fases
from osclab.formats.base import Record, lembrado

#: As três que a transformação exige. O neutro é bem-vindo e não é obrigatório:
#: ele não entra na conta, só acompanha o conjunto na tela.
NECESSARIAS = ("A", "B", "C")

#: As três de uma trinca em DELTA: o relé gravou entre fases, não contra o
#: neutro. `VAB`, `VBC`, `VCA` — e existe em corrente também, num TC de delta
#: fechado (`IAB`).
#:
#: Uma trinca é de uma base ou da outra, nunca das duas: `VA`, `VB` e `VAB` no
#: mesmo grupo não é trinca de nada. Ver `_agrupar`.
NECESSARIAS_EM_DELTA = ("AB", "BC", "CA")

#: Como se chama cada base, e é o que `Conjunto.base` guarda.
FASE = "fase"
LINHA = "linha"


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
    #: Contra o quê o relé mediu: `"fase"` (contra o neutro) ou `"linha"`
    #: (entre duas fases). Decide o que a trinca PODE produzir — em delta não
    #: há `3V0` nem `VN`, e `V1`/`V2` precisam desfazer o √3∠±30°. Ver
    #: `dsp/simetricas.de_lacos`.
    #:
    #: É campo e não dedução dos números: `VAB` e `VA` são indistinguíveis
    #: olhando a onda, e um sistema de 13,8 kV medido em linha dá valores
    #: perfeitamente plausíveis para um de 23,9 kV medido em fase.
    base: str = FASE

    @property
    def e_de_linha(self) -> bool:
        """A trinca é em delta — mediu entre fases."""
        return self.base == LINHA

    @property
    def rotulos(self) -> tuple[str, str, str]:
        """As três chaves de `canais` que entram na conta, nesta base."""
        return NECESSARIAS_EM_DELTA if self.e_de_linha else NECESSARIAS

    @property
    def abc(self) -> tuple[int, int, int]:
        """Os três índices que entram na conta, na ordem.

        Em delta são `AB`, `BC`, `CA` — e NÃO são as fases A, B e C. Quem lê
        daqui tem que olhar `base` antes de aplicar Fortescue: a mesma conta
        sobre laços devolve números que parecem `3V0`, `V1` e `V2` e não são.
        O nome continua `abc` porque a POSIÇÃO é a mesma (a primeira, a
        segunda, a terceira) e renomeá-lo faria quinze chamadas mudarem sem
        que nenhuma delas ficasse mais correta.
        """
        return tuple(self.canais[f] for f in self.rotulos)


def sem_a_fase(nome: str, fase: str) -> str:
    """O nome sem a última ocorrência da letra da fase.

    É a chave do conjunto. Ver o cabeçalho para por que a ÚLTIMA e não todas.
    """
    limpo = (nome or "").strip().upper()
    marca = (fase or "").upper()
    if not fase:
        return limpo
    # O sufixo do enrolamento (`Current IA.a`, MiCOM P63x) fica de fora da
    # busca: sem isso a última ocorrência do A era a do `.a`, e `CURRENT IA.*`
    # nunca encontrava o `CURRENT I*.A` da fase B — o diferencial inteiro sem
    # trinca nenhuma (31/10/2026).
    corpo, sufixo = fases.sem_enrolamento(limpo)
    achado = _marca_do_neutro(corpo) if marca == "N" else None
    if achado is not None:
        inicio, fim = achado
    else:
        inicio = corpo.rfind(marca)
        if inicio < 0:
            corpo, sufixo = limpo, ""
            inicio = corpo.rfind(marca)
        if inicio < 0:
            return limpo
        # `len(marca)` e não 1, por causa do laço: em `IAB` a fase é `AB`, e
        # tirar um caractere só deixaria `I*B` contra o `I*C` de `IBC` — três
        # conjuntos de um canal cada, onde há uma trinca em delta. Para fase
        # simples o comprimento é 1 e nada muda.
        fim = inicio + len(marca)
    return f"{corpo[:inicio]}*{corpo[fim:]}{sufixo}"


#: A marca do neutro colada na grandeza: o `N` de `IN`, o `G` de `IG`, o `Y`
#: de `IY`, o `NG` de `VNG`. É o que o residual tem no lugar da letra da fase.
_MARCA_DO_NEUTRO = re.compile(r"(?:^|(?<=[^A-Z0-9]))[IVU]([NGEXY]{1,2})(?![A-Z])")


def _marca_do_neutro(nome: str) -> tuple[int, int] | None:
    """Onde está a letra do neutro no nome, ou `None`.

    O neutro não tem letra de fase para tirar, e a ÚLTIMA ocorrência do `N` não
    é a marca dele em `CURRENT IY.A` (cairia no `N` de `CURRENT`). Procura-se a
    marca colada na grandeza, a última que houver.
    """
    achados = list(_MARCA_DO_NEUTRO.finditer(nome))
    if not achados:
        return None
    return achados[-1].span(1)


def _sem_as_marcas(nome: str, fase: str) -> str | None:
    """A SEGUNDA tentativa de chave: o nome sem TODAS as marcas de fase.

    Marca de fase é a letra SOLTA (`Fase A`, `Voltage A-G`) ou colada na
    grandeza com o terminal da SEL depois (`IA`, `IAW1`). `None` quando não
    há marca nenhuma.

    Só vale para quem a última ocorrência deixou sem trinca (ver `_agrupar`):
    como chave principal ela erraria `IC 13.8kV:I C`, onde o `IC` do começo
    é o nome do equipamento. Dois nomes do parque pediram isto (24/10/2026),
    e nos dois trinca nenhuma fechava:

    - o religador escreve `T1 Phase C Current`, e a ÚLTIMA ocorrência do C é a
      de `CURRENT` — a letra dentro de uma palavra comum;
    - o PL300 escreve `IA-Int.Fase A`, com a fase DUAS vezes: tirando só uma,
      sobrava `IA-…` contra `IB-…`.
    """
    limpo = (nome or "").strip().upper()
    marca = (fase or "").upper()
    if not marca:
        return None
    m = re.escape(marca)
    marcas = re.compile(
        rf"(?<![A-Z0-9]){m}(?![A-Z0-9])"                       # solta
        rf"|(?:(?<=^[IVU])|(?<=[^A-Z0-9][IVU])){m}"            # colada: IA, IAW1
        rf"(?=[A-Z0-9]{{0,2}}(?![A-Z0-9]))")
    achadas = list(marcas.finditer(limpo))
    if not achadas:
        return None
    saida, antes = [], 0
    for a in achadas:
        saida.append(limpo[antes:a.start()] + "*")
        antes = a.end()
    saida.append(limpo[antes:])
    return "".join(saida)


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
    ondas = _ondas(registro)

    destino: dict[int, int] = {}
    for canal in registro.analog_channels:
        if canal.index in usados:
            continue
        if ondas is not None and canal.index not in ondas:
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
    ondas = _ondas(registro)
    saida: dict[int, str] = {}
    for canal in registro.analog_channels:
        if canal.index in usados or canal.index in pendurados:
            continue
        if ondas is not None and canal.index not in ondas:
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
    """As trincas completas do registro, ainda sem apelido e sem veredito.

    Duas passadas. A primeira usa a chave de sempre (`sem_a_fase`). A segunda
    só olha os canais DEDUZIDOS que ficaram fora de toda trinca, e os junta
    pela chave sem as marcas de fase (`_sem_as_marcas`) — assim ela pode
    fechar a trinca do religador e a do PL300 sem mexer em nenhuma que já
    fechava.
    """
    ondas = _ondas(registro)
    candidatos = []
    for canal in registro.analog_channels:
        padrao = fases.padrao(canal)         # "IA", "VB"... já filtra grandeza
        if not padrao:
            continue
        if ondas is not None and canal.index not in ondas:
            continue
        fase = padrao[1:]
        if fase not in NECESSARIAS + NECESSARIAS_EM_DELTA + ("N",):
            continue
        candidatos.append((canal, padrao, fase))

    # **Um `ccbm` que junta DUAS fases A da mesma unidade não é nome de
    # equipamento: é o nome do RELÉ.** O SEL-487E escreve no COMTRADE o mesmo
    # `ALTA TR01_UPC1` em todo canal, e o nosso leitor de `.CEV` põe o RID ali.
    # Acreditar nisso juntava os cinco terminais de TC num grupo só; a primeira
    # fase A ganhava, e o terminal T — o outro lado do trafo — sumia, sem aviso:
    # 23 dos 28 registros de 487E/787 do parque ficavam sem diferencial, sem o
    # 3I0 do outro lado e sem a localização dele (25/10/2026). Nesse caso vale
    # a dedução pelo nome do canal (`IAS` → `I*S`), como no `ccbm` só de dígitos.
    contagem: dict[tuple[str, str, str], int] = {}
    for canal, _, fase in candidatos:
        declarado = (getattr(canal, "component", "") or "").strip()
        chave = (declarado, canal.unit.strip(), fase)
        contagem[chave] = contagem.get(chave, 0) + 1
    # Vale para o ARQUIVO inteiro, não só para a unidade que repetiu: se o
    # `ccbm` é o nome do relé nas correntes, é também nas tensões — deixá-las
    # com o nome do relé e as correntes com `I*` desfazia a correspondência
    # `I*` ↔ `V*` de que o plano de impedância precisa.
    do_rele = {d for (d, _, _), n in contagem.items() if d and n > 1}

    def chave(canal) -> tuple[str, OrigemDoConjunto]:
        declarado = (getattr(canal, "component", "") or "").strip()
        if declarado in do_rele:
            fase, _ = fases.da_canal(canal)
            return sem_a_fase(getattr(canal, "name", ""), fase), OrigemDoConjunto.DEDUZIDA
        nome, _, origem = _chave(canal)
        return nome, origem

    saida = _trincas_de(
        [(canal, padrao, fase, *chave(canal))
         for canal, padrao, fase in candidatos])
    usados = {i for d in saida for i in d["canais"].values()}
    segunda = []
    for canal, padrao, fase in candidatos:
        if canal.index in usados:
            continue
        nome, origem = chave(canal)
        if origem != OrigemDoConjunto.DEDUZIDA:
            continue
        outra = _sem_as_marcas(getattr(canal, "name", ""), fase)
        if outra is not None:
            segunda.append((canal, padrao, fase, outra, origem))
    saida += _trincas_de(segunda)

    # Terceira tentativa, pelo mesmo critério da segunda (só quem sobrou): o
    # nome sem o número do BORNE. O GE UR (L90, T60) nomeia o canal pelo
    # módulo e pelo borne — `F1-IA`, `F2-IB`, `F3-IC`, `F4-IG` —, e o número
    # muda a cada fase. Sem esta passada as ondas do relé não fechavam trinca
    # nenhuma (31/10/2026).
    usados = {i for d in saida for i in d["canais"].values()}
    terceira = []
    for canal, padrao, fase in candidatos:
        if canal.index in usados:
            continue
        nome, origem = chave(canal)
        if origem != OrigemDoConjunto.DEDUZIDA:
            continue
        sem_borne = _sem_o_borne(getattr(canal, "name", ""))
        if sem_borne is not None:
            terceira.append((canal, padrao, fase, sem_a_fase(sem_borne, fase), origem))
    return saida + _trincas_de(terceira)


#: `F1-`, `M8-`, `L4-` no começo do nome: o módulo (letra) e o borne
#: (número) do GE UR.
_BORNE = re.compile(r"^([A-Z])\d{1,2}(?=\s*-)", re.IGNORECASE)


def _sem_o_borne(nome: str) -> str | None:
    """`F#-IA` de `F1-IA`; `None` quando o nome não começa por um borne."""
    limpo = (nome or "").strip()
    if not _BORNE.match(limpo):
        return None
    return _BORNE.sub(r"\1#", limpo)


#: Uma magnitude é comparável às ondas da mesma grandeza; a entrada morta
#: lendo o offset do conversor, não. Em fração da maior onda VIVA, com tudo em
#: primário. Medido: magnitudes do GE UR e do 850 entre 11 % e 100 % da onda;
#: entradas mortas de `.CEV` (1,4 A contra centenas) e do PL300 abaixo de 2 %.
FRACAO_DA_ONDA = 0.05


def _em_primario(canal) -> float:
    """Quanto multiplica o valor gravado para chegar ao primário, com prefixo."""
    fator = _prefixo(canal.unit)
    if (canal.scaling or "S").upper() == "S" and canal.secondary:
        fator *= (canal.primary or 1.0) / canal.secondary
    return fator


def _prefixo(unidade: str) -> float:
    """O multiplicador do prefixo: `kV` → 1000, `mA` → 0,001, `V` → 1."""
    limpa = (unidade or "").strip()
    if len(limpa) > 1 and fases.grandeza_da_unidade(limpa):
        return {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3}.get(limpa[0], 1.0)
    return 1.0


def _ondas(registro: Record) -> frozenset[int] | None:
    """Os canais que podem fechar trinca: tudo menos a MAGNITUDE do relé.

    **Magnitude calculada pelo relé não é fase.** O GE grava, junto das ondas,
    o módulo do fasor de cada fase com a unidade de corrente e a letra da fase
    no nome (`SRC 1 … Ia Mag`, `J1 Ia`). Pelo nome e pela unidade ela é uma
    fase A como outra qualquer, e no GE UR era ela que fechava trinca: 3I0,
    I1, I2, o classificador e a localização de falta saíam de magnitudes, sem
    nada na tela dizer isso (31/10/2026).

    Magnitude é o canal que **nunca fica negativo** e é **comparável à maior
    onda viva da mesma grandeza**, em primário (`FRACAO_DA_ONDA`). Cada
    ressalva abaixo existe por um caso real:

    - a entrada que ninguém cabeou também não passa por zero (o offset do
      conversor), e é trinca morta, que conta para a numeração. O que a separa
      é o tamanho perto da onda viva — e por isso a régua é a ONDA, e não o
      nominal declarado: o PL300 grava em primário com relação 1/1, e 4 A de
      offset passavam por magnitude contra um «nominal» de 1 A;
    - o neutro se compara com o neutro: a magnitude do residual é pequena
      perto das fases e do tamanho da onda do residual;
    - onda viva é senoide de 60 Hz de verdade (`presenca.FUNDAMENTAL_MINIMA`).
      Sem nenhuma, não há com o que comparar — o vão desenergizado inteiro — e
      nada é excluído: o nome decide, como sempre decidiu.

    O teste `alternados` de `analysis/presenca` não serve aqui: ele compara a
    fundamental com a média, e o degrau da falta numa magnitude tem 60 Hz de
    sobra — o `J1 Ia` do 850 passava.

    `None` quando não há amostra com que medir.
    """
    if registro.analog.size == 0 or not registro.analog_channels:
        return None
    # Import adiado pelo mesmo motivo de `canais_sem_sinal`.
    from osclab.analysis import presenca
    from osclab.dsp import fasor

    por_ciclo = fasor.ciclo_em_amostras(registro.base_rate_hz,
                                        registro.line_frequency)
    if por_ciclo < fasor.MINIMO_POR_CICLO:
        return None

    maior_onda: dict[str, float] = {}
    candidatas: list[tuple[int, str, float]] = []
    for canal in registro.analog_channels:
        grandeza = fases.grandeza_da_unidade(canal.unit)
        if not grandeza:
            continue
        # Neutro se compara com neutro: o `J1 Ig` (magnitude do residual,
        # 10 A) é pequeno perto das FASES e do tamanho do `J1 -IG`.
        if fases.da_canal(canal)[0] == "N":
            grandeza += "N"
        valores = registro.analog[canal.index]
        finitos = valores[np.isfinite(valores)]
        if finitos.size == 0:
            continue
        pico = float(np.max(np.abs(finitos))) * abs(_em_primario(canal))
        if float(finitos.min()) >= 0.0:
            candidatas.append((canal.index, grandeza, pico))
            continue
        if presenca.fundamental_relativa(valores, por_ciclo) >= presenca.FUNDAMENTAL_MINIMA:
            maior_onda[grandeza] = max(maior_onda.get(grandeza, 0.0), pico)

    magnitudes = {i for i, g, pico in candidatas
                  if maior_onda.get(g, 0.0) > 0.0
                  and pico >= FRACAO_DA_ONDA * maior_onda[g]}
    return frozenset(c.index for c in registro.analog_channels
                     if c.index not in magnitudes)


def _trincas_de(canais) -> list[dict]:
    """Junta `(canal, padrao, fase, chave, origem)` por chave e unidade, e
    devolve só os grupos que fecham uma trinca."""
    juntando: dict[tuple[str, str], dict] = {}
    for canal, padrao, fase, nome, origem in canais:
        unidade = canal.unit.strip()
        alvo = juntando.setdefault((nome, unidade), {
            "nome": nome, "grandeza": padrao[0], "unidade": unidade,
            "canais": {}, "origem": origem,
        })
        # Primeiro canal de cada fase vence. Dois `IA` no mesmo conjunto é
        # arquivo estranho, e escolher o segundo não seria mais certo que o
        # primeiro — só menos previsível.
        alvo["canais"].setdefault(fase, canal.index)

    # Fase OU delta, nunca os dois. Um grupo que tivesse `VA`, `VB`, `VC` e
    # `VAB` não é trinca dupla: é um nome que casou com canais de naturezas
    # diferentes, e misturá-los daria componentes somando volt de fase com
    # volt de linha. A base completa vence; com as duas completas vence a de
    # fase, que é a que produz mais coisa (tem resíduo e tem 3V0).
    saida = []
    for d in juntando.values():
        em_fase = all(f in d["canais"] for f in NECESSARIAS)
        em_delta = all(f in d["canais"] for f in NECESSARIAS_EM_DELTA)
        if not em_fase and not em_delta:
            continue
        d["base"] = FASE if em_fase else LINHA
        saida.append(d)
    return saida


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


def _escolhidos(canais: dict[str, int], escolha, base: str) -> dict[str, int]:
    """Os canais da trinca com a correção do usuário por cima.

    Só as três da conta se corrigem — `A`, `B`, `C` numa trinca de fase;
    `AB`, `BC`, `CA` numa em delta. O residual acompanha a trinca e não entra
    na conta; quem o pendura é `_pendurados`, pelo nome.
    """
    if not isinstance(escolha, dict):
        return canais
    saida = dict(canais)
    for fase in (NECESSARIAS_EM_DELTA if base == LINHA else NECESSARIAS):
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
        base = d.get("base", FASE)
        canais = _escolhidos(d["canais"], escolhas.get(d["nome"]), base)
        completos.append((
            min(d["canais"].values()),
            Conjunto(nome=d["nome"], grandeza=d["grandeza"],
                     unidade=d["unidade"], canais=canais, origem=d["origem"],
                     base=base,
                     sem_sinal=bool(set(canais.values()) <= mortos) if mortos
                     else False),
        ))
    return [c for _, c in sorted(completos, key=lambda x: x[0])]


def de_registro(registro: Record) -> tuple[Conjunto, ...]:
    """Os conjuntos trifásicos completos do registro, já com nome de grupo.

    Lembrado no registro (`base.lembrado`): é chamado várias vezes por pedido,
    e mede a presença de sinal em cada canal a cada vez. Muda quando mudam os
    canais (a correção de fase troca a tupla) ou as trincas corrigidas. O
    estimador entra porque a presença de sinal passa pela fundamental.
    """
    from osclab.dsp import fasor
    return lembrado(
        registro, "conjuntos",
        (repr(registro.trincas_escolhidas), fasor.estimador()),
        (registro.analog_channels, registro.analog, registro.time),
        lambda: tuple(rotular(_completos(registro))))
