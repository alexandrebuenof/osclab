"""Que falta foi esta: quais fases, com terra ou sem.

## A pergunta, e por que ela não se responde com um número só

São onze respostas possíveis — `AG`, `BG`, `CG`, `AB`, `BC`, `CA`, `ABG`,
`BCG`, `CAG`, `ABC`, `ABCG` — e cada pista sozinha erra num caso real:

| pista | o que separa bem | onde erra sozinha |
|---|---|---|
| `3I0` | envolve a terra? | não diz **quais** fases |
| `I2` | envolve mais de uma fase? | some na falta trifásica, que é equilibrada |
| salto de **corrente** por fase | quais fases conduziram | falta resistiva mal levanta a corrente |
| afundamento de **tensão** por fase | quais fases afundaram | carga pesada afunda as três sem falta nenhuma |

Por isso este módulo cruza as quatro e **diz em que se apoiou**. Um veredito
sem os porquês é pior que nenhum: quem olhar não tem como saber se concorda.

## Tudo é medido em SUPERPOSTO, não em absoluto

A conta é sempre `falta − pré-falta`, fasor a fasor. É o que torna o critério
independente da carga: num alimentador carregado a 400 A, uma falta que leve a
fase A a 900 A é um salto de 500 A; noutro vazio, a mesma falta é um salto de
900 A. O absoluto muda, o superposto não — e é o superposto que o relé usa.

A mesma conta na tensão: `ΔV` é o afundamento, e ele é negativo nas fases em
falta e perto de zero nas sãs. Carga pesada afunda as três igualmente, e aí o
`ΔV` não elege fase nenhuma — que é exatamente o que se quer que aconteça.

## Onde a falta começa, e onde ela acaba

O detector é a diferença da amostra com a de **um ciclo atrás**: em regime
permanente ela é zero, e qualquer descontinuidade a levanta. É o mesmo
princípio do filtro superposto dos relés, e custa uma subtração por amostra.

O fim é a abertura do disjuntor: a corrente cai para a fuga. Sem achar o fim,
uma janela de «falta» posta depois da abertura mediria ruído — e o veredito
sairia de uma janela onde não há evento nenhum.

## O que este módulo NÃO faz

Não diz **onde** foi a falta (isso é `faultloc`), não decide se o relé agiu
certo (isso é o plano de impedância com os ajustes) e **não discorda do relé
em silêncio**: quando o arquivo traz a classificação dele, quem compara é a
tela, e as duas aparecem lado a lado.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

from osclab.dsp import fasor as fasor_mod
from osclab.dsp import simetricas
from osclab.formats.base import Record

FASES = ("A", "B", "C")

#: Quanto o detector de descontinuidade precisa subir acima do ruído de
#: regime para a falta ser declarada. Três vezes o maior resíduo dos ciclos
#: iniciais: abaixo disso é escorregamento de frequência, que levanta o
#: superposto sem haver evento nenhum.
VEZES_O_RUIDO = 3.0

#: E um piso absoluto, em fração do maior salto do registro. Sem ele, num
#: registro perfeitamente limpo o ruído é zero e qualquer poeira vira falta.
PISO_DO_SALTO = 0.15

#: Uma fase participa quando o salto dela chega a esta fração do maior salto.
#: Medido contra os casos sintéticos: numa falta bifásica as duas envolvidas
#: ficam acima de 0,85 uma da outra e a sã abaixo de 0,25. O meio está vazio,
#: e é por isso que um limiar único serve.
FRACAO_DA_FASE = 0.5

#: `3I0` acima desta fração do maior salto de fase conta como terra. Numa
#: falta fase-fase pura o `3I0` é teoricamente zero e na prática fica abaixo
#: de 0,1 por desequilíbrio de TC; numa fase-terra ele vale o próprio salto.
FRACAO_DA_TERRA = 0.25

#: O salto tem de valer pelo menos esta fração do pico das correntes. É o
#: que separa «não houve falta» de «houve uma falta pequena»: abaixo de 5 % do
#: pico não há evento que classificar, e o detector relativo sozinho acharia
#: um no ruído de ponto flutuante de um registro perfeitamente limpo.
FRACAO_MINIMA_DO_SALTO = 0.05

#: Abaixo disto a corrente é fuga: o disjuntor abriu.
FRACAO_DA_ABERTURA = 0.1


@dataclass(frozen=True)
class Veredito:
    """O que se concluiu, e com base em quê."""

    #: `AG`, `BC`, `ABCG`… ou `""` quando não há falta que classificar.
    tipo: str
    fases: tuple[str, ...]
    terra: bool
    #: Amostra em que a descontinuidade aparece, e em que a corrente colapsa.
    instante: int | None = None
    fim: int | None = None
    #: `alta` quando corrente e tensão concordam; `media` com uma só;
    #: `baixa` quando as duas existem e discordam.
    confianca: str = "baixa"
    #: As evidências, em português, na ordem em que pesaram.
    porques: tuple[str, ...] = ()
    #: O que NÃO fechou. Nunca fica escondido.
    discordancias: tuple[str, ...] = ()
    #: Numa falta EVOLUTIVA, o tipo do começo (`AB` de `AB → ABG`); vazio
    #: quando ela não mudou. O `tipo` é sempre o do FIM — o mais severo, o que
    #: o relé viu ao disparar e o laço que o plano de impedância abre.
    tipo_inicial: str = ""
    #: A amostra, aproximada em meio ciclo, em que ela virou o tipo final.
    evolucao: int | None = None

    @property
    def houve_falta(self) -> bool:
        return bool(self.tipo)

    @property
    def sigla(self) -> str:
        """`AB → ABG` na evolutiva, a sigla sozinha no resto."""
        if self.tipo_inicial and self.tipo_inicial != self.tipo:
            return f"{self.tipo_inicial} → {self.tipo}"
        return self.tipo

    #: O laço que o plano de impedância deve abrir — o da falta, e não `AN`
    #: por falta de escolha melhor. Numa bifásica é o laço entre as duas; numa
    #: monofásica, o de terra daquela fase.
    @property
    def laco(self) -> str:
        if len(self.fases) == 1:
            return f"{self.fases[0]}N"
        if len(self.fases) == 2:
            a, b = self.fases
            return f"{a}{b}" if f"{a}{b}" in ("AB", "BC", "CA") else f"{b}{a}"
        if len(self.fases) == 3:
            return "AB"
        return "AN"


# ---------------------------------------------------------------------------
# Onde a falta começa e onde acaba
# ---------------------------------------------------------------------------

def _taxa(registro: Record) -> float:
    """A taxa do primeiro trecho — e não `sample_rates[0]`, que vale 0 quando
    o `.cfg` declara `nrates = 0` (SEL-751, 311C, GE 850): ali a taxa sai do
    vetor de tempo, e é `Record.trechos` quem sabe fazer isso."""
    trechos = registro.trechos
    return trechos[0].taxa_hz if trechos else 0.0


def _superposto(amostras: np.ndarray, por_ciclo: int) -> np.ndarray:
    """`x[n] − x[n − 1 ciclo]`: zero em regime, degrau na descontinuidade."""
    d = np.zeros_like(amostras, dtype=np.float64)
    if por_ciclo <= 0 or amostras.size <= por_ciclo:
        return d
    d[por_ciclo:] = amostras[por_ciclo:] - amostras[:-por_ciclo]
    return d


def instante_da_falta(registro: Record, canais: dict[str, int]) -> int | None:
    """A primeira amostra em que as correntes deixam de ser o que eram.

    Devolve `None` quando nada salta — um registro de carga, uma manobra que
    não é falta, um trecho só de pré-falta.
    """
    taxa = _taxa(registro)
    por_ciclo = fasor_mod.amostras_por_ciclo(taxa, registro.line_frequency)
    if por_ciclo <= 0:
        return None

    soma = None
    for fase in FASES:
        idx = canais.get(fase)
        if idx is None:
            continue
        d = np.abs(_superposto(registro.analog[idx], por_ciclo))
        soma = d if soma is None else soma + d
    if soma is None or soma.size <= 2 * por_ciclo:
        return None

    # O ruído de REGIME sai dos dois primeiros ciclos depois que o detector
    # tem história: antes disso ele é zero por construção, e usar esse zero
    # como piso faria qualquer coisa virar falta.
    inicio = 2 * por_ciclo
    if soma.size <= inicio + por_ciclo:
        return None
    ruido = float(np.max(soma[por_ciclo:inicio])) if inicio > por_ciclo else 0.0
    maior = float(np.max(soma[inicio:]))
    if maior <= 0:
        return None

    # E a descontinuidade tem de ser grande perto da PRÓPRIA CORRENTE, não só
    # perto de si mesma. Num registro de carga limpa o detector é zero exato
    # (a senoide repete a cada ciclo), e o maior resíduo é o erro de ponto
    # flutuante — contra o qual qualquer limiar relativo dispara. Sem este
    # piso, um registro sem falta nenhuma ganhava uma.
    escala = 0.0
    for fase in FASES:
        idx = canais.get(fase)
        if idx is not None:
            escala = max(escala, float(np.max(np.abs(registro.analog[idx]))))
    if maior < escala * FRACAO_MINIMA_DO_SALTO:
        return None
    limiar = max(ruido * VEZES_O_RUIDO, maior * PISO_DO_SALTO)
    acima = np.nonzero(soma[inicio:] > limiar)[0]
    if acima.size == 0:
        return None
    return int(acima[0] + inicio)


def instante_da_abertura(registro: Record, canais: dict[str, int],
                         depois_de: int) -> int | None:
    """A amostra em que a corrente vira fuga — o disjuntor abriu."""
    taxa = _taxa(registro)
    por_ciclo = fasor_mod.amostras_por_ciclo(taxa, registro.line_frequency)
    if por_ciclo <= 0:
        return None
    indices = [canais[f] for f in FASES if f in canais]
    if not indices:
        return None
    bloco = np.abs(registro.analog[indices])
    envelope = bloco.max(axis=0)
    # Média móvel de um ciclo, para o zero natural da senoide não contar como
    # abertura: sem isto, toda passagem por zero seria um disjuntor abrindo.
    nucleo = np.ones(por_ciclo) / por_ciclo
    suave = np.convolve(envelope, nucleo, mode="same")
    janela = suave[depois_de:]
    if janela.size <= por_ciclo:
        return None
    pico = float(np.max(janela))
    if pico <= 0:
        return None
    # A busca começa UM CICLO depois do início: a média é centrada, e logo no
    # começo da falta ela ainda está no nível da carga — abaixo da fração do
    # pico, com cara de abertura. Num `.CEV` de 4 amostras por ciclo isso
    # punha a abertura no próprio início, o veredito saía vazio e o laço da
    # LDL era recusado (validação independente da LDL, 24/10/2026).
    abaixo = np.nonzero(janela[por_ciclo:] < pico * FRACAO_DA_ABERTURA)[0]
    if abaixo.size == 0:
        return None
    return int(abaixo[0] + por_ciclo + depois_de)


# ---------------------------------------------------------------------------
# Os fasores de antes e de durante
# ---------------------------------------------------------------------------

def _fasor_em(registro: Record, canal: int, n: int) -> complex | None:
    taxa = _taxa(registro)
    por_ciclo = fasor_mod.ciclo_em_amostras(taxa, registro.line_frequency)
    if por_ciclo < fasor_mod.MINIMO_POR_CICLO:
        return None
    pesos = fasor_mod.pesos_do_ciclo(por_ciclo)
    inicio = int(n) - pesos.size + 1
    if inicio < 0 or int(n) + 1 > registro.analog.shape[1]:
        return None
    f = fasor_mod.de_janela(registro.analog[canal, inicio:int(n) + 1],
                            por_ciclo, pesos)
    if f is None:
        return None
    return f.fundamental * complex(math.cos(math.radians(f.angulo)),
                                   math.sin(math.radians(f.angulo)))


def _trinca_em(registro: Record, canais: dict[str, int],
               n: int) -> tuple[complex, complex, complex] | None:
    saida = []
    for fase in FASES:
        idx = canais.get(fase)
        if idx is None:
            return None
        f = _fasor_em(registro, idx, n)
        if f is None:
            return None
        saida.append(f)
    return tuple(saida)      # type: ignore[return-value]


def _girar(registro: Record, trinca: tuple[complex, ...], n_de: int,
           n_para: int) -> tuple[complex, ...]:
    """A trinca medida em `n_de`, levada ao instante `n_para`.

    O ângulo do fasor é referido ao instante da janela: o MESMO regime medido
    um pouco depois sai girado de ω·Δt. O superposto `durante − antes` só tem
    sentido com os dois no mesmo instante — sem isto, o `antes` e o `durante`
    ficavam a dois ciclos e UMA amostra (18° a 20 por ciclo), e a carga girada
    aparecia como «salto» na fase sã (P437, 22/10/2026).
    """
    if registro.time.size <= max(n_de, n_para):
        return trinca
    dt = float(registro.time[n_para] - registro.time[n_de])
    giro = complex(math.cos(2 * math.pi * registro.line_frequency * dt),
                   math.sin(2 * math.pi * registro.line_frequency * dt))
    return tuple(x * giro for x in trinca)


def _janelas(registro: Record, inicio: int, fim: int | None) -> tuple[int, int] | None:
    """`(n_pre, n_falta)`: onde medir antes e onde medir durante.

    O `antes` fica um ciclo ANTES da descontinuidade: a janela do fasor olha
    um ciclo para trás, e uma janela que encoste no degrau mede metade de cada
    regime. O `durante` fica dois ciclos DEPOIS, pelo mesmo motivo do outro
    lado, e antes da abertura.
    """
    taxa = _taxa(registro)
    por_ciclo = fasor_mod.amostras_por_ciclo(taxa, registro.line_frequency)
    if por_ciclo <= 0:
        return None
    pre = int(inicio) - 1
    falta = int(inicio) + 2 * por_ciclo
    limite = (int(fim) - por_ciclo) if fim is not None else registro.analog.shape[1] - 1
    falta = min(falta, limite)
    if pre < por_ciclo or falta <= inicio:
        return None
    return pre, falta


# ---------------------------------------------------------------------------
# O veredito
# ---------------------------------------------------------------------------

def _saltos(antes: tuple[complex, ...], durante: tuple[complex, ...]) -> list[float]:
    """`|ΔI|` de cada fase: o módulo do fasor superposto."""
    return [abs(durante[k] - antes[k]) for k in range(3)]


#: A ordem em que o ofício escreve cada par: `CA`, e não `AC` — é como o relé
#: grava, como o laço do plano de impedância se chama e como se fala.
_PARES = {frozenset("AB"): "AB", frozenset("BC"): "BC", frozenset("CA"): "CA"}


def _nome(fases: tuple[str, ...], terra: bool) -> str:
    letras = _PARES.get(frozenset(fases), "".join(fases))
    return letras + ("G" if terra else "")


#: Acima disto de I2/I1 durante a falta, ela NÃO é trifásica. Uma falta ABC é
#: equilibrada e tem I2 perto de zero; uma bifásica, perto de 100 %. O meio do
#: caminho separa as duas com folga.
DESEQUILIBRIO_DA_BIFASICA = 0.5


def _par_oposto(antes: tuple[complex, ...], durante: tuple[complex, ...]) -> tuple[str, ...]:
    """O par cujas correntes superpostas mais se OPÕEM: `|ΔIx − ΔIy|` máximo.

    Numa falta bifásica a corrente de falta entra por uma fase e volta pela
    outra, então `ΔIB ≈ −ΔIC` e a diferença dobra; a terceira fase só carrega
    a variação da carga.
    """
    delta = [durante[k] - antes[k] for k in range(3)]
    pares = [("A", "B"), ("B", "C"), ("C", "A")]
    indice = {"A": 0, "B": 1, "C": 2}
    return max(pares, key=lambda p: abs(delta[indice[p[0]]] - delta[indice[p[1]]]))


def _desequilibrio(durante: tuple[complex, ...]) -> float | None:
    _, i1, i2 = simetricas.de_fasores(*durante)
    return abs(i2) / abs(i1) if abs(i1) > 0 else None


def _sem_trifasica_desequilibrada(fases, terra, antes, durante):
    """Três fases sem terra e I2/I1 alto não é ABC: é a bifásica do par que se
    opõe. Foi o caso de uma BC fraca (3 A sobre 1 A de carga): a variação da
    carga na fase sã passou do limiar e o selo dizia ABC (P437, 22/10/2026)."""
    if len(fases) != 3 or terra:
        return fases
    d = _desequilibrio(durante)
    if d is not None and d > DESEQUILIBRIO_DA_BIFASICA:
        return _par_oposto(antes, durante)
    return fases


def _fases_e_terra(antes: tuple[complex, ...],
                   durante: tuple[complex, ...]) -> tuple[tuple[str, ...], bool] | None:
    """As fases e a terra de UMA janela, pelo mesmo critério do veredito."""
    saltos = _saltos(antes, durante)
    maior = max(saltos)
    if maior <= 0:
        return None
    fases = tuple(FASES[k] for k in range(3) if saltos[k] >= maior * FRACAO_DA_FASE)
    zero_antes, _, _ = simetricas.de_fasores(*antes)
    zero_durante, _, _ = simetricas.de_fasores(*durante)
    terra = abs(zero_durante - zero_antes) >= maior * FRACAO_DA_TERRA
    return _sem_trifasica_desequilibrada(fases, terra, antes, durante), terra


def _evolucao(registro: Record, corrente: dict[str, int],
              antes: tuple[complex, ...], n_falta: int, fim: int | None,
              fases: tuple[str, ...], terra: bool,
              n_pre: int | None = None) -> tuple[str, int] | None:
    """`(tipo_final, amostra)` se a falta CRESCEU até a abertura; senão None.

    A segunda janela é a última inteira antes de o disjuntor abrir. Só conta
    como evolutiva a falta que GANHA fase ou terra (`AB → ABG`, `AG → ABG`):
    o que perde fase no fim é TC saturando ou o arco apagando numa das
    fases, não uma falta nova — e chamar isso de evolutiva poria um tipo
    errado no selo.
    """
    taxa = _taxa(registro)
    por_ciclo = fasor_mod.amostras_por_ciclo(taxa, registro.line_frequency)
    if por_ciclo <= 0:
        return None
    ultimo = (int(fim) - por_ciclo) if fim is not None else registro.analog.shape[1] - 1
    if ultimo < n_falta + por_ciclo:
        return None
    def no_mesmo(n: int) -> tuple[complex, ...]:
        return _girar(registro, antes, n_pre, n) if n_pre is not None else antes

    # A ÚLTIMA janela ainda EM FALTA. Sem abertura detectada, `ultimo` era o
    # fim do registro — e ali a falta já tinha sido eliminada por outro
    # disjuntor: o «salto» da carga que voltou, comparado com a pré-falta,
    # virava fase ou terra nova, e uma BC reversa saía «BC → BCG» (LT COXIPO,
    # 22/10/2026). Só conta a janela cujo maior salto ainda é metade do
    # primeiro.
    primeira = _trinca_em(registro, corrente, n_falta)
    if primeira is None:
        return None
    maior_inicial = max(_saltos(no_mesmo(n_falta), primeira))
    passo = max(1, por_ciclo // 2)
    em_falta = n_falta
    for n in range(n_falta + passo, ultimo + 1, passo):
        trinca = _trinca_em(registro, corrente, n)
        if trinca is None or max(_saltos(no_mesmo(n), trinca)) < 0.5 * maior_inicial:
            break
        em_falta = n
    ultimo = em_falta
    if ultimo < n_falta + por_ciclo:
        return None
    durante = _trinca_em(registro, corrente, ultimo)
    medido = _fases_e_terra(no_mesmo(ultimo), durante) if durante else None
    if medido is None:
        return None
    fases_fim, terra_fim = medido
    cresceu = (set(fases) <= set(fases_fim) and terra <= terra_fim
               and (set(fases) != set(fases_fim) or terra != terra_fim))
    if not cresceu:
        return None
    final = _nome(fases_fim, terra_fim)
    # ONDE ela virou: a primeira janela, de meio em meio ciclo, que já dá o
    # tipo final. São dezenas de passos por registro, não um por amostra. A
    # janela olha um ciclo para trás, e o limiar de fase é metade do maior
    # salto: o tipo novo aparece com a janela meio cheia dele.
    for n in range(n_falta + passo, ultimo + 1, passo):
        trinca = _trinca_em(registro, corrente, n)
        m = _fases_e_terra(no_mesmo(n), trinca) if trinca else None
        if m and _nome(*m) == final:
            return final, max(n_falta, n - por_ciclo // 2)
    return final, ultimo


def classificar(registro: Record, corrente: dict[str, int],
                tensao: dict[str, int] | None = None) -> Veredito:
    """Que falta é esta. Nunca levanta: sem evidência, devolve veredito vazio.

    `corrente` e `tensao` são `{"A": idx, "B": idx, "C": idx}` — as trincas
    que `formats/conjuntos.py` já identificou.
    """
    inicio = instante_da_falta(registro, corrente)
    if inicio is None:
        return Veredito(tipo="", fases=(), terra=False,
                        porques=("Nenhuma descontinuidade nas correntes: "
                                 "este registro não tem falta para classificar.",))

    fim = instante_da_abertura(registro, corrente, inicio)
    quando = _janelas(registro, inicio, fim)
    if quando is None:
        return Veredito(tipo="", fases=(), terra=False, instante=inicio, fim=fim,
                        porques=("A descontinuidade está perto demais da borda "
                                 "do registro para medir antes e depois dela.",))
    n_pre, n_falta = quando

    antes_cru = _trinca_em(registro, corrente, n_pre)
    durante_i = _trinca_em(registro, corrente, n_falta)
    antes_i = (None if antes_cru is None
               else _girar(registro, antes_cru, n_pre, n_falta))
    if antes_i is None or durante_i is None:
        return Veredito(tipo="", fases=(), terra=False, instante=inicio, fim=fim,
                        porques=("Não consegui medir os fasores das três "
                                 "correntes nas duas janelas.",))

    saltos = _saltos(antes_i, durante_i)
    maior = max(saltos)
    if maior <= 0:
        return Veredito(tipo="", fases=(), terra=False, instante=inicio, fim=fim,
                        porques=("As correntes não mudaram de valor.",))

    porques: list[str] = []
    discordancias: list[str] = []

    por_corrente = tuple(FASES[k] for k in range(3)
                         if saltos[k] >= maior * FRACAO_DA_FASE)
    porques.append(
        "Salto de corrente: "
        + " · ".join(f"Δ{FASES[k]} {saltos[k] / maior * 100:.0f} %"
                     for k in range(3))
        + f" → {'/'.join(por_corrente)}"
    )

    # A TERRA, pelo 3I0 superposto. `3I0` absoluto já existe na carga de um
    # alimentador desequilibrado; o que acusa terra é o que ele GANHOU.
    # `de_fasores` devolve `(3·zero, positiva, negativa)` — o zero JÁ vem
    # multiplicado por três, que é a soma que circula pelo neutro.
    tres_i0_antes, _, _ = simetricas.de_fasores(*antes_i)
    tres_i0_durante, _, _ = simetricas.de_fasores(*durante_i)
    tres_i0 = abs(tres_i0_durante - tres_i0_antes)
    terra = tres_i0 >= maior * FRACAO_DA_TERRA
    porques.append(
        f"3I0 superposto {tres_i0 / maior * 100:.0f} % do maior salto → "
        + ("envolve terra" if terra else "sem terra")
    )

    # A SEGUNDA OPINIÃO: o afundamento de tensão. Ela não elege sozinha — só
    # confirma ou levanta a mão.
    por_tensao: tuple[str, ...] = ()
    if tensao:
        antes_v = _trinca_em(registro, tensao, n_pre)
        durante_v = _trinca_em(registro, tensao, n_falta)
        if antes_v and durante_v:
            quedas = [abs(antes_v[k]) - abs(durante_v[k]) for k in range(3)]
            maior_queda = max(quedas)
            base = max(abs(x) for x in antes_v) or 1.0
            if maior_queda > base * 0.02:
                por_tensao = tuple(FASES[k] for k in range(3)
                                   if quedas[k] >= maior_queda * FRACAO_DA_FASE)
                porques.append(
                    "Afundamento de tensão: "
                    + " · ".join(f"Δ{FASES[k]} {quedas[k] / base * 100:+.0f} %"
                                 for k in range(3))
                    + f" → {'/'.join(por_tensao)}"
                )
            else:
                porques.append("A tensão quase não afundou: falta de alta "
                               "impedância, ou longe daqui.")

    fases = por_corrente
    # TRÊS FASES COM I2 ALTO não é trifásica: é a bifásica do par que se opõe.
    reduzidas = _sem_trifasica_desequilibrada(fases, terra, antes_i, durante_i)
    if reduzidas != fases:
        d = _desequilibrio(durante_i) or 0.0
        porques.append(
            f"I2/I1 durante a falta: {d * 100:.0f} % — trifásica é equilibrada; "
            f"o par que se opõe é {_nome(reduzidas, False)}, e a terceira fase "
            f"só variou com a carga")
        fases = reduzidas
        por_corrente = reduzidas
    if por_tensao and set(por_tensao) != set(por_corrente):
        discordancias.append(
            f"A corrente aponta {'/'.join(por_corrente)} e a tensão "
            f"{'/'.join(por_tensao)}. Mantive o que a corrente diz — é ela que "
            f"a falta obriga a mudar; a tensão também cai por carga."
        )
        confianca = "baixa"
    elif por_tensao:
        confianca = "alta"
    else:
        confianca = "media"
        if tensao is None:
            discordancias.append("Sem trinca de tensão neste registro: o "
                                 "veredito saiu só da corrente.")

    # Trifásica: `I2` some quando as três são iguais, e é esse sumiço que
    # confirma a simetria. Com I2 ainda presente, as três subiram mas não
    # igualmente — vale dizer, porque muda o laço que se vai olhar.
    if len(fases) == 3:
        _, i1_durante, i2_durante = simetricas.de_fasores(*durante_i)
        if abs(i1_durante) > 0:
            desequilibrio = abs(i2_durante) / abs(i1_durante)
            porques.append(f"I2/I1 durante a falta: {desequilibrio * 100:.0f} %")
            if desequilibrio > 0.1:
                discordancias.append(
                    "As três fases subiram, mas I2/I1 passa de 10 %: a falta "
                    "não é simétrica. Pode ser uma evolutiva — olhe os ciclos "
                    "um a um antes de chamar de trifásica."
                )

    # A EVOLUTIVA: a janela de cima é a do começo. Uma falta que começa AB e
    # pega a terra três ciclos depois só se vê numa segunda janela, no fim.
    tipo = _nome(fases, terra)
    tipo_inicial = ""
    evolucao = None
    evoluiu = _evolucao(registro, corrente, antes_cru, n_falta, fim, fases, terra,
                        n_pre)
    if evoluiu is not None:
        tipo_inicial = tipo
        tipo, evolucao = evoluiu
        taxa = _taxa(registro)
        depois = (evolucao - inicio) / taxa * 1000 if taxa > 0 else 0.0
        porques.append(f"Evolutiva: começou {tipo_inicial} e virou {tipo} "
                       f"≈ {depois:.0f} ms depois")
        fases = tuple(f for f in FASES if f in tipo)
        terra = tipo.endswith("G")

    return Veredito(
        tipo=tipo,
        fases=fases,
        terra=terra,
        instante=inicio,
        fim=fim,
        confianca=confianca,
        porques=tuple(porques),
        discordancias=tuple(discordancias),
        tipo_inicial=tipo_inicial,
        evolucao=evolucao,
    )


# ---------------------------------------------------------------------------
# Comparar com o que o relé gravou
# ---------------------------------------------------------------------------

def _so_as_letras(sigla: str) -> tuple[str, bool]:
    """`AG T` → `("A", True)`; `AB T` → `("AB", False)`; `3PH` → `("ABC", False)`.

    **O «T» solto da SEL é TRIP, não terra.** `AB T` é «falta AB, e o relé
    disparou»; a terra vem DENTRO da sigla, como `G` (`ABG T`). Conferido nos
    arquivos do parque em 21/10/2026: no alimentador de 21/09 o relé gravou
    `AB T` com TRIP e 3PT acesos e 3I0 superposto de 0 %; no de 17/09 gravou
    `CA`, sem T — e ali o TRIP não mudou. A primeira versão lia o T como terra,
    e todo «AB» nosso aparecia como conflito com o «AB T» do relé.

    Por isso só a PRIMEIRA palavra é a sigla: o que vem depois do espaço é
    sufixo de evento, não fase.
    """
    bruto = (sigla or "").upper().strip()
    primeira = bruto.split()[0] if bruto else ""
    if "3P" in primeira or "ABC" in primeira:
        return "ABC", primeira.endswith("G")
    letras = "".join(sorted(set(c for c in primeira if c in "ABC")))
    # Terra: `G` na sigla (SEL, GE) ou `N` (quem escreve `AN`).
    terra = bool({"G", "N"} & set(primeira))
    return letras, terra


def mesmo_tipo(nosso: str, do_rele: str) -> bool:
    """`AG` e `AG T` são o mesmo veredito escrito de dois jeitos.

    Sem esta normalização todo caso NORMAL apareceria como conflito — e um
    aviso que aparece quando está tudo certo é um aviso que se aprende a
    ignorar. Com uma das duas siglas vazia não há o que comparar, e isso não
    é conflito: é ausência.
    """
    if not nosso or not do_rele:
        return True
    return _so_as_letras(nosso) == _so_as_letras(do_rele)


def rele_concorda(tipo: str, tipo_inicial: str, do_rele: str) -> bool:
    """Na evolutiva o relé concorda se bater com o começo OU com o fim.

    Ele grava UMA sigla, e qual das duas depende do instante em que o relé
    fechou o relatório — não é discordância de veredito.
    """
    if mesmo_tipo(tipo, do_rele):
        return True
    return bool(tipo_inicial) and mesmo_tipo(tipo_inicial, do_rele)


# ---------------------------------------------------------------------------
# O relé disparou?
# ---------------------------------------------------------------------------

#: O digital de trip, pelo NOME: `TRIP` (SEL, GE), `MAIN : Gen. trip command`
#: (Schneider), `Trip/open cmd.` e `Operate:general` (SIPROTEC, que chama o
#: trip de «Operate»). Conferido nos registros do parque em 22/10/2026.
#: A Ingeteam escreve em espanhol: `Disparo general`, `Disparo 50/51 Fase A`,
#: `50N-Disparo Inst.Neutro` (24/10/2026). O `Disp.` abreviado fica de fora:
#: no parque ele só aparece no `50BF-Arr./Disp.Fallo int`, a falha de disjuntor.
_TRIP = re.compile(r"trip|\boperate\b|\bdisparo\b", re.IGNORECASE)
#: O que tem «trip» no nome e não é trip: `ULTRIP` da SEL é o DESTRAVAMENTO
#: do trip, e sobe justamente quando ele acaba; bloqueio sobe sem disparo.
_NAO_E_TRIP = re.compile(r"^UL|block|bloq|\bblk", re.IGNORECASE)
#: O trip GERAL do relé ganha dos parciais: o «Parallel trip EXT» do MiCOM é
#: a entrada de um trip de FORA e sobe antes do «Gen. trip command».
_TRIP_GERAL = re.compile(
    r"^\s*TRIP\s*$|\bgen(eral)?\b\.?.*trip|operate:general|trip/open"
    r"|\bdisparo\s+general\b",
    re.IGNORECASE)


@dataclass(frozen=True)
class Disparo:
    """O primeiro digital de trip que subiu, e em que amostra."""

    sinal: str
    amostra: int


def disparo_do_rele(registro: Record) -> Disparo | None:
    """O primeiro digital de trip que foi de 0 a 1 no registro, ou `None`.

    Só a SUBIDA conta: um trip que já começa aceso é de um evento anterior,
    e o registro não mostra o relé decidindo. `None` não afirma que o relé
    restringiu — diz que nenhum digital com nome de trip subiu; o relé pode
    ter gravado o trip com outro nome.
    """
    dados = registro.status
    # (não é geral, amostra): o geral vem primeiro, e entre iguais o mais cedo.
    melhor: tuple[bool, int, str] | None = None
    for canal in registro.status_channels:
        nome = canal.name.strip()
        if not _TRIP.search(nome) or _NAO_E_TRIP.search(nome):
            continue
        if canal.index >= dados.shape[0]:
            continue
        linha = dados[canal.index].astype(np.int8)
        subidas = np.flatnonzero(np.diff(linha) > 0)
        if subidas.size:
            chave = (not _TRIP_GERAL.search(nome), int(subidas[0] + 1), nome)
            if melhor is None or chave < melhor:
                melhor = chave
    return Disparo(sinal=melhor[2], amostra=melhor[1]) if melhor else None


def trip_na_sigla(do_rele: str) -> bool:
    """O «T» solto da SEL (`AB T`) — o relé escreveu que disparou."""
    partes = (do_rele or "").upper().split()
    return len(partes) > 1 and "T" in partes[1:]
