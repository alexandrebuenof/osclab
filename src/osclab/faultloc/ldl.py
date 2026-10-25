"""LDL no tempo: a localização calculada amostra a amostra, nos dois terminais.

O painel «localizar falta» mostra a distância de cada método ao longo do
registro, como o SynchroWAVe mostra o FLOCAT — e é dessa curva que sai o
número: a MEDIANA do platô, o trecho em que a falta já está estabelecida e o
disjuntor ainda não abriu. Num instante só, o número depende de onde se pôs o
cursor; no platô inteiro, depende da falta.

Dois métodos nesta etapa, os padrões da proteção (decidido em 23/10/2026):

- **sequência negativa, dois terminais** (`seqneg.localizar`, a planilha
  LocDef), vetorizada aqui;
- **laço da falta pela reatância** (o método clássico de um terminal; é o
  que a Energisa MT usa, mas o nome na tela é neutro — o programa é universal):
  `m = Im{V_laço / I_laço} / X1L`, com `I_laço = Iφ + k0·3I0` no laço de
  terra e `Iφ1 − Iφ2` no de fase. O laço é o que o classificador de falta
  escolheu (`falta.Veredito.laco`).

Tudo em PRIMÁRIO e em fasor EFICAZ: a conversão de TC/TP vem antes da conta,
como em `seqneg.fasores_de`.

## A direção pela sequência negativa (o 32Q)

Com V2 na referência, `V2 = −Z2fonte·I2` numa falta para FRENTE: I2 fica
adiantada de V2 por 180° − ∠Z2 da fonte (≈ +97° numa fonte de 83°). Para trás,
`V2 = +Z2·I2` e I2 fica ≈ −83°. O teste é o sinal da parte real de
`(V2/I2)·1∠−θL` — negativa para frente. Os dois terminais vendo «para frente» é
a falta interna; um deles vendo «para trás» põe a falta fora da linha, e
nenhuma localização vale.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass

import numpy as np

from osclab.analysis import falta as falta_mod
from osclab.dsp import envoltoria, simetricas
from osclab.faultloc import seqneg
from osclab.formats import conjuntos
from osclab.formats.base import Record
from osclab.plot import conversao, escala, serie, unidades

#: Os métodos desta etapa, na ordem de preferência do RESULTADO. Sem as
#: simulações (etapa 2), a preferência é fixa: a seq. negativa quando há os dois
#: terminais, o laço da falta quando não há.
METODOS = ("seqneg", "laco")
NOMES = {"seqneg": "Sequência negativa · 2 terminais (LocDef)",
         "laco": "Laço da falta · reatância"}
CURTOS = {"seqneg": "Seq. neg. 2T", "laco": "Laço (reatância)"}

#: O platô começa DOIS ciclos depois do início da falta: um para a janela do
#: fasor encher, outro para a contínua da falta amortecer o bastante. Numa
#: falta curta demais para isso, 1,1 ciclo: a janela cheia, e a DC que for.
#: Acaba ¾ de ciclo antes do fim: o fim é medido onde a corrente já caiu à
#: metade, meio ciclo depois de a janela começar a pegar a abertura.
#: Abaixo disto de |I2|/|I1| no platô do IED A a sequência negativa não
#: localiza nada: é a falta trifásica (equilibrada) e o que sobra de I2 é ruído
#: e desequilíbrio de carga. Na validação independente (24/10/2026) uma ABC a
#: 40 km saía «53,3 km ± 0,3» pela seq. negativa, ao lado do laço com 40,0.
#: Uma falta assimétrica fica muito acima: na AG, I2 ≈ I1 da falta.
MINIMO_I2_SOBRE_I1 = 0.05

CICLOS_ANTES_DO_PLATO = 2.0
CICLOS_ANTES_NA_FALTA_CURTA = 1.1
CICLOS_DEPOIS_DO_PLATO = 0.75
#: A faixa de patrulha mínima: a dispersão no platô de uma falta limpa chega a
#: zero, e uma faixa de zero quilômetros promete o que nenhum método entrega.
FAIXA_MINIMA_KM = 0.3


# ---------------------------------------------------------------------------
# Os fasores contínuos de uma trinca, em primário
# ---------------------------------------------------------------------------

def _fator_primario(registro: Record, canal: int) -> float | None:
    """O que leva o canal a volt/ampère PRIMÁRIO, ou `None` sem relação."""
    c = registro.analog_channels[canal]
    fator = unidades.fator_do_prefixo(c.unit)[0]
    if not c.is_primary:
        razao = conversao.relacao(c)
        if razao <= 1.0:
            return None
        fator *= razao
    return fator


def _trinca(registro: Record, conj) -> dict[str, np.ndarray] | None:
    """`{"A": X, "B": X, "C": X}`: o fasor eficaz de cada amostra, em primário.

    É o fasor que GIRA com o tempo (`envoltoria.fasores`): o ângulo absoluto
    muda de amostra para amostra, mas as contas daqui só usam razões e
    combinações de fasores do MESMO instante, onde o giro se cancela.
    """
    saida = {}
    for fase in "ABC":
        canal = conj.canais[fase]
        fator = _fator_primario(registro, canal)
        if fator is None:
            return None
        bruto = envoltoria.calcular_fasores(registro.analog[canal], registro.trechos,
                                            registro.line_frequency)
        saida[fase] = bruto * (fator / math.sqrt(2.0))
    return saida


@dataclass
class Terminal:
    """O que um registro entrega para a localização."""

    registro: Record
    v: dict[str, np.ndarray] | None
    i: dict[str, np.ndarray] | None
    canais_v: list[str]
    canais_i: list[str]
    aviso: str
    veredito: falta_mod.Veredito | None


def _sem_trinca(registro: Record) -> str:
    """Por que não há trinca utilizável — dizendo quando a tensão é só de linha."""
    vivos = [c for c in conjuntos.de_registro(registro) if not c.sem_sinal]
    if any(c.grandeza == "V" and c.e_de_linha for c in vivos) and \
            not any(c.grandeza == "V" and not c.e_de_linha for c in vivos):
        return ("a tensão só vem medida entre fases (VAB, VBC, VCA); a "
                "localização precisa da tensão de fase")
    return "o registro não tem trinca de tensão E de corrente"


def terminal(registro: Record) -> Terminal:
    """As trincas de tensão e de corrente de um registro, e o veredito da falta.

    Usa a PRIMEIRA trinca de cada grandeza com sinal — a mesma escolha de
    `seqneg.fasores_de`, para o número do painel e o da conta antiga baterem.
    """
    # Só trinca de FASE: a de linha (VAB, VBC, VCA) não tem chave `A`, e a
    # conta dela daria V2 girado de 30° e vezes √3.
    achados = [c for c in conjuntos.de_registro(registro)
               if not c.sem_sinal and not c.e_de_linha]
    corrente = next((c for c in achados if c.grandeza == "I"), None)
    tensao = next((c for c in achados if c.grandeza == "V"), None)
    if corrente is None or tensao is None:
        return Terminal(registro, None, None, [], [], _sem_trinca(registro), None)
    nomes = lambda conj: [registro.analog_channels[conj.canais[f]].name for f in "ABC"]  # noqa: E731
    v, i = _trinca(registro, tensao), _trinca(registro, corrente)
    veredito = falta_mod.classificar(registro, corrente.canais, tensao.canais)
    aviso = "" if v is not None and i is not None else "sem relação de TC/TP declarada"
    return Terminal(registro, v, i, nomes(tensao), nomes(corrente), aviso, veredito)


def seq2(trinca: dict[str, np.ndarray]) -> np.ndarray:
    return simetricas.de_fasores(trinca["A"], trinca["B"], trinca["C"])[2]


# ---------------------------------------------------------------------------
# Os métodos, vetorizados
# ---------------------------------------------------------------------------

def seqneg_vetor(v2s: np.ndarray, i2s: np.ndarray, v2r: np.ndarray, i2r: np.ndarray,
                 z2l: complex) -> np.ndarray:
    """`seqneg.localizar` amostra a amostra: o `m` da raiz que cai na linha.

    NaN onde a conta não fecha: corrente zero num lado, Δ < 0, nenhuma raiz na
    linha ou as duas (não dá para escolher).
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        ab = -v2s
        cd = i2s * z2l
        ef = -v2r / i2r + z2l
        gh = z2l
        quadrado = np.abs(i2r) ** 2
        A = quadrado * abs(gh) ** 2 - np.abs(cd) ** 2
        B = (-2 * quadrado * (ef.real * gh.real + ef.imag * gh.imag)
             - 2 * (ab.real * cd.real + ab.imag * cd.imag))
        C = quadrado * np.abs(ef) ** 2 - np.abs(ab) ** 2
        delta = B * B - 4 * A * C
        raiz = np.sqrt(np.where(delta >= 0, delta, np.nan))
        # A forma estável de Bhaskara — ver `seqneg.localizar`.
        q = -0.5 * (B + np.where(B >= 0, raiz, -raiz))
        q = np.where(q == 0, np.nan, q)
        m1 = np.where(B >= 0, C / q, q / A)
        m2 = np.where(B >= 0, q / A, C / q)
    folga = seqneg.FOLGA
    ok1 = (m1 >= -folga) & (m1 <= 1 + folga)
    ok2 = (m2 >= -folga) & (m2 <= 1 + folga)
    m = np.where(ok1 & ~ok2, m1, np.where(ok2 & ~ok1, m2, np.nan))
    invalido = (np.abs(i2s) == 0) | (np.abs(i2r) == 0) | (A == 0) | ~np.isfinite(delta)
    return np.where(invalido, np.nan, m)


def k0(z1l: complex, z0l: complex) -> complex:
    """`(Z0L − Z1L) / (3·Z1L)` — a convenção dos slides (Cap. IV, 23–30)."""
    return (z0l - z1l) / (3.0 * z1l)


def laco_vetor(v: dict[str, np.ndarray], i: dict[str, np.ndarray], laco: str,
               z1l: complex, z0l: complex | None) -> np.ndarray | None:
    """`Im{V_laço / I_laço} / X1L`, amostra a amostra. `None` sem Z0 num laço de terra."""
    if laco.endswith("N"):
        if z0l is None:
            return None
        fase = laco[0]
        i_laco = i[fase] + k0(z1l, z0l) * (i["A"] + i["B"] + i["C"])
        v_laco = v[fase]
    else:
        f1, f2 = laco[0], laco[1]
        v_laco, i_laco = v[f1] - v[f2], i[f1] - i[f2]
    with np.errstate(divide="ignore", invalid="ignore"):
        return (v_laco / i_laco).imag / z1l.imag


def direcao_no_plato(v2: np.ndarray, i2: np.ndarray, z1l: complex,
                     onde: np.ndarray) -> bool | None:
    """A direção que vale para o PLATÔ inteiro: a da maioria das amostras.

    `None` quando não há I2 com que decidir (falta trifásica, platô vazio) ou
    quando o platô se divide — aí não se afirma nada.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        giro = (v2 / i2) * complex(math.cos(-math.atan2(z1l.imag, z1l.real)),
                                   math.sin(-math.atan2(z1l.imag, z1l.real)))
    real = np.real(giro[onde])
    real = real[np.isfinite(real)]
    if real.size == 0:
        return None
    frente = float(np.mean(real < 0))
    if frente >= 0.8:
        return True
    if frente <= 0.2:
        return False
    return None


def direcao(v2: complex, i2: complex, z1l: complex) -> bool | None:
    """`True` para frente (para a linha), `False` para trás, `None` sem I2."""
    if not (abs(i2) > 0 and math.isfinite(abs(v2))):
        return None
    giro = (v2 / i2) * complex(math.cos(-math.atan2(z1l.imag, z1l.real)),
                               math.sin(-math.atan2(z1l.imag, z1l.real)))
    return giro.real < 0


# ---------------------------------------------------------------------------
# O painel
# ---------------------------------------------------------------------------

def _mais_proximas(tempo: np.ndarray, alvo: np.ndarray) -> np.ndarray:
    """O índice da amostra de `tempo` mais perto de cada `alvo`; −1 fora dele.

    Sem interpolar: entre duas amostras não há medida (ver o CLAUDE.md).
    """
    if tempo.size == 0:
        return np.full(alvo.shape, -1, dtype=np.int64)
    j = np.clip(np.searchsorted(tempo, alvo), 1, tempo.size - 1)
    esquerda = tempo[j - 1]
    j = np.where(np.abs(alvo - esquerda) <= np.abs(tempo[j] - alvo), j - 1, j)
    meio = 0.5 * float(np.median(np.diff(tempo))) if tempo.size > 1 else 0.0
    fora = (alvo < tempo[0] - meio) | (alvo > tempo[-1] + meio)
    return np.where(fora, -1, j)


def _no(arr: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """`arr[idx]`, com NaN onde `idx` é −1."""
    saida = arr[np.clip(idx, 0, arr.size - 1)].astype(arr.dtype)
    return np.where(idx < 0, np.nan, saida)


def _ciclo_s(registro: Record) -> float:
    return 1.0 / registro.line_frequency if registro.line_frequency > 0 else 1.0 / 60.0


#: A falta acabou quando a corrente das fases com defeito volta para menos da
#: metade do caminho entre a pré-falta e o começo da falta.
FRACAO_DO_FIM = 0.5


def fim_da_falta(term: Terminal) -> float | None:
    """O instante em que a FALTA acaba, em segundos do registro, ou `None`.

    Não é a abertura do disjuntor: quem eliminou a falta pode ter sido o OUTRO
    terminal, e aí a corrente deste volta à carga em vez de ir a zero — e a
    abertura nunca aparece. Foi o que um registro real do COXIPO mostrou: sem
    isto o platô ia até o fim do arquivo, o cursor caía na carga, e o laço
    marcava −140 km com a direção «para trás».

    A conta é pelo MÓDULO da corrente das fases com defeito (o maior delas):
    a pré-falta é a mediana de um ciclo, terminando um ciclo antes do início;
    o começo da falta é a mediana do ciclo que começa 1,25 ciclo depois dele
    (a janela do fasor já cheia). A falta acaba na primeira amostra, depois
    disso, abaixo do meio do caminho entre os dois.
    """
    v, i = term.veredito, term.i
    if v is None or v.instante is None or i is None or not v.fases:
        return None
    t = term.registro.time
    ciclo = _ciclo_s(term.registro)
    inicio = float(t[v.instante])
    # `fmax` ignora o NaN do primeiro ciclo sem o aviso que o `nanmax` dá.
    modulo = np.fmax.reduce(np.vstack([np.abs(i[f]) for f in v.fases]), axis=0)

    def mediana(de: float, ate: float) -> float | None:
        trecho = modulo[(t >= de) & (t < ate)]
        trecho = trecho[np.isfinite(trecho)]
        return float(np.median(trecho)) if trecho.size else None
    antes = mediana(inicio - 2 * ciclo, inicio - ciclo)
    durante = mediana(inicio + 1.25 * ciclo, inicio + 2.25 * ciclo)
    if antes is None or durante is None or durante <= 1.2 * antes:
        return None       # sem salto claro na corrente: não dá para dizer
    limiar = antes + FRACAO_DO_FIM * (durante - antes)
    depois = (t > inicio + 1.25 * ciclo) & np.isfinite(modulo) & (modulo < limiar)
    achados = np.nonzero(depois)[0]
    return float(t[achados[0]]) if achados.size else None


def _plato(term: Terminal) -> tuple[float, float] | None:
    """`(t0, t1)` do platô, em segundos do registro, ou `None`.

    Acaba ¾ de ciclo antes do primeiro destes: o fim da falta
    (`fim_da_falta`) ou a abertura; sem nenhum dos dois, antes do fim do
    registro. Começa dois ciclos depois do início — ou 1,1 ciclo, numa falta
    curta demais para isso: a janela de um ciclo vale enquanto couber INTEIRA
    dentro da falta, e uma falta de 2,6 ciclos (o COXIPO real) não tem platô
    nenhum pela regra longa.
    """
    v = term.veredito
    if v is None or v.instante is None:
        return None
    t = term.registro.time
    ciclo = _ciclo_s(term.registro)
    inicio = float(t[v.instante])
    candidatos = [x for x in (fim_da_falta(term),
                              float(t[v.fim]) if v.fim is not None and v.fim < t.size else None)
                  if x is not None and x > inicio + ciclo]
    fim = min(candidatos) if candidatos else float(t[-1])
    t1 = fim - CICLOS_DEPOIS_DO_PLATO * ciclo
    for antes in (CICLOS_ANTES_DO_PLATO, CICLOS_ANTES_NA_FALTA_CURTA):
        t0 = inicio + antes * ciclo
        if t1 > t0:
            return (t0, t1)
    return None


def _polar(z: complex | None) -> dict | None:
    if z is None or not math.isfinite(abs(z)):
        return None
    return {"mod": abs(z), "ang": math.degrees(math.atan2(z.imag, z.real))}


def _ajeita(graus: float) -> float:
    g = (graus + 180.0) % 360.0 - 180.0
    return 180.0 if g == -180.0 else g


def _reduzida(tempo: np.ndarray, linhas: list[np.ndarray], colunas: int) -> dict:
    r = serie.reduzir(tempo, np.vstack(linhas), colunas)
    limpa = lambda a: [None if not math.isfinite(x) else round(float(x), 6) for x in a]  # noqa: E731
    return {"t": limpa(r.tempo), "v": [limpa(linha) for linha in r.valores]}


def _escala_simetrica(*arrays) -> dict:
    validos = [a for a in arrays if a.size and np.isfinite(a).any()]
    maior = max((float(np.nanmax(np.abs(a))) for a in validos), default=1.0) or 1.0
    lo, hi = escala.faixa(-maior, maior)
    return {"min": lo, "max": hi, "marcas": escala.marcacoes(lo, hi, 4)}


#: As contas pesadas da combinação aberta agora (registros, alinhamento, linha,
#: estimador, largura): andar com o cursor 1 refaz só a leitura dele. UMA
#: entrada só, de propósito — o servidor já caiu por falta de memória no
#: Windows, e o que fica guardado são poucas séries do tamanho do registro.
_GUARDADOS: dict = {}
_QUANTOS = 1
#: O Flask atende em várias threads: sem a trava, dois pedidos ao mesmo tempo
#: podiam esvaziar o dicionário juntos e o segundo `pop` estourava (500).
_TRAVA = threading.Lock()


def montar(reg_a: Record, reg_b: Record | None, d: float, linha: dict | None,
           t_cursor: float | None, colunas: int = 800, chave=None,
           colunas_ondas: int | None = None) -> dict:
    """O pacote do painel. `d`: o instante `t` de A cai em `t + d` em B.

    `linha` = `{r, x, km, r0?, x0?}` em ohm primário da linha inteira.
    `t_cursor` é o cursor 1, em segundos de A; sem ele, vale o meio do platô.
    `chave` identifica a combinação para guardar as contas pesadas; `None`
    refaz tudo (é o que os testes usam).
    """
    with _TRAVA:
        guardado = _GUARDADOS.get(chave) if chave is not None else None
    if guardado is None:
        term_a = terminal(reg_a)
        term_b = terminal(reg_b) if reg_b is not None else None
        guardado = _preparar(term_a, term_b, d, linha, colunas, colunas_ondas or colunas)
        if chave is not None:
            with _TRAVA:
                while len(_GUARDADOS) >= _QUANTOS:
                    _GUARDADOS.pop(next(iter(_GUARDADOS)))
                _GUARDADOS[chave] = guardado
    pacote, interno = guardado
    pacote = dict(pacote)
    pacote["cursor"] = _cursor(interno, linha, d, t_cursor) if interno else None
    return pacote


def _preparar(term_a: Terminal, term_b: Terminal | None, d: float, linha: dict | None,
              colunas: int, colunas_ondas: int) -> tuple[dict, dict | None]:
    pacote: dict = {"aviso": "", "metodos": {}, "resultado": None, "cursor": None,
                    "terminais": [{"letra": "A", "canais_v": term_a.canais_v,
                                   "canais_i": term_a.canais_i, "aviso": term_a.aviso}]}
    if term_b is not None:
        pacote["terminais"].append({"letra": "B", "canais_v": term_b.canais_v,
                                    "canais_i": term_b.canais_i, "aviso": term_b.aviso})
    reg_a = term_a.registro
    t_a = reg_a.time
    if term_a.v is None or term_a.i is None:
        pacote["aviso"] = f"IED A: {term_a.aviso}"
        return pacote, None
    v = term_a.veredito
    laco = v.laco if v is not None and v.tipo else ""
    pacote["tipo"] = v.tipo if v is not None else ""
    pacote["laco"] = laco
    if v is None or v.instante is None:
        pacote["aviso"] = "o IED A não mostra o início de uma falta"
        return pacote, None
    if term_b is not None and term_b.aviso:
        pacote["aviso"] = f"IED B: {term_b.aviso}"

    ciclo = _ciclo_s(reg_a)
    inicio = float(t_a[v.instante])
    plato_a = _plato(term_a)
    tem_b = term_b is not None and term_b.v is not None and term_b.i is not None
    idx_b = _mais_proximas(term_b.registro.time, t_a + d) if tem_b else None
    plato = plato_a
    if tem_b and plato is not None:
        plato_b = _plato(term_b)
        if plato_b is not None:
            # O platô de B, trazido para o tempo de A: os dois precisam estar
            # dentro da falta sustentada ao mesmo tempo.
            t0, t1 = max(plato[0], plato_b[0] - d), min(plato[1], plato_b[1] - d)
            plato = (t0, t1) if t1 > t0 else None
    pacote["eventos"] = {"inicio": inicio, "plato": list(plato) if plato else None,
                         "abre_a": (None if v.fim is None
                                    else float(t_a[min(v.fim, t_a.size - 1)])),
                         "fim_falta": fim_da_falta(term_a)}

    # A janela da tela: do pouco antes da falta ao pouco depois do platô.
    fim_plato = plato[1] if plato else inicio + 6 * ciclo
    j0 = int(np.searchsorted(t_a, inicio - 4 * ciclo))
    j1 = int(np.searchsorted(t_a, fim_plato + 6 * ciclo, side="right"))
    j1 = max(j0 + 2, min(j1, t_a.size))
    janela = slice(j0, j1)
    tj = t_a[janela]
    pacote["janela"] = [float(tj[0]), float(tj[-1])]
    # As marcações do eixo do tempo, em ms a partir do início da falta — o
    # mesmo «0» para os quatro gráficos do alinhamento e para a LDL.
    pacote["marcas_t"] = [{"t": inicio + ms / 1000.0, "ms": ms}
                          for ms in escala.marcacoes((tj[0] - inicio) * 1000.0,
                                                     (tj[-1] - inicio) * 1000.0, 6)]

    v2a, i2a = seq2(term_a.v), seq2(term_a.i)
    v2b = i2b = None
    if tem_b:
        v2b = _no(seq2(term_b.v), idx_b)
        i2b = _no(seq2(term_b.i), idx_b)

    # --- as curvas dos dois IEDs, já reduzidas por coluna de pixel
    def ondas(trinca_v, trinca_i, x2v, x2i, idx=None):
        pegar = (lambda a: a[janela]) if idx is None else (lambda a: _no(a, idx)[janela])
        inst = lambda trinca: [np.real(pegar(trinca[f])) * math.sqrt(2.0) for f in "ABC"]  # noqa: E731
        onda2 = lambda x2: np.real(x2[janela]) * math.sqrt(2.0)  # noqa: E731
        env2 = lambda x2: np.abs(x2[janela]) * math.sqrt(2.0)  # noqa: E731
        fi, fv = inst(trinca_i), inst(trinca_v)
        c = colunas_ondas

        def grandeza(fases, x2):
            return {"fases": _reduzida(tj, fases, c),
                    "seq": _reduzida(tj, [onda2(x2), env2(x2)], c),
                    "escala_fases": _escala_simetrica(*fases),
                    "escala_seq": _escala_simetrica(env2(x2))}
        return {"I": grandeza(fi, x2i), "V": grandeza(fv, x2v)}
    pacote["curvas"] = {"A": ondas(term_a.v, term_a.i, v2a, i2a)}
    if tem_b:
        pacote["curvas"]["B"] = ondas(term_b.v, term_b.i, v2b, i2b, idx_b)

    # --- os métodos
    series: dict[str, np.ndarray] = {}
    motivos: dict[str, str] = {}
    if linha is None:
        motivos = {m: "falta o parâmetro da linha" for m in METODOS}
    else:
        z1 = complex(linha["r"], linha["x"])
        z0 = (complex(linha["r0"], linha["x0"])
              if linha.get("r0") is not None and linha.get("x0") is not None else None)
        km = float(linha["km"])
        trifasica = set("ABC") <= set(pacote.get("tipo") or "")
        razao_i2 = _razao_i2(term_a, i2a, plato_a, t_a)
        if not tem_b:
            motivos["seqneg"] = "precisa da oscilografia do outro terminal"
        elif trifasica or (razao_i2 is not None and razao_i2 < MINIMO_I2_SOBRE_I1):
            motivos["seqneg"] = (
                "falta trifásica: não há sequência negativa para localizar"
                if trifasica else
                f"I2 é só {100 * razao_i2:.1f} % de I1 no platô — pouco para "
                "localizar pela sequência negativa".replace(".", ",", 1))
        else:
            series["seqneg"] = seqneg_vetor(v2a, i2a, v2b, i2b, z1) * km
        if not laco:
            motivos["laco"] = "o classificador não achou o laço da falta"
        else:
            m_laco = laco_vetor(term_a.v, term_a.i, laco, z1, z0)
            if m_laco is None:
                motivos["laco"] = "falta o Z0 da linha (para o k0 do laço de terra)"
            else:
                series["laco"] = m_laco * km
        pacote["km_linha"] = km

    # A LDL só existe DURANTE a falta: antes dela o laço mede a carga e dá um
    # número que não significa nada (e tem cara de distância), e depois do fim
    # da falta a corrente é carga ou fuga. Vai até um ciclo depois do fim (ou
    # da abertura), para se ver a curva saindo da linha — é assim que se
    # reconhece que a falta acabou.
    fins = [x for x in (pacote["eventos"]["abre_a"], pacote["eventos"]["fim_falta"])
            if x is not None and x > inicio + ciclo]
    fim_valido = min(fins) + ciclo if fins else t_a[-1]
    durante = (t_a >= inicio) & (t_a <= fim_valido)
    series = {m: np.where(durante, s, np.nan) for m, s in series.items()}

    no_plato = (t_a >= plato[0]) & (t_a <= plato[1]) if plato else np.zeros(t_a.size, bool)
    # O laço só precisa do IED A: o platô dele é o de A, não o comum aos dois
    # — com erro de relógio grande o comum encolhia a nada e o laço de A,
    # perfeito, saía «nenhum valor no platô».
    no_plato_a = ((t_a >= plato_a[0]) & (t_a <= plato_a[1]) if plato_a
                  else np.zeros(t_a.size, bool))
    # A direção (o 32Q), no platô de cada terminal: um deles vendo a falta
    # PARA TRÁS a põe fora da linha, e nenhum método vale — é a regra do
    # cabeçalho deste módulo, que o cursor mostrava e o resultado ignorava
    # (falta na barra do outro terminal saía «55,5 km ± 0,3»).
    atras = ""
    if linha is not None:
        z1_dir = complex(linha["r"], linha["x"])
        if direcao_no_plato(v2a, i2a, z1_dir, no_plato_a) is False:
            atras = "o IED A vê a falta PARA TRÁS"
        elif tem_b and direcao_no_plato(v2b, i2b, z1_dir, no_plato) is False:
            atras = "o IED B vê a falta PARA TRÁS"
    pacote["direcao"] = atras
    curvas_ldl = {}
    for metodo in METODOS:
        if metodo not in series:
            pacote["metodos"][metodo] = {"nome": NOMES[metodo], "curto": CURTOS[metodo],
                                         "km": None, "motivo": motivos.get(metodo, "")}
            continue
        s = series[metodo]
        valores = s[no_plato_a if metodo == "laco" else no_plato]
        valores = valores[np.isfinite(valores)]
        km_med = float(np.median(valores)) if valores.size else None
        disp = (float(np.percentile(valores, 90) - np.percentile(valores, 10)) / 2.0
                if valores.size else None)
        km = pacote["km_linha"]
        # Número fora da linha não é localização: é falta externa, falta para
        # trás ou platô errado. Aparece, com o porquê, e nunca vira resultado.
        folga = seqneg.FOLGA * km
        na_linha = km_med is not None and -folga <= km_med <= km + folga
        fora = km_med is not None and (not na_linha or bool(atras))
        motivo = ("nenhum valor no platô" if km_med is None
                  else f"{atras}: falta externa à linha — o {km_med:.1f} km não é "
                       "localização".replace(".", ",", 1) if atras
                  else f"deu {km_med:.1f} km: fora da linha — falta externa, para trás, "
                       "ou o platô não pegou a falta".replace(".", ",", 1) if fora else "")
        pacote["metodos"][metodo] = {"nome": NOMES[metodo], "curto": CURTOS[metodo],
                                     "km": km_med, "dispersao": disp, "fora": fora,
                                     "motivo": motivo}
        # A curva vai à tela limitada a ±1 LT além das pontas: um método que
        # diverge na entrada da falta marca milhares de km, e o que importa é
        # ver que ele saiu da linha, não quanto.
        curvas_ldl[metodo] = _reduzida(tj, [np.clip(s[janela], -km, 2 * km)], colunas)
    pacote["ldl"] = curvas_ldl
    if linha is not None:
        km = pacote["km_linha"]
        lo, hi = -0.05 * km, 1.1 * km
        pacote["escala_ldl"] = {"min": lo, "max": hi, "marcas": escala.marcacoes(0, km, 6)}

    # --- o resultado: a preferência fixa desta etapa
    valido = lambda m: (pacote["metodos"].get(m, {}).get("km") is not None  # noqa: E731
                        and not pacote["metodos"][m].get("fora"))
    escolhido = next((m for m in METODOS if valido(m)), None)
    if escolhido:
        info = pacote["metodos"][escolhido]
        pacote["resultado"] = {
            "metodo": escolhido, "km": info["km"],
            "faixa": max(FAIXA_MINIMA_KM, info["dispersao"] or 0.0),
            "conferencia": [{"metodo": m, "delta": pacote["metodos"][m]["km"] - info["km"]}
                            for m in METODOS if m != escolhido and valido(m)],
        }
        # A LDL «perto do resultado»: ±6 km em volta dele, com as marcações
        # daqui — quem escolhe escala é o servidor, não a tela.
        x = info["km"]
        pacote["escala_ldl_perto"] = {"min": x - 6.0, "max": x + 6.0,
                                      "marcas": escala.marcacoes(x - 6.0, x + 6.0, 6)}

    interno = {"t": t_a, "plato": plato, "no_plato": no_plato, "series": series,
               "v2a": v2a, "i2a": i2a, "v2b": v2b, "i2b": i2b}
    return pacote, interno


def _razao_i2(term: Terminal, i2: np.ndarray, plato, t: np.ndarray) -> float | None:
    """A mediana de |I2|/|I1| no platô, ou `None` sem platô."""
    if not plato:
        return None
    i1 = simetricas.de_fasores(term.i["A"], term.i["B"], term.i["C"])[1]
    onde = (t >= plato[0]) & (t <= plato[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.abs(i2[onde]) / np.abs(i1[onde])
    r = r[np.isfinite(r)]
    return float(np.median(r)) if r.size else None


def _cursor(interno: dict, linha: dict | None, d: float, t_cursor: float | None) -> dict | None:
    """O que o cursor 1 lê: V2 na referência, o ângulo de I2, a direção e o km."""
    t_a, plato, series = interno["t"], interno["plato"], interno["series"]
    if t_cursor is None and plato:
        t_cursor = (plato[0] + plato[1]) / 2.0
    if t_cursor is None:
        return None
    n = int(np.clip(np.searchsorted(t_a, t_cursor), 0, t_a.size - 1))
    if n > 0 and abs(t_a[n - 1] - t_cursor) <= abs(t_a[n] - t_cursor):
        n -= 1
    cur = {"t": float(t_a[n]), "no_plato": bool(interno["no_plato"][n]),
           "km": {m: (None if not math.isfinite(series[m][n]) else float(series[m][n]))
                  for m in series}}
    z1 = complex(linha["r"], linha["x"]) if linha else None

    def lado(v2, i2):
        if not (math.isfinite(abs(v2)) and math.isfinite(abs(i2))) or abs(i2) == 0:
            return None
        return {"v2": abs(v2), "i2": abs(i2),
                "ang": _ajeita(math.degrees(math.atan2(i2.imag, i2.real)
                                            - math.atan2(v2.imag, v2.real))),
                "frente": direcao(v2, i2, z1) if z1 is not None else None}
    cur["A"] = lado(complex(interno["v2a"][n]), complex(interno["i2a"][n]))
    if interno["v2b"] is not None:
        cur["B"] = lado(complex(interno["v2b"][n]), complex(interno["i2b"][n]))
        cur["t_b"] = float(t_a[n] + d)
    return cur


def linha_com_z0(fonte: dict | None) -> dict | None:
    """A linha que entra na conta, ou `None` quando a fonte não tem Z1."""
    if not fonte or not fonte.get("ok"):
        return None
    return {k: fonte.get(k) for k in ("r", "x", "km", "r0", "x0")}

