"""Os painéis: o que a tela mostra, na ordem em que mostra.

## O que mudou, e por quê

Até aqui um gráfico NASCIA de uma unidade do arquivo: os canais em ampères
viravam o gráfico de correntes, os em volts o de tensões, e os digitais um
bloco no fim. O arranjo era consequência do arquivo, e não escolha de quem
analisa.

Só que analisar um evento é, em boa parte, **montar a vista**: pôr `IA` e
`IA 60Hz` lado a lado para ver o atraso do filtro; separar as tensões de barra
das de linha; deixar quatro digitais perto das correntes e afastar os outros
trinta. Nada disso cabe num arranjo que o arquivo dita.

Então o gráfico virou **painel**: uma lista ordenada, cada item com um tipo,
um nome e os sinais dele. O arranjo do arquivo continua existindo — é o
`padrao()`, com que toda oscilografia abre —, mas agora ele é só o ponto de
partida.

## O nome e a ordem são da TELA; os sinais são do servidor

O servidor precisa saber que sinais cada painel tem, porque é ele que calcula
as séries e a escala vertical. **Não** precisa saber como o painel se chama nem
em que posição está: isso é rótulo e arrumação, e mandar essas coisas para o
servidor só criaria um segundo lugar onde elas podem divergir.

A exceção é o painel que o próprio servidor criou, no `padrao()`: ele nasce com
um nome (`Correntes (A)`), porque a tela não teria de onde tirar um melhor.
Depois disso o nome é do usuário, e o servidor devolve o que recebeu.

## Painel digital é painel

Poderia ser um bloco à parte, como era. Mas aí "mudar a ordem dos gráficos"
não poderia pôr digitais entre duas trincas de corrente — que é exatamente o
que se quer quando se está olhando um religamento: a corrente, o trip, a
corrente de novo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from osclab.formats.base import Record
from osclab.plot import digitais as digitais_mod
from osclab.plot import serie, unidades

ANALOGICO = "analogico"
DIGITAL = "digital"
#: O diagrama de fasores de um instante. Ver `plot/fasorial.py`.
FASORIAL = "fasorial"
#: O espectro de harmônicos de um instante, em barras. Ver `plot/harmonicos.py`.
HARMONICOS = "harmonicos"
#: O triângulo de tensões de um instante. Ver `plot/triangulo.py`.
TRIANGULO = "triangulo"
#: O plano de impedância de um LAÇO, ao longo da janela. Ver
#: `plot/impedancia.py`. Ao contrário do fasorial e do triângulo, ele não é de
#: um instante: é uma TRAJETÓRIA, e é por isso que ele vem da janela e não da
#: leitura do cursor.
IMPEDANCIA = "impedancia"
#: O plano complexo: o CAMINHO do fasor de cada sinal, do começo do registro
#: até o cursor. Ver `plot/complexo.py`.
COMPLEXO = "complexo"
#: O plano alfa (87L): a razão `k` entre a corrente de dois terminais, ao
#: longo do registro. Ver `plot/alfa.py`.
ALFA = "alfa"
#: O diferencial de transformador (87T): Iop × Irt ao longo do registro, com
#: os ajustes lidos do arquivo ou digitados. Ver `plot/diferencial.py`.
DIFERENCIAL = "diferencial"
TIPOS = (ANALOGICO, DIGITAL, FASORIAL, HARMONICOS, TRIANGULO, IMPEDANCIA,
         COMPLEXO, ALFA, DIFERENCIAL)


@dataclass(frozen=True)
class Painel:
    """Um gráfico da tela: o tipo, o nome e o que está dentro."""

    id: str
    tipo: str
    nome: str
    #: Analógico: ids do catálogo (`c0:instantaneo`, `v0:rms`, `q0:0:rms`).
    #: Fasorial: o id da BASE de cada linha (`c0:instantaneo`, `q0:n:instantaneo`,
    #: `q0:0:rms`) — o fasor é da linha, não de uma conta dela.
    #: Digital: índices de canal digital, como texto.
    sinais: tuple[str, ...] = ()
    #: Só no analógico: `instantaneo` ou `rms`, e vale para os canais do IED
    #: que estão nele. Ver `plot/sinais.py`.
    medida: str = "instantaneo"
    #: Só no fasorial: o id do sinal que é o zero dos ângulos DELE, ou vazio
    #: para a regra automática (a tensão da fase A).
    #:
    #: Vem à parte de `sinais` porque ele **não é desenhado**: pode-se querer
    #: os ângulos das correntes a partir de `VAY` sem ter `VAY` no diagrama. E
    #: vem ao servidor, ao contrário do nome e da ordem, porque muda o que o
    #: servidor CALCULA — aquele sinal precisa entrar na leitura do cursor.
    referencia: str = ""
    #: Só no plano complexo: a referência vale o ângulo dela no PRIMEIRO
    #: ponto do registro (`True`) ou o dela em cada instante (`False`). Vem
    #: ao servidor porque muda o que ele calcula. Ver `plot/complexo.py`.
    referencia_fixa: bool = True
    #: Marca o painel cujo nome ainda é o que o servidor deu. Enquanto for
    #: verdade, o nome é recalculado a cada janela — é assim que ele acompanha
    #: a troca de primário para secundário. Renomear apaga a marca, e a partir
    #: daí o nome é do usuário e o servidor devolve o que recebeu.
    do_padrao: bool = False
    #: Só no triângulo: a chave da trinca de CORRENTE do vínculo de onde ele
    #: sai. Um campo, e não seis ids em `sinais`: o vínculo já diz quais seis
    #: canais são, e guardar os ids aqui faria uma correção de trinca no
    #: editor de grupos deixar este painel para trás. Ver `plot/triangulo.py`.
    vinculo: str = ""
    #: Só no triângulo: quais das três camadas estão acesas. Ver `CAMADAS`.
    camadas: tuple[str, ...] = ("linha", "fase", "corrente")
    #: Só na impedância: qual dos seis laços está no plano — `AN`…`CA`.
    #:
    #: Um campo, e não um id em `sinais`: um laço não é um sinal do catálogo,
    #: é uma CONTA entre dois canais de tensão e dois de corrente, e quais são
    #: esses canais sai do vínculo. Guardar os ids aqui faria uma correção de
    #: trinca deixar este painel para trás, que é o mesmo motivo do triângulo.
    laco: str = "AN"
    #: Só na impedância: o que o usuário digitou por cima do que o arquivo
    #: trouxe — `{"zl": {"modulo": …, "angulo": …},
    #: "zonas": {"Z1": {"alcance": …, "tempo": "inst."}}}`, sempre em ohms
    #: SECUNDÁRIOS, que é a base em que todo ajuste de distância é escrito.
    #:
    #: Vem ao servidor, e não fica só na tela, porque muda o que o servidor
    #: CALCULA: a zona desenhada, o veredito de entrada e o «% da LT» saem
    #: daqui. Ver `plot/impedancia.manuais_de`.
    manuais: dict = field(default_factory=dict)
    #: Só na impedância: a forma em vista — `mho`, `quad` ou `ambas`. Vazio é
    #: «a que o relé usa». Vai ao servidor porque muda o VEREDITO de entrada.
    caracteristica: str = ""
    #: Só no plano alfa: de que terminal se olha (`local` põe o local no
    #: denominador de `k`), as trincas de cada lado (`G1`, vazio = a regra
    #: automática) e os dois ajustes da característica. Vêm ao servidor
    #: porque mudam o `k` e a decisão que ele calcula. Ver `plot/alfa.py`.
    vista: str = "local"
    local: str = ""
    remoto: str = ""
    r87: float = 6.0
    ang87: float = 195.0
    #: Só no diferencial: o que o usuário digitou e os suspeitos que ele
    #: aceitou — `{"valores": {id: valor}, "aceitos": [id]}`. Vem ao servidor
    #: porque muda tudo o que ele calcula. Os lados 1 e 2 usam `local` e
    #: `remoto`, os mesmos campos do plano alfa. Ver `plot/diferencial.py`.
    ajustes87: dict = field(default_factory=dict)
    #: Só no plano alfa com um terminal em cada registro: acertar o ângulo
    #: entre os dois pela pré-falta. Ver `plot/alfa._refino`.
    refinar: bool = False
    avisos: list[str] = field(default_factory=list)


def _por_trinca(registro: Record) -> list[tuple[str, str, list[int]]] | None:
    """`(unidade, lado, canais)` de cada painel, ou `None` se não houver trinca.

    **Só corrente e tensão.** Um relé grava muito mais que isso — a tensão da
    bateria, a frequência, os ângulos que ele mesmo calculou, a corrente
    diferencial em pu — e cada unidade dessas virava um gráfico na abertura. O
    que se olha primeiro num evento é corrente e tensão; o resto é escolha de
    quem analisa, e está a um clique no «+ sinal».

    A separação não é por unidade e sim por TRINCA, e é isso que tira a tensão
    da bateria do caminho: ela é volt, mas não é uma das três fases de nada.
    """
    from osclab.formats import conjuntos

    achados = [c for c in conjuntos.de_registro(registro)
               if not c.sem_sinal and c.grandeza in ("I", "V")]
    if not achados:
        return None

    canais: list[list[int]] = [sorted(c.canais.values()) for c in achados]
    usados = {i for grupo in canais for i in grupo}
    for solto, alvo in conjuntos.residuais_soltos(registro).items():
        if 0 <= alvo < len(canais) and solto not in usados:
            canais[alvo].append(solto)

    # O LADO de um conjunto é a posição dele dentro da grandeza — a primeira
    # trinca de corrente e a primeira de tensão são do mesmo lado do
    # equipamento, e é isso que põe `IA/IB/IC` e `VA/VB/VC` da alta um em cima
    # do outro na abertura. É o campo `ordem`, e não o nome do grupo: com `G1`
    # contado entre TODOS os conjuntos, a corrente é `G1` e a tensão do mesmo
    # lado é `G2`, e comparar os dois nomes nunca casaria par nenhum.
    #
    # Corrente e tensão só se intercalam quando os lados de um CORRESPONDEM aos
    # do outro. Num relé com duas trincas de corrente e uma de tensão não há
    # par que fazer, e intercalar só quebraria a sequência das correntes: ali
    # vão todas as correntes e depois todas as tensões.
    lados = {g: {c.ordem for c in achados if c.grandeza == g} for g in ("I", "V")}
    emparelha = bool(lados["I"]) and lados["I"] == lados["V"]

    def chave(i: int) -> tuple:
        # Pelo NÚMERO, não como texto: com dez conjuntos, `G10` viria antes de
        # `G2` no alfabeto.
        lado = achados[i].ordem
        grandeza = 0 if achados[i].grandeza == "I" else 1
        return (lado, grandeza) if emparelha else (grandeza, lado)

    ordem = sorted(range(len(achados)), key=chave)
    return [(achados[i].unidade, achados[i].rotulo, sorted(canais[i]))
            for i in ordem]


def _por_unidade(registro: Record,
                 fora: frozenset[int]) -> list[tuple[str, str, list[int]]]:
    """O arranjo antigo: um painel por unidade do arquivo, sem lado nenhum.

    Só entra quando o programa não reconheceu trinca nenhuma. Aí ele não tem
    com que escolher, e uma tela vazia seria pior que uma tela cheia demais.
    """
    por_unidade: dict[str, list[int]] = {}
    for canal in registro.analog_channels:
        if canal.index in fora:
            continue
        por_unidade.setdefault(canal.unit.strip(), []).append(canal.index)
    return [(unidade, "", indices) for unidade, indices in por_unidade.items()]


def padrao(registro: Record, lado: str = "arquivo") -> list[Painel]:
    """O arranjo com que uma oscilografia abre.

    Um painel por trinca de corrente e de tensão, na ordem em que se conta um
    evento: **corrente e tensão da alta, depois corrente e tensão da baixa**.
    Quem abre um registro pela primeira vez não escolheu nada ainda, e a tela
    não pode esperar escolha para mostrar alguma coisa.

    Fecha com um painel dos digitais que mudaram.

    **A trinca de reserva fica de fora.** Um relé tem mais entradas do que a
    instalação usa, e o registro grava as vazias igual: sem isto, um SEL-451 de
    alimentador abre com seis correntes, três delas sendo uma reta em zero. Só
    sai do desenho — os canais continuam inteiros no catálogo, e o cabeçalho diz
    quantos ficaram de fora. Ver `formats/conjuntos.py` e `analysis/presenca.py`.
    """
    from osclab.formats import conjuntos

    escalas = unidades.por_unidade(registro, lado)
    grupos = _por_trinca(registro)
    if grupos is None:
        grupos = _por_unidade(registro, conjuntos.canais_sem_sinal(registro))

    saida: list[Painel] = []
    for i, (unidade, _do_lado, indices) in enumerate(grupos, start=1):
        if not indices:
            continue
        _, mostrada = escalas.get(unidade, (1.0, unidade))
        saida.append(Painel(
            id=f"p{i}",
            tipo=ANALOGICO,
            nome=serie.titulo_do_grupo(mostrada),
            sinais=tuple(f"c{k}:instantaneo" for k in indices),
            do_padrao=True,
        ))

    escolhidos = digitais_mod.escolhidos_por_padrao(registro)
    if registro.status_channels:
        saida.append(Painel(
            id=f"p{len(saida) + 1}",
            tipo=DIGITAL,
            nome="Digitais",
            sinais=tuple(str(k) for k in escolhidos),
            do_padrao=True,
        ))
    return saida


def de_json(cru) -> list[Painel] | None:
    """Lê o arranjo que a tela mandou, ou `None` se ela não mandou nenhum.

    Tudo que não casar é ignorado em silêncio, como em todo dado que vem da
    tela: o servidor não confia nela. Um painel sem tipo conhecido some; um id
    repetido fica com o primeiro.
    """
    if not isinstance(cru, list):
        return None

    saida: list[Painel] = []
    vistos: set[str] = set()
    for i, item in enumerate(cru, start=1):
        if not isinstance(item, dict):
            continue
        tipo = str(item.get("tipo", "")).strip()
        if tipo not in TIPOS:
            continue
        identidade = str(item.get("id", "") or f"p{i}")
        if identidade in vistos:
            continue
        vistos.add(identidade)

        brutos = item.get("sinais")
        sinais = tuple(str(x) for x in brutos) if isinstance(brutos, list) else ()
        medida = str(item.get("medida", "instantaneo"))
        referencia = str(item.get("referencia", "") or "")
        # As camadas do triângulo, peneiradas contra a lista conhecida: a tela
        # manda texto, e o servidor não confia nela. Lista vazia volta ao
        # padrão — um triângulo com nada aceso seria um quadro em branco sem
        # jeito de sair dele.
        cruas = item.get("camadas")
        camadas = tuple(x for x in ("linha", "fase", "corrente")
                        if isinstance(cruas, list) and x in cruas)
        # O laço, peneirado contra os seis que existem: a tela manda texto.
        # Um laço inventado faria a conta cair no `else` do módulo e devolver
        # um plano vazio sem dizer por quê.
        from osclab.plot.impedancia import LACOS, manuais_de
        laco = str(item.get("laco", "") or "AN").strip().upper()
        if laco not in LACOS:
            laco = "AN"
        # Peneirado no módulo que sabe o que é um alcance e o que é um
        # ângulo de linha — aqui só se sabe que veio da tela, e dado da tela
        # o servidor não aceita de olhos fechados.
        manuais = manuais_de(item.get("manuais"))
        # Os dois ajustes do plano alfa, presos a faixas que um 87L aceita:
        # um raio abaixo de 1 inverteria a coroa, e um ângulo fora de
        # 90°…270° não é setor de bloqueio de ninguém.
        r87 = _numero_entre(item.get("r87"), 6.0, 1.5, 20.0)
        from osclab.plot.diferencial import manuais_de as ajustes87_de
        ang87 = _numero_entre(item.get("ang87"), 195.0, 90.0, 270.0)
        saida.append(Painel(
            id=identidade,
            tipo=tipo,
            nome=str(item.get("nome", "") or ""),
            sinais=sinais,
            medida=medida if medida in ("instantaneo", "rms") else "instantaneo",
            referencia=referencia,
            # Sem o campo, fixa: é como o plano nasce.
            referencia_fixa=item.get("fixa") is not False,
            vinculo=str(item.get("vinculo", "") or ""),
            camadas=camadas or ("linha", "fase", "corrente"),
            laco=laco,
            manuais=manuais,
            caracteristica=(str(item.get("caracteristica") or "").lower()
                            if str(item.get("caracteristica") or "").lower()
                            in ("mho", "quad", "ambas") else ""),
            vista="remoto" if item.get("vista") == "remoto" else "local",
            local=str(item.get("local", "") or ""),
            remoto=str(item.get("remoto", "") or ""),
            r87=r87,
            ang87=ang87,
            ajustes87=ajustes87_de(item.get("ajustes87")),
            refinar=item.get("refinar") is True,
            # A tela devolve esta marca para os painéis que nunca foram
            # renomeados, e o servidor então reescreve o nome deles. É o que
            # faz `Correntes (A)` virar `Correntes (kA)` quando se troca para
            # primário: o nome vem da unidade, e a unidade acabou de mudar.
            do_padrao=bool(item.get("do_padrao")),
        ))
    return saida


def _numero_entre(cru, padrao: float, menor: float, maior: float) -> float:
    """Um número da tela, preso à faixa; o padrão quando não é número."""
    try:
        valor = float(cru)
    except (TypeError, ValueError):
        return padrao
    if valor != valor:                       # NaN
        return padrao
    return min(max(valor, menor), maior)


def indices_digitais(painel: Painel) -> list[int]:
    """Os índices de canal digital de um painel, ignorando o que não for."""
    saida = []
    for texto in painel.sinais:
        try:
            saida.append(int(texto))
        except (TypeError, ValueError):
            continue
    return saida
