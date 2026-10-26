"""As conferências do comissionamento: o OscLab contra o que o RELÉ gravou.

Cada conferência é uma função que recebe um registro e devolve LINHAS — uma
por coisa conferida —, cada uma com o número do relé, o nosso, o erro e um
veredito: `confere`, `diverge` ou `não se aplica` (com o motivo escrito).

Moram aqui, e não dentro do teste, porque têm DOIS usuários:

- `tests/test_comissionamento.py`, que reprova quando alguma linha diverge;
- `tools/comissionar.py`, que roda as mesmas contas sobre um banco inteiro e
  grava o placar, para comparar uma rodada com a seguinte.

Uma conta só, nos dois. Duas cópias da mesma conferência é como uma delas
envelhece sem ninguém ver — e a que envelhece é sempre a que não roda no CI.

Nada aqui conhece arquivo real: o teste e a ferramenta é que apontam a pasta.
O porquê de cada conferência está na docstring do teste correspondente; aqui
fica o porquê de cada CRITÉRIO e de cada tolerância.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from osclab.dsp import envoltoria
from osclab.dsp import fasor as dspf
from osclab.formats import ajustes as ajustes_mod
from osclab.formats import cev, conjuntos
from osclab.formats.base import Record, Trecho
from osclab.plot import catalogo, conversao, unidades
from osclab.plot import diferencial as dif

CONFERE = "confere"
DIVERGE = "diverge"
NAO_SE_APLICA = "não se aplica"
ERRO = "erro"


@dataclass
class Linha:
    """Uma coisa conferida num registro."""

    conferencia: str
    item: str = ""
    rele: float | None = None
    nosso: float | None = None
    erro: float | None = None
    unidade: str = ""
    tolerancia: float | None = None
    veredito: str = NAO_SE_APLICA
    motivo: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


def julgar(conferencia: str, item: str, rele, nosso, erro: float, unidade: str,
           tolerancia: float, motivo: str = "") -> Linha:
    """`confere` quando |erro| cabe na tolerância. Erro não finito diverge."""
    ok = erro is not None and math.isfinite(erro) and abs(erro) <= tolerancia
    return Linha(conferencia, item, _num(rele), _num(nosso), _num(erro), unidade,
                 tolerancia, CONFERE if ok else DIVERGE, motivo)


def nao_se_aplica(conferencia: str, motivo: str, item: str = "") -> Linha:
    return Linha(conferencia, item, veredito=NAO_SE_APLICA, motivo=motivo)


def _num(x):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------------------
# Ferramenta comum
# ---------------------------------------------------------------------------

def serie(registro: Record, identidade: str) -> np.ndarray:
    """A série de um sinal do catálogo, pelo caminho que a tela usa — mas na
    unidade do ARQUIVO.

    A tela divide pelo prefixo que ela escolheu (`kA` acima de 10 000 A), e o
    gabarito do relé está em A: comparar sem desfazer isso reprovava todo
    registro com corrente acima de 10 kA (comissionamento em massa, 24/10).
    """
    n = registro.analog.shape[1]
    trechos = [Trecho(t.inicio, t.fim, t.taxa_hz) for t in registro.trechos]
    escalas = unidades.por_unidade(registro, "arquivo")
    sinal = catalogo.por_id(registro)[identidade]
    divisor, _ = escalas.get(sinal.unidade, (1.0, sinal.unidade))
    return catalogo.serie(registro, sinal, 0, n, trechos, "arquivo", escalas) * divisor


def mesma_base(registro: Record, a: int, b: int) -> bool:
    """Os dois canais estão na mesma relação de TC/TP e no mesmo lado?

    O MiCOM do parque declara `Voltage VNG` com TP de 79.674 V e as fases com
    138.000 V — é 138000/√3, ou seja, um mede fase-neutro e o outro
    fase-fase. Comparar os dois compararia coisas diferentes, e o erro sairia
    em por cento como se fosse defeito do programa.
    """
    canais = {c.index: c for c in registro.analog_channels}
    x, y = canais.get(a), canais.get(b)
    if x is None or y is None or x.is_primary != y.is_primary:
        return False
    rx, ry = conversao.relacao(x), conversao.relacao(y)
    if rx <= 0 or ry <= 0:
        return rx == ry
    return abs(rx - ry) <= 1e-6 * max(rx, ry)


def em_regime(valores: np.ndarray, por_ciclo: int, piso: float) -> np.ndarray:
    """Onde a amplitude é igual à de um ciclo atrás — e vale a pena comparar.

    Mesma lição de `analysis/filtragem.py`: no transitório, a janela de um
    ciclo de cada lado mede trechos diferentes do mesmo evento, e a diferença
    entre dois estimadores vira o resultado. Só em regime a comparação diz
    algo sobre a CONTA em vez de dizer algo sobre a janela.
    """
    n = valores.size
    regime = np.zeros(n, dtype=bool)
    if por_ciclo <= 0 or n <= 2 * por_ciclo:
        return regime
    agora, antes = valores[2 * por_ciclo:], valores[por_ciclo:n - por_ciclo]
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(agora) & np.isfinite(antes) & (agora > piso)
        regime[2 * por_ciclo:] = ok & (np.abs(agora - antes)
                                       <= 0.005 * np.maximum(agora, antes))
    return regime


#: A janela das colunas de média móvel do `.CEV` da SEL, em ciclos.
JANELA_DAS_COLUNAS = 10

#: Quanto o NOSSO valor pode variar dentro dessa janela e ainda contar como
#: regime: 2 %, um quinto da tolerância da coluna. A média de um valor que
#: varia 2 % não se afasta dele mais que 2 %.
VARIACAO_NA_JANELA = 0.02


def parado_na_janela(nosso: np.ndarray, por_ciclo: int, ciclos: int,
                     degrau: float = 0.0) -> np.ndarray:
    """Onde o NOSSO valor ficou parado durante os `ciclos` anteriores inteiros.

    **O critério de um ciclo não serve para coluna de média móvel**, e foi o
    comissionamento em massa que mostrou (24/10/2026). As colunas `L*` do
    `.CEV` — e, no SEL-451 de Araputanga, também `V1M`, `3V0M` e `3V2M` — são
    média de dez ciclos: sobem em rampa enquanto dura a falta, ficam num platô
    e descem em rampa depois que o disjuntor abre. No platô a coluna do relé
    está parada (passa no critério de um ciclo) enquanto a corrente de
    verdade já caiu a zero: `LI1M` 1589 A contra 70 A nossos, −95 % de «erro»
    que era só a janela.

    O critério certo olha a ENTRADA da média, não a saída: se a nossa grandeza
    de um ciclo ficou parada durante toda a janela do relé (mais um ciclo de
    folga), a média dele TEM de ser igual a ela — seja a coluna de um ciclo ou
    de dez. Vale igual para as duas, então não é preciso saber de antemão qual
    relé grava qual.

    «Parada» admite, além dos 2 %, um `degrau` de gravação: num `.CEV` a
    corrente é inteiro, e uma carga de 31 A tem a sequência positiva pulando
    ±1 A de uma amostra para a outra só pelo arredondamento. Esse pulo é
    simétrico e some na mediana; a deriva de verdade, não.
    """
    n = nosso.size
    largura = (ciclos + 1) * por_ciclo
    parado = np.zeros(n, dtype=bool)
    if por_ciclo <= 0 or n <= largura:
        return parado
    janelas = np.lib.stride_tricks.sliding_window_view(nosso, largura + 1)
    with np.errstate(invalid="ignore"):
        finitas = np.all(np.isfinite(janelas), axis=1)
        alto = np.max(np.where(np.isfinite(janelas), janelas, -np.inf), axis=1)
        baixo = np.min(np.where(np.isfinite(janelas), janelas, np.inf), axis=1)
        meio = 0.5 * (alto + baixo)
        ok = finitas & (meio > 0) & (alto - baixo <= VARIACAO_NA_JANELA * meio + degrau)
    parado[largura:] = ok
    return parado


def degrau(registro: Record, indices) -> float:
    """O menor passo entre dois valores gravados nestes canais.

    É a resolução da gravação: o `.CEV` imprime tensão com duas casas (em kV)
    e corrente em INTEIRO. Tudo o que calculamos a partir das amostras herda
    esse arredondamento.
    """
    passos = []
    for i in indices:
        valores = np.unique(registro.analog[i][np.isfinite(registro.analog[i])])
        if valores.size < 2:
            continue
        d = np.diff(valores)
        d = d[d > 1e-9 * max(1.0, float(np.max(np.abs(valores))))]
        if d.size:
            passos.append(float(np.min(d)))
    return min(passos) if passos else 0.0


#: Um valor do relé abaixo de tantos degraus de gravação das fases não se
#: confere em por cento. O fasor de um ciclo de três canais arredondados erra,
#: por conta do arredondamento, da ordem de um terço de degrau a 4 amostras por
#: ciclo; abaixo de dez degraus isso passa de 3 % — um terço da tolerância da
#: coluna — e o «erro» medido passa a ser a resolução do arquivo.
DEGRAUS_MINIMOS = 10


def _pico(registro: Record, indices) -> float:
    return float(np.nanmax(np.abs(registro.analog[list(indices)])))


# ---------------------------------------------------------------------------
# O cabeçalho do `.CEV`, lido AQUI
# ---------------------------------------------------------------------------

def cabecalho_do_cev(caminho: Path) -> dict:
    """Os campos da linha de fasores do `.CEV`, lidos AQUI.

    De propósito não pelo nosso leitor: um teste que usa o código sob teste
    para montar o próprio gabarito não conferiria a leitura, conferiria a si
    mesmo.
    """
    texto = Path(caminho).read_bytes().decode("latin-1")
    linhas = [x for x in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
              if x.strip()]
    # A linha 4 é o cabeçalho em AMBOS os dialetos — a de títulos, com os
    # valores logo abaixo. Procurar por um campo (`IA_PF`) em vez da posição
    # fazia o 787 devolver vazio, e o teste dele PULAVA em silêncio: teste que
    # some por engano é pior que teste que reprova.
    if len(linhas) < 6:
        return {}
    titulo, valores = linhas[4], linhas[5]
    saida = {}
    for chave, valor in zip(next(csv.reader(io.StringIO(titulo))),
                            next(csv.reader(io.StringIO(valores))), strict=False):
        try:
            saida[chave.strip()] = float(valor.strip())
        except ValueError:
            continue
    return saida


def e_cev(caminho: Path) -> bool:
    return Path(caminho).suffix.lower() == ".cev"


# ---------------------------------------------------------------------------
# 1. O resíduo que o relé MEDIU contra o que o OscLab CALCULA
# ---------------------------------------------------------------------------

#: % do pico das três fases.
#:
#: **Por que tão larga, se o medido é 0,001 %.** Seis dos oito pares do parque
#: fecham em 0,001 % ou menos — são os casos em que o canal do relé É a soma
#: das mesmas três entradas (os quatro `3I0`/`3V0` do SIPROTEC, o `IG` do
#: `.CEV` da SEL, que vem da ligação residual dos mesmos TCs). O MiCOM erra
#: 15,6 %, e **não é defeito nosso**: o `Current IN` dele é uma entrada
#: própria, que pode estar num TC toroidal, noutro ponto do circuito. As
#: relações de TC declaradas são idênticas, então não há como saber isso pelo
#: arquivo — e um teste que reprovasse ali estaria cobrando uma igualdade que
#: a física não promete.
#:
#: O que este teste existe para pegar é trinca errada, fase trocada de sinal e
#: escala de TC furada. Qualquer um dos três dá erro da ORDEM DA PRÓPRIA
#: CORRENTE DE FASE — 100 % ou mais. Uma folga de 25 % pega todos eles e
#: aceita um neutro medido noutro lugar. Apertar até 2 % reprovaria o MiCOM
#: toda vez, e um teste que se reprova sozinho vira teste que se desliga.
TOLERANCIA_DO_RESIDUO = 25.0

RESIDUO = "1 resíduo × medido"
NEUTRO_PELO_NOME = "1n neutro ligado pelo nome × resíduo"


def pares_de_residuo(registro: Record):
    """`(i, conjunto, canal medido)` de toda trinca com resíduo conferível."""
    achados = conjuntos.de_registro(registro)
    saida = []
    for i, conjunto in enumerate(achados):
        dentro = conjunto.canais.get("N")
        if dentro is not None:
            saida.append((i, conjunto, dentro))
    for solto, alvo in conjuntos.residuais_soltos(registro).items():
        if 0 <= alvo < len(achados):
            saida.append((alvo, achados[alvo], solto))
    return saida


#: `IGW1` → `G`, `Current IN` → `N`. A letra COMO ESTÁ ESCRITA, e não o `N`
#: normalizado: é ela que, trocada por `*`, reproduz a chave da trinca.
_LETRA_DE_NEUTRO = re.compile(r"(?:^|[^A-Z0-9])[IVU]([NGE])", re.IGNORECASE)


def neutros_pelo_nome(registro: Record):
    """`(i, conjunto, canal)` de neutro que o NOME liga a uma trinca.

    O `IGW1` do SEL-787 e o `J1 -IG` do GE ficam de fora da dedução do
    programa — com mais de uma trinca da mesma unidade e sem nível de tensão no
    nome, `conjuntos` não escolhe, e faz certo em não chutar.

    **Aqui dentro a escolha é barata**, porque esta conferência não desenha
    nada: se o par estiver errado, ela reprova e alguém olha. Fazer a mesma
    dedução no `conjuntos.py` mexeria no que alimenta `3I0`, `I1` e a
    localização de falta — risco desproporcional para um ganho que é só de
    conferência. Ver a conversa de 22/09/2026.
    """
    achados = conjuntos.de_registro(registro)
    chaves = {}
    for i, conjunto in enumerate(achados):
        nome_a = registro.analog_channels[conjunto.abc[0]].name
        chaves.setdefault(
            (conjuntos.sem_a_fase(nome_a, "A"), conjunto.unidade), i)

    ja = {c.canais.get("N") for c in achados}
    ja |= set(conjuntos.residuais_soltos(registro))
    saida = []
    for canal in registro.analog_channels:
        if canal.index in ja:
            continue
        achou = _LETRA_DE_NEUTRO.search(canal.name or "")
        if achou is None:
            continue
        chave = (conjuntos.sem_a_fase(canal.name, achou.group(1)),
                 canal.unit.strip())
        if chave in chaves:
            saida.append((chaves[chave], achados[chaves[chave]], canal.index))
    return saida


def _conferir_residuos(registro: Record, pares, conferencia: str,
                       vazio: str) -> list[Linha]:
    if not pares:
        return [nao_se_aplica(conferencia, vazio)]
    saida = []
    for i, conjunto, medido in pares:
        item = f"{conjunto.nome} × {registro.analog_channels[medido].name}"
        if conjunto.sem_sinal:
            saida.append(nao_se_aplica(conferencia, "trinca sem sinal", item))
            continue
        if not mesma_base(registro, conjunto.abc[0], medido):
            saida.append(nao_se_aplica(
                conferencia, "o medido e as fases estão em relações de TC/TP "
                "diferentes", item))
            continue
        pico = _pico(registro, conjunto.abc)
        if not np.isfinite(pico) or pico <= 0:
            # Trinca legitimamente em zero — o outro lado de um transformador
            # energizado por um só. Zero contra zero não confere nada.
            saida.append(nao_se_aplica(conferencia, "fases em zero", item))
            continue
        # Fases com poucos degraus de gravação: o MiCOM de um vão desligado
        # grava 0,09 A de pico em dois degraus do A/D, e o erro «de 200 %» é a
        # soma de três arredondamentos (ver `DEGRAUS_MINIMOS`).
        q = degrau(registro, conjunto.abc)
        if q > 0 and pico < DEGRAUS_MINIMOS * q:
            saida.append(nao_se_aplica(
                conferencia, f"fases no ruído de gravação: pico {pico:.4g} = "
                f"{pico / q:.0f} degraus, menos de {DEGRAUS_MINIMOS}", item))
            continue
        calculado = serie(registro, f"q{i}:n:instantaneo")
        alvo = registro.analog[medido]
        onde = np.isfinite(calculado) & np.isfinite(alvo)
        if not onde.any():
            saida.append(nao_se_aplica(conferencia, "sem amostra comum", item))
            continue
        erro = float(np.max(np.abs(calculado[onde] - alvo[onde]))) / pico * 100
        saida.append(julgar(
            conferencia, item, float(np.max(np.abs(alvo[onde]))),
            float(np.max(np.abs(calculado[onde]))), erro, "% do pico das fases",
            TOLERANCIA_DO_RESIDUO, "valores: pico do medido e do calculado"))
    return saida


def residuo(caminho: Path, registro: Record) -> list[Linha]:
    return _conferir_residuos(registro, pares_de_residuo(registro), RESIDUO,
                              "nenhuma trinca com resíduo medido")


def neutro_pelo_nome(caminho: Path, registro: Record) -> list[Linha]:
    return _conferir_residuos(registro, neutros_pelo_nome(registro),
                              NEUTRO_PELO_NOME,
                              "nenhum neutro que o nome ligue a uma trinca")


# ---------------------------------------------------------------------------
# 2 e 3. Os fasores que o relé carimbou no cabeçalho do `.CEV`
# ---------------------------------------------------------------------------

#: Medido: 0,60 % de módulo e 0,13° a 8 amostras por ciclo; 1,09 % e 0,41° a 4.
TOLERANCIA_DE_MODULO = 3.0       # %
TOLERANCIA_DE_ANGULO = 1.5       # graus, em ângulo RELATIVO entre fases

PRE_FALTA = "2 fasor de pré-falta do cabeçalho"
FALTA = "3 fasor de falta do cabeçalho"
_FASES = ("IA", "IB", "IC")


def _tem_as_fases(registro: Record) -> bool:
    nomes = {c.name for c in registro.analog_channels}
    return all(g in nomes for g in _FASES)


def fasores_de(registro: Record, nomes, por_ciclo: float) -> dict[str, np.ndarray]:
    indices = {c.name: c.index for c in registro.analog_channels}
    saida = {}
    for nome in nomes:
        canal = registro.analog[indices[nome]]
        coluna = np.full(canal.size, np.nan + 0j, dtype=np.complex128)
        for i in range(canal.size):
            f = dspf.no_instante(canal, i, por_ciclo)
            if f is not None:
                coluna[i] = f.fundamental * np.exp(1j * math.radians(f.angulo))
        saida[nome] = coluna
    return saida


def melhor_casamento(nossos: dict, alvo: dict, fases) -> tuple[float, float, int]:
    """O menor erro de módulo e de ângulo RELATIVO, sobre todo o registro.

    Relativo porque o ângulo absoluto não é comparável: a referência do relé é
    interna dele e a nossa é o cursor. A diferença entre fases não depende de
    referência nenhuma — é conferência mais forte, não mais fraca.

    Devolve `(módulo %, ângulo °, amostra)`; amostra −1 quando não há nenhuma.
    """
    referencia = fases[0]
    matriz = np.vstack([nossos[g] for g in fases])
    validas = np.all(np.isfinite(matriz) & (np.abs(matriz) > 0), axis=0)
    if not validas.any():
        return float("inf"), float("inf"), -1
    with np.errstate(invalid="ignore", divide="ignore"):
        modulo = np.max(np.vstack([
            np.abs(np.abs(nossos[g]) - alvo[g][0]) / max(alvo[g][0], 1.0)
            for g in fases]), axis=0) * 100
        angulo = np.max(np.vstack([
            np.abs((np.degrees(np.angle(nossos[g] / nossos[referencia]))
                    - (alvo[g][1] - alvo[referencia][1]) + 540) % 360 - 180)
            for g in fases if g != referencia]), axis=0)
    custo = np.where(validas, modulo / 100 + angulo / 180, np.inf)
    i = int(np.argmin(custo))
    return float(modulo[i]), float(angulo[i]), i


def _linhas_do_casamento(conferencia: str, nossos, alvo, registro: Record,
                         nota: str) -> list[Linha]:
    modulo, angulo, i = melhor_casamento(nossos, alvo, _FASES)
    if i < 0:
        return [nao_se_aplica(conferencia, "nenhuma amostra com as três fases")]
    pior = max(_FASES, key=lambda g: abs(abs(nossos[g][i]) - alvo[g][0])
               / max(alvo[g][0], 1.0))
    onde = f"melhor amostra {i}"
    ti = registro.trigger_index
    if ti is not None:
        por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz,
                                           registro.line_frequency)
        onde += f" ({(i - ti) / por_ciclo:+.2f} ciclo do disparo)"
    return [
        # O item é FIXO (a fase vai no motivo): é a chave com que duas rodadas
        # se comparam, e uma chave que muda de nome some de um lado e aparece
        # do outro sem que ninguém veja que uma conferência se perdeu.
        julgar(conferencia, "módulo (pior fase)", alvo[pior][0],
               abs(nossos[pior][i]), modulo, "%", TOLERANCIA_DE_MODULO,
               f"pior fase {pior}; {onde}; {nota}"),
        julgar(conferencia, "ângulo relativo (pior fase)", None, None, angulo, "°",
               TOLERANCIA_DE_ANGULO, f"{onde}; {nota}"),
    ]


def fasor_de_pre_falta(caminho: Path, registro: Record) -> list[Linha]:
    """O relé gravou o fasor de pré-falta. Ele tem que existir na nossa curva.

    **Exige um ciclo de pré-falta inteiro no ARQUIVO.** Um `.CEV` do SEL-451
    (Araputanga, 05/10/2026) começa 0,75 ciclo antes do disparo: a primeira
    janela cheia já termina NO disparo, e o fasor que o relé chama de
    pré-falta saiu de amostras anteriores à primeira gravada. Reprovava com
    7,5 % sem diagnóstico nenhum — a conta estava certa, o número do relé é
    que não está no arquivo.
    """
    if not e_cev(caminho):
        return [nao_se_aplica(PRE_FALTA, "só o .CEV traz fasores no cabeçalho")]
    if not _tem_as_fases(registro):
        return [nao_se_aplica(PRE_FALTA, "o arquivo não tem canais IA, IB e IC")]
    cabecalho = cabecalho_do_cev(caminho)
    alvo = {g: (cabecalho.get(f"{g}_PF"), cabecalho.get(f"{g}_DEG_PF"))
            for g in _FASES}
    if any(v[0] is None or v[1] is None for v in alvo.values()):
        return [nao_se_aplica(PRE_FALTA, "o arquivo não traz fasores de pré-falta")]
    if max(v[0] for v in alvo.values()) < 1.0:
        return [nao_se_aplica(PRE_FALTA, "o relé gravou pré-falta zerada")]
    por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz, registro.line_frequency)
    ti = registro.trigger_index
    if ti is not None and ti < 2 * por_ciclo:
        return [nao_se_aplica(
            PRE_FALTA, f"o registro começa {ti / por_ciclo:.2f} ciclo antes do "
            f"disparo: não há janela inteira de pré-falta no arquivo")]
    fraca = _abaixo_da_resolucao(registro, alvo, PRE_FALTA)
    if fraca:
        return fraca
    nossos = fasores_de(registro, _FASES, por_ciclo)
    # E esse ciclo tem de estar PARADO: o SEL-421 de PETROVINA (BG, 23/01)
    # grava um ciclo de carga e a corrente já começa a mudar cinco ciclos
    # antes do disparo; o relé tirou a pré-falta de antes da primeira amostra
    # (142/131/134 A contra os nossos 135/136/145 A). Sem trecho parado antes
    # do disparo, a pré-falta do relé não é nenhum instante do arquivo.
    if ti is not None and not _parado_nas_tres(nossos, registro)[:ti].any():
        return [nao_se_aplica(PRE_FALTA, "não há ciclo parado nas três fases antes "
                                         "do disparo: a pré-falta não está no arquivo")]
    return _linhas_do_casamento(PRE_FALTA, nossos, alvo, registro,
                                f"{por_ciclo:g} am/ciclo")


def _parado_nas_tres(nossos: dict, registro: Record) -> np.ndarray:
    passo = dspf.amostras_por_ciclo(registro.base_rate_hz, registro.line_frequency)
    regime = np.ones(registro.n_samples, dtype=bool)
    for g in _FASES:
        regime &= em_regime(np.abs(nossos[g]), passo, 0.0)
    return regime


def _abaixo_da_resolucao(registro: Record, alvo: dict, conferencia: str) -> list[Linha]:
    """Fase que o relé carimbou com menos de dez degraus de gravação.

    O `.CEV` grava corrente em INTEIRO: uma pré-falta de 2 A (SEL-421 de
    Poconé, 4 amostras por ciclo) é feita de amostras que só podem valer 0, ±1,
    ±2 A — e o próprio relé imprime o fasor como `2`, meio ampère de
    arredondamento. Abaixo de dez degraus o erro em por cento é a resolução
    dos dois números, não a conta (ver `DEGRAUS_MINIMOS`).
    """
    indices = {c.name: c.index for c in registro.analog_channels}
    q = degrau(registro, [indices[g] for g in _FASES])
    fracas = [g for g in _FASES if alvo[g][0] < DEGRAUS_MINIMOS * q]
    if not fracas:
        return []
    texto = ", ".join(f"{g} {alvo[g][0]:g}" for g in fracas)
    return [nao_se_aplica(conferencia, f"o relé marca {texto}: menos de "
                                       f"{DEGRAUS_MINIMOS} degraus de gravação "
                                       f"({q:.3g}); o erro seria a resolução")]


def fasor_de_falta(caminho: Path, registro: Record) -> list[Linha]:
    if not e_cev(caminho):
        return [nao_se_aplica(FALTA, "só o .CEV traz fasores no cabeçalho")]
    if not _tem_as_fases(registro):
        return [nao_se_aplica(FALTA, "o arquivo não tem canais IA, IB e IC")]
    cabecalho = cabecalho_do_cev(caminho)
    alvo = {g: (cabecalho.get(g), cabecalho.get(f"{g}_DEG")) for g in _FASES}
    if any(v[0] is None or v[1] is None for v in alvo.values()):
        return [nao_se_aplica(FALTA, "o arquivo não traz fasores de falta")]
    if max(v[0] for v in alvo.values()) < 1.0:
        return [nao_se_aplica(FALTA, "o relé gravou falta zerada")]
    por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz, registro.line_frequency)
    fraca = _abaixo_da_resolucao(registro, alvo, FALTA)
    if fraca:
        return fraca
    nossos = fasores_de(registro, _FASES, por_ciclo)
    # Há trecho de falta parado um ciclo inteiro? Olhado na fase EM FALTA — a
    # de maior corrente no cabeçalho do relé. Olhava-se sempre a `IA`, e numa
    # falta CG a `IA` é a fase sã: no SEL-411L de Cidade Alta C1 o «regime»
    # que liberava a conferência era o de uma corrente de 100 A, enquanto a de
    # 3433 A é que dizia se a falta cabia numa janela. (Exigir as três fases
    # paradas foi tentado e desfeito: a fase sã de uma falta quase nunca fica
    # parada a 0,5 %, e quinze registros que conferiam deixavam de ser
    # conferidos por um critério que nenhum deles reprovava.)
    em_falta = max(_FASES, key=lambda g: alvo[g][0])
    modulos = np.abs(nossos[em_falta])
    piso = 0.5 * float(np.nanmax(modulos)) if np.isfinite(modulos).any() else 0.0
    passo = dspf.amostras_por_ciclo(registro.base_rate_hz, registro.line_frequency)
    if not em_regime(modulos, passo, piso).any():
        return [nao_se_aplica(FALTA, f"a falta ({em_falta}) não fica parada um ciclo "
                                     f"a {por_ciclo:.0f} amostras por ciclo")]
    return _linhas_do_casamento(FALTA, nossos, alvo, registro,
                                f"{por_ciclo:g} am/ciclo")


# ---------------------------------------------------------------------------
# 4 e 8. As colunas que o relé gravou, contra as nossas componentes
# ---------------------------------------------------------------------------

#: Coluna do relé → (componente nossa, grandeza, fator).
#:
#: O **fator 3 do `3V2M`** é convenção, não erro: a SEL grava `3V2` e nós
#: chamamos de `V2`. Achado por este comissionamento — sem o fator, o erro
#: mediano dava −67,89 %; com ele, −4,90 %.
COLUNAS_DO_RELE = {
    "V1M": ("1", "V", 1.0),
    "3V0M": ("0", "V", 1.0),
    "3V2M": ("2", "V", 3.0),
}

#: As colunas LENTAS (`L*`): média móvel de dez ciclos, sempre.
COLUNAS_LENTAS = {
    "LI1M": ("1", "I", 1.0),
    "L3I2M": ("2", "I", 3.0),
    "LIGM": ("0", "I", 1.0),
}

#: Medido em regime: +0,04 % no `V1M`, +1,12 % no `3V0M`, −4,90 % no `3V2M`.
TOLERANCIA_DA_COLUNA = 10.0      # % — mediana, em regime

#: Medido: +2,67 % de mediana do `LI1M` com o critério antigo de regime (um
#: ciclo), que deixava passar deriva de carga dentro da janela de dez ciclos.
TOLERANCIA_DA_COLUNA_LENTA = 10.0    # %

COLUNAS = "4 colunas V1M/3V0M/3V2M em regime"
LENTAS = "8 colunas lentas L* em regime"


def _conferir_colunas(registro: Record, tabela: dict, conferencia: str,
                      tolerancia: float) -> list[Linha]:
    indices = {c.name: c.index for c in registro.analog_channels}
    passo = dspf.amostras_por_ciclo(registro.base_rate_hz, registro.line_frequency)
    achados = conjuntos.de_registro(registro)
    saida = []
    for coluna, (chave, grandeza, fator) in tabela.items():
        if coluna not in indices:
            continue
        posicao = next((i for i, c in enumerate(achados)
                        if c.grandeza == grandeza and not c.sem_sinal), None)
        if posicao is None:
            saida.append(nao_se_aplica(conferencia, f"sem trinca de {grandeza}",
                                       coluna))
            continue
        nosso = serie(registro, f"q{posicao}:{chave}:rms") * fator
        rele = registro.analog[indices[coluna]]
        if not np.isfinite(rele).any():
            saida.append(nao_se_aplica(conferencia, "coluna vazia", coluna))
            continue
        # Sem piso relativo ao máximo: o de 5 % do pico tirava a pré-falta
        # justamente quando a falta era grande (31 A de carga contra 1589 A
        # de pico no 451 de Araputanga) e sobrava só o platô da média móvel.
        # Quem barra o valor pequeno demais agora é a resolução, logo abaixo.
        regime = em_regime(rele, passo, 0.0)
        # A resolução primeiro: abaixo de dez degraus a nossa grandeza nem
        # fica parada — o arredondamento a faz pular de amostra em amostra.
        q = degrau(registro, achados[posicao].abc)
        with np.errstate(invalid="ignore"):
            resolvido = rele >= DEGRAUS_MINIMOS * q
        if regime.any() and not (regime & resolvido).any():
            valor = float(np.median(rele[regime]))
            saida.append(nao_se_aplica(
                conferencia, f"o relé marca {valor:.4g}, menos de "
                f"{DEGRAUS_MINIMOS} degraus de gravação das fases ({q:.3g}): "
                f"o erro seria a resolução do arquivo", coluna))
            continue
        onde = (regime & resolvido
                & parado_na_janela(nosso, passo, JANELA_DAS_COLUNAS, q))
        if onde.sum() < 3:
            saida.append(nao_se_aplica(
                conferencia, f"a nossa grandeza não fica parada "
                f"{JANELA_DAS_COLUNAS + 1} ciclos (a janela da coluna)", coluna))
            continue
        valor = float(np.median(rele[onde]))
        erro = float(np.median((nosso[onde] - rele[onde]) / rele[onde])) * 100
        saida.append(julgar(
            conferencia, coluna, valor, float(np.median(nosso[onde])), erro,
            "% (mediana)", tolerancia,
            f"fator {fator:g}; {int(onde.sum())} amostras de regime"))
    if not saida:
        saida.append(nao_se_aplica(conferencia, "o relé não gravou essas colunas"))
    return saida


def colunas(caminho: Path, registro: Record) -> list[Linha]:
    """Em regime, e só: fora dele a comparação mede a janela, não a conta."""
    if not e_cev(caminho):
        return [nao_se_aplica(COLUNAS, "só o .CEV grava essas colunas")]
    return _conferir_colunas(registro, COLUNAS_DO_RELE, COLUNAS, TOLERANCIA_DA_COLUNA)


def colunas_lentas(caminho: Path, registro: Record) -> list[Linha]:
    if not e_cev(caminho):
        return [nao_se_aplica(LENTAS, "só o .CEV grava essas colunas")]
    return _conferir_colunas(registro, COLUNAS_LENTAS, LENTAS,
                             TOLERANCIA_DA_COLUNA_LENTA)


# ---------------------------------------------------------------------------
# 5. O mesmo evento exportado duas vezes
# ---------------------------------------------------------------------------

#: Medido na pré-falta do par do alimentador: 0,5 % nas correntes.
TOLERANCIA_ENTRE_EXPORTACOES = 3.0    # %

MESMO_EVENTO = "5 mesmo evento em dois formatos"


def chave_de_evento(registro: Record) -> dict:
    """O que é preciso para casar dois registros do mesmo disparo."""
    return {"disparo": None if registro.trigger_time is None
            else registro.trigger_time.isoformat(),
            "filtragem": str(registro.filtering),
            "equipamento": _equipamento(registro)}


def _equipamento(registro: Record) -> str:
    """O relé E a subestação, sem espaços: o `.CEV` da SEL escreve
    `SE CIDADE ALTA` e o COMTRADE do mesmo evento `SECIDADEALTA`. O campo do
    relé sozinho não serve — é a versão de firmware (`FID=SEL-411L-R126…`), a
    mesma nos dois terminais de uma linha."""
    rele = re.sub(r"\s+", "", registro.device_id or "").upper()
    estacao = re.sub(r"\s+", "", registro.station or "").upper()
    return f"{rele}|{estacao}" if rele or estacao else ""


#: O maior fuso que um carimbo pode ter contra o outro, em horas.
FUSO_MAXIMO = 14


def pares_do_mesmo_evento(chaves: dict) -> list[tuple]:
    """Um `.CEV` e um COMTRADE do MESMO curto, casados pelo carimbo de disparo.

    `chaves` é `{identificador: chave_de_evento(...)}`. O par do alimentador
    difere em 63 µs — o `.CEV` grava milissegundo e o COMTRADE grava
    microssegundo. Um milissegundo de folga casa os dois sem casar eventos
    diferentes: dois registros do mesmo relé a menos de 1 ms um do outro são o
    mesmo disparo.

    **E a diferença pode ser de horas inteiras.** O SEL-421 do COXIPO carimba
    o `.CEV` em hora local e o COMTRADE em UTC (ver «O fuso do COMTRADE» no
    `CLAUDE.md`): quatro horas e 63 µs. Por isso o casamento aceita um número
    inteiro de horas mais o milissegundo — mas aí só com o MESMO equipamento
    escrito nos dois, porque os dois terminais de uma linha disparam juntos.
    Sem o mesmo equipamento, vale só a coincidência dentro do milissegundo,
    como sempre valeu.
    """
    lidos = [(k, datetime.fromisoformat(v["disparo"]), v["filtragem"],
              v.get("equipamento", ""))
             for k, v in chaves.items() if v.get("disparo")]
    pares = []
    for i, (a, ta, fa, ea) in enumerate(lidos):
        for b, tb, fb, eb in lidos[i + 1:]:
            if fa == fb:
                continue
            d = (tb - ta).total_seconds()
            horas = round(d / 3600)
            if abs(d - horas * 3600) > 0.001 or abs(horas) > FUSO_MAXIMO:
                continue
            mesmo = bool(ea) and ea == eb
            if horas != 0 and not mesmo:
                continue
            if ea and eb and not mesmo:
                continue
            pares.append((a, b))
    return pares


def _instante_relativo(registro: Record, segundos: float) -> int:
    """A amostra mais próxima de `segundos` RELATIVOS AO DISPARO."""
    zero = (registro.trigger_time - registro.start_time).total_seconds()
    return int(np.argmin(np.abs(registro.time - (zero + segundos))))


#: Quanto a carga pode variar em um ciclo, no instante escolhido, nos dois.
VARIACAO_DA_PRE_FALTA = 0.02


def _correntes_do_par(r: Record):
    """`(por_ciclo, {fase: curva da fundamental})` da primeira trinca de
    corrente com sinal, e a curva da carga total (soma dos três módulos)."""
    conjunto = next((c for c in conjuntos.de_registro(r)
                     if c.grandeza == "I" and not c.sem_sinal), None)
    if conjunto is None:
        return None
    por_ciclo = dspf.ciclo_em_amostras(r.base_rate_hz, r.line_frequency)
    curvas = {f: envoltoria.fundamental(r.analog[i], por_ciclo)
              for f, i in zip("ABC", conjunto.abc, strict=False)}
    return por_ciclo, curvas, sum(curvas.values())


def mesmo_evento(registro_a: Record, registro_b: Record) -> list[Linha]:
    """A pré-falta dos dois arquivos, no MESMO instante relativo ao disparo.

    **Era «dois ciclos depois do começo de cada arquivo»**, e os dois arquivos
    não começam no mesmo instante: o `.CEV` e o COMTRADE do mesmo evento
    gravam pré-faltas de tamanhos diferentes. Comparava-se a carga num
    instante com a carga noutro — PETROVINA (SEL-421) reprovava com 25,8 %, e
    medido no mesmo instante dá 3,1 % (comissionamento em massa, 24/10/2026).

    Agora o instante é o mesmo nos dois, contado do disparo de cada um, e é o
    MAIS PARADO da pré-falta que os dois têm: onde a carga total muda menos
    de um ciclo para o outro, nos dois arquivos ao mesmo tempo. Um instante
    fixo erra num arquivo ou noutro — no PETROVINA BG a corrente começa a
    mudar cinco ciclos antes do disparo, e no 487E de Primavera Rural a
    primeira janela do `.CEV` ainda é o arranque do filtro do relé (15,5 A
    contra 17,6 A no COMTRADE). Comparar onde a carga varia é medir o
    instante, não a leitura.
    """
    regs = (registro_a, registro_b)
    if any(r.trigger_time is None or r.start_time is None or r.n_samples == 0
           for r in regs):
        return [nao_se_aplica(MESMO_EVENTO, "um dos arquivos não tem disparo")]
    dados = [_correntes_do_par(r) for r in regs]
    if any(d is None for d in dados):
        return [nao_se_aplica(MESMO_EVENTO, "não há trinca de corrente nos dois")]
    zeros = [(r.trigger_time - r.start_time).total_seconds() for r in regs]
    # Os instantes candidatos são as amostras do arquivo de taxa MENOR, da
    # segunda janela cheia (para haver um ciclo atrás com que comparar) até o
    # disparo.
    lento = min((0, 1), key=lambda k: regs[k].base_rate_hz)
    r = regs[lento]
    relativos = r.time - zeros[lento]
    comeco = max(float(x.time[0]) - z + 2 * d[0] / x.base_rate_hz
                 for x, z, d in zip(regs, zeros, dados, strict=True))
    candidatos = relativos[(relativos >= comeco) & (relativos <= 0)]
    if candidatos.size == 0:
        return [nao_se_aplica(MESMO_EVENTO, "os dois arquivos não têm dois ciclos "
                                            "de pré-falta em comum")]
    variacao = np.zeros(candidatos.size)
    for x, z, (por_ciclo, _, carga) in zip(regs, zeros, dados, strict=True):
        i = np.clip(np.searchsorted(x.time, candidatos + z), 0, x.n_samples - 1)
        atras = np.clip(i - int(round(por_ciclo)), 0, x.n_samples - 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            v = np.abs(carga[i] - carga[atras]) / carga[i]
        variacao = np.maximum(variacao, np.where(np.isfinite(v), v, np.inf))
    k = int(np.argmin(variacao))
    if not variacao[k] <= VARIACAO_DA_PRE_FALTA:
        return [nao_se_aplica(MESMO_EVENTO, "a carga não fica parada um ciclo em "
                                            "nenhum instante comum da pré-falta")]
    instante = float(candidatos[k])
    medidas = []
    for x, (_, curvas, _) in zip(regs, dados, strict=True):
        i = _instante_relativo(x, instante)
        medidas.append({f: float(c[i]) for f, c in curvas.items()
                        if np.isfinite(c[i]) and c[i] > 1.0})
    comuns = sorted(set(medidas[0]) & set(medidas[1]))
    if not comuns:
        return [nao_se_aplica(MESMO_EVENTO,
                              "não há trinca de corrente com carga nos dois")]
    nota = (f"{instante * 1000:+.1f} ms do disparo (carga variando "
            f"{variacao[k] * 100:.2f} % no ciclo); «relé» = o segundo arquivo, "
            f"«nosso» = o primeiro")
    return [julgar(MESMO_EVENTO, f"fase {fase}", medidas[1][fase], medidas[0][fase],
                   abs(medidas[0][fase] - medidas[1][fase])
                   / max(medidas[0][fase], medidas[1][fase]) * 100,
                   "%", TOLERANCIA_ENTRE_EXPORTACOES, nota)
            for fase in comuns]


# ---------------------------------------------------------------------------
# 6. A hora do TRIP que o relé carimbou, contra o nosso canal digital
# ---------------------------------------------------------------------------

TRIP = "6 hora do TRIP × digital"

#: O carimbo do relé tem resolução de milissegundo.
RESOLUCAO_DO_CARIMBO = 0.001     # s


def carimbos_de_trip(caminho: Path, registro: Record) -> dict[str, float]:
    """`{"T1": segundos desde a primeira amostra, ...}` de cada carimbo.

    O `.CEV` carimba `HOUR_Tn`/`MIN_Tn`/`SEC_Tn`/`MSEC_Tn` no cabeçalho, um por
    disjuntor: o 451 tem dois, o 487E tem cinco (S, T, U, W, X). É hora de
    relógio, então converter para amostra passa por TUDO que o leitor monta: a
    hora do disparo, o `start_time` recuado pela marca `>`, e a taxa.
    """
    cabecalho = cabecalho_do_cev(caminho)
    if registro.start_time is None or registro.n_samples == 0:
        return {}
    saida = {}
    for n in range(1, 10):
        campos = tuple(f"{c}_T{n}" for c in ("HOUR", "MIN", "SEC", "MSEC"))
        if not all(c in cabecalho for c in campos):
            continue
        hora, minuto, segundo, ms = (int(cabecalho[c]) for c in campos)
        try:
            trip = registro.start_time.replace(hour=hora, minute=minuto,
                                               second=segundo,
                                               microsecond=ms * 1000)
        except ValueError:
            continue
        segundos = (trip - registro.start_time).total_seconds()
        if 0 <= segundos <= float(registro.time[-1]) + RESOLUCAO_DO_CARIMBO:
            saida[f"T{n}"] = segundos
    return saida


def trip(caminho: Path, registro: Record) -> list[Linha]:
    """A amostra em que um digital de TRIP muda, contra o carimbo do relé.

    Dois critérios corrigidos depois do comissionamento em massa (24/10/2026):

    - **A amostra esperada é a PRIMEIRA em ou depois do carimbo**, não a mais
      próxima. Um digital amostrado em `t[k]` mostra o estado em `t[k]`: um
      trip comandado entre duas amostras só aparece na seguinte. Arredondar
      reprovava o SEL-421 de Poconé a 4 amostras por ciclo (carimbo a 25,44
      amostras, `TRIP` muda na 26). A folga é a resolução do carimbo (1 ms).
    - **`Tn` é o trip do DISJUNTOR n, não o `TRIP` geral.** O 487E carimba o
      disjuntor S em `T1`, e o digital que muda ali é o `TRIPS`; o `TRIP`
      geral tinha subido 6 amostras antes. Vale qualquer digital cujo nome
      começa com `TRIP`: é palavra de relé, não lista de fabricante.
    """
    if not e_cev(caminho):
        return [nao_se_aplica(TRIP, "só o .CEV carimba a hora do trip")]
    carimbos = carimbos_de_trip(caminho, registro)
    if not carimbos:
        return [nao_se_aplica(TRIP, "o arquivo não carimba a hora do comando de trip")]
    if registro.status.size == 0:
        return [nao_se_aplica(TRIP, "o arquivo não traz digitais")]
    status = registro.status.astype(np.int8)
    mudou = np.zeros(status.shape, dtype=bool)
    mudou[:, 1:] = np.diff(status, axis=1) != 0
    qualquer = np.flatnonzero(mudou.any(axis=0))
    de_trip = [c.index for c in registro.status_channels
               if c.name.strip().upper().startswith("TRIP")]
    tempo = registro.time
    saida = []
    for nome, segundos in carimbos.items():
        cedo = int(np.searchsorted(tempo, segundos - RESOLUCAO_DO_CARIMBO, "left"))
        tarde = int(np.searchsorted(tempo, segundos + RESOLUCAO_DO_CARIMBO, "left"))
        candidatas = range(max(cedo, 1), min(tarde, registro.n_samples - 1) + 1)
        esperada = max(cedo, 1)
        if de_trip:
            mudam = np.flatnonzero(mudou[de_trip].any(axis=0))
            quem = "digital TRIP*"
        else:
            mudam = qualquer
            quem = "qualquer digital (sem digital TRIP*)"
        if mudam.size == 0:
            saida.append(julgar(TRIP, nome, esperada, None, float("inf"), "amostras",
                                0, f"{quem}: nenhuma mudança no registro"))
            continue
        perto = int(mudam[np.argmin(np.abs(mudam - esperada))])
        ja = set(mudam.tolist())
        acerto = next((k for k in candidatas if k in ja), None)
        erro = 0.0 if acerto is not None else float(perto - esperada)
        nomes = [registro.status_channels[i].name for i in (de_trip or [])
                 if mudou[i, acerto if acerto is not None else perto]]
        saida.append(julgar(
            TRIP, nome, esperada, acerto if acerto is not None else perto, erro,
            "amostras", 0,
            f"carimbo a {segundos * registro.base_rate_hz:.2f} amostras; {quem}"
            + (f": {', '.join(nomes[:4])}" if nomes else "")))
    return saida


# ---------------------------------------------------------------------------
# 7. O instantâneo que o relé gravou coluna a coluna (SEL-787)
# ---------------------------------------------------------------------------

#: Medido no `.CEV` do SEL-787: os sete canais com sinal fecham dentro de 6,8 %,
#: e o pior deles é a fase que colapsou — a que mais se mexe entre a janela e o
#: instante que o relé escolheu. Os outros seis ficam abaixo de 1,3 %.
TOLERANCIA_DO_INSTANTANEO = 12.0     # %

INSTANTANEO = "7 valor por coluna do cabeçalho"


def instantaneo(caminho: Path, registro: Record) -> list[Linha]:
    if not e_cev(caminho):
        return [nao_se_aplica(INSTANTANEO, "só o .CEV grava esse cabeçalho")]
    cabecalho = cabecalho_do_cev(caminho)
    rotulos = {c.name: c.index for c in registro.analog_channels}
    alvos = {}
    for canal in registro.analog_channels:
        # Só coluna de ONDA: `FREQ`, `IOPA` (pu) e as sem unidade não têm
        # fundamental a conferir — casá-las reprovava 19 arquivos que, em A e
        # V, conferem.
        if canal.unit.strip().upper() not in cev.UNIDADES_DE_ONDA:
            continue
        titulo = f"{canal.name}({canal.unit})" if canal.unit else canal.name
        if titulo in cabecalho and abs(cabecalho[titulo]) > 0:
            alvos[canal.name] = cabecalho[titulo]
    if len(alvos) < 3:
        return [nao_se_aplica(INSTANTANEO, "o cabeçalho não traz o valor das colunas")]
    # Canal que o relé marca abaixo de dez degraus de gravação dele sai da
    # conta, pelo mesmo motivo de `DEGRAUS_MINIMOS`: o `IGW1` do 787 da PCH
    # Paranatinga II marca 0,85 A num canal gravado em degraus de 0,42 A, e
    # era ele, sozinho, que reprovava o registro (36 %).
    fora = [n for n in alvos
            if abs(alvos[n]) < DEGRAUS_MINIMOS * degrau(registro, [rotulos[n]])]
    for n in fora:
        del alvos[n]
    if len(alvos) < 3:
        return [nao_se_aplica(INSTANTANEO, "menos de três canais acima de dez "
                                           "degraus de gravação")]
    por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz, registro.line_frequency)
    nomes = list(alvos)
    curvas = np.vstack([envoltoria.fundamental(registro.analog[rotulos[n]], por_ciclo)
                        for n in nomes])
    referencia = np.array([abs(alvos[n]) for n in nomes])[:, None]
    with np.errstate(invalid="ignore"):
        erros = np.abs(curvas - np.array([alvos[n] for n in nomes])[:, None]) / referencia
        pior = np.where(np.all(np.isfinite(curvas), axis=0), np.max(erros, axis=0), np.inf)
    i = int(np.argmin(pior))
    if not np.isfinite(pior[i]):
        return [nao_se_aplica(INSTANTANEO, "nenhuma amostra com todos os canais")]
    k = int(np.argmax(erros[:, i]))
    return [julgar(INSTANTANEO, "canais (pior)",
                   alvos[nomes[k]], float(curvas[k, i]), float(pior[i]) * 100, "%",
                   TOLERANCIA_DO_INSTANTANEO,
                   f"{len(nomes)} canais, pior {nomes[k]}; melhor amostra {i}"
                   + (f"; fora, abaixo de dez degraus: {', '.join(fora)}" if fora else ""))]


# ---------------------------------------------------------------------------
# 9. O diferencial de transformador (87T) contra as colunas do próprio relé
# ---------------------------------------------------------------------------

#: O `.CEV` do SEL-487E grava `IOPA`/`IRTA`/`IOPB`/`IRTB`/`IOPC`/`IRTC` — a
#: Iop e a Irt que o relé calculou, em pu do TAP, com duas casas —, ao lado
#: das amostras. É o gabarito do `plot/diferencial.py` com os ajustes lidos
#: do próprio arquivo, como a tela faz.
#:
#: **Só em regime.** O `.CEV` já é a saída do filtro do relé, e a nossa janela
#: de um ciclo em cima dele é um segundo filtro: no transitório a nossa curva
#: chega 2 a 4 amostras (4 a 8 ms) depois da do relé, e a diferença mede o
#: atraso, não a conta. Sobre o COMTRADE bruto do mesmo evento, com o
#: estimador cosseno, o atraso cai para ~1,5 ms e a falta também fecha (erro
#: mediano de 0,002 a 0,008 pu) — mas isso pede o par de arquivos; aqui é um
#: registro só. A decisão (bits `87R*`, `87*HB`, `87*HR`) também fica de fora:
#: o `87R*` do relé tem selo e temporização internos que o arquivo não diz, e
#: a 2ª harmônica não se mede num `.CEV`, que o filtro do relé já limpou.
#:
#: Medido em 16 `.CEV` de 487E do parque (25/10/2026): mediana de |erro| da
#: Iop em regime ≤ 0,003 pu (pior amostra ±0,022), e da Irt entre −0,15 % e
#: +0,40 %. A coluna tem degrau de 0,01 pu; a folga é dois degraus na Iop e
#: 3 % na Irt. Em regime a Iop é quase sempre a de carga (≈ 0), e é isso que
#: ela prende: TAP, RTC ou compensação (`TnCTC`) errados dão Iop falsa da
#: ordem da corrente de carga — décimos de pu, dez vezes a folga.
TOLERANCIA_DA_IOP = 0.02         # pu, mediana de |erro|
TOLERANCIA_DA_IRT = 3.0          # %, mediana
#: Abaixo disto a Irt são poucos degraus da coluna (0,01 pu) e o erro
#: relativo vira a resolução do arquivo.
IRT_MINIMA = 0.2                 # pu
#: Regime: a coluna do relé não andou mais que isto em um ciclo e meio.
VARIACAO_DO_87T = 0.03

DIFERENCIAL = "9 87T × colunas IOP/IRT do relé"


def _parado(x: np.ndarray, janela: int) -> np.ndarray:
    """Onde a série não andou mais que `VARIACAO_DO_87T` (mais um degrau da
    coluna) nas últimas `janela` amostras."""
    saida = np.zeros(x.size, dtype=bool)
    if janela < 2 or x.size <= janela:
        return saida
    vista = np.lib.stride_tricks.sliding_window_view(x, janela)
    with np.errstate(invalid="ignore"):
        amplitude = np.nanmax(vista, axis=1) - np.nanmin(vista, axis=1)
        topo = np.nanmax(vista, axis=1)
        saida[janela - 1:] = (np.all(np.isfinite(vista), axis=1)
                              & (amplitude <= VARIACAO_DO_87T * np.maximum(topo, IRT_MINIMA)
                                 + 0.01))
    return saida


def diferencial_87t(caminho: Path, registro: Record) -> list[Linha]:
    if not e_cev(caminho):
        return [nao_se_aplica(DIFERENCIAL, "só o .CEV grava as colunas IOP/IRT")]
    indices = {c.name: c.index for c in registro.analog_channels}
    nomes = [f"{q}{f}" for f in "ABC" for q in ("IOP", "IRT")]
    if not all(n in indices for n in nomes):
        return [nao_se_aplica(DIFERENCIAL, "o relé não gravou IOPA…IRTC")]
    pasta = Path(caminho).parent
    irmaos = [p.name for p in pasta.iterdir()
              if p.is_file() and p.stem.lower() == Path(caminho).stem.lower()]
    lidos = dif.lidos_do_arquivo(ajustes_mod.do_registro(pasta, irmaos, []))
    terminais = dif.nomes_por_terminal(lidos)
    if not terminais:
        return [nao_se_aplica(DIFERENCIAL, "sem E87: não se sabe que terminais entram")]
    trincas = {t.nome: t for t in dif.trincas_de_corrente(registro)}
    um = terminais["rtc1"].removeprefix("CTR")
    dois = terminais["rtc2"].removeprefix("CTR")
    lado1, lado2 = trincas.get(f"I*{um}"), trincas.get(f"I*{dois}")
    if lado1 is None or lado2 is None:
        return [nao_se_aplica(DIFERENCIAL, f"E87 pede os terminais {um} e {dois}, "
                                           f"e o arquivo não tem as duas trincas")]
    fab = dif.fabricante(registro, lidos)
    campos = dif.resolver(registro, lidos, {"valores": {}, "aceitos": []}, fab,
                          lado1, lado2)
    faltando = dif.faltam(campos)
    if faltando:
        return [nao_se_aplica(DIFERENCIAL, "faltam ajustes: "
                              + ", ".join(x["id"] for x in faltando))]
    conta = dif.calcular(registro, lado1, lado2, {c["id"]: c["valor"] for c in campos})

    por_ciclo = dspf.amostras_por_ciclo(registro.base_rate_hz, registro.line_frequency)
    janela = int(math.ceil(1.5 * por_ciclo))
    erros_iop, erros_irt, ref_irt = [], [], []
    for k, fase in enumerate("ABC"):
        iop_r = registro.analog[indices[f"IOP{fase}"]]
        irt_r = registro.analog[indices[f"IRT{fase}"]]
        iop, irt = conta["iop"][k], conta["irt"][k]
        regime = (_parado(iop_r, janela) & _parado(irt_r, janela)
                  & np.isfinite(iop) & np.isfinite(irt))
        erros_iop.append(iop[regime] - iop_r[regime])
        com_carga = regime & (irt_r >= IRT_MINIMA)
        erros_irt.append((irt[com_carga] - irt_r[com_carga]) / irt_r[com_carga])
        ref_irt.append(irt_r[com_carga])
    e_iop = np.concatenate(erros_iop)
    e_irt = np.concatenate(erros_irt)
    if e_iop.size < 3:
        return [nao_se_aplica(DIFERENCIAL, "nenhum trecho em regime")]
    contexto = f"{fab}, lados I*{um}/I*{dois}"
    saida = [julgar(DIFERENCIAL, "Iop em regime", None, None,
                    float(np.median(np.abs(e_iop))), "pu (mediana de |erro|)",
                    TOLERANCIA_DA_IOP,
                    f"{contexto}; {e_iop.size} amostras; pior "
                    f"{float(e_iop[np.argmax(np.abs(e_iop))]):+.3f} pu")]
    if e_irt.size < 3:
        saida.append(nao_se_aplica(DIFERENCIAL, f"Irt do relé abaixo de {IRT_MINIMA:g} "
                                   f"pu em todo o regime: o erro seria a resolução "
                                   f"da coluna", "Irt em regime"))
    else:
        saida.append(julgar(DIFERENCIAL, "Irt em regime",
                            float(np.median(np.concatenate(ref_irt))), None,
                            100 * float(np.median(e_irt)), "% (mediana)",
                            TOLERANCIA_DA_IRT, f"{contexto}; {e_irt.size} amostras"))
    return saida


# ---------------------------------------------------------------------------
# 10. O plano de impedância (21) contra a falta que o relé localizou
# ---------------------------------------------------------------------------

#: O relé de linha da SEL escreve onde achou a falta: `LOCATION` (na unidade
#: do `LL`) no `.CEV` e no `.HDR` da família 400 e do 321, e o 311C ainda
#: escreve `PER_UNIT_LL` e o ponto do plano — `FLT_LOC_Z` ∠ `FLT_LOC_ANG` e
#: `FLT_R`, em ohm secundário. **O ângulo NÃO é medido**: é o `Z1ANG` ajustado
#: (± 180° na reversa), então `FLT_LOC_Z` é `m · Z1MAG` e a única grandeza do
#: plano que ele afirma é a REATÂNCIA, `FLT_LOC_Z · sen(FLT_LOC_ANG)`.
#:
#: Do nosso lado sai o `% da linha` pela reatância (`X / (Z1MAG · sen Z1ANG)`,
#: que é o que o localizador do relé estima) na trajetória que o painel
#: desenha, no PLATÔ: o ciclo de menor espalhamento dentro da falta. Não o
#: `|Z| / |Z1|` da ficha da tela: ele soma a resistência de falta ao
#: comprimento, e numa falta de 2 Ω num laço de 1,4 Ω a falta «andaria» 70 %.
#:
#: Medido em 22 faltas internas do parque (25/10/2026; 311C, 321, 421, 451;
#: 4 a 128 am/ciclo), com o 3I0 tirado da soma das fases: |Δ| ≤ 4,2 pontos
#: de % da linha em 21, mediana 1,2. Fica fora o 321 de Coxipó (−11,2
#: pontos, sem explicação achada: o k0 do relé e o nosso são o mesmo e o
#: platô é parado). A folga de 5 pontos é o pior caso explicado mais uma
#: margem; fase trocada, k0 ausente ou base errada dão dezenas de pontos — e
#: o canal `IN` do 311C tomado como 3I0 dá +8 a +71 pontos (ver
#: `docs-privados/aprendizado/impedancia-gabarito.md`).
#:
#: A reatância do 311C (10 faltas): |erro| ≤ 4,1 % em 9, e −9,2 % no
#: COMTRADE bruto de Rondonópolis, em que o relé congelou o ponto no primeiro
#: ciclo da falta, com a contínua ainda viva, e o nosso platô é o depois
#: dela. Folga de 12 %.
TOLERANCIA_DA_DISTANCIA = 5.0        # pontos de % da linha
TOLERANCIA_DA_REATANCIA = 12.0       # %

#: Fora destes limites o localizador do relé está extrapolando o modelo da
#: linha (falta externa, reversa, ou o relé localizando a CARGA). Medido em
#: 25 desses: há os que fecham em 2 pontos no instante do resumo e os que
#: erram 600 — o número depende de onde o relé congelou, e não prende conta.
FAIXA_DA_LINHA = (0.0, 1.1)
#: Corrente de falta mínima, em múltiplos da de CARGA. Abaixo disso
#: o relé localizou carga — os seis `ABC` sem `T` do A. Floresta são isso.
CORRENTE_DE_FALTA = 3.0
#: O platô tem de existir: espalhamento máximo da janela de um ciclo. Acima,
#: a falta evolui (Sinop C2: 25 a 33 %) e o relé e nós congelamos instantes
#: diferentes de uma impedância que anda.
ESPALHAMENTO_DO_PLATO = 0.10

DISTANCIA = "10 21 × falta localizada pelo relé"

_NUMERO = r"([-+]?\d+(?:\.\d+)?)"


def resumo_da_falta(caminho: Path) -> dict:
    """O que o relé escreveu sobre a falta, lido AQUI e não pelo leitor.

    `{evento, local, pu, z, angulo, rf, correntes}` com o que houver. O
    `.CEV` CSV tem o resumo nas linhas 4 e 5; o do 321 é texto; o COMTRADE o
    traz no `.HDR` irmão.
    """
    caminho = Path(caminho)
    saida: dict = {}

    def num(x):
        try:
            v = float(str(x).strip())
        except (TypeError, ValueError):
            return None
        return v if math.isfinite(v) else None

    def do_texto(texto: str) -> None:
        m = re.search(r"Event:\s*([A-Z0-9]+(?: T)?)\s+Location:\s*" + _NUMERO, texto)
        if m:
            saida["evento"], saida["local"] = m.group(1), float(m.group(2))
        for chave, rotulo in (("z", "Fault Location Impedance"),
                              ("angulo", "Fault Location Angle"),
                              ("pu", "Per-Unit of Line Length"),
                              ("rf", "Fault Resistance")):
            m = re.search(rotulo + r":\s*" + _NUMERO, texto)
            if m:
                saida[chave] = float(m.group(1))

    if e_cev(caminho):
        texto = caminho.read_bytes().decode("latin-1")
        linhas = [x for x in texto.replace("\r\n", "\n").split("\n") if x.strip()]
        if texto.startswith('"FID"') and len(linhas) >= 6:
            cab = dict(zip((c.strip() for c in next(csv.reader(io.StringIO(linhas[4])))),
                           (v.strip() for v in next(csv.reader(io.StringIO(linhas[5])))),
                           strict=False))
            saida["evento"] = cab.get("EVENT")
            saida["local"] = num(cab.get("LOCATION"))
            for chave, campo in (("pu", "PER_UNIT_LL"), ("z", "FLT_LOC_Z"),
                                 ("angulo", "FLT_LOC_ANG"), ("rf", "FLT_R")):
                if num(cab.get(campo)) is not None:
                    saida[chave] = num(cab.get(campo))
            correntes = {f: num(cab.get("I" + f)) for f in "ABC"}
            if all(v is not None for v in correntes.values()):
                saida["correntes"] = correntes
        else:
            do_texto(texto)
    else:
        hdr = next((p for p in caminho.parent.iterdir()
                    if p.stem.lower() == caminho.stem.lower()
                    and p.suffix.lower() == ".hdr"), None)
        if hdr is not None:
            do_texto(hdr.read_bytes().decode("latin-1"))
    return saida


def lacos_do_evento(evento: str) -> tuple[str, ...]:
    """`AG` → `AN`; `BC`, `BCG` → `BC`; `ABC` → os três laços de fase (o
    relé escolhe o de menor impedância, e nós também). Vazio quando o evento
    não é um tipo de falta (`TRIP`, `ER`, `TRIG`)."""
    e = (evento or "").upper().replace(" T", "").strip()
    if not re.fullmatch(r"[ABC]{1,3}G?", e):
        return ()
    fases = "".join(c for c in "ABC" if c in e)
    if len(fases) == 1:
        return (fases + "N",) if e.endswith("G") else ()
    if len(fases) == 2:
        return ({"AB": "AB", "BC": "BC", "AC": "CA"}[fases],)
    return ("AB", "BC", "CA")


def _arquivos_irmaos(caminho: Path) -> list[str]:
    return [p.name for p in Path(caminho).parent.iterdir()
            if p.is_file() and p.stem.lower() == Path(caminho).stem.lower()]


def _plato(z: np.ndarray, falta: np.ndarray, largura: int):
    """`(mediana, espalhamento)` da janela de `largura` pontos, toda dentro da
    falta, em que a impedância menos anda. `None` sem janela inteira."""
    melhor = None
    for a in range(0, z.size - largura + 1):
        bloco = z[a:a + largura]
        if not (falta[a:a + largura].all() and np.isfinite(bloco).all()):
            continue
        med = complex(np.median(bloco.real), np.median(bloco.imag))
        if abs(med) == 0:
            continue
        espalhamento = float(np.max(np.abs(bloco - med)) / abs(med))
        if melhor is None or espalhamento < melhor[1]:
            melhor = (med, espalhamento)
    return melhor


def distancia(caminho: Path, registro: Record) -> list[Linha]:
    """A falta que o relé localizou contra a trajetória do plano de impedância.

    A trajetória é a do painel (`impedancia.montar`), com os ajustes do
    próprio arquivo, levada a ohm SECUNDÁRIO — a base do `Z1MAG` do relé.
    """
    from osclab.formats import ajustes as ajustes_mod
    from osclab.plot import impedancia, paineis

    resumo = resumo_da_falta(caminho)
    if resumo.get("local") is None and resumo.get("pu") is None:
        return [nao_se_aplica(DISTANCIA, "o relé não localizou a falta")]
    lacos = lacos_do_evento(resumo.get("evento"))
    if not lacos:
        return [nao_se_aplica(DISTANCIA, f"o evento «{resumo.get('evento')}» não diz o laço")]
    lidos = ajustes_mod.do_registro(Path(caminho).parent, _arquivos_irmaos(caminho),
                                    [c.name for c in registro.status_channels])
    ajustes = impedancia.como_dicionario(lidos.get("ajustes"))
    parametros = impedancia.parametros_da_linha(ajustes)
    if parametros is None:
        return [nao_se_aplica(DISTANCIA, "o arquivo não traz Z1MAG/Z1ANG")]
    z1, angulo1 = parametros.modulo.valor, parametros.angulo.valor
    x1 = z1 * math.sin(math.radians(angulo1))
    if resumo.get("pu") is not None:
        m_rele = resumo["pu"]
    else:
        # O 411L escreve o comprimento em `LLR`; o `LL` dele é o de fábrica.
        comprimento = None
        for nome in ("LLR", "LL"):
            try:
                comprimento = float(ajustes[nome])
                break
            except (KeyError, ValueError):
                continue
        if not comprimento:
            return [nao_se_aplica(DISTANCIA, "o arquivo não traz o comprimento (LL)")]
        m_rele = resumo["local"] / comprimento
    if not FAIXA_DA_LINHA[0] <= m_rele <= FAIXA_DA_LINHA[1]:
        return [nao_se_aplica(DISTANCIA, f"o relé localizou fora da linha ({m_rele:+.2f} pu)")]

    trinca = next((c for c in conjuntos.de_registro(registro)
                   if c.grandeza == "I" and not c.sem_sinal
                   and all(f in c.canais for f in "ABC")), None)
    if trinca is None:
        return [nao_se_aplica(DISTANCIA, "sem trinca de corrente")]
    por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz, registro.line_frequency)
    fases = {f: envoltoria.fundamental(registro.analog[trinca.canais[f]], por_ciclo)
             for f in "ABC"}
    if not all(np.isfinite(v).any() for v in fases.values()):
        return [nao_se_aplica(DISTANCIA, "registro curto demais para um ciclo de fasor")]
    maior = max(float(np.nanmax(v)) for v in fases.values())
    if resumo.get("correntes") and max(resumo["correntes"].values()) < 0.5 * maior:
        # O 421 de Poconé carimbou o resumo antes de a corrente subir (o ponto
        # dele é da carga, e o 311C no mesmo vão, do mesmo evento, fecha); o
        # 311C de Sinop C2, numa falta que ainda crescia.
        return [nao_se_aplica(DISTANCIA, "o resumo do relé é de um instante com menos "
                                         "da metade da corrente máxima do registro")]

    melhor = None
    motivo = (f"corrente de falta abaixo de {CORRENTE_DE_FALTA:g}× a de carga, "
              "ou sem trajetória")
    for laco in lacos:
        letras = impedancia.LACOS[laco]
        corrente_do_laco = np.fmax.reduce(np.vstack([fases[f] for f in letras]), axis=0)
        validos = corrente_do_laco[np.isfinite(corrente_do_laco)]
        pico = float(np.nanmax(corrente_do_laco))
        # A CARGA é o maior entre o primeiro ciclo e o percentil 20 do que
        # corre (acima de 2 % do pico). Só o primeiro ciclo erra no registro
        # que começa com o disjuntor aberto (Braço Norte 13_12: 0 A, e depois
        # 46 a 80 A); só o percentil erra no evento em que a fase CAI (Braço
        # Norte 12_13_03: IA de 149 para 46 A, as outras paradas em 155 A).
        correndo = validos[validos > 0.02 * pico]
        carga = max(float(np.percentile(correndo, 20)) if correndo.size else 0.0,
                    float(np.median(validos[:max(int(por_ciclo), 1)])) if validos.size else 0.0)
        if carga > 0 and pico < CORRENTE_DE_FALTA * carga:
            continue
        cheio = np.flatnonzero(corrente_do_laco >= 0.5 * pico)
        i0 = max(int(cheio[0]) - int(2 * por_ciclo), 0)
        i1 = min(i0 + impedancia.MAXIMO_DE_PONTOS - 1, registro.n_samples - 1)
        painel = paineis.de_json([{"id": "z", "tipo": "impedancia", "nome": "Z",
                                   "laco": laco, "sinais": []}])[0]
        pacote = impedancia.montar(registro, painel, lidos, "secundario", i0, i1)
        if "ajuste" not in pacote:
            # Sem plano (dois pares corrente × tensão sem vínculo, como o
            # COMTRADE do 421 com VY e VZ): a conferência diz o que a tela diz.
            motivo = "; ".join(a.get("curto", "") for a in pacote.get("avisos", []))
            continue
        base = pacote["ajuste"]
        fator = 1.0
        if base.get("base") == "primario":
            if not base.get("relacao"):
                continue
            fator = 1.0 / base["relacao"]
        pontos = pacote.get("pontos") or []
        if not pontos:
            continue
        indices = np.array([p["n"] for p in pontos])
        z = np.array([complex(p["r"], p["x"]) * fator if p["r"] is not None
                      else complex(np.nan, np.nan) for p in pontos])
        achado = _plato(z, corrente_do_laco[indices] >= 0.5 * np.nanmax(corrente_do_laco),
                        max(int(round(por_ciclo)), 3))
        if achado and (melhor is None or abs(achado[0]) < abs(melhor[1])):
            melhor = (laco, achado[0], achado[1])
    if melhor is None:
        return [nao_se_aplica(DISTANCIA, motivo)]
    laco, z_plato, espalhamento = melhor
    if espalhamento > ESPALHAMENTO_DO_PLATO:
        return [nao_se_aplica(DISTANCIA, f"a falta evolui: o ciclo mais parado anda "
                                         f"{100 * espalhamento:.0f} %")]
    m_nosso = z_plato.imag / x1
    contexto = f"laço {laco}, platô com {100 * espalhamento:.1f} % de espalhamento"
    saida = [julgar(DISTANCIA, "% da linha", 100 * m_rele, 100 * m_nosso,
                    100 * (m_nosso - m_rele), "pontos", TOLERANCIA_DA_DISTANCIA, contexto)]
    if resumo.get("z") is not None and resumo.get("angulo") is not None:
        x_rele = resumo["z"] * math.sin(math.radians(resumo["angulo"]))
        if abs(x_rele) > 0:
            saida.append(julgar(DISTANCIA, "reatância do laço", x_rele, z_plato.imag,
                                100 * (z_plato.imag - x_rele) / abs(x_rele), "%",
                                TOLERANCIA_DA_REATANCIA,
                                f"{contexto}; Ω secundário; Rf do relé {resumo.get('rf')} Ω"))
    return saida


# ---------------------------------------------------------------------------
# Todas
# ---------------------------------------------------------------------------

#: As conferências de UM registro, na ordem do placar. O par (5) é à parte:
#: precisa de dois registros.
POR_REGISTRO = (residuo, neutro_pelo_nome, fasor_de_pre_falta, fasor_de_falta,
                colunas, trip, instantaneo, colunas_lentas, diferencial_87t,
                distancia)


def todas(caminho: Path, registro: Record) -> list[Linha]:
    """Todas as conferências de um registro. Uma que quebre vira linha `erro`
    — e as outras seguem: uma exceção numa conta não pode apagar o placar das
    outras sete."""
    saida = []
    for conferir in POR_REGISTRO:
        try:
            saida.extend(conferir(caminho, registro))
        except Exception as exc:          # vira linha do placar
            saida.append(Linha(NOMES[conferir], veredito=ERRO,
                               motivo=f"{type(exc).__name__}: {str(exc)[:200]}"))
    return saida


NOMES = {residuo: RESIDUO, neutro_pelo_nome: NEUTRO_PELO_NOME,
         fasor_de_pre_falta: PRE_FALTA, fasor_de_falta: FALTA, colunas: COLUNAS,
         trip: TRIP, instantaneo: INSTANTANEO, colunas_lentas: LENTAS,
         diferencial_87t: DIFERENCIAL, distancia: DISTANCIA}
