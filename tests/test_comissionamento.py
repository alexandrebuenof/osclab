"""Comissionamento: o OscLab contra os números que o PRÓPRIO relé gravou.

## A ideia

Todo arquivo de oscilografia traz, além das amostras, medidas que o relé
calculou por dentro: o resíduo que ele mediu numa entrada própria, as
componentes que ele gravou em coluna, os fasores que ele carimbou no cabeçalho.
**Esses números são um gabarito escrito pelo fabricante.** Comparar o OscLab
contra eles não precisa de arquivo de referência nenhum — e vale para qualquer
arquivo novo que o Alexandre largue na pasta.

Foi essa a razão de descartar o plano anterior, de um `gabarito.json` chaveado
por sha256: um gabarito que a gente mesmo escreve prova que a conta não mudou,
não que ela está certa. Este aqui prova as duas coisas.

## As três camadas, e o que cada uma prende

1. **Sintéticos** (`tests/fabrica.py`): resposta CONHECIDA — "a senoide tinha
   100 A de pico, o leitor tem que devolver 100 A". Prende a MATEMÁTICA, de
   forma absoluta. É melhor que comparar com software: não há segunda
   implementação para estar errada.
2. **Este arquivo**: prende matemática MAIS leitura — escala de TC/TP, ordem de
   canal, base de tempo — contra o que o relé afirma.
3. **SIGRA**: terceiro independente, manual, cursor a cursor. Ver `CLAUDE.md`.
   Cobre os arquivos da SEL que não trazem gabarito nenhum dentro.

## Os arquivos não entram no repositório

Identificam instalação, data e comportamento da rede, e o repositório é
público. Então estes testes ficam desligados por padrão:

    set OSCLAB_AMOSTRAS=C:\\Users\\alexa\\Documents\\06 - Ferramentas\\Oscilografias
    python app.py --testes

## As tolerâncias saem de MEDIDA, não de chute

Cada uma tem o número medido ao lado, e a folga é deliberada: apertar até o
valor medido faria o teste quebrar no próximo arquivo por variação legítima.
"""

from __future__ import annotations

import csv
import io
import math
import os
import re
from pathlib import Path

import numpy as np
import pytest

from osclab.dsp import envoltoria
from osclab.dsp import fasor as dspf
from osclab.formats import cev, conjuntos, registry
from osclab.formats.base import Record, Trecho
from osclab.plot import catalogo, conversao, unidades

_RAIZ = os.environ.get("OSCLAB_AMOSTRAS", "").strip()
AMOSTRAS = Path(_RAIZ).expanduser() if _RAIZ else None

pytestmark = pytest.mark.skipif(
    AMOSTRAS is None or not AMOSTRAS.is_dir(),
    reason="defina OSCLAB_AMOSTRAS apontando para a pasta das oscilografias reais",
)

PRINCIPAIS = (".cfg", ".cff", ".cev")


def _e_oscilografia(caminho: Path) -> bool:
    """Um `.cfg` só é COMTRADE se tiver o `.dat` irmão.

    `.cfg` é extensão disputada: um `pyvenv.cfg` de ambiente virtual do Python
    mora em qualquer pasta de projeto, tem 300 bytes de `home = ...` e casaria
    com a varredura. O comissionamento reprovaria por não conseguir lê-lo — e
    reprovar por motivo besta é o caminho mais curto para alguém desligar a
    suíte.

    **O critério é estrutural, não lista de nomes**, e é essa a diferença que
    importa: um arquivo que não traz o par de dados não é oscilografia
    nenhuma. Um `.CEV` — que é auto-contido — continua entrando sempre, e foi
    justamente um `.CEV` que o programa não lia (o do SEL-787) que este teste
    denunciou. A guarda não podia ser larga a ponto de ter escondido aquele.
    """
    if caminho.suffix.lower() != ".cfg":
        return True
    return any(caminho.with_suffix(ext).is_file()
               for ext in (".dat", ".DAT", ".Dat"))


def _arquivos() -> list[Path]:
    if AMOSTRAS is None or not AMOSTRAS.is_dir():
        return []
    return sorted(p for p in AMOSTRAS.rglob("*")
                  if p.is_file() and p.suffix.lower() in PRINCIPAIS
                  and _e_oscilografia(p))


def _ids(caminhos: list[Path]) -> list[str]:
    base = AMOSTRAS or Path(".")
    return [str(p.relative_to(base)) for p in caminhos]


SEM_AMOSTRAS = ("defina OSCLAB_AMOSTRAS apontando para a pasta das "
                "oscilografias reais")


def _casos(caminhos: list[Path]) -> dict:
    """Os argumentos do `parametrize`, com um caso visível quando não há
    arquivo nenhum.

    Sai como dicionário para entrar com `**`: o terceiro posicional do
    `parametrize` é `indirect`, não `ids`, e passar a lista ali dentro falha
    de um jeito que não parece o que é.

    Sem isto, uma lista vazia some do relatório com a mensagem genérica do
    pytest — «got empty parameter set» —, e quem roda a suíte lê "pulou" sem
    saber o que fazer para não pular. Um teste que não roda tem que DIZER por
    que não rodou; senão a suíte fica verde afirmando uma coisa que não
    conferiu.
    """
    if caminhos:
        return {"argvalues": caminhos, "ids": _ids(caminhos)}
    return {"argvalues": [pytest.param(
                None, marks=pytest.mark.skip(reason=SEM_AMOSTRAS))],
            "ids": ["sem amostras"]}


CAMINHOS = _arquivos()


# ---------------------------------------------------------------------------
# Ferramenta comum
# ---------------------------------------------------------------------------

def _serie(registro: Record, identidade: str) -> np.ndarray:
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


def _mesma_base(registro: Record, a: int, b: int) -> bool:
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


def _pares_de_residuo(registro: Record):
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


def _em_regime(valores: np.ndarray, por_ciclo: int, piso: float) -> np.ndarray:
    """Onde a amplitude é igual à de um ciclo atrás — e vale a pena comparar.

    Mesma lição de `analysis/filtragem.py`: no transitório, a janela de um
    ciclo de cada lado mede trechos diferentes do mesmo evento, e a diferença
    entre dois estimadores vira o resultado. Só em regime a comparação diz
    algo sobre a CONTA em vez de dizer algo sobre a janela.
    """
    n = valores.size
    regime = np.zeros(n, dtype=bool)
    for i in range(2 * por_ciclo, n):
        agora, antes = valores[i], valores[i - por_ciclo]
        if not (np.isfinite(agora) and np.isfinite(antes)) or agora <= piso:
            continue
        regime[i] = abs(agora - antes) <= 0.005 * max(agora, antes)
    return regime


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


@pytest.mark.parametrize("caminho", **_casos(CAMINHOS))
def test_o_residuo_calculado_bate_com_o_MEDIDO(caminho: Path):
    """**A conferência mais forte que existe neste arquivo.**

    O resíduo medido vem de uma entrada própria do relé; o nosso vem da soma
    de três canais. São dois caminhos FISICAMENTE independentes para o mesmo
    número — se a trinca estiver errada, se uma fase entrar com sinal trocado,
    se a escala de TC estiver furada, isto abre. Nenhuma comparação com outro
    software prova tanto: software comparado com software pode estar errado
    dos dois lados.

    Ver `TOLERANCIA_DO_RESIDUO` para por que a folga é larga e por que isso
    não enfraquece o que o teste pega.
    """
    registro = registry.read(caminho)
    pares = [(i, c, m) for i, c, m in _pares_de_residuo(registro)
             if not c.sem_sinal and _mesma_base(registro, c.abc[0], m)]
    if not pares:
        pytest.skip("nenhuma trinca com resíduo medido na mesma base")

    for i, conjunto, medido in pares:
        calculado = _serie(registro, f"q{i}:n:instantaneo")
        alvo = registro.analog[medido]
        pico = float(np.nanmax(np.abs(registro.analog[list(conjunto.abc)])))
        if not np.isfinite(pico) or pico <= 0:
            # Trinca legitimamente em zero — o outro lado de um transformador
            # energizado por um só. Zero contra zero não confere nada.
            continue
        onde = np.isfinite(calculado)
        erro = float(np.nanmax(np.abs(calculado[onde] - alvo[onde]))) / pico * 100
        assert erro <= TOLERANCIA_DO_RESIDUO, (
            f"{conjunto.nome}: IN calculado erra {erro:.3f} % do pico das fases "
            f"contra o canal medido")


# ---------------------------------------------------------------------------
# 2. Os fasores que o relé carimbou no cabeçalho do `.CEV`
# ---------------------------------------------------------------------------

#: Medido: 0,60 % de módulo e 0,13° a 8 amostras por ciclo; 1,09 % e 0,41° a 4.
TOLERANCIA_DE_MODULO = 3.0       # %
TOLERANCIA_DE_ANGULO = 1.5       # graus, em ângulo RELATIVO entre fases


def _cabecalho_do_cev(caminho: Path) -> dict:
    """Os campos da linha de fasores do `.CEV`, lidos AQUI.

    De propósito não pelo nosso leitor: um teste que usa o código sob teste
    para montar o próprio gabarito não conferiria a leitura, conferiria a si
    mesmo.
    """
    texto = caminho.read_bytes().decode("latin-1")
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
                            next(csv.reader(io.StringIO(valores)))):
        try:
            saida[chave.strip()] = float(valor.strip())
        except ValueError:
            continue
    return saida


def _fasores_de(registro: Record, nomes, por_ciclo: float):
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


CEVS = [p for p in CAMINHOS if p.suffix.lower() == ".cev"]


@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_o_fasor_de_PRE_FALTA_do_cabecalho_aparece_na_nossa_conta(caminho: Path):
    """O relé gravou o fasor que ele mediu. Ele tem que existir na nossa curva.

    A asserção é «existe uma amostra em que bate», e não «bate na amostra tal»:
    qual instante a SEL usa é convenção interna dela, e fixar um palpite sobre
    isso testaria o palpite. O que importa é que o número do relé esteja lá.

    **Só a pré-falta vale em todo arquivo.** Ver o teste seguinte.
    """
    registro = registry.read(caminho)
    cabecalho = _cabecalho_do_cev(caminho)
    fases = ("IA", "IB", "IC")
    alvo = {g: (cabecalho.get(f"{g}_PF"), cabecalho.get(f"{g}_DEG_PF"))
            for g in fases}
    if any(v[0] is None for v in alvo.values()):
        pytest.skip("o arquivo não traz fasores de pré-falta")
    if max(v[0] for v in alvo.values()) < 1.0:
        pytest.skip("o relé gravou pré-falta zerada")

    por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz,
                                       registro.line_frequency)
    nossos = _fasores_de(registro, fases, por_ciclo)
    modulo, angulo = _melhor_casamento(nossos, alvo, fases)
    assert modulo <= TOLERANCIA_DE_MODULO and angulo <= TOLERANCIA_DE_ANGULO, (
        f"melhor casamento: {modulo:.2f} % de módulo, {angulo:.2f}° de ângulo")


def _melhor_casamento(nossos: dict, alvo: dict, fases) -> tuple[float, float]:
    """O menor erro de módulo e de ângulo RELATIVO, sobre todo o registro.

    Relativo porque o ângulo absoluto não é comparável: a referência do relé é
    interna dele e a nossa é o cursor. A diferença entre fases não depende de
    referência nenhuma — é conferência mais forte, não mais fraca.
    """
    referencia = fases[0]
    melhor = (float("inf"), float("inf"), float("inf"))
    for i in range(next(iter(nossos.values())).size):
        if any(not np.isfinite(nossos[g][i]) or abs(nossos[g][i]) == 0
               for g in fases):
            continue
        erro_modulo = max(abs(abs(nossos[g][i]) - alvo[g][0]) / max(alvo[g][0], 1.0)
                          for g in fases) * 100
        erro_angulo = max(
            abs((math.degrees(np.angle(nossos[g][i] / nossos[referencia][i]))
                 - (alvo[g][1] - alvo[referencia][1]) + 540) % 360 - 180)
            for g in fases if g != referencia)
        custo = erro_modulo / 100 + erro_angulo / 180
        if custo < melhor[0]:
            melhor = (custo, erro_modulo, erro_angulo)
    return melhor[1], melhor[2]


@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_o_fasor_de_FALTA_bate_quando_a_falta_cabe_numa_janela(caminho: Path):
    """E quando não cabe, o teste PULA em vez de reprovar.

    O `.CEV` de 4 amostras por ciclo do parque registra um curto de 1,5 ciclo.
    Não existe janela de um ciclo inteiramente dentro dele, e o relé calculou o
    fasor dele por dentro, a 16 amostras por ciclo ou mais, ANTES de decimar o
    relatório para 4. Medido ali: 18,9 % de erro de módulo.

    **Isso não é defeito do leitor, é resolução do relatório** — e é limite que
    vale saber antes de confiar num arquivo de 4 amostras por ciclo para
    conferir corrente de falta.
    """
    registro = registry.read(caminho)
    cabecalho = _cabecalho_do_cev(caminho)
    fases = ("IA", "IB", "IC")
    alvo = {g: (cabecalho.get(g), cabecalho.get(f"{g}_DEG")) for g in fases}
    if any(v[0] is None for v in alvo.values()):
        pytest.skip("o arquivo não traz fasores de falta")
    if max(v[0] for v in alvo.values()) < 1.0:
        pytest.skip("o relé gravou falta zerada")

    por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz,
                                       registro.line_frequency)
    passo = dspf.amostras_por_ciclo(registro.base_rate_hz,
                                    registro.line_frequency)
    nossos = _fasores_de(registro, fases, por_ciclo)

    # Há trecho de falta que fique parado por um ciclo inteiro?
    modulos = np.abs(nossos["IA"])
    piso = 0.5 * float(np.nanmax(modulos))
    if not _em_regime(modulos, passo, piso).any():
        pytest.skip(f"a falta não fica parada um ciclo a "
                    f"{por_ciclo:.0f} amostras por ciclo")

    modulo, angulo = _melhor_casamento(nossos, alvo, fases)
    assert modulo <= TOLERANCIA_DE_MODULO and angulo <= TOLERANCIA_DE_ANGULO, (
        f"melhor casamento: {modulo:.2f} % de módulo, {angulo:.2f}° de ângulo")


# ---------------------------------------------------------------------------
# 3. As colunas que o relé gravou, contra as nossas componentes
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

#: Medido em regime: +0,04 % no `V1M`, +1,12 % no `3V0M`, −4,90 % no `3V2M`.
#: O `3V0M` e o `3V2M` são diferenças de três fasores de ~8 kV gravados com
#: 0,01 kV de degrau, sobre resultados de 0,07 e 5 V — poucos por cento ali são
#: a resolução do arquivo, não a nossa conta.
TOLERANCIA_DA_COLUNA = 10.0      # % — mediana, em regime


@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_as_colunas_do_rele_batem_EM_REGIME(caminho: Path):
    """Em regime, e só: fora dele a comparação mede a janela, não a conta.

    As colunas com prefixo `L` (`LI1M`, `L3I2M`, `LIGM`) ficam de fora de
    propósito — este comissionamento descobriu que elas são **média móvel de
    10 ciclos** do valor instantâneo, não o valor de um ciclo. Sobem e descem
    em rampa e continuam caindo dez ciclos depois de o disjuntor abrir. Em
    regime elas coincidem com as nossas; fora dele, são outra grandeza.
    """
    registro = registry.read(caminho)
    indices = {c.name: c.index for c in registro.analog_channels}
    passo = dspf.amostras_por_ciclo(registro.base_rate_hz,
                                    registro.line_frequency)
    achados = conjuntos.de_registro(registro)

    conferidas = 0
    for coluna, (chave, grandeza, fator) in COLUNAS_DO_RELE.items():
        if coluna not in indices:
            continue
        posicao = next((i for i, c in enumerate(achados)
                        if c.grandeza == grandeza and not c.sem_sinal), None)
        if posicao is None:
            continue
        nosso = _serie(registro, f"q{posicao}:{chave}:rms") * fator
        rele = registro.analog[indices[coluna]]
        piso = 0.05 * float(np.nanmax(rele))
        onde = _em_regime(rele, passo, piso) & np.isfinite(nosso)
        if onde.sum() < 3:
            continue
        erro = float(np.median((nosso[onde] - rele[onde]) / rele[onde])) * 100
        assert abs(erro) <= TOLERANCIA_DA_COLUNA, (
            f"{coluna}: mediana de {erro:+.2f} % em {int(onde.sum())} amostras "
            f"de regime")
        conferidas += 1

    if not conferidas:
        pytest.skip("o relé não gravou coluna nenhuma que dê para conferir")


# ---------------------------------------------------------------------------
# 4. O mesmo evento exportado duas vezes
# ---------------------------------------------------------------------------

#: Medido na pré-falta do par do alimentador: 0,5 % nas correntes.
TOLERANCIA_ENTRE_EXPORTACOES = 3.0    # %


def _pares_do_mesmo_evento() -> list[tuple[Path, Path]]:
    """Um `.CEV` e um COMTRADE do MESMO curto, casados pelo carimbo de disparo.

    O par do alimentador difere em 63 µs — o `.CEV` grava milissegundo e o
    COMTRADE grava microssegundo. Um milissegundo de folga casa os dois sem
    casar eventos diferentes: dois registros do mesmo relé a menos de 1 ms um
    do outro são o mesmo disparo.
    """
    lidos = []
    for caminho in CAMINHOS:
        try:
            registro = registry.read(caminho)
        except Exception:
            continue
        if registro.trigger_time is not None:
            lidos.append((caminho, registro))

    pares = []
    for i, (caminho_a, a) in enumerate(lidos):
        for caminho_b, b in lidos[i + 1:]:
            if str(a.filtering) == str(b.filtering):
                continue
            if abs((a.trigger_time - b.trigger_time).total_seconds()) > 0.001:
                continue
            pares.append((caminho_a, caminho_b))
    return pares


PARES = _pares_do_mesmo_evento()


@pytest.mark.parametrize(
    "par",
    PARES or [pytest.param(None, marks=pytest.mark.skip(
        reason=SEM_AMOSTRAS if AMOSTRAS is None
        else "não há o mesmo evento exportado nos dois formatos"))],
    ids=([f"{a.stem[:18]}|{b.stem[:18]}" for a, b in PARES] or ["sem par"]))
def test_o_mesmo_evento_exportado_DUAS_VEZES_da_o_mesmo_numero(par):
    """O `.CEV` filtrado e o COMTRADE bruto do mesmo curto.

    São dois arquivos com taxas diferentes (8 e 33,33 amostras por ciclo),
    escalas diferentes (o `.CEV` grava eficaz e o leitor converte para
    instantâneo) e conteúdo diferente (um já filtrado pelo relé, o outro
    cru). Se os dois derem a mesma pré-falta, o caminho de leitura dos DOIS
    formatos está certo — e é o `.CEV` que carrega para o COMTRADE a
    validação que ele recebeu do cabeçalho do relé.
    """
    medidas = []
    for caminho in par:
        registro = registry.read(caminho)
        por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz,
                                           registro.line_frequency)
        # A pré-falta, dois ciclos depois do começo: janela já cheia e ainda
        # longe de qualquer transitório.
        i = int(round(2 * por_ciclo))
        por_fase: dict[str, float] = {}
        for conjunto in conjuntos.de_registro(registro):
            if conjunto.grandeza != "I" or conjunto.sem_sinal:
                continue
            for fase, indice in zip("ABC", conjunto.abc):
                f = dspf.no_instante(registro.analog[indice], i, por_ciclo)
                if f is not None and f.fundamental > 1.0:
                    por_fase.setdefault(fase, f.fundamental)
            if por_fase:
                break
        medidas.append(por_fase)

    comuns = set(medidas[0]) & set(medidas[1])
    if not comuns:
        pytest.skip("não há trinca de corrente com carga nos dois arquivos")

    for fase in sorted(comuns):
        a, b = medidas[0][fase], medidas[1][fase]
        erro = abs(a - b) / max(a, b) * 100
        assert erro <= TOLERANCIA_ENTRE_EXPORTACOES, (
            f"fase {fase}: {a:.2f} contra {b:.2f} ({erro:.2f} %)")


# ---------------------------------------------------------------------------
# 5. A hora do TRIP que o relé carimbou, contra o nosso canal digital
# ---------------------------------------------------------------------------

def _instante_do_trip(caminho: Path, registro: Record) -> int | None:
    """A amostra em que o relé diz que o disjuntor foi comandado.

    O `.CEV` carimba `HOUR_T1`/`MIN_T1`/`SEC_T1`/`MSEC_T1` no cabeçalho. É uma
    hora de relógio, então converter para amostra passa por TUDO que o leitor
    monta: a hora do disparo, o `start_time` recuado pela marca `>`, e a taxa.
    """
    cabecalho = _cabecalho_do_cev(caminho)
    campos = ("HOUR_T1", "MIN_T1", "SEC_T1", "MSEC_T1")
    if not all(c in cabecalho for c in campos):
        return None
    if registro.start_time is None or registro.base_rate_hz <= 0:
        return None
    hora, minuto, segundo, ms = (int(cabecalho[c]) for c in campos)
    trip = registro.start_time.replace(hour=hora, minute=minuto,
                                       second=segundo, microsecond=ms * 1000)
    segundos = (trip - registro.start_time).total_seconds()
    if not 0 <= segundos <= registro.n_samples / registro.base_rate_hz:
        return None
    return int(round(segundos * registro.base_rate_hz))


@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_a_hora_do_TRIP_cai_na_amostra_em_que_o_digital_MUDA(caminho: Path):
    """**Esta é a única conferência que prende a BASE DE TEMPO.**

    Todo o resto compara número com número na mesma amostra, e passaria igual
    se o registro inteiro estivesse deslocado no tempo. Aqui não: o relé
    carimbou uma hora de RELÓGIO, e para ela virar índice de amostra passam a
    hora do disparo, o recuo pela marca `>` e a taxa. Se qualquer um estiver
    errado, o trip cai noutra amostra.

    E prende o desempacotamento dos digitais junto — a tira hexadecimal vira
    bit na posição certa, ou o `TRIP` não estaria ali.

    Medido no alimentador: o relé carimba 13:36:57,980, que dá a amostra 208, e
    é exatamente onde `TRIP` muda. Das 481 amostras do registro, só 40 têm
    mudança alguma, e a 208 é a maior rajada delas (17 digitais).
    """
    registro = registry.read(caminho)
    amostra = _instante_do_trip(caminho, registro)
    if amostra is None:
        pytest.skip("o arquivo não carimba a hora do comando de trip")
    if registro.status.size == 0:
        pytest.skip("o arquivo não traz digitais")

    mudam = np.flatnonzero(
        np.any(np.diff(registro.status.astype(np.int8), axis=1) != 0, axis=0)) + 1
    assert amostra in mudam, (
        f"o relé carimbou o trip na amostra {amostra} e nenhum digital muda "
        f"ali; as mudanças estão em {mudam[:12].tolist()}…")

    # `TRIP` é palavra de relé, não nome de fabricante, e a conferência fica
    # condicionada a ele existir: um arquivo sem `TRIP` não reprova por isso.
    por_nome = {c.name.strip().upper(): c.index
                for c in registro.status_channels}
    if "TRIP" in por_nome:
        linha = registro.status[por_nome["TRIP"]].astype(np.int8)
        assert linha[amostra] != linha[amostra - 1], (
            f"o digital TRIP não muda na amostra {amostra}, que é onde o relé "
            f"diz ter comandado o disjuntor")


# ---------------------------------------------------------------------------
# 6. O instantâneo que o relé gravou coluna a coluna (SEL-787)
# ---------------------------------------------------------------------------

#: Medido no `.CEV` do SEL-787: os sete canais com sinal fecham dentro de 6,8 %,
#: e o pior deles é a fase que colapsou — a que mais se mexe entre a janela e o
#: instante que o relé escolheu. Os outros seis ficam abaixo de 1,3 %.
TOLERANCIA_DO_INSTANTANEO = 12.0     # %


@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_o_instantaneo_do_cabecalho_aparece_na_nossa_conta(caminho: Path):
    """O SEL-787 grava, no cabeçalho, o valor de CADA COLUNA num instante.

    O campo se chama igual ao título da coluna, unidade inclusive —
    `IAW1(A)`, `VB(V)` —, e é isso que o distingue do bloco `IA_PF`/`IA` do
    451, cujos campos não trazem unidade. Por isso o casamento é por nome
    EXATO: no 451 nenhum campo casa e o teste pula; no 787 casam os doze.

    Foi com este gabarito que se provou que o `.CEV` do 787 também vem em
    eficaz, mesmo sendo relatório BRUTO: com o ×√2 os canais fecham dentro de
    1,3 %; sem ele, erram 30 %.
    """
    registro = registry.read(caminho)
    cabecalho = _cabecalho_do_cev(caminho)
    rotulos = {c.name: c.index for c in registro.analog_channels}

    # O título da coluna, como está no arquivo, é `nome(unidade)`.
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
        pytest.skip("o cabeçalho não traz o instantâneo das colunas")

    por_ciclo = dspf.ciclo_em_amostras(registro.base_rate_hz,
                                       registro.line_frequency)
    curvas = {nome: envoltoria.fundamental(registro.analog[rotulos[nome]],
                                           por_ciclo)
              for nome in alvos}

    melhor = float("inf")
    for i in range(registro.n_samples):
        if any(not np.isfinite(curvas[n][i]) for n in alvos):
            continue
        erro = max(abs(curvas[n][i] - alvos[n]) / abs(alvos[n]) for n in alvos)
        melhor = min(melhor, erro * 100)
    assert melhor <= TOLERANCIA_DO_INSTANTANEO, (
        f"o melhor casamento dos {len(alvos)} canais erra {melhor:.1f} %")


# ---------------------------------------------------------------------------
# 7. O neutro medido cujo NOME diz de que trinca ele é
# ---------------------------------------------------------------------------

#: `IGW1` → `G`, `Current IN` → `N`. A letra COMO ESTÁ ESCRITA, e não o `N`
#: normalizado: é ela que, trocada por `*`, reproduz a chave da trinca.
_LETRA_DE_NEUTRO = re.compile(r"(?:^|[^A-Z0-9])[IVU]([NGE])", re.IGNORECASE)


def _neutros_pelo_nome(registro: Record):
    """`(i, conjunto, canal)` de neutro que o NOME liga a uma trinca.

    O `IGW1` do SEL-787 e o `J1 -IG` do GE ficam de fora da dedução do
    programa — com mais de uma trinca da mesma unidade e sem nível de tensão no
    nome, `conjuntos` não escolhe, e faz certo em não chutar.

    **Aqui dentro a escolha é barata**, porque este arquivo não desenha nada:
    se o par estiver errado, o teste reprova e alguém olha. Fazer a mesma
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


@pytest.mark.parametrize("caminho", **_casos(CAMINHOS))
def test_o_neutro_que_o_NOME_liga_a_trinca_tambem_confere(caminho: Path):
    """Quatro pares que a dedução do programa deixa de lado, de propósito.

        SEL-787   IGW1  → I*W1        IGW2  → I*W2
        GE        J1 -IG → J1 -I*     J1 Ig → J1 I*

    São neutros de verdade, com a trinca escrita no próprio nome. Conferi-los
    aqui é ganho puro: mais gabarito, nenhum risco na tela.
    """
    registro = registry.read(caminho)
    pares = [(i, c, m) for i, c, m in _neutros_pelo_nome(registro)
             if not c.sem_sinal and _mesma_base(registro, c.abc[0], m)]
    if not pares:
        pytest.skip("nenhum neutro que o nome ligue a uma trinca")

    for i, conjunto, medido in pares:
        calculado = _serie(registro, f"q{i}:n:instantaneo")
        alvo = registro.analog[medido]
        pico = float(np.nanmax(np.abs(registro.analog[list(conjunto.abc)])))
        if not np.isfinite(pico) or pico <= 0:
            continue
        onde = np.isfinite(calculado)
        erro = float(np.nanmax(np.abs(calculado[onde] - alvo[onde]))) / pico * 100
        assert erro <= TOLERANCIA_DO_RESIDUO, (
            f"{conjunto.nome}: IN calculado erra {erro:.3f} % do pico das "
            f"fases contra {registro.analog_channels[medido].name}")


# ---------------------------------------------------------------------------
# 8. A sequência positiva de CORRENTE contra a coluna lenta do relé
# ---------------------------------------------------------------------------

#: Medido: +2,67 % de mediana em 56 amostras de regime.
#:
#: A folga é larga e o motivo é a NATUREZA da coluna, não a nossa conta: o
#: `LI1M` é média móvel de dez ciclos (ver o teste das colunas), e mesmo num
#: trecho que passa no critério de regime — amplitude igual à de um ciclo
#: atrás dentro de 0,5 % — a carga ainda deriva ao longo desses dez ciclos.
#: O que sobra é essa deriva.
TOLERANCIA_DA_COLUNA_LENTA = 10.0    # %


@pytest.mark.parametrize("caminho", **_casos(CEVS))
def test_a_sequencia_POSITIVA_de_corrente_bate_com_a_coluna_do_rele(caminho: Path):
    """A única conferência de componente de CORRENTE contra o relé.

    O `V1M` das tensões já é conferido no teste das colunas; a corrente não
    era, e é ela que manda na localização de falta. As outras duas colunas de
    corrente — `L3I2M` e `LIGM` — continuam fora: a falta nunca fica parada dez
    ciclos, então elas nunca têm trecho comparável, e forçar a comparação fora
    de regime mediria a janela em vez da conta.
    """
    registro = registry.read(caminho)
    indices = {c.name: c.index for c in registro.analog_channels}
    if "LI1M" not in indices:
        pytest.skip("o relé não gravou a coluna LI1M")

    achados = conjuntos.de_registro(registro)
    posicao = next((i for i, c in enumerate(achados)
                    if c.grandeza == "I" and not c.sem_sinal), None)
    if posicao is None:
        pytest.skip("o arquivo não tem trinca de corrente")

    nosso = _serie(registro, f"q{posicao}:1:rms")
    rele = registro.analog[indices["LI1M"]]
    passo = dspf.amostras_por_ciclo(registro.base_rate_hz,
                                    registro.line_frequency)
    onde = _em_regime(rele, passo, 0.05 * float(np.nanmax(rele)))
    onde &= np.isfinite(nosso)
    if onde.sum() < 3:
        pytest.skip("sem trecho em regime para comparar")

    erro = float(np.median((nosso[onde] - rele[onde]) / rele[onde])) * 100
    assert abs(erro) <= TOLERANCIA_DA_COLUNA_LENTA, (
        f"I1: mediana de {erro:+.2f} % contra LI1M em {int(onde.sum())} "
        f"amostras de regime")
