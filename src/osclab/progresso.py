"""O progresso de ABRIR um registro, etapa por etapa (14/11/2026).

Pedido dele: «quando estamos abrindo uma oscilografia, apareça uma barra com
o progresso». Um registro de ondas viajantes (1 a 3 milhões de amostras por
canal) leva de 12 a 36 s para abrir, e o «Carregando o registro…» parado não
dizia se o programa estava andando ou tinha travado.

**O progresso é VERDADEIRO, não animação.** Quem anda é o servidor, por
etapas conhecidas, e é ele quem diz a etapa e a fração:

    ler          o leitor do formato abre o arquivo        `formats/registry`
    diagnostico  bruto × filtrado, canal a canal            `analysis/filtragem`
    canais       fase, trinca e relação corrigidas          `library/acervo`
    contas       as contas do registro inteiro              `base.lembrado`
    desenho      a primeira janela, montada e enviada       a rota da janela

Dentro de uma etapa, quem percorre canais ou linhas diz quantos já foram
(`avancar(feito, total)`), e a fração anda dentro dela. Os PESOS das etapas
e das contas são medidos (registros sintéticos de 1 M × 12 e 3 M × 6
amostras, 14/11/2026: ler 1–2 %, diagnóstico 21–22 %, contas 70–72 %, o
resto é a janela; sem a energia do catálogo, que saiu da abertura no mesmo
dia, diagnóstico ~32 % e contas ~54 %); em outro registro a proporção muda um pouco, e a barra
anda mais depressa numa etapa e mais devagar noutra — mas nunca para trás
(`fracao` só cresce) e nunca passa de 1 antes de terminar.

Duas partes, e é isto que deixa um pedido ACOMPANHAR a abertura feita por
outro:

* a LEITURA de um registro (`lendo`) é do REGISTRO, guardada por `sha`: dois
  pedidos que abrem o mesmo registro ao mesmo tempo (a janela e o painel
  localizador, depois de «+ adicionar oscilografia») veem a mesma — e o
  acervo só o lê uma vez (`acervo.ler`, com uma trava por registro);
* a ABERTURA (`abrindo`) é do PEDIDO, guardada pelo `token` que a tela
  manda: ela soma a leitura dos registros novos, as contas e o desenho.

Sem abertura em curso, todas as funções daqui são no-op: um leitor chamado
pelo teste, pelo modo lote ou por um pedido de cursor não paga nada.

Este módulo não importa nada do OscLab: quem lê formato, quem conta e quem
serve a tela importam ele, e ele não depende de nenhum.
"""

from __future__ import annotations

import contextvars
import threading
import time
from contextlib import contextmanager

#: As etapas, na ordem, com o nome curto que a tela escreve ao lado da barra.
ETAPAS: tuple[tuple[str, str], ...] = (
    ("ler", "lendo o arquivo"),
    ("diagnostico", "bruto × filtrado"),
    ("canais", "canais e grupos"),
    ("contas", "contas do registro"),
    ("desenho", "primeiro desenho"),
)
ROTULO = dict(ETAPAS)
ORDEM = tuple(chave for chave, _ in ETAPAS)

#: Quanto da barra cada etapa ocupa. Medido (ver o cabeçalho): somam 1.
PESOS: dict[str, float] = {
    "ler": 0.04, "diagnostico": 0.32, "canais": 0.01, "contas": 0.54, "desenho": 0.09,
}
#: As três primeiras são a LEITURA de um registro (`acervo.ler`).
DA_LEITURA = ("ler", "diagnostico", "canais")

#: O peso de cada conta do registro inteiro dentro da etapa `contas`, pelo
#: tempo PRÓPRIO dela (sem as contas que ela chama), medido num sintético de
#: 1 M amostras × 12 canais: trincas 2,1 s, presença 1,6 s, início 0,6 s.
#: Conta que não está aqui pesa `PESO_DE_OUTRA_CONTA`. A energia do catálogo
#: (3,4 s) saiu da abertura em 14/11/2026: é feita quando o «+ sinal» abre,
#: com uma barra só dela (`abrindo(..., contas=SO_A_ENERGIA)`).
PESOS_DAS_CONTAS: dict[str, float] = {
    "conjuntos.ondas": 0.47,
    "presenca.alternados": 0.34,
    "imas.inicio": 0.12,
    "unidades.por_unidade": 0.035,
    "presenca.sem_sinal": 0.035,
}
PESO_DE_OUTRA_CONTA = 0.005
#: As contas que uma barra «só destas contas» acompanha: a da energia do
#: «+ sinal». Ali a barra inteira é dela — de 0 a 100 %.
SO_A_ENERGIA = ("catalogo.energia",)

#: O nome curto de cada conta, para a etapa `contas` dizer qual está andando.
ROTULO_DA_CONTA: dict[str, str] = {
    "catalogo.energia": "energia dos sinais",
    "conjuntos.ondas": "trincas",
    "presenca.alternados": "presença de sinal",
    "presenca.sem_sinal": "presença de sinal",
    "imas.inicio": "início da perturbação",
    "digitais.trocas": "digitais",
    "digitais.resumos": "digitais",
    "serie.piramide": "mín./máx. do traço",
}

#: Quanto tempo uma abertura terminada continua respondendo (a última
#: consulta da tela pode chegar depois do fim) antes de ser esquecida.
GUARDAR_TERMINADA_S = 30.0
#: Teto de aberturas guardadas — um pedido por aba aberta, na prática.
ABERTURAS_NO_MAXIMO = 64


class _Leitura:
    """Onde está a leitura de UM registro: a etapa (`DA_LEITURA`) e a fração."""

    __slots__ = ("etapa", "fracao")

    def __init__(self) -> None:
        self.etapa = "ler"
        self.fracao = 0.0

    def total(self) -> float:
        """A fração da leitura inteira, de 0 a 1, pelos pesos das três etapas."""
        peso = sum(PESOS[e] for e in DA_LEITURA)
        feito = 0.0
        for e in DA_LEITURA:
            if e == self.etapa:
                feito += PESOS[e] * min(max(self.fracao, 0.0), 1.0)
                break
            feito += PESOS[e]
        return feito / peso


class _Abertura:
    """A abertura que UM pedido acompanha."""

    def __init__(self, token: str, shas: tuple[str, ...],
                 so: tuple[str, ...] = ()) -> None:
        self.token = token
        self.shas = shas
        #: Uma barra «só destas contas» (a energia do «+ sinal»): sem leitura
        #: nem desenho, e a barra inteira é delas. Vazio é a abertura de sempre.
        self.so = so
        self.lidos: set[str] = set()
        self.fase = "contas" if so else "leitura"   # leitura → contas → desenho
        self.feito_das_contas = 0.0
        #: As contas em curso, da de fora para a de dentro: [nome, fração].
        self.pilha: list[list] = []
        self.erro: str | None = None
        self.pronto = False
        self.maior = 0.0
        self.fim: float | None = None


_trava = threading.Lock()
_leituras: dict[str, _Leitura] = {}
_aberturas: dict[str, _Abertura] = {}
_abertura_atual: contextvars.ContextVar[_Abertura | None] = contextvars.ContextVar(
    "osclab_abertura", default=None)
_leitura_atual: contextvars.ContextVar[_Leitura | None] = contextvars.ContextVar(
    "osclab_leitura", default=None)


# ---------------------------------------------------------------------------
# O lado de quem TRABALHA: leitor, diagnóstico, contas
# ---------------------------------------------------------------------------

@contextmanager
def abrindo(token: str | None, shas, contas=()):
    """Acompanha a abertura dos registros `shas` neste pedido, sob `token`.

    Sem token ou sem registro novo não acompanha nada: a janela de um registro
    já aberto não tem o que mostrar, e a barra não pode aparecer num gesto.
    Exceção dentro vira o estado de erro (e continua subindo).

    Com `contas` (ex.: `SO_A_ENERGIA`), a barra acompanha SÓ essas contas do
    registro já aberto, de 0 a 100 % — é a do «+ sinal» de um registro
    gigante, que faz a energia do catálogo na primeira vez que se abre.
    """
    shas = tuple(dict.fromkeys(s for s in (shas or ()) if s))
    if not token or not shas:
        yield None
        return
    abertura = _Abertura(str(token)[:64], shas, tuple(contas or ()))
    with _trava:
        _esquecer_velhas()
        _aberturas[abertura.token] = abertura
    marca = _abertura_atual.set(abertura)
    try:
        yield abertura
    except BaseException as exc:
        falhou(str(exc) or exc.__class__.__name__)
        raise
    finally:
        _abertura_atual.reset(marca)
        with _trava:
            abertura.pronto = True
            abertura.fim = time.monotonic()


@contextmanager
def lendo(sha: str):
    """A leitura do registro `sha` (o leitor, o diagnóstico, as correções)."""
    leitura = _Leitura()
    with _trava:
        _leituras[sha] = leitura
    marca = _leitura_atual.set(leitura)
    try:
        yield leitura
    finally:
        _leitura_atual.reset(marca)
        with _trava:
            if _leituras.get(sha) is leitura:
                del _leituras[sha]
        lido(sha)


def lido(sha: str) -> None:
    """O registro `sha` está aberto (lido agora, ou já estava)."""
    abertura = _abertura_atual.get()
    if abertura is not None:
        with _trava:
            abertura.lidos.add(sha)


def etapa(chave: str) -> None:
    """Passa à etapa `chave`. Dentro de `lendo`, é a etapa da leitura."""
    leitura = _leitura_atual.get()
    if leitura is not None and chave in DA_LEITURA:
        with _trava:
            leitura.etapa = chave
            leitura.fracao = 0.0
        return
    abertura = _abertura_atual.get()
    if abertura is None or chave not in ("contas", "desenho"):
        return
    with _trava:
        abertura.fase = chave


def avancar(feito: float, total: float) -> None:
    """`feito` de `total` da etapa (ou da conta) em curso já foram."""
    if not total or total <= 0:
        return
    fracao = min(max(float(feito) / float(total), 0.0), 1.0)
    leitura = _leitura_atual.get()
    if leitura is not None:
        leitura.fracao = max(leitura.fracao, fracao)
        return
    abertura = _abertura_atual.get()
    if abertura is not None and abertura.pilha:
        topo = abertura.pilha[-1]
        topo[1] = max(topo[1], fracao)


def falhou(mensagem: str) -> None:
    """A abertura deste pedido deu erro: a tela mostra a mensagem."""
    abertura = _abertura_atual.get()
    if abertura is not None:
        with _trava:
            if abertura.erro is None:
                abertura.erro = str(mensagem)


@contextmanager
def conta(nome: str):
    """Uma conta do registro inteiro (`base.lembrado`) está sendo feita."""
    abertura = _abertura_atual.get()
    if abertura is None:
        yield
        return
    item = [nome, 0.0]
    with _trava:
        abertura.pilha.append(item)
    try:
        yield
    finally:
        with _trava:
            if item in abertura.pilha:
                abertura.pilha.remove(item)
            abertura.feito_das_contas += _peso(abertura, nome)


def _peso(abertura: _Abertura, nome: str) -> float:
    """O peso da conta `nome` na barra desta abertura. Numa barra «só destas
    contas», cada uma delas pesa 1 e as outras (que elas chamam) nada."""
    if abertura.so:
        return 1.0 if nome in abertura.so else 0.0
    return PESOS_DAS_CONTAS.get(nome, PESO_DE_OUTRA_CONTA)


# ---------------------------------------------------------------------------
# O lado de quem PERGUNTA: a rota de progresso
# ---------------------------------------------------------------------------

def estado(token: str) -> dict | None:
    """Onde a abertura `token` está, pronta para a tela: etapa, rótulo,
    fração de 0 a 1 (só cresce), erro e se terminou. `None` se não há."""
    with _trava:
        abertura = _aberturas.get(str(token)[:64])
        if abertura is None:
            return None
        chave, rotulo, fracao = _onde(abertura)
        fracao = 1.0 if abertura.pronto and abertura.erro is None else min(fracao, 0.999)
        abertura.maior = max(abertura.maior, fracao)
        return {
            "ativa": True,
            "etapa": chave,
            "rotulo": rotulo,
            "fracao": round(abertura.maior, 4),
            "erro": abertura.erro,
            "pronto": abertura.pronto,
            "registros": len(abertura.shas),
        }


def _onde(abertura: _Abertura) -> tuple[str, str, float]:
    """(etapa, rótulo, fração) da abertura, sem a guarda de só crescer."""
    if abertura.so:
        # A barra inteira é das contas pedidas (a energia do «+ sinal»).
        feito = abertura.feito_das_contas
        rotulo = ROTULO_DA_CONTA.get(abertura.so[0], ROTULO["contas"])
        for nome, parcial in abertura.pilha:
            if nome in abertura.so:
                feito += parcial
                break
        total = float(len(abertura.so))
        return "contas", rotulo, min(feito / total, 0.99)
    peso_da_leitura = sum(PESOS[e] for e in DA_LEITURA)
    if abertura.fase == "leitura":
        partes, chave = [], None
        for sha in abertura.shas:
            leitura = _leituras.get(sha)
            if sha in abertura.lidos:
                partes.append(1.0)
            elif leitura is None:
                partes.append(0.0)
            else:
                partes.append(leitura.total())
                # A etapa escrita é a do primeiro registro sendo lido.
                chave = chave or leitura.etapa
        chave = chave or ("canais" if min(partes) >= 1.0 else "ler")
        fracao = peso_da_leitura * sum(partes) / len(partes)
        return chave, ROTULO[chave], fracao
    base = peso_da_leitura
    if abertura.fase == "contas":
        total = len(abertura.shas) * sum(PESOS_DAS_CONTAS.values())
        feito = abertura.feito_das_contas
        rotulo = ROTULO["contas"]
        if abertura.pilha:
            nome, parcial = abertura.pilha[-1]
            feito += PESOS_DAS_CONTAS.get(nome, PESO_DE_OUTRA_CONTA) * parcial
            rotulo = ROTULO_DA_CONTA.get(nome, rotulo)
        dentro = min(feito / total, 0.99) if total > 0 else 0.0
        return "contas", rotulo, base + PESOS["contas"] * dentro
    base += PESOS["contas"]
    return "desenho", ROTULO["desenho"], base


def _esquecer_velhas() -> None:
    """Esquece as aberturas terminadas há muito (chamada sob `_trava`)."""
    agora = time.monotonic()
    for token in [t for t, a in _aberturas.items()
                  if a.fim is not None and agora - a.fim > GUARDAR_TERMINADA_S]:
        del _aberturas[token]
    while len(_aberturas) >= ABERTURAS_NO_MAXIMO:
        del _aberturas[next(iter(_aberturas))]
