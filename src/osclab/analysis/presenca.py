"""Este canal está ligado em alguma coisa, ou está lendo o próprio ruído?

## Por que a pergunta existe

Um relé de distribuição tem mais entradas do que a instalação usa. O SEL-451 do
ALIMENTADOR 11 tem dois terminais de TC (`W` e `X`) e dois de TP (`Y` e `Z`), e
só um de cada par está cabeado. O registro grava os quatro do mesmo jeito: o
gráfico padrão abre com seis correntes, três delas sendo uma linha reta em zero,
e o usuário precisa apagar três traços antes de começar a analisar.

Pior que a poluição: enquanto o programa enxerga DUAS trincas de corrente, ele
acha que precisa distinguir uma da outra, e todo canal ganha sufixo — `IA W`,
`IB W`, `IC W`. Reconhecer a trinca morta faz o sufixo cair sozinho, e o
registro volta a se chamar `IA`, `IB`, `IC`. Ver `formats/conjuntos.py`.

## O que separa, medido

O teste que decide é **quanto do eficaz é 60 Hz**. Medido em dois relés reais,
com tudo o que eles gravaram:

| | fundamental / RMS |
|---|---|
| canais ligados (SEL-451 e SEL-487E, 24 canais) | 0,997 a 1,000 |
| entradas abertas (`I*U`, `I*W`, `I*X`, `I*X` do 451, `V*Z`) | 0,515 a 0,726 |

Não há nada no meio. Uma medição de verdade é uma senoide de 60 Hz; uma entrada
aberta é ruído do conversor, e a fundamental dele não chega a três quartos do
eficaz. O limiar fica em 0,90, longe dos dois lados.

## E a exceção que obriga a segunda condição

A `VDC1` é a tensão da bateria da subestação: 132 V contínuos, `fundamental /
RMS` de **0,001**, e é um canal perfeitamente real. Pelo teste de 60 Hz sozinho
ela morreria.

O que a salva é a amplitude: ela é o **maior canal em volts do registro**. Daí a
segunda condição — um canal só é candidato a morto se for pequeno perto do maior
da mesma unidade. Aqui a folga também é larga: no SEL-487E as três trincas de
reserva ficam entre 0,5 % e 1,5 % do maior, e a menor trinca VIVA do mesmo
arquivo está em 9,4 %. O limiar fica em 5 %.

Repare que a ordem dos dois testes importa pouco, mas a necessidade dos dois
importa muito: um sozinho erra num caso real de cada lado.

## A outra pergunta deste módulo: isto aqui é alternado?

Um relé grava contínua junto com alternada — a tensão da bateria da
subestação, a frequência medida, as magnitudes e os ângulos que ele mesmo
calculou. Oferecer `RMS` e `filtro de 60 Hz` para esses é oferecer uma conta
que não significa nada: a componente de 60 Hz de 132 V contínuos é zero, e o
"eficaz de um ciclo" de um número parado é o próprio número, apresentado como
se fosse uma medida de alternada.

A separação também é medida, e com a mesma folga:

| canal | \|média\| | fundamental |
|---|---|---|
| tensão da bateria (`VDC1`) | 132 V | 0,026 V |
| frequência (`FREQ`) | 60,0 Hz | 0,046 Hz |
| sequência positiva do relé (`V1M`) | 7,25 kV | 0,086 kV |
| corrente ou tensão de verdade | ~0 | tudo |

**Alternado é o que oscila em torno do zero**: a fundamental passa da média. Um
TC e um TP não passam contínua, então a média de um canal de verdade é
praticamente zero mesmo numa falta com assimetria. A maior razão
`\|média\|/fundamental` medida num canal alternado real foi 0,9; a menor num
contínuo, 84. Quase cem vezes de distância.

Falta um caso que a medição sozinha não separa: os **ângulos** que o relé
grava (`3V2A`, `LIGA`). Eles giram de −180° a +180°, o que tem cara de
fundamental. O que os denuncia é a unidade: o CEV não declara nenhuma para as
colunas `ANAnn`. Daí a segunda condição — **sem unidade declarada, não é
alternado**. Sem ela, `3V2A RMS` apareceria na lista.

## Canal sem unidade declarada nunca é escondido

As colunas `ANAnn` de um CEV não declaram unidade, e ali convivem tensão em kV,
corrente em ampère, ângulo em grau e frequência em hertz. Comparar `V1M` com
`L3I2M` porque os dois não têm unidade daria 0,12 % e esconderia a sequência
positiva de tensão do relé. Sem unidade não há com que comparar, e o programa
não esconde o que não consegue comparar.

## E a hipótese que este módulo NÃO consegue descartar

Um transformador energizado por um lado só tem a trinca do outro lado em zero
legitimamente, e este módulo vai chamá-la de morta. Não há como distinguir isso
de uma entrada aberta olhando um registro só.

Por isso esconder é **padrão de abertura, nunca exclusão**: os canais continuam
no catálogo, o cabeçalho diz quantos ficaram de fora, e um clique traz todos de
volta. Um zero que era informação nunca some sem avisar.
"""

from __future__ import annotations

import numpy as np

from osclab.dsp import envoltoria, fasor
from osclab.formats import fases
from osclab.formats.base import Record

#: Abaixo disto, em relação ao maior canal da MESMA unidade, o canal vira
#: candidato a morto — e aí quem decide é a fundamental. Serve para proteger a
#: tensão da bateria, que não tem 60 Hz nenhum e é o maior canal em volts.
#: Medido: reserva do SEL-487E entre 0,5 % e 1,5 %; menor trinca viva, 9,4 %.
FRACAO_DO_MAIOR = 0.05

#: Quanto do eficaz precisa ser fundamental para o canal contar como ligado.
#: Medido: ligado entre 0,997 e 1,000; entrada aberta entre 0,515 e 0,726.
FUNDAMENTAL_MINIMA = 0.90


def _fundamental_relativa(sinal: np.ndarray, por_ciclo: int) -> float:
    """O maior `fundamental / RMS` do canal ao longo do registro.

    O MAIOR, e não a mediana: basta o canal ter sido uma senoide limpa em algum
    trecho para estar ligado. Um canal vivo que passa por um transitório tem
    razão baixa no transitório, e isso não o mata.
    """
    f = envoltoria.fundamental(sinal, por_ciclo)
    r = envoltoria.rms(sinal, por_ciclo)
    vale = np.isfinite(f) & np.isfinite(r) & (r > 0)
    if not vale.any():
        return 0.0
    return float(np.max(f[vale] / r[vale]))


def alternados(registro: Record) -> frozenset[int]:
    """Os canais em que `RMS` e `filtro de 60 Hz` significam alguma coisa.

    Três condições, e cada uma existe por um caso real — ver o cabeçalho:

    1. **Tem unidade declarada.** As colunas `ANAnn` de um CEV não têm, e são
       magnitude e ângulo que o relé já calculou.
    2. **A fundamental não fica abaixo da média.** É o que separa a tensão da
       bateria (132 V de média contra 0,026 V de fundamental) de uma corrente
       de verdade, que oscila em torno do zero.
    3. **Havendo fundamental nenhuma, a unidade decide.** Canal zerado o
       registro inteiro empata as duas primeiras — um vão com o disjuntor
       aberto tem corrente zero, e zero não é contínua: é alternada que não
       está passando. Se a unidade é de corrente ou tensão, ele entra; se é
       grau ou pu, não.
    """
    if registro.analog.size == 0 or not registro.analog_channels:
        return frozenset()

    por_ciclo = fasor.ciclo_em_amostras(registro.base_rate_hz,
                                        registro.line_frequency)
    if por_ciclo < fasor.MINIMO_POR_CICLO:
        # Sem um ciclo que se meça não há como opinar, e negar o botão por
        # falta de resposta seria pior que oferecê-lo.
        return frozenset(c.index for c in registro.analog_channels)

    saida: set[int] = set()
    for canal in registro.analog_channels:
        if not canal.unit.strip():
            continue
        valores = registro.analog[canal.index]
        f = envoltoria.fundamental(valores, por_ciclo)
        maior = float(np.nanmax(f)) if np.isfinite(f).any() else 0.0
        media = float(np.nanmean(valores)) if valores.size else 0.0
        if not np.isfinite(media) or maior < abs(media):
            continue
        if maior > 0.0 or fases.grandeza_da_unidade(canal.unit) in ("I", "V"):
            saida.add(canal.index)
    return frozenset(saida)


def sem_sinal(registro: Record) -> frozenset[int]:
    """Os índices dos canais analógicos que não estão ligados em nada.

    **Canal por canal, e é só metade da resposta.** Quem decide o que some da
    tela é `formats/conjuntos.py`, que só esconde uma TRINCA INTEIRA — ver lá o
    porquê. Esta função é a medição; aquela é a decisão.

    Devolve um conjunto vazio quando não dá para opinar — registro sem amostra,
    taxa que não fecha um ciclo. Na dúvida, mostra tudo.
    """
    if registro.analog.size == 0 or not registro.analog_channels:
        return frozenset()

    por_ciclo = fasor.ciclo_em_amostras(registro.base_rate_hz,
                                        registro.line_frequency)
    if por_ciclo < fasor.MINIMO_POR_CICLO:
        return frozenset()

    picos: dict[int, float] = {}
    for canal in registro.analog_channels:
        valores = registro.analog[canal.index]
        pico = float(np.nanmax(np.abs(valores))) if valores.size else 0.0
        picos[canal.index] = 0.0 if not np.isfinite(pico) else pico

    maior_da_unidade: dict[str, float] = {}
    for canal in registro.analog_channels:
        unidade = canal.unit.strip().upper()
        if not unidade:
            continue
        maior_da_unidade[unidade] = max(maior_da_unidade.get(unidade, 0.0),
                                        picos[canal.index])

    mortos: set[int] = set()
    for canal in registro.analog_channels:
        unidade = canal.unit.strip().upper()
        maior = maior_da_unidade.get(unidade, 0.0)
        if not unidade or maior <= 0.0:
            # Sem unidade não há com que comparar; unidade cujo maior canal é
            # zero é um registro em que TUDO daquela grandeza está parado, e aí
            # o zero é a informação.
            continue
        if picos[canal.index] > FRACAO_DO_MAIOR * maior:
            continue
        if _fundamental_relativa(registro.analog[canal.index],
                                 por_ciclo) >= FUNDAMENTAL_MINIMA:
            continue
        mortos.add(canal.index)

    return frozenset(mortos)
