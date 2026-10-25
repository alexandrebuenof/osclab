"""O plano complexo: o caminho que o fasor de cada sinal percorre.

## O que ele é

O diagrama fasorial responde «para onde apontava cada grandeza NESTE
instante». O plano complexo responde «por onde ela passou até chegar aqui»:
cada amostra vira um ponto no plano real × imaginário, e os pontos ligados
formam a trajetória. Um fasor que muda de ângulo sem mudar de módulo é uma
reta num gráfico de tempo — nada acontece na tela — e aqui é um arco.

A trajetória vai do começo do registro até o cursor, e quem a corta no cursor
é a tela: o servidor manda o caminho inteiro uma vez e a bolinha anda sem ida
e volta. Decidido com o Alexandre em 21/10/2026, em cima de três rodadas de
maquetes.

## A conta é a mesma do resto do programa

O fasor de cada amostra sai de `envoltoria.calcular_fasores`: a janela de um
ciclo de TEMPO que termina na amostra, trecho a trecho — a mesma da curva de
fundamental e da leitura do cursor. Fazer outra conta aqui faria o plano
discordar da tabelinha no mesmo instante.

## Por amostra, não por ciclo

A primeira ideia era um ponto por ciclo. Ela some justamente com o que o
gráfico existe para mostrar: a janela da DFT leva UM ciclo para sair do valor
de carga e chegar ao de falta, e com um ponto por ciclo sobra no máximo um
ponto no meio dessa travessia. Por amostra, a travessia sai com trinta e
tantos pontos — é o caminho que o filtro do relé de fato percorre.

Os CICLOS continuam disponíveis, como marca: `ciclos` diz onde cai cada ciclo
contado do início da perturbação, e a tela os desenha quando o usuário pede.

## A referência: qual sinal é o zero, e se ele é fixo ou anda

O fasor que a DFT devolve gira a 60 Hz junto com o tempo (a janela termina
num instante diferente a cada amostra). Para ficar parado num plano, ele é
desgirado pelo tempo ABSOLUTO da amostra — `e^{−j2πf·t}` —, e não pelo índice
dentro do trecho: num registro de taxa variável o índice recomeça em cada
trecho, e o fasor daria um salto que não existe na rede.

Desgirado, um fasor de 60 Hz exatos fica parado; um de 60,03 Hz gira devagar
— é o losango do SynchroWave. Daí as duas referências:

- **fixa**: tudo é girado do ângulo da referência no PRIMEIRO ponto em que ela
  existe. O desvio de frequência aparece como giro, e a própria referência
  tem trajetória.
- **dinâmica**: cada ponto é girado do ângulo da referência NO MESMO
  instante, como no diagrama fasorial e no SIGRA. O giro some, a referência
  fica cravada no eixo real, e o ângulo de cada sinal é o mesmo que a
  tabelinha do fasorial mostra.

**A referência dinâmica pode MORRER.** Uma corrente vai a zero quando o
disjuntor abre, e o ângulo de um zero é ruído. Dali em diante não há zero de
ângulo, e o ponto de TODOS os sinais vira `None` — a tela diz até quando a
referência existiu, em vez de desenhar ângulo de ruído com cara de medida.

## A janela que atravessa a falta

Na primeira janela depois do início da perturbação há pré-falta e falta
misturadas, e a contínua de uma falta assimétrica ainda vaza para a DFT de um
ciclo: o fasor dá voltas que são do FILTRO, não da rede. Esse trecho vai
marcado em `transicao`, e a tela o desenha tracejado. O início da
perturbação é palpite (`plot/imas.py`), e a tela diz isso no hover.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.dsp import envoltoria, fasor
from osclab.formats import conjuntos
from osclab.formats.base import Record
from osclab.plot import catalogo, conversao, fasorial, imas
from osclab.plot.paineis import COMPLEXO

#: Quantos pontos cada trajetória leva, no máximo. A 2 kHz são cinco segundos
#: de registro amostra a amostra; acima disso o caminho vai uma amostra a cada
#: `passo` — e a tela diz qual é o passo, porque o ponto do cursor passa a ser
#: o da amostra mantida mais perto, e não o da própria amostra.
MAXIMO_DE_PONTOS = 10000

#: Abaixo desta fração do maior módulo da REFERÊNCIA, ela não serve de zero:
#: o ângulo de um sinal que foi a zero é ruído do conversor. A mesma ordem do
#: piso da seta do fasorial.
PISO_DA_REFERENCIA = 0.002

#: Quantas marcas de ciclo, no máximo. Um registro de dez segundos tem 600
#: ciclos, e 600 marcas não marcam nada.
MAXIMO_DE_CICLOS = 400


def fasores_do_sinal(registro: Record, sinal: catalogo.Sinal, lado: str,
                     escalas: dict) -> np.ndarray | None:
    """O fasor complexo EFICAZ do sinal em cada amostra do registro.

    Na unidade e no lado que a tela mostra, como em `catalogo.serie`. `None`
    quando o sinal não tem fasor de 60 Hz (ver `fasorial.tem_fasor`) ou quando
    um canal dele sumiu do registro.

    O resultado ainda GIRA a 60 Hz com o tempo; quem desgira é `estacionario`.
    """
    if not fasorial.tem_fasor(sinal):
        return None
    n = registro.n_samples
    trechos = registro.trechos
    f = registro.line_frequency
    divisor, _ = escalas.get(sinal.unidade, (1.0, sinal.unidade))
    canais = {c.index: c for c in registro.analog_channels}

    def da_onda(onda: np.ndarray) -> np.ndarray:
        return envoltoria.calcular_fasores(onda, trechos, f) / math.sqrt(2.0)

    if sinal.familia == "conta":
        from osclab.plot import contas as contas_mod
        analise = sinal.analise or contas_mod.analisar(
            sinal.expressao, registro, escalas, sinal.contas_antes)
        onda = contas_mod.serie(registro, analise, lado, divisor)
        if onda is None or onda.size < n:
            return None
        return da_onda(onda[:n])

    if sinal.id[0] == "c":
        canal = canais.get(int(sinal.id[1:].split(":")[0]))
        if canal is None:
            return None
        convertido, _, _ = conversao.converter(registro.analog[canal.index],
                                               canal, lado)
        return da_onda(convertido / divisor)

    _, chave, _ = sinal.id.split(":")
    achados = conjuntos.de_registro(registro)
    posicao = int(sinal.id[1:].split(":")[0])
    if not 0 <= posicao < len(achados):
        return None
    conjunto = achados[posicao]
    if chave == catalogo.RESIDUAL:
        onda = catalogo.residuo(registro, conjunto, 0, n, lado, divisor)
        return None if onda is None else da_onda(onda)

    # Componente simétrica: as três fases viram fasor e Fortescue combina —
    # a MESMA transformação de `catalogo._serie_de_componente`, que sabe
    # tratar a trinca em delta.
    ordem, _, _ = catalogo.COMPONENTES[chave]
    tres = []
    for indice in conjunto.abc:
        canal = canais.get(indice)
        if canal is None:
            return None
        convertido, _, _ = conversao.converter(registro.analog[indice], canal,
                                               lado)
        tres.append(da_onda(convertido / divisor))
    return catalogo._fortescue(conjunto)(*tres)[ordem]


def estacionario(registro: Record, fasores_: np.ndarray) -> np.ndarray:
    """O fasor desgirado pelo tempo ABSOLUTO: parado se a rede está a 60 Hz.

    O fasor da DFT de janela deslizante tem a fase do instante em que a
    janela termina, então ele gira 360° por ciclo. Multiplicar por
    `e^{−j2πf(t−t₀)}` tira esse giro. Pelo tempo e não pelo índice: num
    registro de taxa variável o índice recomeça em cada trecho.

    Em cada trecho a DFT conta o giro a partir do PRIMEIRO índice do trecho,
    e é isso que se desfaz aqui: o índice local `k` vale `f·(t − t_trecho)`
    ciclos. Sem tratar trecho a trecho, a fronteira entre dois trechos daria
    um salto de ângulo que a rede nunca deu.
    """
    saida = np.array(fasores_, dtype=np.complex128, copy=True)
    t = registro.time
    f = float(registro.line_frequency)
    for trecho in registro.trechos:
        fatia = slice(trecho.inicio, trecho.fim)
        n = fasor.ciclo_em_amostras(trecho.taxa_hz, f)
        if n <= 0:
            continue
        k = np.arange(trecho.fim - trecho.inicio, dtype=np.float64)
        # Dois giros saem: o que a DFT pôs pelo índice local (`k/n` ciclos
        # desde o começo do trecho) e o tanto que o começo do trecho está
        # adiante do começo do registro. O que sobra é a fase contada de t₀,
        # a mesma em todos os trechos.
        local = np.exp(-2j * np.pi * (k % n) / n)
        atraso = np.exp(-2j * np.pi * f * (t[trecho.inicio] - t[0]))
        saida[fatia] = saida[fatia] * local * atraso
    return saida


def _referencia(registro: Record, painel, por_id: dict):
    """O id e o sinal da referência: a escolhida, ou a tensão da fase A."""
    from osclab.plot import leitura

    escolhida = (painel.referencia or "").strip()
    alvo = por_id.get(escolhida) if escolhida else None
    if alvo is not None and fasorial.tem_fasor(alvo):
        return escolhida, alvo
    indice = leitura.canal_de_referencia(registro)
    if indice is None:
        return None, None
    identidade = f"c{indice}:instantaneo"
    return identidade, por_id.get(identidade)


def girar(pontos: np.ndarray, ref: np.ndarray, fixa: bool) -> tuple[np.ndarray, int | None]:
    """Os pontos medidos a partir da referência, e onde a referência morreu.

    `fixa`: um só ângulo, o do primeiro ponto em que a referência existe.
    Dinâmica: o ângulo dela em cada instante — e onde ela não existe, o ponto
    também não. Devolve também o índice da primeira amostra em que a
    referência dinâmica deixou de existir DEPOIS de ter existido, para a tela
    dizer até quando ela valeu.
    """
    modulo = np.abs(ref)
    finitos = modulo[np.isfinite(modulo)]
    maior = float(finitos.max()) if finitos.size else 0.0
    viva = np.isfinite(modulo) & (modulo > maior * PISO_DA_REFERENCIA)
    if maior <= 0 or not viva.any():
        return np.full(pontos.shape, np.nan + 0j), None
    primeira = int(np.argmax(viva))
    if fixa:
        giro = np.conj(ref[primeira]) / modulo[primeira]
        return pontos * giro, None
    unitario = np.full(ref.shape, np.nan + 0j, dtype=np.complex128)
    unitario[viva] = np.conj(ref[viva]) / modulo[viva]
    depois = ~viva[primeira:]
    morreu = int(primeira + np.argmax(depois)) if depois.any() else None
    return pontos * unitario, morreu


def _arredondar(valores: np.ndarray) -> list:
    """Seis algarismos significativos, e `None` onde não há número."""
    return [None if not math.isfinite(v) else float(f"{v:.6g}")
            for v in valores.tolist()]


def montar(registro: Record, painel, por_id: dict, escalas: dict,
           lado: str) -> dict:
    """O pacote de um plano complexo: os sinais, a base do pu e as trajetórias."""
    # Nomes, cores, base do pu e pico do registro: tudo igual ao fasorial, e
    # por isso sai DELE. Duas implementações da base do pu é como dois
    # gráficos passariam a chamar de «1 pu» coisas diferentes.
    pacote = fasorial.montar(registro, painel, por_id, escalas, lado)
    pacote["tipo"] = COMPLEXO
    pacote["nome"] = painel.nome or "Plano complexo"

    fixa = bool(getattr(painel, "referencia_fixa", True))
    id_ref, sinal_ref = _referencia(registro, painel, por_id)
    n = registro.n_samples
    passo = max(1, math.ceil(n / MAXIMO_DE_PONTOS)) if n else 1
    indices = np.arange(0, n, passo, dtype=np.int64)

    ref = None
    if sinal_ref is not None:
        cru = fasores_do_sinal(registro, sinal_ref, lado, escalas)
        if cru is not None:
            ref = estacionario(registro, cru)

    morreu = None
    trajetorias = {}
    for item in pacote["sinais"]:
        alvo = por_id.get(item["id"])
        cru = fasores_do_sinal(registro, alvo, lado, escalas) if alvo else None
        if cru is None or ref is None:
            trajetorias[item["id"]] = {"re": [None] * indices.size,
                                       "im": [None] * indices.size}
            continue
        girados, morte = girar(estacionario(registro, cru), ref, fixa)
        morreu = morte if morreu is None else morreu
        escolhidos = girados[indices]
        trajetorias[item["id"]] = {"re": _arredondar(escolhidos.real),
                                   "im": _arredondar(escolhidos.imag)}

    tempo = registro.time
    inicio = imas.inicio_da_perturbacao(registro)
    transicao = None
    ciclos = []
    if inicio is not None and 0 <= inicio < n:
        # A janela de UM CICLO atravessa o início da perturbação enquanto ela
        # termina menos de um ciclo depois dele. Pelo TEMPO, para valer em
        # qualquer taxa.
        f = float(registro.line_frequency or 0.0)
        if f > 0:
            t0 = float(tempo[inicio])
            transicao = [t0, t0 + 1.0 / f]
            alvos = t0 + np.arange(1, MAXIMO_DE_CICLOS + 1) / f
            alvos = alvos[alvos <= float(tempo[-1])]
            amostras = np.clip(np.searchsorted(tempo, alvos), 0, n - 1)
            posicoes = np.clip(np.rint(amostras / passo).astype(np.int64), 0,
                               indices.size - 1)
            ciclos = [{"k": int(p), "ciclo": j + 1}
                      for j, p in enumerate(posicoes.tolist())]

    nome_ref = (sinal_ref.linha or sinal_ref.nome) if sinal_ref else None
    pacote.update({
        # `zero`, e não `referencia`: a tela guarda em `referencia` o id que
        # o usuário ESCOLHEU (texto), e os dois nomes iguais no mesmo painel
        # fariam um sobrescrever o outro.
        "zero": {
            "id": id_ref,
            "nome": nome_ref,
            "escolhida": bool((painel.referencia or "").strip()),
            "fixa": fixa,
            # Até quando a referência DINÂMICA existiu: depois disso não há
            # zero de ângulo e o rastro de todos para.
            "ate": (float(tempo[morreu]) if morreu is not None else None),
        },
        "passo": int(passo),
        "pontos": {"n": indices.tolist(),
                   "t": [round(float(x), 9) for x in tempo[indices]]},
        "trajetorias": trajetorias,
        "transicao": transicao,
        "ciclos": ciclos,
    })
    return pacote
