"""O registro é a onda crua, ou o relé já filtrou antes de gravar?

## Por que a pergunta importa

Alguns IEDs gravam a onda como o conversor A/D a viu; outros gravam o que o
filtro interno deles produziu — só a componente de 60 Hz. As duas coisas se
parecem na tela e significam coisas diferentes:

* num registro **bruto**, filtrar é escolha do analista, e a tela oferece o
  botão para isso;
* num registro **já filtrado**, filtrar de novo não "limpa" nada — apenas
  acrescenta mais um ciclo de atraso, e a falta passa a aparecer dois ciclos
  depois de ter acontecido. Por isso o botão trava.

Travar sobre um palpite seria pior que não travar. Daí o cuidado abaixo.

## O que NÃO funciona, e custou uma medição para descobrir

A ideia natural — "registro filtrado não tem distorção" — não se sustenta como
foi escrita. Uma janela de um ciclo que pega uma MUDANÇA de amplitude não é uma
senoide, por mais filtrado que o sinal esteja: medindo um degrau de amplitude
num sinal de 60 Hz puro, a distorção aparente chega a **189 %** — o mesmo que
numa falta bruta. O transitório domina a medida e esconde o que se queria ver.

## O que funciona: medir só onde a amplitude está parada

Em trecho de regime — amplitude igual à de um ciclo atrás — a janela é
estacionária de verdade e a distorção medida é a distorção real do sinal. Aí a
separação é enorme:

    filtrado (só 60 Hz)                      0,0000 %
    filtrado + ruído de quantização 16 bits  0,0041 %
    bruto, com a sujeira de uma rede real    2,2204 %

Um fator de 500. A sujeira do último caso são os harmônicos que um registro
real sempre tem — 0,4 % de 2ª, 2,1 % de 3ª, 0,6 % de 5ª, medidos numa
oscilografia de distribuição de verdade. **Rede real nunca é limpa**, e é essa
sujeira que denuncia que ninguém filtrou.

## A inferência é forte num sentido só

*Ter* harmônicos prova que o sinal não passou por filtro — um filtro de 60 Hz
os teria removido. Isso torna o veredito `BRUTO` seguro.

*Não ter* harmônicos é mais fraco: pode ser filtro, ou pode ser um sinal
excepcionalmente limpo — injeção de mala de teste, por exemplo, que é senoide
sintetizada. Por isso a faixa entre os dois limiares devolve `DESCONHECIDO`, e
`FILTRADO` só sai com distorção no nível do próprio ruído de quantização.

Na dúvida, `DESCONHECIDO` e botão livre: o custo de não travar é o usuário
filtrar duas vezes e ver o atraso; o custo de travar errado é ele não conseguir
filtrar um registro que precisava ser filtrado.
"""

from __future__ import annotations

import numpy as np

from osclab.dsp import envoltoria, fasor
from osclab.formats.base import Filtering, FilteringSource, Record

#: Acima disto há harmônico de verdade, logo ninguém filtrou. Uma rede real de
#: distribuição fica bem acima: o registro que serviu de referência deu 2,2 %.
SUJEIRA_DA_REDE = 0.5

#: Abaixo disto não há harmônico nenhum — é o nível do ruído de quantização de
#: um conversor de 16 bits (medido: 0,0041 %).
RUIDO_DE_QUANTIZACAO = 0.05

#: Quanto a amplitude pode variar num ciclo para o trecho contar como parado.
VARIACAO_DE_REGIME = 0.01

#: Sem pelo menos isto de trecho parado não se opina. Dois ciclos é o mínimo
#: para a medida não ser um acidente de uma janela só.
CICLOS_PARADOS_MINIMOS = 2


def _distorcoes_em_regime(sinal: np.ndarray, por_ciclo: int) -> np.ndarray:
    """A distorção do canal, só nas amostras em que a amplitude está parada."""
    f = envoltoria.fundamental(sinal, por_ciclo)
    r = envoltoria.rms(sinal, por_ciclo)

    parado = np.zeros(f.shape, dtype=bool)
    if f.size > por_ciclo:
        anterior, agora = f[:-por_ciclo], f[por_ciclo:]
        parado[por_ciclo:] = np.abs(agora - anterior) <= VARIACAO_DE_REGIME * agora

    # A mesma guarda de `fasor.MINIMO_FUNDAMENTAL`: percentual DA fundamental só
    # significa algo quando há fundamental. Ela também exclui, de graça, os
    # canais mortos — os que só têm offset do conversor e nada de 60 Hz.
    vale = parado & np.isfinite(f) & np.isfinite(r) & (f > fasor.MINIMO_FUNDAMENTAL * r)
    if not vale.any():
        return np.empty(0)

    sobra = np.maximum(r[vale] ** 2 - f[vale] ** 2, 0.0)
    return 100.0 * np.sqrt(sobra) / f[vale]


def diagnosticar(registro: Record) -> tuple[Filtering, FilteringSource]:
    """O veredito e de onde ele veio.

    Nunca sobrepõe o que o arquivo declarou: se algum formato futuro trouxer o
    campo, ele manda. Dedução é o que se faz na falta de declaração.
    """
    if registro.filtering_source == FilteringSource.DECLARADO:
        return registro.filtering, registro.filtering_source

    if registro.analog.size == 0:
        return Filtering.DESCONHECIDO, FilteringSource.DEDUZIDO

    # Cada trecho tem a sua janela de um ciclo. Medir o registro inteiro com a
    # taxa do primeiro trecho acharia "distorção" onde só há taxa diferente.
    medidas = []
    por_ciclo = 0
    for trecho in registro.trechos:
        n = fasor.amostras_por_ciclo(trecho.taxa_hz, registro.line_frequency)
        if n < fasor.MINIMO_POR_CICLO:
            continue
        por_ciclo = max(por_ciclo, n)
        for canal in registro.analog[:, trecho.inicio:trecho.fim]:
            if (d := _distorcoes_em_regime(canal, n)).size:
                medidas.append(d)
    if por_ciclo == 0:
        return Filtering.DESCONHECIDO, FilteringSource.DEDUZIDO
    if not medidas:
        return Filtering.DESCONHECIDO, FilteringSource.DEDUZIDO

    juntas = np.concatenate(medidas)
    if juntas.size < CICLOS_PARADOS_MINIMOS * por_ciclo:
        return Filtering.DESCONHECIDO, FilteringSource.DEDUZIDO

    # Mediana, não média: um canal esquisito — saturado, mal escalado, ligado no
    # lugar errado — não pode decidir sozinho o que vale para o registro todo.
    tipica = float(np.median(juntas))

    if tipica > SUJEIRA_DA_REDE:
        return Filtering.BRUTO, FilteringSource.DEDUZIDO
    if tipica < RUIDO_DE_QUANTIZACAO:
        return Filtering.FILTRADO, FilteringSource.DEDUZIDO
    return Filtering.DESCONHECIDO, FilteringSource.DEDUZIDO


def aplicar(registro: Record) -> Record:
    """Escreve o veredito no registro e o devolve. Usado por `formats.registry`,
    para todo formato herdar a dedução sem nenhum leitor precisar saber dela."""
    registro.filtering, registro.filtering_source = diagnosticar(registro)
    return registro
