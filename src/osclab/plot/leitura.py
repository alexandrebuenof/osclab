"""O que os cursores leem: valor de cada canal num instante, e o tempo entre eles.

## Por que esta leitura não pode sair do desenho

O gráfico não mostra as amostras: mostra o **mínimo e o máximo de cada coluna de
pixel** (ver `plot/serie.py`). É o certo para desenhar — nenhum pico some — e é
justamente por isso que ler o valor do traço na tela daria o número errado:
metade dos pontos desenhados é um mínimo, metade é um máximo, e nenhum dos dois
é "o valor naquele instante".

Por isso o cursor pergunta ao servidor, que vai à amostra de verdade.

## O cursor cai em cima de uma amostra, sempre

Entre duas amostras não existe medida — existe interpolação, que é palpite. Num
registro a 16 amostras/ciclo, meia amostra é 11° de defasagem: um palpite desses
estraga fasor e localização de falta. Então o instante pedido é encostado na
amostra mais próxima, e é **essa** que a tela desenha e lê.

## Tempo: sempre nas duas unidades

Cada instante e o intervalo entre os cursores saem em **ms** e em **ciclos**, e
a tela escolhe qual mostrar. São as duas linguagens do ofício: o relatório e o
ajuste do relé falam em ms; a conversa fala em ciclos ("o disjuntor abriu em 2,5
ciclos").

**Não se calcula frequência a partir do intervalo.** `1/Δt` é tentador e engana
duas vezes: o usuário lê como "a frequência do sistema na falta", e a precisão
não sustenta a leitura. A 20 amostras/ciclo, uma amostra são 0,83 ms num período
de 16,67 ms — **±5 %, ou ±3 Hz**, que é justamente a diferença que se queria
enxergar. Medir frequência exige muitos ciclos e implementação própria.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.dsp import fasor
from osclab.formats import conjuntos, fases
from osclab.formats.base import Record
from osclab.plot import catalogo, conversao, sinais, unidades
from osclab.plot.conversao import LADOS


def indice(registro: Record, instante: float) -> int:
    """O índice da amostra mais próxima de `instante`."""
    t = registro.time
    if t.size == 0:
        return 0
    if not math.isfinite(instante):
        return 0
    i = int(np.clip(np.searchsorted(t, instante), 0, t.size - 1))
    if i > 0 and abs(float(t[i - 1]) - instante) <= abs(float(t[i]) - instante):
        i -= 1
    return i


def _num(x: float) -> float | None:
    """JSON não tem NaN nem infinito; canal saturado ou vazio vira `null`."""
    return float(x) if math.isfinite(x) else None


def casas(valor: float | None) -> int:
    """Quantas casas decimais mostrar num valor lido.

    Fixar uma casa para tudo erra dos dois lados: `6743,2 A` de corrente de
    falta primária tem uma casa que ninguém usa e que só rouba largura da
    coluna, enquanto `0,3 A` de corrente de fuga esconde justamente o dígito
    que interessa. A regra segue a ordem de grandeza, mirando **cinco dígitos
    significativos**.

    ## Por que cinco e não quatro

    O erro que o arredondamento introduz é meia casa decimal, e ele é pior no
    começo de cada década. Com quatro dígitos, `10,0` erra 0,5 % — a mesma ordem
    de grandeza do erro do próprio relé, e é desconfortável que a tela contribua
    tanto quanto o instrumento. Com cinco, `10,00` erra 0,05 %: uma ordem abaixo,
    ou seja, o display deixa de aparecer na conta.

    Custa um caractere de largura na tabelinha. Vale.
    """
    if valor is None or not math.isfinite(valor):
        return 1
    grandeza = abs(valor)
    if grandeza >= 1000:
        return 0                 # 6743 A — abaixo do ampère já não há medida
    if grandeza >= 100:
        return 1                 # 152,7 A
    if grandeza >= 10:
        return 2                 # 12,35 A
    if grandeza >= 1:
        return 3                 # 2,354 A
    return 4                     # 0,3123 A — corrente de fuga


def casas_do_tempo(resolucao: float) -> int:
    """Casas decimais para um tempo cuja resolução real é `resolucao`.

    A resolução de um instante não é escolha de gosto: é o **intervalo entre
    amostras**. Num registro a 1200 Hz, duas amostras vizinhas distam 0,833 ms —
    escrever `225,000 ms` promete microssegundo onde não há, rouba largura da
    coluna e ainda trunca na tela.

    A regra devolve a menor quantidade de casas em que duas amostras vizinhas
    ainda saem diferentes: 1 casa a 1200 Hz (225,0 · 225,8 · 226,7), 2 casas a
    20 kHz, e zero casa num registro muito lento.
    """
    if not math.isfinite(resolucao) or resolucao <= 0:
        return 3
    return int(min(max(math.ceil(-math.log10(resolucao)), 0), 6))


def _resolucoes(registro: Record) -> tuple[int, int]:
    """Quantas casas mostrar no tempo, em ms e em ciclos."""
    t = registro.time
    if t.size < 2:
        return (3, 2)
    passo = (float(t[-1]) - float(t[0])) / (t.size - 1)
    frequencia = float(registro.line_frequency or 0.0)
    return (
        casas_do_tempo(passo * 1000.0),
        casas_do_tempo(passo * frequencia) if frequencia > 0 else 2,
    )


def canal_de_referencia(registro: Record, pedido: int | None = None) -> int | None:
    """Qual canal é o zero dos ângulos.

    Ângulo absoluto não existe: todo fasor é relativo a alguma coisa. A escolha
    é por SIGNIFICADO, não por posição no arquivo — a tensão da fase A, e não
    "o primeiro canal", porque um relé que liste a tensão de barra antes da de
    linha, ou comece pela fase B, faria a referência mudar sem ninguém notar.

    Quedas, em ordem: tensão da fase A → corrente da fase A → primeiro canal.

    `pedido` é o índice que o usuário clicou na tabelinha; ele ganha de tudo.
    """
    canais = registro.analog_channels
    if not canais:
        return None
    if pedido is not None and 0 <= pedido < len(canais):
        return pedido

    def primeiro(unidades_aceitas: tuple[str, ...]) -> int | None:
        for canal in canais:
            fase, _ = fases.da_canal(canal)
            if fase == "A" and canal.unit.strip().upper() in unidades_aceitas:
                return canal.index
        return None

    return primeiro(("V", "KV")) or primeiro(("A", "KA")) or canais[0].index


def _em_uma_amostra(registro: Record, i: int, lado: str, escalas: dict,
                    por_ciclo: int, referencia: int | None,
                    filtro: bool = False,
                    medidas: dict[str, str] | None = None,
                    rotulos: dict[int, str] | None = None,
                    acrescentados: list | None = None) -> dict:
    """Tudo que a tela mostra de um cursor parado na amostra `i`.

    `escalas` vem de `unidades.por_unidade` — a MESMA que o desenho usou. Se
    cada um decidisse o prefixo por si, o gráfico mostraria `kA` e o cursor
    leria `A` no mesmo instante, e o usuário acreditaria no que estivesse
    olhando.
    """
    t = float(registro.time[i])
    disparo = _instante_do_disparo(registro)
    frequencia = float(registro.line_frequency or 0.0)

    # O ângulo da referência é calculado primeiro: todos os outros saem dele.
    angulo_zero = None
    if referencia is not None:
        f = fasor.no_instante(registro.analog[referencia], i, por_ciclo)
        angulo_zero = f.angulo if f else None

    valores = []
    for canal in registro.analog_channels:
        bruto = np.array([registro.analog[canal.index, i]], dtype=np.float64)
        convertido, lado_final, foi = conversao.converter(bruto, canal, lado)
        fase, _ = fases.da_canal(canal)
        divisor, mostrada = escalas.get(canal.unit.strip(), (1.0, canal.unit.strip()))
        valor = _num(convertido[0] / divisor)

        linha = {
            "nome": canal.name,
            # Qual grandeza a coluna mostra é decisão do botão do cabeçalho, e
            # ela vale para o gráfico e para a tabelinha ao mesmo tempo. Ler
            # "RMS" no gráfico e instantâneo na tabela seria a tela se
            # contradizendo no mesmo instante.
            # O nome do ARQUIVO acima; o nosso aqui. A tabelinha e a legenda
            # mostram os dois, para nunca haver dúvida de qual é qual.
            "padrao": fases.padrao(canal),
            "unidade": mostrada,
            "fase": fase,
            "lado": lado_final,
            "convertido": foi,
            "valor": valor,
            "casas": casas(valor),
        }
        linha.update(_fasor_do_canal(registro, canal, i, lado, divisor,
                                     por_ciclo, angulo_zero))

        # `valor` é o que a coluna mostra — e é dele que sai a diferença 2−1.
        # O instantâneo continua no pacote em campo próprio: ele é a impressão
        # digital da amostra, e é por ele que se confere, contra o SIGRA, se os
        # dois programas estão olhando o mesmo ponto do arquivo.
        linha["instantaneo"] = valor
        linha["casas_instantaneo"] = linha["casas"]

        # Cada gráfico escolhe a sua medida, então a grandeza sai da UNIDADE do
        # canal — é ela que diz a que gráfico ele pertence.
        grandeza = sinais.por_grupo(canal.unit.strip(), filtro, medidas)
        linha["grandeza"] = grandeza
        linha["sinal"] = sinais.nome(linha["padrao"], grandeza,
                                     (rotulos or {}).get(canal.index, ""))
        if grandeza == "fundamental":
            linha["valor"], linha["casas"] = linha["fundamental"], linha["casas_fasor"]
        elif grandeza == "rms":
            linha["valor"], linha["casas"] = linha["rms"], linha["casas_rms"]
        elif grandeza == "filtrado":
            linha["valor"], linha["casas"] = linha["filtrado"], linha["casas_filtrado"]

        valores.append(linha)

    desde_o_disparo = t - disparo
    return {
        "t": round(t, 9),
        "amostra": int(i),
        "ms": round(desde_o_disparo * 1000.0, 6),
        "ciclos": round(desde_o_disparo * frequencia, 4) if frequencia > 0 else None,
        "valores": valores,
        # Os sinais acrescentados à mão vêm à parte, casados pelo `id`. Os
        # canais continuam casando por POSIÇÃO, que é o que a tela já faz — e
        # misturar os dois numa lista só quebraria esse casamento.
        "extras": {x["id"]: x for x in _extras_em_uma_amostra(
            registro, i, lado, escalas, por_ciclo, angulo_zero,
            acrescentados)},
    }


def _extras_em_uma_amostra(registro: Record, i: int, lado: str, escalas: dict,
                           por_ciclo: int, angulo_zero: float | None,
                           acrescentados: list | None) -> list[dict]:
    """A leitura dos sinais que o usuário acrescentou aos gráficos.

    O sinal acrescentado carrega a PRÓPRIA grandeza: quem pôs `IA RMS` num
    gráfico que está em instantâneo quer ver o eficaz ali, e nem o botão do
    gráfico nem o do filtro mandam nele. É o que permite `Current IA` e
    `IA 60Hz RMS` na mesma tela — a comparação que mostra o atraso de um ciclo
    do filtro.
    """
    canais = {c.index: c for c in registro.analog_channels}
    saida = []
    for sinal in (acrescentados or []):
        divisor, mostrada = escalas.get(sinal.unidade, (1.0, sinal.unidade))
        # A CONTA do sinal, não a grandeza que o nomeia: num registro já
        # filtrado `IA 60Hz` é o próprio canal. Ver `plot/catalogo.py`.
        grandeza = sinal.conta
        linha = {"id": sinal.id, "nome": sinal.nome, "sinal": sinal.nome,
                 "unidade": mostrada, "familia": sinal.familia,
                 "grandeza": sinal.grandeza, "fase": ""}

        if sinal.id[0] in ("c", "v"):
            canal = canais.get(int(sinal.id[1:].split(":")[0]))
            if canal is None:
                continue
            bruto = np.array([registro.analog[canal.index, i]], dtype=np.float64)
            convertido, _, _ = conversao.converter(bruto, canal, lado)
            instantaneo = _num(convertido[0] / divisor)
            linha.update(_fasor_do_canal(registro, canal, i, lado, divisor,
                                         por_ciclo, angulo_zero))
            linha["instantaneo"] = instantaneo
            linha["casas_instantaneo"] = casas(instantaneo)
            linha["valor"], linha["casas"] = instantaneo, casas(instantaneo)
            if grandeza == "rms":
                linha["valor"], linha["casas"] = linha["rms"], linha["casas_rms"]
            elif grandeza == "fundamental":
                linha["valor"], linha["casas"] = (linha["fundamental"],
                                                  linha["casas_fasor"])
            elif grandeza == "filtrado":
                linha["valor"], linha["casas"] = (linha["filtrado"],
                                                  linha["casas_filtrado"])
            saida.append(linha)
            continue

        # Componente simétrica: módulo e ângulo saem da transformação de
        # Fortescue sobre os três fasores de fase. Não há instantâneo nem RMS
        # verdadeiro aqui — ver `plot/catalogo.py`.
        medido = catalogo.fasor_de_componente(registro, sinal, i, por_ciclo,
                                              lado, divisor)
        modulo, angulo = medido if medido else (None, None)
        linha.update({
            "valor": _num(modulo) if modulo is not None else None,
            "casas": casas(modulo),
            "fundamental": _num(modulo) if modulo is not None else None,
            "casas_fasor": casas(modulo),
            "angulo": (round(fasor.em_relacao_a(angulo, angulo_zero), 2)
                       if angulo is not None else None),
            "rms": None, "dc": None, "dc_valor": None, "distorcao": None,
            "filtrado": None, "instantaneo": None,
        })
        saida.append(linha)
    return saida


def _fasor_do_canal(registro: Record, canal, i: int, lado: str, divisor: float,
                    por_ciclo: int, angulo_zero: float | None) -> dict:
    """O fasor de um canal, já convertido para o lado e a unidade da tela.

    A conversão de TC/TP e o prefixo `k` são MULTIPLICAÇÕES POR ESCALAR, então
    aplicá-las depois da DFT dá o mesmo que antes — e custa uma operação em vez
    de uma janela inteira. O ângulo não se toca: escalar não gira fasor.
    """
    f = fasor.no_instante(registro.analog[canal.index], i, por_ciclo)
    if f is None:
        return {"fundamental": None, "angulo": None, "rms": None,
                "dc": None, "dc_valor": None, "distorcao": None, "filtrado": None,
                "casas_fasor": 1, "casas_rms": 1, "casas_dc": 1,
                "casas_filtrado": 1}

    razao = conversao.relacao(canal)
    lado_do_canal = "primario" if canal.is_primary else "secundario"
    fator = 1.0
    if lado != lado_do_canal and razao > 0:
        fator = razao if lado == "primario" else 1.0 / razao
    fator /= divisor

    fundamental = _num(f.fundamental * fator)
    rms = _num(f.rms * fator)

    # O valor da onda FILTRADA neste instante: a senoide de 60 Hz vale
    # `amplitude · cos(ângulo)`, com o ângulo ABSOLUTO — o referido ao cursor,
    # antes de qualquer referência de tela. Trocar a referência gira o fasor na
    # tabela e não pode mexer na onda desenhada.
    filtrado = _num(f.fundamental * math.sqrt(2.0) * math.cos(math.radians(f.angulo))
                    * fator)

    # O percentual pode não existir (ver `fasor.MINIMO_FUNDAMENTAL`); a DC em
    # unidade de engenharia existe sempre, porque média não tem denominador.
    # É ela que vai para o hover quando a coluna mostra traço.
    dc_valor = _num(f.dc * fator)
    # O `or 0.0` mata o zero negativo: `-0.0` chega no navegador como "-0,0", e
    # um sinal de menos onde não há grandeza faz o leitor parar para entender
    # uma coisa que não existe. `None` atravessa intocado.
    percentual = None if f.dc_percentual is None else round(f.dc_percentual, 1) or 0.0
    distorcao = None if f.distorcao is None else round(f.distorcao, 1) or 0.0

    return {
        "fundamental": fundamental,
        "angulo": round(fasor.em_relacao_a(f.angulo, angulo_zero), 2),
        "rms": rms,
        "filtrado": filtrado,
        "casas_filtrado": casas(filtrado),
        "dc": percentual,
        "dc_valor": dc_valor,
        "distorcao": distorcao,
        "casas_dc": casas(dc_valor),
        "casas_fasor": casas(fundamental),
        # O RMS verdadeiro pode cair noutra ordem de grandeza que a
        # fundamental — num transitório com DC forte a diferença passa de 40 %.
        # Reaproveitar `casas_fasor` esconderia justamente o dígito que mostra
        # essa diferença.
        "casas_rms": casas(rms),
    }


def _trecho_de(trechos, i: int):
    """O trecho de taxa constante que contém a amostra `i`, ou `None`."""
    for trecho in trechos:
        if trecho.inicio <= i < trecho.fim:
            return trecho
    return trechos[-1] if trechos else None


def _instante_do_disparo(registro: Record) -> float:
    if registro.trigger_time is None or registro.start_time is None:
        return 0.0
    return (registro.trigger_time - registro.start_time).total_seconds()


def entre(registro: Record, a: dict, b: dict) -> dict:
    """O que separa os dois cursores: tempo e diferença de cada canal.

    A subtração canal a canal sai daqui, e não do navegador, pela mesma razão
    que tudo mais: é número. Afundamento de tensão e salto de corrente entre
    dois instantes vão para o relatório; conta que vai para relatório tem teste.
    """
    segundos = b["t"] - a["t"]
    frequencia = float(registro.line_frequency or 0.0)

    diferencas = []
    for va, vb in zip(a["valores"], b["valores"], strict=True):
        if va["valor"] is None or vb["valor"] is None:
            diferencas.append({"nome": va["nome"], "unidade": va["unidade"],
                               "valor": None, "casas": 1})
            continue
        d = vb["valor"] - va["valor"]
        diferencas.append({"nome": va["nome"], "unidade": va["unidade"],
                           "valor": d, "casas": casas(d)})

    extras = {}
    for id_do_sinal, va in (a.get("extras") or {}).items():
        vb = (b.get("extras") or {}).get(id_do_sinal)
        if vb is None or va["valor"] is None or vb["valor"] is None:
            extras[id_do_sinal] = {"nome": va["nome"], "unidade": va["unidade"],
                                   "valor": None, "casas": 1}
            continue
        d = vb["valor"] - va["valor"]
        extras[id_do_sinal] = {"nome": va["nome"], "unidade": va["unidade"],
                               "valor": d, "casas": casas(d)}

    return {
        "segundos": round(segundos, 9),
        "ms": round(segundos * 1000.0, 6),
        "ciclos": round(segundos * frequencia, 4) if frequencia > 0 else None,
        "valores": diferencas,
        "extras": extras,
    }


def em(registro: Record, pedidos: list[tuple[float | None, int, float]],
       lado: str = "arquivo", refere: int | None = None,
       filtro: bool = False, medidas: dict[str, str] | None = None,
       extras: dict[str, list[str]] | None = None) -> dict:
    """A leitura dos cursores.

    Cada pedido é `(instante_em_segundos, passo_em_amostras, passo_em_ciclos)`.
    Os dois passos são o que as setas do teclado mandam. Andar **um ciclo** é
    pedido em ciclos, não em amostras: quantas amostras cabem num ciclo depende
    da taxa de amostragem e da frequência nominal do registro, e essa conta é
    daqui — o navegador não tem por que saber que um SEL-411L a 60 Hz anda 32
    amostras e um GE a 96 amostras/ciclo anda 96.
    """
    if lado not in LADOS:
        lado = "arquivo"
    if lado == "arquivo":
        lado = conversao.lado_natural(registro)
    filtro = sinais.aplicavel(filtro, registro.filtering)

    n = registro.n_samples
    escalas = unidades.por_unidade(registro, lado)
    rotulos = conjuntos.rotulos_por_canal(registro)
    trechos = registro.trechos
    referencia = canal_de_referencia(registro, refere)

    # Os sinais acrescentados a qualquer gráfico, achatados: a leitura não tem
    # grupos, e a tela casa cada um pelo `id`.
    por_id = catalogo.por_id(registro, lado)
    acrescentados = [por_id[i] for lista in (extras or {}).values()
                     for i in lista if i in por_id]

    cursores = []
    for instante, passo, ciclos in pedidos:
        if instante is None or n == 0:
            cursores.append(None)
            continue
        # Quantas amostras cabem num ciclo depende de ONDE o cursor está: num
        # registro de taxa variável, "andar um ciclo" são 96 amostras na falta
        # e 16 no pós-falta. A tecla é a mesma; a conta não.
        aqui = indice(registro, instante)
        trecho = _trecho_de(trechos, aqui)
        amostras = fasor.amostras_por_ciclo(trecho.taxa_hz if trecho else 0.0,
                                            registro.line_frequency)
        andar = int(passo)
        if ciclos and amostras > 0:
            andar += int(round(float(ciclos) * amostras))
        i = int(np.clip(aqui + andar, 0, n - 1))

        # Depois de andar, o cursor pode ter mudado de trecho.
        trecho = _trecho_de(trechos, i)
        amostras = fasor.amostras_por_ciclo(trecho.taxa_hz if trecho else 0.0,
                                            registro.line_frequency)
        # Uma janela que atravessa a fronteira não é um ciclo de coisa nenhuma.
        if trecho is not None and i - amostras + 1 < trecho.inicio:
            amostras = 0
        cursores.append(_em_uma_amostra(registro, i, lado, escalas,
                                        amostras, referencia, filtro,
                                        medidas, rotulos, acrescentados))

    primeiro = cursores[0] or (cursores[1] if len(cursores) > 1 else None)
    do_cursor = _trecho_de(trechos, primeiro["amostra"]) if primeiro else None
    por_ciclo = ((do_cursor.taxa_hz / registro.line_frequency)
                 if do_cursor and registro.line_frequency > 0 else 0.0)
    amostras = fasor.amostras_por_ciclo(do_cursor.taxa_hz if do_cursor else 0.0,
                                        registro.line_frequency)

    casas_ms, casas_ciclos = _resolucoes(registro)
    presentes = [c for c in cursores if c is not None]
    canais = registro.analog_channels
    return {
        "referencia": {
            "indice": referencia,
            "nome": canais[referencia].name if referencia is not None else None,
            "padrao": fases.padrao(canais[referencia])
            if referencia is not None else None,
        },
        "amostras_da_janela": amostras,
        "filtro": filtro,
        "cursores": cursores,
        "entre": entre(registro, presentes[0], presentes[1])
        if len(presentes) == 2 else None,
        "lado_pedido": lado,
        "amostras_por_ciclo": round(por_ciclo, 4),
        "casas_ms": casas_ms,
        "casas_ciclos": casas_ciclos,
    }
