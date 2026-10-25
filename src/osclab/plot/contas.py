"""A calculadora de sinais: contas que o usuário escreve sobre as ondas.

## O que ela é, e o que ela não é

Uma conta é uma expressão sobre os canais do registro, escrita com o nome deles
entre colchetes: `([VAY] - [VBY]) / 1.732`. O resultado é **uma onda nova**,
amostra por amostra, que entra no catálogo no bloco «Calculados» com as mesmas
cinco colunas de um canal — onda, RMS, DC, 60 Hz e 60 Hz RMS. É o mesmo lugar
onde já mora o resíduo `IN`, e pelo mesmo motivo: resíduo é exatamente isso, a
conta `[IAW] + [IBW] + [ICW]` com nome fixo.

**Este módulo é o domínio ONDA.** O domínio FASOR — `Z = V ÷ I`, `S = V × I*`,
`V1/V2` — é outro interpretador, sobre módulo e ângulo de 60 Hz, e ainda não
existe. Dividir uma onda por outra é aceito **com aviso**: o resultado estoura
em cada passagem por zero (vira buraco no gráfico), e o que o usuário quer ao
escrever `V ÷ I` quase sempre é impedância, que é conta de fasor.

## A conversão vem ANTES da conta

Cada canal é convertido para o lado da tela (primário ou secundário) antes de
entrar na soma, como já faz o resíduo. Somar primário com secundário erraria
por mil vezes sem avisar, e o erro ficaria escondido dentro de um sinal com
nome bonito.

A conta roda em unidade de engenharia do ARQUIVO (V, A) e o prefixo `k` é
aplicado no fim, sobre o resultado — a mesma `escalas` que o desenho usa. Assim
`[VAY] - [VBY]` num registro em kV sai em kV, e `[VAY] × [IAW]` sai em V·A, que
não tem prefixo nenhum declarado e fica como está.

## O que a conta pode usar

Tudo que o catálogo oferece como LINHA: os canais do arquivo, o resíduo da
trinca (`IN G1`), as componentes de sequência (`3I0 G1`, `I1 G1`) e as contas
que o usuário criou ANTES desta. Só as anteriores — e isso não é limitação de
implementação: é a ordem de criação fazendo, de graça, o trabalho que um
detector de ciclo faria (`x1 = x2 + 1` com `x2 = x1 + 1`).

Uma linha tem várias colunas — onda, RMS, DC, 60 Hz — e o nome aponta sempre
para a NATURAL dela: a onda de quem tem onda, e o eficaz de quem só existe em
eficaz.

E é aí que mora a ressalva mais importante desta calculadora. Componente de
sequência é FASOR: `3I0` só existe em eficaz, um patamar que anda devagar.
Canal é ONDA: cruza o zero cento e vinte vezes por segundo. A conta é feita
amostra a amostra, então somar os dois dá um número que existe e não descreve
grandeza nenhuma — e o aviso diz isso. `[IN G1] - [3I0 G1]`, que é a pergunta
que o engenheiro quer fazer (o resíduo medido bate com a conta?), só fecha
comparando eficaz com eficaz: `[IN G1 · RMS]` com `[3I0 G1]`.

## As unidades são conferidas, mas nada é BLOQUEADO

`A + A` passa; `V × A` vira `V·A`; `[IAW]²` vira `A²`.

E `A + V`? **Faz a conta mesmo assim, com aviso.** É a regra do projeto:
*avisa, nunca bloqueia* — a mesma que vale para os diagnósticos de trinca e de
TC/TP. Quem analisa uma oscilografia às vezes sabe algo que o programa não
sabe: o canal pode estar rotulado errado no arquivo, ou a soma pode ser um
passo intermediário de uma conta que só faz sentido no fim. Recusar tira a
ferramenta da mão de quem tem razão; avisar não tira nada de ninguém.

O que o aviso custa é a UNIDADE: somando grandezas diferentes, o resultado não
tem unidade que se escreva, e ele sai sem nenhuma — o que é mais honesto que
escolher uma das duas.

Só três coisas continuam sendo ERRO, porque nelas não há o que calcular: o que
não se consegue ler (parêntese aberto, símbolo estranho), o canal que não
existe no registro, e o nome repetido em dois canais.

Guardo as unidades como expoentes (`{"V": 1, "A": -1}`), que é o que permite
dizer que a raiz de `A²` é `A` — e avisar, na raiz de `A`, que o resultado sai
sem unidade.

## Em que bloco o resultado mora

Pela FORMA da conta, não medindo a onda: se ela só soma, subtrai e multiplica
por número, e todos os canais que entram são alternados, o resultado é
alternado — ganha fasor, espectro e as cinco colunas. Se houver produto entre
dois sinais, o resultado não é senoidal (potência instantânea oscila no dobro
da frequência, com nível contínuo) e ele cai em «Outros sinais», com o motivo
escrito, igual a um canal de bateria. Divisão de sinal por sinal entra aqui
pela mesma porta: `V ÷ I` amostra a amostra estoura em cada passagem por zero
do denominador — a conta é feita, com ressalva, e o resultado não é senoide.

## Aviso e motivo são campos DIFERENTES

`Analise.avisos` acompanha uma conta que FUNCIONA: a tela escreve num ⓘ cor de
atenção ao lado do nome, e o botão de criar continua aberto. `Sinal.motivo`
explica por que um sinal NÃO serve para algo — e ali a tela pinta de defeito.
Juntar os dois faria uma conta que funciona parecer quebrada, que é
exatamente o ruído que esta regra quer evitar.

Decidir pela forma e não medindo é deliberado: medir exigiria calcular a onda
inteira a cada montagem do catálogo, que acontece a cada pedido da tela.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from osclab.formats import fases
from osclab.formats.base import Record

#: O maior tamanho de expressão aceito. Não é limite técnico: é que uma conta
#: que não cabe em duas linhas não se confere de olho, e conta que não se
#: confere não deveria ir para um laudo.
LIMITE_DA_EXPRESSAO = 400

#: Quantas contas cabem num registro. O mesmo motivo: a lista é para ser lida.
LIMITE_DE_CONTAS = 20

#: As funções de uma variável, com o que elas fazem com a unidade.
#:
#: `raiz` divide os expoentes por dois e por isso só aceita unidade de expoente
#: PAR: a raiz de `A²` é `A`, e a raiz de `A` não se escreve.
FUNCOES = ("abs", "raiz")


@dataclass(frozen=True)
class Conta:
    """Uma conta do usuário: o nome que ele deu e a expressão que ele escreveu."""

    id: str
    nome: str
    expressao: str


def de_json(cru) -> list[Conta]:
    """Lê as contas que a tela mandou. O que não casar some em silêncio."""
    if not isinstance(cru, list):
        return []
    saida: list[Conta] = []
    vistos: set[str] = set()
    for i, item in enumerate(cru, start=1):
        if not isinstance(item, dict) or len(saida) >= LIMITE_DE_CONTAS:
            continue
        identidade = str(item.get("id", "") or f"x{i}").strip()
        # O prefixo `x` é o espaço de ids das contas, ao lado de `c` (canal),
        # `v` (conta de canal) e `q` (trinca). Um id fora dele poderia
        # atropelar um sinal do catálogo e a tela desenharia outra coisa.
        if not re.fullmatch(r"x[0-9]{1,4}", identidade):
            continue
        nome = str(item.get("nome", "") or "").strip()
        expressao = str(item.get("expressao", "") or "").strip()
        if not identidade or not nome or not expressao:
            continue
        if identidade in vistos or len(expressao) > LIMITE_DA_EXPRESSAO:
            continue
        vistos.add(identidade)
        saida.append(Conta(id=identidade, nome=nome, expressao=expressao))
    return saida


# --- unidades --------------------------------------------------------------

def _vazia() -> dict[str, int]:
    return {}


def _multiplicar(a: dict, b: dict) -> dict:
    saida = dict(a)
    for chave, expoente in b.items():
        saida[chave] = saida.get(chave, 0) + expoente
    return {k: v for k, v in saida.items() if v}


def _elevar(a: dict, n: int) -> dict:
    return {k: v * n for k, v in a.items() if v * n}


def _iguais(a: dict, b: dict) -> bool:
    return a == b


def _escrever_unidade(expoentes: dict, por_grandeza: dict[str, str]) -> str:
    """`{"V": 1}` → `kV`; `{"V": 1, "I": 1}` → `V·A`; `{"I": 2}` → `A²`.

    As chaves são as GRANDEZAS como `formats/fases` as nomeia (`V` e `I`), e
    `por_grandeza` diz qual é a unidade de arquivo de cada uma NESTE registro —
    num relé que grava tensão em kV, a tensão é `kV`. Misturar os dois
    vocabulários foi o primeiro bug deste módulo: o laço procurava a chave `A`,
    que não existe, e toda conta saía sem unidade.
    """
    if not expoentes:
        return ""
    sobrescrito = {2: "²", 3: "³", -1: "⁻¹", -2: "⁻²"}
    em_cima, embaixo = [], []
    for chave in ("V", "I"):
        n = expoentes.get(chave, 0)
        if not n:
            continue
        texto = por_grandeza.get(chave, chave)
        if abs(n) > 1:
            texto += sobrescrito.get(abs(n), f"^{abs(n)}")
        (em_cima if n > 0 else embaixo).append(texto)
    if not em_cima:
        return "1/" + "·".join(embaixo)
    if not embaixo:
        return "·".join(em_cima)
    # V ÷ A é ohm, e ohm tem nome. Vale a pena escrever o nome: `V/A` num
    # laudo faz o leitor parar para traduzir o que já tem símbolo.
    if em_cima == ["V"] and embaixo == ["A"]:
        return "Ω"          # V ÷ A tem nome próprio, e nome se escreve
    return "·".join(em_cima) + "/" + "·".join(embaixo)


# --- a gramática -----------------------------------------------------------

class ErroDaConta(Exception):
    """O que está errado na expressão, em uma frase para a tela mostrar."""


_SIMBOLOS = re.compile(r"""
    \s*(?:
      (?P<nome>\[[^\]\[]{1,60}\])
    | (?P<numero>\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)
    | (?P<funcao>[A-Za-z_][A-Za-z_0-9]*)
    | (?P<sinal>[-+*/^()])
    )\s*
""", re.VERBOSE)


def _quebrar(expressao: str) -> list[tuple[str, str]]:
    fichas, i = [], 0
    while i < len(expressao):
        achado = _SIMBOLOS.match(expressao, i)
        if achado is None or achado.end() == i:
            resto = expressao[i:].strip()
            raise ErroDaConta(f"não entendi «{resto[:20]}»")
        for tipo in ("nome", "numero", "funcao", "sinal"):
            valor = achado.group(tipo)
            if valor is not None:
                fichas.append((tipo, valor))
                break
        i = achado.end()
    if not fichas:
        raise ErroDaConta("a conta está vazia")
    return fichas


@dataclass
class _No:
    """Um nó da árvore: `op` diz o quê, `filhos` diz sobre o quê."""

    op: str
    filhos: list = field(default_factory=list)
    numero: float = 0.0
    #: O sinal do CATÁLOGO que este nó lê, quando `op == "sinal"`. Era o índice
    #: do canal; virou o sinal inteiro quando a conta passou a poder usar o
    #: resíduo, as componentes e as contas que vieram antes — ver o cabeçalho.
    sinal: object = None
    unidade: dict = field(default_factory=_vazia)


class _Leitor:
    def __init__(self, fichas, por_nome, por_grandeza):
        self.fichas = fichas
        self.i = 0
        #: `NOME EM MAIÚSCULAS` → o `Sinal` do catálogo. Entram os canais do
        #: arquivo, o resíduo, as componentes de sequência e as contas que o
        #: usuário criou ANTES desta. `None` no valor marca nome repetido.
        self.por_nome = por_nome
        self.por_grandeza = por_grandeza
        #: Se algum produto entre SINAIS apareceu: é o que tira o resultado do
        #: bloco dos alternados. Ver o cabeçalho do módulo.
        self.tem_produto_de_sinais = False
        self.usados: list = []
        #: Os domínios que entraram na conta: `instantaneo` e/ou `eficaz`.
        #: Misturar os dois é a ressalva mais importante desta calculadora.
        self.dominios: set[str] = set()
        #: O que ficou estranho mas não impede a conta. Ver o cabeçalho.
        self.avisos: list[str] = []

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

    def expressao(self) -> _No:
        no = self.termo()
        while self.olhar()[1] in ("+", "-"):
            op = self.comer()
            direita = self.termo()
            unidade = no.unidade or direita.unidade
            if not no.unidade and not direita.unidade:
                pass                       # número com número: segue número
            elif not _iguais(no.unidade, direita.unidade):
                esq = _escrever_unidade(no.unidade, self.por_grandeza) or "número"
                dir_ = _escrever_unidade(direita.unidade, self.por_grandeza) or "número"
                # Curto de propósito: o aviso é lido no veredito da
                # calculadora, que fica ao lado do botão de criar. Uma
                # explicação de seis linhas ali empurra o botão para fora do
                # alcance do dedo — e um aviso que empurra o botão é um aviso
                # que o usuário aprende a fechar sem ler.
                self.avisos.append(
                    f"somando {esq} com {dir_}: o resultado não tem unidade "
                    "que se escreva")
                unidade = {}
            no = _No(op, [no, direita], unidade=unidade)
        return no

    def termo(self) -> _No:
        no = self.fator()
        while self.olhar()[1] in ("*", "/"):
            op = self.comer()
            direita = self.fator()
            if op == "/":
                if direita.unidade:
                    self.avisos.append(
                        "sinal ÷ sinal estoura em cada passagem por zero do "
                        "de baixo; impedância mesmo é conta de FASOR, que "
                        "ainda não existe")
                    self.tem_produto_de_sinais = True
                no = _No("/", [no, direita],
                         unidade=_multiplicar(no.unidade,
                                              _elevar(direita.unidade, -1)))
            else:
                if no.unidade and direita.unidade:
                    self.tem_produto_de_sinais = True
                no = _No("*", [no, direita],
                         unidade=_multiplicar(no.unidade, direita.unidade))
        return no

    def fator(self) -> _No:
        if self.olhar()[1] == "-":
            self.comer()
            dentro = self.fator()
            return _No("neg", [dentro], unidade=dentro.unidade)
        if self.olhar()[1] == "+":
            self.comer()
            return self.fator()
        return self.potencia()

    def potencia(self) -> _No:
        base = self.primario()
        if self.olhar()[1] != "^":
            return base
        self.comer("^")
        tipo, valor = self.olhar()
        if tipo != "numero":
            raise ErroDaConta("o expoente tem que ser um número inteiro")
        self.comer()
        n = float(valor.replace(",", "."))
        if n != int(n) or not 1 <= int(n) <= 4:
            raise ErroDaConta("o expoente tem que ser inteiro, de 1 a 4")
        n = int(n)
        if n > 1 and base.unidade:
            self.tem_produto_de_sinais = True
        return _No("pot", [base], numero=n, unidade=_elevar(base.unidade, n))

    def primario(self) -> _No:
        tipo, valor = self.olhar()
        if tipo is None:
            raise ErroDaConta("a conta termina no meio")
        if valor == "(":
            self.comer("(")
            dentro = self.expressao()
            self.comer(")")
            return dentro
        if tipo == "numero":
            self.comer()
            return _No("num", numero=float(valor.replace(",", ".")))
        if tipo == "nome":
            self.comer()
            nome = valor[1:-1].strip()
            procurado = chave_do_nome(nome)
            if procurado not in self.por_nome:
                raise ErroDaConta(f"não existe sinal chamado «{nome}» neste "
                                  "registro — e uma conta só enxerga as "
                                  "contas criadas ANTES dela")
            achado = self.por_nome[procurado]
            if achado is None:
                raise ErroDaConta(f"há mais de um sinal chamado «{nome}»: "
                                  "renomeie um deles para a conta saber qual é")
            self.usados.append(achado)
            # O DOMÍNIO do sinal, que é a ressalva mais importante aqui: uma
            # componente de sequência só existe em eficaz, e somá-la a uma onda
            # instantânea é somar um patamar com uma senoide. Ver o cabeçalho.
            # A linha é COMPONENTE × MÓDULO, e não instantâneo × eficaz: a
            # `· 60Hz` e a `· DC` são parcelas com sinal da própria onda, e
            # somá-las a ela é legítimo — `[VAY] - [VAY · 60Hz]` é a onda da
            # distorção. Ver `Referencia.COMPONENTES`.
            self.dominios.add("componente" if achado.e_onda else "modulo")
            grandeza = fases.grandeza_da_unidade(str(achado.unidade).strip())
            return _No("sinal", sinal=achado,
                       unidade={grandeza: 1} if grandeza else {})
        if tipo == "funcao":
            if valor not in FUNCOES:
                conhecidas = ", ".join(FUNCOES)
                raise ErroDaConta(f"não conheço a função «{valor}» — tenho "
                                  f"{conhecidas}")
            self.comer()
            self.comer("(")
            dentro = self.expressao()
            self.comer(")")
            if valor == "abs":
                return _No("abs", [dentro], unidade=dentro.unidade)
            if any(n % 2 for n in dentro.unidade.values()):
                atual = _escrever_unidade(dentro.unidade, self.por_grandeza)
                self.avisos.append(
                    f"a raiz de {atual} não tem unidade que se escreva: o "
                    "resultado sai sem unidade")
                return _No("raiz", [dentro], unidade={})
            return _No("raiz", [dentro],
                       unidade={k: v // 2 for k, v in dentro.unidade.items()})
        raise ErroDaConta(f"não esperava «{valor}» aqui")



@dataclass
class Analise:
    """O que se sabe de uma expressão depois de lida."""

    arvore: _No | None = None
    unidade: dict = field(default_factory=_vazia)
    unidade_escrita: str = ""
    canais: tuple[int, ...] = ()
    #: Os NOMES dos sinais que entraram, na ordem. `canais` só traz os do
    #: arquivo; aqui entram também o resíduo, as componentes e as contas
    #: anteriores — é o que a tela escreve no «sai de».
    fontes: tuple[str, ...] = ()
    alternado: bool = True
    #: Se houve produto ou divisão ENTRE SINAIS. Separa os dois motivos de a
    #: conta não ser senoide — o produto cria frequências novas; o módulo e a
    #: contínua não são onda — e a tela escreve um ou outro.
    tem_produto: bool = False
    #: Os domínios que entraram: `componente` (instantâneo, 60 Hz, DC — parcela
    #: com sinal da onda) e/ou `modulo` (RMS, fundamental — jogaram fora sinal
    #: e fase). Guardado, e não só consumido no aviso, porque é o que decide se
    #: a conta TEM onda: soma de componentes é onda; qualquer módulo dentro, e
    #: o resultado é um módulo, que não tem onda nem contínua para oferecer.
    #:
    #: O rótulo sobe pela árvore: nenhum operador transforma módulo em
    #: componente. Por isso a decisão é exata para qualquer expressão, por mais
    #: estranha que seja — e não depende de olhar número nenhum, que é o que a
    #: tornaria um palpite (num sinal unipolar o RMS e a DC dão valores
    #: parecidos, e deduzir pelo número erraria).
    dominios: tuple[str, ...] = ()
    erro: str = ""
    #: O que a conta tem de estranho mas NÃO impede. Ver o cabeçalho: a regra
    #: do projeto é avisar, nunca bloquear — quem decide o que faz sentido é o
    #: engenheiro, não o programa.
    avisos: tuple[str, ...] = ()

    @property
    def vale(self) -> bool:
        return self.arvore is not None and not self.erro

    @property
    def e_onda(self) -> bool:
        """Se o resultado é ONDA: tem forma no tempo, e contínua.

        Só quando TODAS as folhas são componente. A mistura
        (`componente` + `modulo`) devolve `False` aqui e `None` em
        `tem_onda` — ver lá: "não sei" não é "não existe", e a regra
        do projeto é avisar, nunca bloquear.
        """
        return self.dominios == ("componente",)

    @property
    def tem_onda(self):
        """`True`, `False` ou `None` — e o `None` é o que importa.

        A tela só apaga a folha quando tem CERTEZA de que não existe
        (`False`). Na mistura devolve `None`, e aí a folha fica de pé com
        o ⓘ ao lado: o que não sabemos não se barra.
        """
        if len(self.dominios) > 1:
            return None
        return self.dominios != ("modulo",)


@dataclass
class Referencia:
    """Um nome que a conta pode escrever entre colchetes.

    É o que o catálogo oferece, reduzido ao que a calculadora precisa saber:
    como o sinal se chama, em que unidade está, e se é ONDA ou EFICAZ.

    `analise` só existe quando a referência é outra conta do usuário. Guardá-la
    aqui é o que torna a avaliação direta: a conta de cima desce na árvore da
    de baixo, sem voltar ao catálogo e sem reanalisar a expressão. Antes disso
    o custo dobrava a cada conta encadeada — seis contas já levavam 125 ms, e
    vinte (o limite) seriam minutos.
    """

    linha: str
    unidade: str = ""
    grandeza: str = "instantaneo"
    bloco: str = "alternado"
    canal: int = -1
    sinal: object = None
    analise: object = None

    #: As colunas que são COMPONENTE do sinal: parcela com sinal, na mesma
    #: unidade e na mesma base de tempo. Elas se somam — `onda = 60Hz + DC +
    #: harmônicos` — e somar entre si é aritmética legítima.
    #:
    #: Ficam de fora `rms` e `fundamental`, que são MÓDULOS: jogaram fora
    #: sinal e fase. Somar um módulo a uma onda é que é o erro de categoria.
    COMPONENTES = ("instantaneo", "filtrado", "dc")

    @property
    def e_onda(self) -> bool:
        """Se é componente do sinal (e não módulo). Ver `COMPONENTES`."""
        return self.grandeza in Referencia.COMPONENTES

    @property
    def e_senoide(self) -> bool:
        """Se dá para tirar fasor de 60 Hz. A DC não é senoide."""
        return self.grandeza in ("instantaneo", "filtrado")


#: Marca interna de nome repetido, para distinguir "duas linhas com este
#: nome" de "ainda não vi este nome". `None` na saída é o que o leitor lê.
_REPETIDO = object()


def chave_do_nome(nome: str) -> str:
    """O nome reduzido à forma com que se procura: maiúsculas, sem o `·`.

    O ponto médio que o catálogo usa para separar a coluna (`IAW · 60Hz`) NÃO
    está no teclado ABNT. Exigi-lo era pedir que o usuário copiasse e colasse
    um caractere para escrever o nome de um sinal da própria tela.

    Então ele vira espaço, e espaços repetidos viram um só: `IAW 60Hz`,
    `IAW  ·  60Hz` e `IAW·60Hz` são o mesmo nome. O hífen fica como está —
    ele aparece DENTRO de nome de canal de verdade (`Voltage A-G`), e comê-lo
    juntaria sinais diferentes.
    """
    return " ".join(str(nome).upper().replace("·", " ").split())


def _do_catalogo(registro: Record) -> dict:
    """As referências que saem do ARQUIVO: canais, resíduo e componentes.

    Sem conta de usuário nenhuma — é a base fixa, e é o único ponto em que
    esta camada chama o catálogo.

    Cada sinal entra DUAS vezes: pelo nome da LINHA (`IAW`), que aponta para a
    coluna natural dela, e pelo nome da COLUNA (`IAW · 60Hz`, `IAW · DC`), que
    aponta para aquela coluna exata. É o que deixa escrever
    `[VAY] - [VAY · 60Hz]` — a onda da distorção — sem gramática nova: o
    sufixo já é parte do nome que o catálogo dá.
    """
    from osclab.plot import catalogo

    por_coluna: dict = {}
    por_linha: dict = {}
    for sinal in catalogo.de_registro(registro, "arquivo"):
        chave = chave_do_nome(sinal.linha or sinal.nome)
        if not chave:
            continue
        # O nome da COLUNA, quando ele difere do da linha: `IAW · 60Hz`.
        cheio = chave_do_nome(sinal.nome or "")
        if cheio and cheio != chave:
            por_coluna[cheio] = (None if cheio in por_coluna else sinal)
        atual = por_linha.get(chave)
        if atual is None:
            por_linha[chave] = sinal
        elif atual is _REPETIDO:
            continue
        elif atual.linha != sinal.linha:
            # Duas LINHAS diferentes com o mesmo nome não servem de
            # referência: escolher uma no escuro seria pior que recusar.
            por_linha[chave] = _REPETIDO
        elif (atual.grandeza != "instantaneo"
                and sinal.grandeza == "instantaneo"):
            # A mesma linha na outra coluna não é repetição: a ONDA ganha da
            # RMS, que é a coluna natural de quem tem as duas.
            por_linha[chave] = sinal
    saida: dict = {}
    # As colunas primeiro, as linhas depois: se um canal se chamar, por azar,
    # `IN G1 · RMS`, quem manda é a LINHA — ela é o que o usuário vê no
    # catálogo como nome do sinal.
    for origem in (por_coluna, por_linha):
        for chave, sinal in origem.items():
            if sinal is None or sinal is _REPETIDO:
                saida[chave] = None
                continue
            saida[chave] = Referencia(
                linha=sinal.nome if origem is por_coluna
                      else (sinal.linha or sinal.nome),
                unidade=sinal.unidade, grandeza=sinal.grandeza,
                bloco=sinal.bloco, canal=sinal.canal, sinal=sinal)
    return saida


def referenciaveis(registro: Record, anteriores=()) -> dict:
    """`NOME EM MAIÚSCULAS` → a `Referencia`, ou `None` se o nome se repete.

    Entram os canais do arquivo, o resíduo da trinca (`IN G1`), as componentes
    de sequência (`3I0 G1`, `I1 G1`) e as contas que o usuário criou ANTES
    desta — nesta ordem, cada conta enxergando só o que veio antes dela.

    Em UMA passada: cada conta é analisada uma vez, contra o mapa montado até
    ali. É o que mantém o custo linear.
    """
    mapa = _do_catalogo(registro)
    for conta in (anteriores or ()):
        chave = chave_do_nome(conta.nome or "")
        analise = analisar_com(conta.expressao, registro, mapa)
        if not chave:
            continue
        if chave in mapa:
            mapa[chave] = None        # repetido: nem um nem outro serve
            continue
        if not analise.vale:
            # Conta quebrada não vira referência: quem a usasse herdaria o
            # erro sem saber de onde ele veio.
            continue
        mapa[chave] = Referencia(
            linha=conta.nome, unidade=analise.unidade_escrita,
            grandeza="instantaneo",
            bloco="alternado" if analise.alternado else "outros",
            analise=analise)
    return mapa


def analisar(expressao: str, registro: Record, escalas: dict,
             anteriores=()) -> Analise:
    """Lê a expressão contra os sinais DESTE registro.

    `anteriores` são as contas que o usuário criou antes desta — e só elas.
    Uma conta enxergar as que vieram depois abriria referência circular
    (`x1 = x2 + 1` com `x2 = x1 + 1`), e detectar ciclo é trabalho que a ordem
    de criação já faz de graça.
    """
    return analisar_com(expressao, registro,
                        referenciaveis(registro, anteriores))


def analisar_com(expressao: str, registro: Record, por_nome: dict) -> Analise:
    """O mesmo que `analisar`, com o mapa de nomes já montado.

    Existe para quem vai analisar VÁRIAS contas contra mapas que crescem — o
    catálogo e o `referenciaveis` — e não pode remontar o mapa a cada uma.

    Devolve sempre um `Analise`: o erro vai no campo, não numa exceção. A tela
    mostra o motivo enquanto o usuário digita, e exceção ali viraria `try` em
    volta de cada tecla.
    """
    from osclab.analysis import presenca

    por_grandeza: dict[str, str] = {}
    for canal in registro.analog_channels:
        g = fases.grandeza_da_unidade(canal.unit.strip())
        if g and g not in por_grandeza:
            por_grandeza[g] = canal.unit.strip()

    try:
        leitor = _Leitor(_quebrar(expressao), por_nome, por_grandeza)
        arvore = leitor.expressao()
        if leitor.i != len(leitor.fichas):
            sobra = leitor.fichas[leitor.i][1]
            raise ErroDaConta(f"sobrou «{sobra}» no fim da conta")
    except ErroDaConta as erro:
        return Analise(erro=str(erro))
    except RecursionError:
        return Analise(erro="a conta tem parênteses demais")

    if not leitor.usados:
        return Analise(erro="a conta não usa nenhum sinal — escreva o nome "
                            "dele entre colchetes, como [IAW]")

    avisos = list(leitor.avisos)
    # Instantâneo com eficaz: a ressalva mais importante desta calculadora. Um
    # eficaz é um patamar que anda devagar; uma onda cruza o zero cento e vinte
    # vezes por segundo. A soma existe, e não descreve grandeza nenhuma.
    if len(leitor.dominios) > 1:
        avisos.insert(0, "está somando um MÓDULO (RMS, eficaz) com uma onda: "
                         "o módulo jogou fora sinal e fase, e a conta é feita "
                         "amostra a amostra — o resultado não descreve "
                         "grandeza nenhuma")

    alternados = presenca.alternados(registro)

    def e_alternado(ref):
        if not ref.e_senoide:
            return False              # módulo e contínua não são senoide
        if ref.canal >= 0:
            return ref.canal in alternados
        return ref.bloco == "alternado"

    return Analise(
        arvore=arvore,
        unidade=arvore.unidade,
        unidade_escrita=_escrever_unidade(arvore.unidade, por_grandeza),
        canais=tuple(dict.fromkeys(r.canal for r in leitor.usados
                                   if r.canal >= 0)),
        fontes=tuple(dict.fromkeys(r.linha for r in leitor.usados)),
        # Soma e subtração de senoides de mesma frequência é senoide; produto
        # entre sinais não é. Ver o cabeçalho.
        alternado=(all(e_alternado(r) for r in leitor.usados)
                   and not leitor.tem_produto_de_sinais),
        tem_produto=leitor.tem_produto_de_sinais,
        dominios=tuple(sorted(leitor.dominios)),
        avisos=tuple(dict.fromkeys(avisos)),
    )


#: Abaixo de quanto o 60 Hz de um sinal é ruído do método, e não medida.
#:
#: Como fração do eficaz do PRÓPRIO sinal, que é o que torna o número
#: independente de escala e de unidade. Medido, em quatro taxas:
#:
#:     taxa      am/ciclo   `[V]-[V·60Hz]`   `[V]×[W]`   sinal com 2 % de 60 Hz
#:     1200 Hz     20,00        0,088 %       0,223 %          1,96 %
#:     2000 Hz     33,33        0,099 %       0,229 %          1,96 %
#:     4000 Hz     66,67        0,087 %       0,225 %          1,96 %
#:
#: Os nulos ficam entre 0,09 % e 0,23 % — é o vazamento do próprio filtro, e
#: ele não cresce com a taxa fracionária do SEL, que era a dúvida. Um por
#: cento fica uma ordem de grandeza acima disso e metade do menor caso
#: legítimo que vale a pena guardar.
#:
#: Medido de novo, agora em sinal SUJO (3º harmônico e contínua decaindo), que
#: é onde a primeira calibração falhou:
#:
#:     conta                        mediana da razão
#:     `[A] - [B]`                       99,06 %
#:     `[A · 60Hz] - [B · 60Hz]`        100,00 %
#:     `[A] - [A · 60Hz]`                 0,04 %
#:     `[A] × [B]`                        0,13 %
PISO_DE_60HZ = 0.01


def tem_60hz(onda, registro: Record) -> bool:
    """Se sobrou 60 Hz neste sinal, ou se o que há ali é ruído do método.

    MEDIDO na própria série, não deduzido da expressão. `[VAY] - [VAY · 60Hz]`
    é a onda da distorção: tudo menos 60 Hz. `[VAY] × [IAW]` é potência: tem
    contínua e 120 Hz, e nada em 60. Nos dois casos a coluna do filtrado
    desenharia uma reta no zero com cara de medida — e é por isso que a
    pergunta é feita aqui, e não pela procedência das entradas.
    """
    from osclab.dsp import envoltoria

    if onda is None or getattr(onda, "size", 0) == 0:
        return True                      # sem série não se afirma ausência
    try:
        f60 = envoltoria.calcular(onda, registro.trechos,
                                  registro.line_frequency, "fundamental")
        eficaz = envoltoria.calcular(onda, registro.trechos,
                                     registro.line_frequency, "rms")
    except (ValueError, FloatingPointError):
        return True
    if f60 is None or eficaz is None:
        return True
    # A MEDIANA da razão, amostra a amostra — não o pico dela.
    #
    # Com o pico, o transitório do começo do registro mandava no resultado: a
    # contínua decaindo de uma falta tem 60 Hz de vazamento, e a distorção
    # media 3,5 % só por causa das primeiras amostras. Pela mediana ela mede
    # 0,04 %, contra 99 % de uma conta linear. Três ordens de grandeza de
    # separação, em vez de um fator de trinta.
    bons = np.isfinite(f60) & np.isfinite(eficaz) & (eficaz > 0.0)
    if not bool(bons.any()):
        # Série identicamente nula: não há 60 Hz ali, e isso é afirmação, não
        # ignorância. `[VAY] - [VAY · 60Hz]` numa senoide limpa dá exatamente
        # zero — a distorção de um sinal sem distorção.
        return False
    return float(np.median(f60[bons] / eficaz[bons])) >= PISO_DE_60HZ


# --- a conta, sobre as amostras --------------------------------------------

def serie(registro: Record, analise: Analise, lado: str,
          divisor: float) -> np.ndarray | None:
    """A onda da conta, sobre o registro INTEIRO, já na unidade da tela.

    Inteiro e não só a janela: o fasor de um instante precisa do ciclo que vem
    antes dele, e esse ciclo pode estar fora da janela desenhada — é a mesma
    razão do resíduo.
    """
    if not analise.vale or registro.analog.size == 0:
        return None
    try:
        saida = _avaliar(analise.arvore, registro, lado)
    except (ValueError, KeyError, FloatingPointError):
        return None
    if saida is None:
        return None
    return saida / divisor if divisor and divisor != 1.0 else saida


def _serie_do_sinal(ref, registro: Record, lado: str) -> np.ndarray:
    """A série de uma referência, convertida e SEM o prefixo da tela.

    Sem o prefixo de propósito: a conta roda em unidade de engenharia do
    arquivo e o `k` é aplicado uma vez só, no fim, sobre o resultado — ver o
    cabeçalho. Por isso o `escalas` vai vazio: ali todo divisor vale 1.

    Quando a referência é outra CONTA, desce direto na árvore dela: voltar ao
    catálogo reanalisaria a expressão, e numa cadeia de contas isso dobra de
    custo a cada elo.
    """
    from osclab.plot import catalogo

    if ref.analise is not None:
        return _avaliar(ref.analise.arvore, registro, lado)
    n = registro.analog.shape[1]
    valores = catalogo.serie(registro, ref.sinal, 0, n, registro.trechos,
                             lado, {})
    return np.asarray(valores, dtype=np.float64)


def _avaliar(no: _No, registro: Record, lado: str) -> np.ndarray:
    n = registro.analog.shape[1]
    if no.op == "num":
        return np.full(n, float(no.numero))
    if no.op == "sinal":
        return _serie_do_sinal(no.sinal, registro, lado)
    if no.op == "neg":
        return -_avaliar(no.filhos[0], registro, lado)
    if no.op == "abs":
        return np.abs(_avaliar(no.filhos[0], registro, lado))
    if no.op == "raiz":
        dentro = _avaliar(no.filhos[0], registro, lado)
        # Raiz de negativo não é erro do usuário nem do programa: é o que
        # acontece numa amostra em que a soma de quadrados ficou negativa por
        # arredondamento. Zero ali é a resposta honesta.
        return np.sqrt(np.maximum(dentro, 0.0))
    if no.op == "pot":
        return _avaliar(no.filhos[0], registro, lado) ** int(no.numero)
    esquerda = _avaliar(no.filhos[0], registro, lado)
    direita = _avaliar(no.filhos[1], registro, lado)
    if no.op == "+":
        return esquerda + direita
    if no.op == "-":
        return esquerda - direita
    if no.op == "*":
        return esquerda * direita
    if no.op == "/":
        # Dividir por sinal agora vale (com ressalva), então o denominador
        # pode zerar de verdade. NaN ali é melhor que explodir o pedido
        # inteiro: a tela desenha buraco e a tabela mostra traço.
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.divide(esquerda, direita,
                             out=np.full_like(esquerda, np.nan),
                             where=direita != 0)
    raise ValueError(no.op)
