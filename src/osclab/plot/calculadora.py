"""A calculadora de sinais, além da onda: fasor, funções, nomes e modelos.

A gramática da ONDA mora em `plot/contas.py`. Aqui fica o resto, tudo no
Python, como manda o projeto (a tela só desenha o que sai daqui):

1. **funções de onda** — `atrasar(x; ms)`, `delta(x)`, `deriv(x)`, `integ(x)`,
   `rms(x)`, `media(x)`, `f60(x)`, `maxjan(x; ms)`. Ver `funcao_de_onda`.
2. **o domínio FASOR** — a mesma gramática sobre o fasor complexo de 60 Hz de
   cada sinal, amostra a amostra (a janela de um ciclo que TERMINA na amostra,
   a mesma de todo o programa). Operador `a`, `j`, `conj`, `mod`, `ang`, `re`,
   `im`, `polar(m; graus)`. É o que faz `Z = V ÷ I` e `S = V·I*`.
3. **modelos** — contas escritas com o nome PADRONIZADO (`[VA]`, `[IA]`,
   `[3I0]`), que valem em qualquer registro que tenha a trinca; e os modelos
   do usuário, guardados fora do registro.

## O GIRO, que decide se o ângulo é absoluto

O fasor que a DFT devolve gira a 60 Hz junto com o tempo. Numa razão (`V/I`)
ou num produto com conjugado (`V·I*`) o giro se cancela e o ângulo é físico —
o da impedância, o da potência. Num `V1` ele não cancela, e o ângulo só tem
sentido contra uma referência. Por isso a análise carrega o `giro` (quantos
fasores "em pé" sobraram: sinal +1, conjugado −1, produto soma, divisão
subtrai) e a leitura escreve o ângulo assim:

    giro 0   ângulo absoluto (Z, S)           «∠ 71,6°»
    giro 1   relativo à referência (VA)       «∠ −12,3° (ref. VA)»
    outro    não se escreve                   — e o aviso diz por quê

Somar dois termos de giro diferente (`V + V·I*`) é aviso, não erro.

## Antes de dividir, o denominador é medida ou é ruído?

Uma impedância depois de o disjuntor abrir é tensão sobre ZERO. A conta dá um
número enorme e plausível. Abaixo de 2 % do maior módulo que o denominador
teve no registro, o resultado vira BURACO (`NaN`) e o aviso diz isso — a mesma
regra do `DC %` (`fasor.MINIMO_FUNDAMENTAL`).
"""

from __future__ import annotations

import cmath
import json
import math
import re
from dataclasses import dataclass, field

import numpy as np

from osclab import paths
from osclab.dsp import envoltoria
from osclab.formats import fases
from osclab.formats import relacoes as relacoes_mod
from osclab.formats.base import Record
from osclab.plot import contas as contas_mod
from osclab.plot import conversao
from osclab.plot.contas import (
    ErroDaConta,
    _elevar,
    _escrever_unidade,
    _multiplicar,
    _No,
    _quebrar,
)

#: Abaixo desta fração do maior módulo do denominador, a divisão vira buraco.
PISO_DO_DENOMINADOR = 0.02

FUNCOES_DE_FASOR = {"conj": 1, "mod": 1, "ang": 1, "re": 1, "im": 1, "raiz": 1, "polar": 2}
OPERADOR_A = cmath.rect(1.0, math.radians(120.0))


# --------------------------------------------------------------------------
# 1. funções de onda
# --------------------------------------------------------------------------


def _atrasar(x: np.ndarray, ms: float, registro: Record) -> np.ndarray:
    """O sinal `ms` milissegundos atrás, INTERPOLADO entre as duas amostras.

    Um ciclo a 2000 Hz são 33,33 amostras: pegar a amostra mais próxima erra
    até meia amostra (5,4°), e `delta` de uma senoide parada deixaria 6 % do
    pico onde devia dar zero. Aqui é sinal calculado, não cursor — o cursor
    continua caindo sempre numa amostra. Antes do começo do registro, buraco.
    """
    t = registro.time
    alvo = t - ms / 1000.0
    return np.interp(alvo, t, np.asarray(x, dtype=np.float64), left=np.nan)


def funcao_de_onda(op: str, x: np.ndarray, numero: float, registro: Record) -> np.ndarray:
    """A função nova sobre a série inteira. Vetorizado: nada amostra a amostra."""
    x = np.asarray(x, dtype=np.float64)
    f = registro.line_frequency or 60.0
    if op == "atrasar":
        return _atrasar(x, numero, registro)
    if op == "delta":
        return x - _atrasar(x, 1000.0 / f, registro)
    if op == "deriv":
        return np.gradient(x, registro.time)
    if op == "integ":
        limpo = np.nan_to_num(x)
        passos = (limpo[1:] + limpo[:-1]) / 2.0 * np.diff(registro.time)
        return np.concatenate([[0.0], np.cumsum(passos)])
    if op in ("rms", "media", "f60"):
        grandeza = {"rms": "rms", "media": "dc", "f60": "filtrado"}[op]
        return envoltoria.calcular(x, registro.trechos, f, grandeza)
    if op == "maxjan":
        taxa = registro.trechos[0].taxa_hz if registro.trechos else 1000.0
        w = max(1, int(round(numero / 1000.0 * taxa)))
        if w >= x.size:
            return np.full_like(x, np.nanmax(np.abs(x)))
        v = np.lib.stride_tricks.sliding_window_view(np.abs(np.nan_to_num(x)), w)
        saida = np.full_like(x, np.nan)
        saida[w - 1 :] = v.max(axis=1)
        return saida
    raise ValueError(op)


# --------------------------------------------------------------------------
# 2. o domínio fasor
# --------------------------------------------------------------------------


@dataclass
class FasorAnalise:
    arvore: _No | None = None
    unidade: dict = field(default_factory=dict)
    unidade_escrita: str = ""
    giro: int | None = 1
    real: bool = False
    graus: bool = False
    fontes: tuple = ()
    canais: tuple = ()
    avisos: tuple = ()
    erro: str = ""
    relacoes: tuple = ()
    sem_relacao: tuple = ()
    alternado: bool = False
    dominios: tuple = ("modulo",)
    tem_produto: bool = False

    @property
    def vale(self) -> bool:
        return self.arvore is not None and not self.erro

    tem_onda = False
    e_onda = False


class _LeitorFasor:
    """A mesma gramática da onda, sobre complexos. Ver o cabeçalho."""

    def __init__(self, fichas, por_nome, por_grandeza, parametros):
        self.fichas, self.i = fichas, 0
        self.por_nome, self.por_grandeza = por_nome, por_grandeza
        self.parametros = parametros
        self.usados: list = []
        self.avisos: list[str] = []
        self.faltam: list[str] = []
        self.divide = False

    def olhar(self):
        return self.fichas[self.i] if self.i < len(self.fichas) else (None, None)

    def comer(self, valor=None):
        tipo, atual = self.olhar()
        if tipo is None:
            raise ErroDaConta("a conta termina no meio")
        if valor is not None and atual != valor:
            raise ErroDaConta(f"esperava «{valor}» e veio «{atual}»")
        self.i += 1
        return atual

    # Cada nó leva `.giro` além da unidade: ver o cabeçalho.
    def _no(self, op, filhos=(), numero=0.0, unidade=None, giro=0, sinal=None):
        no = _No(op, list(filhos), numero=numero, unidade=unidade or {}, sinal=sinal)
        no.giro = giro
        if op in ("+", "-", "*", "/", "neg", "pot") and filhos:

            def real_ou_numero(f):
                return getattr(f, "real", False) or (
                    f.op == "num" and abs(complex(f.numero).imag) < 1e-12
                )

            no.real = all(real_ou_numero(f) for f in filhos) and any(
                getattr(f, "real", False) for f in filhos
            )
        return no

    def expressao(self):
        no = self.termo()
        while self.olhar()[1] in ("+", "-"):
            op = self.comer()
            d = self.termo()
            unidade = no.unidade or d.unidade
            if (no.unidade or d.unidade) and no.unidade != d.unidade:
                e1 = _escrever_unidade(no.unidade, self.por_grandeza) or "número"
                e2 = _escrever_unidade(d.unidade, self.por_grandeza) or "número"
                self.avisos.append(f"somando {e1} com {e2}: o resultado sai sem unidade")
                unidade = {}
            giro = no.giro
            if (
                no.giro is None
                or d.giro is None
                or (no.giro != d.giro and no.unidade and d.unidade)
            ):
                self.avisos.append(
                    "somando um fasor que gira com um que não gira "
                    "(ex.: V com V·I*): o ângulo do resultado não se lê"
                )
                giro = None
            elif not no.unidade:
                giro = d.giro
            no = self._no(op, [no, d], unidade=unidade, giro=giro)
        return no

    def termo(self):
        no = self.fator()
        while self.olhar()[1] in ("*", "/"):
            op = self.comer()
            d = self.fator()
            g = (
                None
                if no.giro is None or d.giro is None
                else (no.giro + d.giro if op == "*" else no.giro - d.giro)
            )
            if op == "/":
                self.divide = self.divide or bool(d.unidade)
                un = _multiplicar(no.unidade, _elevar(d.unidade, -1))
            else:
                un = _multiplicar(no.unidade, d.unidade)
            no = self._no(op, [no, d], unidade=un, giro=g)
        return no

    def fator(self):
        if self.olhar()[1] == "-":
            self.comer()
            d = self.fator()
            return self._no("neg", [d], unidade=d.unidade, giro=d.giro)
        if self.olhar()[1] == "+":
            self.comer()
            return self.fator()
        base = self.primario()
        if self.olhar()[1] == "^":
            self.comer("^")
            tipo, valor = self.olhar()
            if tipo != "numero":
                raise ErroDaConta("o expoente tem que ser um número inteiro")
            self.comer()
            n = float(valor.replace(",", "."))
            if n != int(n) or not 1 <= int(n) <= 4:
                raise ErroDaConta("o expoente tem que ser inteiro, de 1 a 4")
            n = int(n)
            g = None if base.giro is None else base.giro * n
            return self._no("pot", [base], numero=n, unidade=_elevar(base.unidade, n), giro=g)
        return base

    def primario(self):
        tipo, valor = self.olhar()
        if tipo is None:
            raise ErroDaConta("a conta termina no meio")
        if valor == "(":
            self.comer("(")
            d = self.expressao()
            self.comer(")")
            return d
        if tipo == "numero":
            self.comer()
            return self._no("num", numero=complex(float(valor.replace(",", "."))))
        if tipo == "param":
            self.comer()
            nome = valor[1:-1]
            if nome not in self.parametros:
                self.faltam.append(nome)
                return self._no("num", numero=0j)
            return self._no("num", numero=complex(self.parametros[nome]))
        if tipo == "nome":
            self.comer()
            nome = valor[1:-1].strip()
            chave = contas_mod.chave_do_nome(nome)
            if chave not in self.por_nome:
                raise ErroDaConta(f"não existe sinal chamado «{nome}» neste registro")
            ref = self.por_nome[chave]
            if isinstance(ref, str):
                raise ErroDaConta(ref)
            if ref is None:
                raise ErroDaConta(f"há mais de um sinal chamado «{nome}»")
            if not _tem_fasor(ref):
                raise ErroDaConta(
                    f"«{nome}» é módulo (RMS, eficaz) ou não é senoide: no domínio "
                    "fasor use o canal — o fasor de 60 Hz é tirado dele"
                )
            self.usados.append(ref)
            from osclab.formats import fases

            g = fases.grandeza_da_unidade(str(ref.unidade).strip())
            giro = (
                getattr(ref.analise, "giro", 1) if isinstance(ref.analise, FasorAnalise) else 1
            )
            return self._no("sinal", unidade={g: 1} if g else {}, giro=giro, sinal=ref)
        if tipo == "funcao":
            if valor in ("a", "j"):
                self.comer()
                return self._no("num", numero=OPERADOR_A if valor == "a" else 1j)
            if valor not in FUNCOES_DE_FASOR:
                raise ErroDaConta(
                    f"não conheço «{valor}» no domínio fasor — tenho a, j, "
                    + ", ".join(FUNCOES_DE_FASOR)
                )
            self.comer()
            self.comer("(")
            d = self.expressao()
            segundo = None
            if FUNCOES_DE_FASOR[valor] == 2:
                self.comer(";")
                segundo = self.expressao()
            self.comer(")")
            if valor == "polar":
                return self._no("polar", [d, segundo], giro=0)
            if valor == "conj":
                return self._no(
                    "conj", [d], unidade=d.unidade, giro=None if d.giro is None else -d.giro
                )
            if valor == "raiz":
                return self._no(
                    "raiz", [d], unidade={k: v // 2 for k, v in d.unidade.items()}, giro=None
                )
            un = {} if valor == "ang" else d.unidade
            no = self._no(valor, [d], unidade=un, giro=0)
            no.real = True
            return no
        raise ErroDaConta(f"não esperava «{valor}» aqui")


def _tem_fasor(ref) -> bool:
    if isinstance(ref.analise, FasorAnalise):
        return not getattr(ref.analise, "real", False)
    if ref.analise is not None:
        return bool(ref.analise.alternado)
    if ref.sinal is None:
        return False
    from osclab.plot import fasorial

    return fasorial.tem_fasor(ref.sinal)


def analisar_fasor(
    expressao: str, registro: Record, por_nome: dict, parametros=(), relacoes=()
) -> FasorAnalise:
    # No domínio fasor a conta corre em V e A SEM prefixo: um arquivo em kV com
    # corrente em A daria `kV/A` (que é kΩ) no lugar de Ω. Cada folha é trazida
    # para a unidade de base em `_fasor_da_ref`, e o prefixo volta no fim.
    por_grandeza = {"V": "V", "I": "A"}
    try:
        leitor = _LeitorFasor(
            _quebrar(expressao),
            por_nome,
            por_grandeza,
            {n: complex(r, i) for n, r, i, *_ in parametros},
        )
        arvore = leitor.expressao()
        if leitor.i != len(leitor.fichas):
            raise ErroDaConta(f"sobrou «{leitor.fichas[leitor.i][1]}» no fim da conta")
        if leitor.faltam:
            nomes = ", ".join("{" + n + "}" for n in dict.fromkeys(leitor.faltam))
            raise ErroDaConta(f"falta o valor de {nomes} — digite-o no campo ao lado")
    except ErroDaConta as erro:
        return FasorAnalise(erro=str(erro))
    except RecursionError:
        return FasorAnalise(erro="a conta tem parênteses demais")
    if not leitor.usados:
        return FasorAnalise(
            erro="a conta não usa nenhum sinal — escreva o nome entre colchetes"
        )
    avisos = list(leitor.avisos)
    if leitor.divide:
        avisos.append(
            "onde o de baixo cai abaixo de 2 % do maior valor dele no registro "
            "(disjuntor aberto), o resultado vira buraco"
        )
    sem = contas_mod._sem_relacao(registro, leitor.usados, relacoes)
    for i in sem:
        nome = next((c.name for c in registro.analog_channels if c.index == i), str(i))
        avisos.append(f"«{nome}» não tem relação de TC/TP declarada: entra sem converter")
    real = bool(getattr(arvore, "real", False))
    unidade_escrita = (
        "°" if arvore.op == "ang" else _escrever_unidade(arvore.unidade, por_grandeza)
    )
    return FasorAnalise(
        arvore=arvore,
        unidade=arvore.unidade,
        unidade_escrita=unidade_escrita,
        giro=arvore.giro,
        real=real,
        graus=arvore.op == "ang",
        fontes=tuple(dict.fromkeys(r.linha for r in leitor.usados)),
        canais=tuple(dict.fromkeys(r.canal for r in leitor.usados if r.canal >= 0)),
        avisos=tuple(dict.fromkeys(avisos)),
        relacoes=tuple(relacoes),
        sem_relacao=sem,
    )


_PREFIXOS = {"k": 1e3, "M": 1e6, "m": 1e-3}


def _fasor_da_ref(ref, registro: Record, lado: str) -> np.ndarray:
    n = registro.n_samples
    if isinstance(ref.analise, FasorAnalise):
        return serie_fasor(registro, ref.analise, lado)
    if ref.analise is not None:
        onda = contas_mod.serie(registro, ref.analise, lado, 1.0)
        u = str(ref.unidade).strip()
        fator = _PREFIXOS.get(u[:1], 1.0) if len(u) > 1 and u[1:2] in ("V", "A") else 1.0
        return (
            fator
            * envoltoria.calcular_fasores(onda[:n], registro.trechos, registro.line_frequency)
            / math.sqrt(2.0)
        )
    from osclab.plot import complexo

    z = complexo.fasores_do_sinal(registro, ref.sinal, lado, {})
    if z is not None:
        u = str(ref.unidade).strip()
        if len(u) > 1 and u[1:2] in ("V", "A"):
            z = z * _PREFIXOS.get(u[:1], 1.0)
    if z is None:
        return np.full(n, np.nan + 0j)
    razao = contas_mod._RELACOES_ATIVAS.get(getattr(ref, "canal", -1))
    canal = next((c for c in registro.analog_channels
                  if c.index == getattr(ref, "canal", -1)), None)
    # A da conta só vale para canal SEM relação: com uma digitada no registro a
    # série já veio convertida. Ver `contas._serie_do_sinal`.
    if razao and (canal is None or conversao.relacao(canal) <= 0):
        natural = "primario" if canal is not None and canal.is_primary else "secundario"
        if lado == "primario" and natural == "secundario":
            z = z * razao
        elif lado == "secundario" and natural == "primario":
            z = z / razao
    return z


def _avaliar_fasor(no, registro: Record, lado: str):
    n = registro.n_samples
    if no.op == "num":
        return np.full(n, complex(no.numero))
    if no.op == "sinal":
        return _fasor_da_ref(no.sinal, registro, lado)
    filhos = [_avaliar_fasor(f, registro, lado) for f in no.filhos]
    if no.op == "neg":
        return -filhos[0]
    if no.op == "pot":
        return filhos[0] ** int(no.numero)
    if no.op == "conj":
        return np.conj(filhos[0])
    if no.op == "mod":
        return np.abs(filhos[0]).astype(np.complex128)
    if no.op == "ang":
        return np.degrees(np.angle(filhos[0])).astype(np.complex128)
    if no.op == "re":
        return np.real(filhos[0]).astype(np.complex128)
    if no.op == "im":
        return np.imag(filhos[0]).astype(np.complex128)
    if no.op == "raiz":
        return np.sqrt(filhos[0])
    if no.op == "polar":
        m, g = np.real(filhos[0]), np.real(filhos[1])
        return m * np.exp(1j * np.radians(g))
    a, b = filhos
    if no.op == "+":
        return a + b
    if no.op == "-":
        return a - b
    if no.op == "*":
        return a * b
    if no.op == "/":
        mod_b = np.abs(b)
        teto = np.nanmax(mod_b) if np.isfinite(mod_b).any() else 0.0
        bom = np.isfinite(mod_b) & (mod_b > PISO_DO_DENOMINADOR * teto)
        saida = np.full(n, np.nan + 0j)
        saida[bom] = a[bom] / b[bom]
        return saida
    raise ValueError(no.op)


def serie_fasor(registro: Record, analise: FasorAnalise, lado: str) -> np.ndarray | None:
    """O resultado complexo (ou real) em cada amostra, sem o prefixo da tela."""
    if not analise.vale:
        return None
    antes = contas_mod._RELACOES_ATIVAS
    contas_mod._RELACOES_ATIVAS = dict(analise.relacoes)
    try:
        with np.errstate(all="ignore"):
            return _avaliar_fasor(analise.arvore, registro, lado)
    finally:
        contas_mod._RELACOES_ATIVAS = antes


def curva_do_fasor(
    registro: Record, analise: FasorAnalise, lado: str, divisor: float
) -> np.ndarray | None:
    """O que o gráfico desenha: o módulo (ou o valor, quando a conta já é real)."""
    z = serie_fasor(registro, analise, lado)
    if z is None:
        return None
    y = np.real(z) if analise.real else np.abs(z)
    return y / (divisor or 1.0)


# --------------------------------------------------------------------------
# 3. a análise das duas, para a tela
# --------------------------------------------------------------------------


def analisar_conta(conta, registro: Record, por_nome: dict):
    if conta.dominio == "fasor":
        return analisar_fasor(
            conta.expressao, registro, por_nome, conta.parametros, conta.relacoes
        )
    return contas_mod.analisar_com(
        conta.expressao, registro, por_nome, conta.parametros, conta.relacoes
    )


def mapa_ate(registro: Record, contas: list, ate_id: str | None):
    """O mapa de nomes com as contas ANTERIORES a `ate_id` (ou todas)."""
    mapa = contas_mod._do_catalogo(registro)
    for c in contas:
        if c.id == ate_id:
            break
        a = analisar_conta(c, registro, mapa)
        chave = contas_mod.chave_do_nome(c.nome)
        if not chave or not a.vale:
            continue
        if chave in mapa:
            mapa[chave] = None
            continue
        mapa[chave] = contas_mod.Referencia(
            linha=c.nome,
            unidade=a.unidade_escrita,
            grandeza="instantaneo",
            bloco="alternado" if a.alternado else "outros",
            analise=a,
        )
    return mapa


def _amostra(registro: Record, t: float | None) -> int | None:
    if t is None or registro.n_samples == 0:
        return None
    i = int(np.searchsorted(registro.time, t))
    i = min(max(i, 0), registro.n_samples - 1)
    if i > 0 and abs(registro.time[i - 1] - t) < abs(registro.time[i] - t):
        i -= 1
    return i


def _txt(v: float | None, unidade: str = "") -> str:
    if v is None or not math.isfinite(v):
        return "—"
    from osclab.plot import leitura

    casas = leitura.casas(v)
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s.replace('-', '−')} {unidade}".strip()


def _escala(escalas: dict, unidade: str, serie) -> tuple[float, str]:
    """O divisor e a unidade mostrada. O prefixo é do REGISTRO, não do valor:
    a unidade não pode piscar enquanto o cursor anda (`plot/unidades.py`)."""
    if unidade in escalas:
        return escalas[unidade]
    if unidade in ("V", "A") and f"k{unidade}" in escalas:
        # Conta de fasor em V num arquivo em kV: o mesmo prefixo da tela, ×1000.
        divisor, mostrada = escalas[f"k{unidade}"]
        return divisor * 1e3, mostrada
    if "V·A" in unidade and serie is not None:
        finitos = np.abs(np.asarray(serie))[np.isfinite(np.asarray(serie))]
        teto = float(finitos.max()) if finitos.size else 0.0
        for limiar, divisor, prefixo in ((1e7, 1e6, "M"), (1e4, 1e3, "k")):
            if teto >= limiar:
                return divisor, unidade.replace("V·A", f"{prefixo}V·A", 1)
    return 1.0, unidade


def _ang(g: float | None) -> str:
    if g is None or not math.isfinite(g):
        return "—"
    g = (g + 180.0) % 360.0 - 180.0
    return f"{g:.1f}°".replace(".", ",").replace("-", "−")


def _referencia(registro: Record, lado: str):
    """O zero dos ângulos, por SIGNIFICADO: tensão A → corrente A → nada."""
    from osclab.plot import catalogo, complexo

    for fund in ("VA", "IA"):
        for s in catalogo.de_registro(registro, "arquivo"):
            if s.familia == "canal" and s.fundamental == fund and s.bloco == "alternado":
                return s.nome, complexo.fasores_do_sinal(registro, s, lado, {})
    return "", None


def valores(registro: Record, contas: list, lado: str, instantes) -> list[dict]:
    """Cada conta nos cursores: valor (onda) ou módulo∠ângulo (fasor), já escrito."""
    from osclab.plot import unidades

    escalas = unidades.por_unidade(registro, lado)
    idx = [_amostra(registro, t) for t in instantes]
    nome_ref, ref = _referencia(registro, lado)
    mapa = contas_mod._do_catalogo(registro)
    saida = []
    for c in contas:
        a = analisar_conta(c, registro, mapa)
        chave = contas_mod.chave_do_nome(c.nome)
        if chave and a.vale and chave not in mapa:
            mapa[chave] = contas_mod.Referencia(
                linha=c.nome,
                unidade=a.unidade_escrita,
                grandeza="instantaneo",
                bloco="alternado" if a.alternado else "outros",
                analise=a,
            )
        linha = {
            "id": c.id,
            "nome": c.nome,
            "dominio": c.dominio,
            "vale": a.vale,
            "erro": a.erro,
            "avisos": list(a.avisos),
            "fontes": list(a.fontes),
            "giro": getattr(a, "giro", None),
            "real": getattr(a, "real", False),
        }
        if a.vale:
            z = serie_fasor(registro, a, lado) if c.dominio == "fasor" else None
            divisor, mostrada = _escala(
                escalas, a.unidade_escrita, np.abs(z) if z is not None else None
            )
            linha["unidade"] = mostrada
            celulas = []
            if c.dominio == "fasor":
                for i in idx:
                    if i is None or z is None:
                        celulas.append(None)
                        continue
                    v = z[i]
                    if a.real:
                        celulas.append({"valor": _txt(float(np.real(v)) / divisor, mostrada)})
                        continue
                    m = abs(v) / divisor
                    if a.giro == 0:
                        g, qual = math.degrees(cmath.phase(v)), ""
                    elif (
                        a.giro == 1
                        and ref is not None
                        and np.isfinite(ref[i])
                        and abs(ref[i]) > 0
                    ):
                        g, qual = (
                            math.degrees(cmath.phase(v) - cmath.phase(ref[i])),
                            f"ref. {nome_ref}",
                        )
                    else:
                        g, qual = None, "ângulo sem referência"
                    celulas.append(
                        {
                            "valor": _txt(m, mostrada),
                            "angulo": _ang(g) if np.isfinite(m) else "—",
                            "qual": qual,
                            "retangular": (
                                _txt(float(np.real(v)) / divisor)
                                + " "
                                + ("+" if np.imag(v) >= 0 else "−")
                                + " j"
                                + _txt(abs(float(np.imag(v))) / divisor, mostrada)
                            )
                            if np.isfinite(v) and a.giro == 0
                            else "",
                        }
                    )
            else:
                onda = contas_mod.serie(registro, a, lado, 1.0)
                fas = (
                    (
                        envoltoria.calcular_fasores(
                            onda, registro.trechos, registro.line_frequency
                        )
                        / math.sqrt(2.0)
                    )
                    if onda is not None and a.alternado
                    else None
                )
                for i in idx:
                    if i is None or onda is None:
                        celulas.append(None)
                        continue
                    cel = {"valor": _txt(float(onda[i]) / divisor, mostrada)}
                    if fas is not None and np.isfinite(fas[i]):
                        g = None
                        if ref is not None and np.isfinite(ref[i]) and abs(ref[i]) > 0:
                            g = math.degrees(cmath.phase(fas[i]) - cmath.phase(ref[i]))
                        cel["fasor"] = f"{_txt(abs(fas[i]) / divisor, mostrada)} ∠ {_ang(g)}"
                    celulas.append(cel)
            linha["celulas"] = celulas
        saida.append(linha)
    return saida


def previa(registro: Record, conta, contas: list, lado: str, colunas: int = 320) -> dict:
    """A curva da conta sobre o registro INTEIRO, reduzida por mínimo e máximo."""
    from osclab.plot import serie as serie_mod
    from osclab.plot import unidades

    escalas = unidades.por_unidade(registro, lado)
    mapa = mapa_ate(registro, contas, conta.id)
    a = analisar_conta(conta, registro, mapa)
    canais = {c.index: c for c in registro.analog_channels}
    resposta = {
        "vale": a.vale,
        "erro": a.erro,
        "avisos": list(a.avisos),
        "dominio": conta.dominio,
        "fontes": list(a.fontes),
        # A expressão com os nomes COMPLETOS: `[IA]` digitado vira o
        # canal por trás, para o visor dizer qual entrou na conta.
        "expandida": expandir(conta.expressao, registro),
        # Os canais da conta que o arquivo não declara relação, e os que já
        # têm uma DIGITADA (para o campo continuar ali, preenchido e
        # corrigível). O que se digita aqui é gravado NO REGISTRO — vale para
        # o canal em toda a tela, não só nesta conta. Ver `formats/relacoes`.
        "sem_relacao": [
            {"canal": i, "nome": canais[i].name,
             "grandeza": fases.grandeza_da_unidade(canais[i].unit) or "",
             "digitada": (relacoes_mod.como_texto((canais[i].primary, canais[i].secondary))
                          if getattr(canais[i], "relacao_digitada", False) else "")}
            for i in dict.fromkeys(a.canais)
            if i in canais and (conversao.relacao(canais[i]) <= 0
                                or getattr(canais[i], "relacao_digitada", False))
        ]
        if a.vale
        else [],
    }
    if not a.vale:
        return resposta
    divisor, mostrada = escalas.get(a.unidade_escrita, (1.0, a.unidade_escrita))
    if conta.dominio == "fasor":
        z = serie_fasor(registro, a, lado)
        divisor, mostrada = _escala(
            escalas, a.unidade_escrita, np.abs(z) if z is not None else None
        )
        y = curva_do_fasor(registro, a, lado, divisor)
        resposta.update(giro=a.giro, real=a.real, mostra="módulo" if not a.real else "valor")
    else:
        y = contas_mod.serie(registro, a, lado, divisor)
        resposta.update(mostra="onda", alternado=a.alternado)
    resposta["unidade"] = mostrada
    if y is None:
        return resposta
    r = serie_mod.reduzir(registro.time, np.asarray(y, dtype=float)[None, :], colunas)
    vals = np.asarray(r.valores, dtype=float)[0]
    finitos = vals[np.isfinite(vals)]
    lo, hi = (float(finitos.min()), float(finitos.max())) if finitos.size else (0.0, 1.0)
    if hi <= lo:
        hi = lo + 1.0
    resposta.update(
        t=[round(float(x), 6) for x in r.tempo],
        y=[None if not math.isfinite(v) else round(float(v), 6) for v in vals],
        y0=lo,
        y1=hi,
        t0=float(registro.time[0]),
        t1=float(registro.time[-1]),
        faixa=f"{_txt(lo)} a {_txt(hi, mostrada)}",
    )
    return resposta


# --------------------------------------------------------------------------
# 4. modelos
# --------------------------------------------------------------------------

#: Os modelos que vêm com o programa. `[IA]` é a fase A da trinca de corrente
#: escolhida; `[IA#2]` a da SEGUNDA trinca de corrente (diferencial).
MODELOS = [
    # id, categoria, nome, domínio, expressão, parâmetros, para quê
    (
        "zag",
        "Impedância",
        "Zap AG",
        "fasor",
        "[VA] / ([IA] + {k0} * [3I0])",
        ("k0",),
        "laço fase-terra com compensação de sequência zero",
    ),
    (
        "zbg",
        "Impedância",
        "Zap BG",
        "fasor",
        "[VB] / ([IB] + {k0} * [3I0])",
        ("k0",),
        "laço fase-terra B",
    ),
    (
        "zcg",
        "Impedância",
        "Zap CG",
        "fasor",
        "[VC] / ([IC] + {k0} * [3I0])",
        ("k0",),
        "laço fase-terra C",
    ),
    (
        "zab",
        "Impedância",
        "Zap AB",
        "fasor",
        "([VA] - [VB]) / ([IA] - [IB])",
        (),
        "laço fase-fase AB",
    ),
    (
        "zbc",
        "Impedância",
        "Zap BC",
        "fasor",
        "([VB] - [VC]) / ([IB] - [IC])",
        (),
        "laço fase-fase BC",
    ),
    (
        "zca",
        "Impedância",
        "Zap CA",
        "fasor",
        "([VC] - [VA]) / ([IC] - [IA])",
        (),
        "laço fase-fase CA",
    ),
    (
        "s3",
        "Potência",
        "S trifásica",
        "fasor",
        "[VA] * conj([IA]) + [VB] * conj([IB]) + [VC] * conj([IC])",
        (),
        "potência complexa: módulo na curva, ângulo é o do fator de potência",
    ),
    (
        "p3",
        "Potência",
        "P trifásica",
        "fasor",
        "re([VA] * conj([IA]) + [VB] * conj([IB]) + [VC] * conj([IC]))",
        (),
        "potência ativa",
    ),
    (
        "q3",
        "Potência",
        "Q trifásica",
        "fasor",
        "im([VA] * conj([IA]) + [VB] * conj([IB]) + [VC] * conj([IC]))",
        (),
        "potência reativa",
    ),
    (
        "fp",
        "Potência",
        "FP fase A",
        "fasor",
        "re([VA] * conj([IA])) / mod([VA] * conj([IA]))",
        (),
        "fator de potência da fase A",
    ),
    (
        "i2i1",
        "Sequência",
        "I2/I1 (%)",
        "fasor",
        "100 * mod([I2]) / mod([I1])",
        (),
        "desequilíbrio de corrente — condutor partido, fase aberta",
    ),
    (
        "v2v1",
        "Sequência",
        "V2/V1 (%)",
        "fasor",
        "100 * mod([V2]) / mod([V1])",
        (),
        "desequilíbrio de tensão",
    ),
    (
        "v1a",
        "Sequência",
        "V1 pelo operador a",
        "fasor",
        "([VA] + a * [VB] + a^2 * [VC]) / 3",
        (),
        "a sequência positiva escrita à mão — confere com o V1 do OscLab",
    ),
    (
        "dia",
        "Onda",
        "ΔIA (incremental)",
        "onda",
        "delta([IA])",
        (),
        "IA menos IA de um ciclo atrás: zero em regime, salta na falta",
    ),
    (
        "didt",
        "Onda",
        "dIA/dt",
        "onda",
        "deriv([IA])",
        (),
        "derivada — degrau de saturação de TC aparece como pico",
    ),
    (
        "pa",
        "Onda",
        "p(t) fase A",
        "onda",
        "[VA] * [IA]",
        (),
        "potência instantânea: oscila em 120 Hz em torno de P",
    ),
    (
        "vff",
        "Onda",
        "VAB ÷ √3",
        "onda",
        "([VA] - [VB]) / raiz(3)",
        (),
        "tensão de linha em base fase-terra",
    ),
    (
        "dif",
        "Diferencial",
        "Idif A (dois lados)",
        "fasor",
        "mod([IA] + {k} * [IA#2])",
        ("k",),
        "soma dos dois lados, com o casamento {k} (relação e defasagem) digitado",
    ),
]


def _grupos_por_grandeza(registro: Record) -> dict:
    from osclab.plot import catalogo

    grupos = {"I": [], "V": []}
    for s in catalogo.de_registro(registro, "arquivo"):
        if (
            s.familia == "canal"
            and s.grupo
            and s.fundamental[:1] in ("I", "V")
            and s.bloco == "alternado"
            and s.grupo not in grupos[s.fundamental[0]]
        ):
            grupos[s.fundamental[0]].append(s.grupo)
    return grupos


_NOME_DO_MODELO = re.compile(r"\[([^\]#]+?)(?:#(\d))?\]")


def instanciar(expressao: str, escolha: dict) -> str:
    """`[IA]` → `[IA G2]`, `[IA#2]` → `[IA G1]` pelos grupos escolhidos."""

    def troca(m):
        nome, n = m.group(1).strip(), m.group(2) or "1"
        g = "V" if re.match(r"\d*V", nome) else "I"
        grupo = escolha.get(f"{g}{n}")
        return f"[{nome} {grupo}]" if grupo else m.group(0)

    return _NOME_DO_MODELO.sub(troca, expressao)


def _vagas(expressao: str) -> list[str]:
    vagas = []
    for m in _NOME_DO_MODELO.finditer(expressao):
        g = "V" if re.match(r"\d*V", m.group(1).strip()) else "I"
        v = f"{g}{m.group(2) or '1'}"
        if v not in vagas:
            vagas.append(v)
    return sorted(vagas)


def _arquivo_de_modelos():
    """Os modelos do usuário: FORA do registro, para valerem em qualquer um."""
    return paths.MODELOS_DA_CALCULADORA


def id_de_modelo(nome: str, expressao: str) -> str:
    """Um id ESTÁVEL para o modelo do usuário (o `hash` do Python muda a cada
    processo, e o mesmo modelo guardado duas vezes viraria dois)."""
    import hashlib

    return "u" + hashlib.sha1(f"{nome}|{expressao}".encode()).hexdigest()[:10]


def modelos_do_usuario() -> list[dict]:
    try:
        return json.loads(_arquivo_de_modelos().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def guardar_modelo(m: dict) -> list[dict]:
    lista = [x for x in modelos_do_usuario() if x.get("id") != m.get("id")]
    lista.append(m)
    _arquivo_de_modelos().write_text(
        json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return lista


def apagar_modelo(ident: str) -> list[dict]:
    lista = [x for x in modelos_do_usuario() if x.get("id") != ident]
    _arquivo_de_modelos().write_text(
        json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return lista


def modelos(registro: Record, lado: str) -> dict:
    """Os modelos, cada um dizendo se cabe NESTE registro e com que grupos."""
    grupos = _grupos_por_grandeza(registro)
    mapa = contas_mod._do_catalogo(registro)
    todos = [
        dict(
            id=i,
            categoria=cat,
            nome=n,
            dominio=d,
            expressao=e,
            parametros=list(p),
            descricao=desc,
            de="OscLab",
        )
        for i, cat, n, d, e, p, desc in MODELOS
    ]
    for m in modelos_do_usuario():
        todos.append(dict(m, de="seu"))
    saida = []
    for m in todos:
        vagas = _vagas(m["expressao"])
        opcoes = {}
        motivo = ""
        for v in vagas:
            lista = grupos.get(v[0], [])
            k = int(v[1:]) - 1
            if k >= len(lista):
                motivo = (
                    f"o registro não tem {'segunda ' if k else ''}trinca de "
                    f"{'tensão' if v[0] == 'V' else 'corrente'}"
                )
                break
            opcoes[v] = lista
        escolha = {v: opcoes[v][int(v[1:]) - 1] for v in opcoes} if not motivo else {}
        expr = instanciar(m["expressao"], escolha) if not motivo else m["expressao"]
        if not motivo:
            params = tuple((p, 1.0, 0.0, "teste") for p in m.get("parametros") or ())
            conta = contas_mod.Conta(
                id="x9999",
                nome=m["nome"],
                expressao=expr,
                dominio=m["dominio"],
                parametros=params,
            )
            a = analisar_conta(conta, registro, mapa)
            if not a.vale:
                motivo = a.erro
        saida.append(
            dict(
                m,
                cabe=not motivo,
                motivo=motivo,
                vagas=vagas,
                opcoes=opcoes,
                escolha=escolha,
                # Já com os nomes COMPLETOS: é o que o visor mostra.
                instanciada=expandir(expr, registro) if not motivo else expr,
            )
        )
    return {"modelos": saida, "grupos": grupos}


def generalizar(expressao: str, registro: Record) -> dict:
    """`[Current IA]` → `[IA]`: o modelo que vale para outro fabricante.

    Só troca o que tem vínculo de fase e grupo; o resto fica como está, e a
    resposta diz quais nomes não se generalizaram (o modelo continua valendo
    só onde eles existirem).
    """
    from osclab.plot import catalogo

    por_nome = {}
    for s in catalogo.de_registro(registro, "arquivo"):
        if s.familia == "canal" and s.fundamental and s.grupo:
            por_nome[contas_mod.chave_do_nome(s.nome)] = (s.fundamental, s.grupo)
        m = re.fullmatch(r"(.+) (G\d+)", s.linha or "")
        if m and s.nome == s.linha:
            por_nome[contas_mod.chave_do_nome(s.nome)] = (m.group(1), m.group(2))
    grupos_vistos: dict = {}
    presos = []

    def troca(m):
        nome = m.group(1).strip()
        achado = por_nome.get(contas_mod.chave_do_nome(nome))
        if not achado:
            presos.append(nome)
            return m.group(0)
        base, grupo = achado
        g = "V" if re.match(r"\d*V", base) else "I"
        ordem = grupos_vistos.setdefault(g, [])
        if grupo not in ordem:
            ordem.append(grupo)
        n = ordem.index(grupo) + 1
        return f"[{base}]" if n == 1 else f"[{base}#{n}]"

    saida = re.sub(r"\[([^\]\[]{1,60})\]", troca, expressao)
    return {"expressao": saida, "presos": presos}


def ajustes_sugeridos(ajustes) -> dict:
    """O k0 que o RELÉ diz, com a origem — atalho; o campo digitado fica ao lado."""
    from osclab.plot import impedancia

    if not ajustes:
        return {}
    k0 = impedancia.k0_de(impedancia.como_dicionario(ajustes.get("ajustes")))
    if not k0:
        return {}
    z, origem, como = k0
    return {
        "k0": {
            "mod": round(abs(z), 4),
            "ang": round(math.degrees(cmath.phase(z)), 2),
            "origem": "lido do relé" if origem == "lido" else "calculado do relé",
            "como": como,
        }
    }


#: As oito teclas da FILEIRA de sinais, sempre com o nome padronizado.
FILEIRA = ("IA", "IB", "IC", "IN", "VA", "VB", "VC", "VN")


def expandir(expressao: str, registro: Record) -> str:
    """`[IA]` → `[Current IA]`: o nome COMPLETO do que está por trás.

    O usuário tem de ver no visor qual canal entrou na conta — `[IA]` num trafo
    não diz qual dos dois lados. O que não tem nome por trás (o resíduo
    `IN G1`, a componente `3I0 G1`) já está escrito como o catálogo o chama, e
    fica. Nome que não existe também fica: quem diz o erro é a análise.
    """
    mapa = contas_mod._do_catalogo(registro)

    def troca(m):
        ref = mapa.get(contas_mod.chave_do_nome(m.group(1)))
        if ref is None or isinstance(ref, str) or not getattr(ref, "linha", ""):
            return m.group(0)
        return f"[{ref.linha}]"

    return re.sub(r"\[([^\]\[]{1,60})\]", troca, expressao)


def nomes(registro: Record) -> dict:
    """O que a gaveta oferece para escrever entre colchetes.

    - `sinais`: a lista da tecla «[ ]» — o nome do arquivo (ou o do OscLab, no
      que é conta nossa) e, numa coluna à parte, o padronizado com o grupo;
    - `fileira`: as oito teclas IA…VN. A tecla mostra o nome padronizado e
      INSERE o nome completo do canal por trás, por grupo;
    - `grupos`: os grupos de cada grandeza, para o seletor «G1 | G2»;
    - `completar`: tudo que o Tab completa.
    """
    from osclab.plot import catalogo

    mapa = contas_mod._do_catalogo(registro)
    sinais, vistos = [], set()
    padrao_de: dict[str, str] = {}
    for chave, ref in mapa.items():
        if ref is None or isinstance(ref, str):
            continue
        if chave != contas_mod.chave_do_nome(ref.linha) and re.search(r" G\d+$", chave):
            padrao_de.setdefault(ref.linha, chave)
    grupos = _grupos_por_grandeza(registro)
    for s in catalogo.de_registro(registro, "arquivo"):
        if s.nome != (s.linha or s.nome) or s.nome in vistos:
            continue
        ref = mapa.get(contas_mod.chave_do_nome(s.nome))
        if ref is None or isinstance(ref, str):
            continue
        vistos.add(s.nome)
        sinais.append(
            {
                "escrever": s.nome,
                "padrao": padrao_de.get(s.nome, ""),
                "fasor": _tem_fasor(ref),
                "canal": s.familia == "canal",
            }
        )
    fileira = []
    for base in FILEIRA:
        g = base[0]
        opcoes = {}
        for grupo in grupos.get(g, []):
            ref = mapa.get(contas_mod.chave_do_nome(f"{base} {grupo}"))
            if ref is not None and not isinstance(ref, str):
                opcoes[grupo] = ref.linha
        fileira.append(
            {
                "base": base,
                "grandeza": g,
                "opcoes": opcoes,
                "fasor": all(
                    _tem_fasor(mapa[contas_mod.chave_do_nome(n)]) for n in opcoes.values()
                )
                if opcoes
                else False,
            }
        )
    completar = sorted(
        {
            ref.linha
            for ref in mapa.values()
            if ref is not None and not isinstance(ref, str) and ref.linha
        }
        | {
            k
            for k, ref in mapa.items()
            if ref is not None
            and not isinstance(ref, str)
            and k != contas_mod.chave_do_nome(ref.linha)
        }
    )
    # O RADICAL do nome dos canais de cada grupo (`I*W`, `TC BUC 69kV:I *`):
    # é o que o seletor da fileira mostra ao lado de `G1`. Nunca «alta» nem
    # «baixa» — o programa não diz lado.
    from osclab.formats import conjuntos

    # Escrito como o relé escreve (o `nome` do conjunto vem em maiúsculas):
    # o canal da fase A com a ÚLTIMA letra A trocada por `*`, a mesma regra
    # com que `formats/conjuntos.py` junta as três fases.
    por_indice = {c.index: c.name for c in registro.analog_channels}
    rotulos = {}
    for c in conjuntos.de_registro(registro):
        nome_a = por_indice.get(c.canais.get("A", -1), "")
        i = nome_a.upper().rfind("A")
        if c.rotulo and i >= 0:
            rotulos[c.rotulo] = nome_a[:i] + "*" + nome_a[i + 1 :]
        elif c.rotulo:
            rotulos[c.rotulo] = c.nome
    return {
        "sinais": sinais,
        "fileira": fileira,
        "grupos": grupos,
        "rotulos": rotulos,
        "completar": completar,
    }
