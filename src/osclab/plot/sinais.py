"""Que sinal a tela está mostrando, e como ele se chama.

## Canal não é sinal

O arquivo traz **canais**: `Current IA`, amostra por amostra, como o relé
gravou. A tela mostra **sinais**, que são derivados deles por uma operação
conhecida — filtrar em 60 Hz, tomar o eficaz de um ciclo, os dois.

Um canal dá origem a quatro sinais, e eles são coisas diferentes:

    IAW              a amostra crua, como o relé gravou
    IAW · RMS        eficaz verdadeiro da janela de um ciclo
    IAW · 60Hz       só a componente de 60 Hz, no tempo
    IAW · 60Hz RMS   o eficaz dessa componente — a "fundamental"

**A base é o nome do ARQUIVO**, não um nome nosso. Já foi `IA`, `IB`, `IC` —
a fundamental que o programa deduzia —, e a tela ficava com duas nomenclaturas
para a mesma coisa: `IAW` na aba do IED e `IA` na legenda do gráfico. Pior, num
trafo dois canais viravam `IA` e foi preciso inventar um apelido de trinca para
desempatar. Com o nome do relé não há empate possível: ele já nomeia os
terminais dele de forma única, em todo fabricante.

O `·` separa o nome do canal do que se fez com ele. Não é hífen porque o GE
grava canais chamados `J1 -IA`: `J1 -IA - RMS` teria dois hífens de
significados diferentes na mesma linha.

O `60` sai da frequência NOMINAL DO REGISTRO, e não de uma constante: um
arquivo de 50 Hz escreve `IA 50Hz` sozinho. Escrever `60` num registro de 50 Hz
seria um nome errado que nada na tela denunciaria.

Cada um tem nome próprio porque cada um vai poder ser manipulado sozinho:
posto num gráfico separado, comparado com outro, usado numa conta. Sem nome
próprio, um relatório com "IA = 18,2 A" não diz se aquilo saiu do filtro ou
não — e a diferença entre os dois chega a 25 % numa falta assimétrica.

## Por que o nome nasce aqui, e não no navegador

Porque é **identidade**, não rótulo. O nome tem que ser o mesmo na legenda, na
tabelinha, no relatório e, mais adiante, na fórmula que o usuário escrever. Um
nome montado no JavaScript viveria só na tela e teria que ser remontado — igual,
com sorte — em cada um dos outros lugares.

## O nome é UM, e é desenhado inteiro

`IAW · 60Hz RMS` é o nome — em texto puro, o mesmo na legenda, na tabelinha, no
relatório e na fórmula.

Houve uma versão em que a frequência ia em **subscrito**, e ela saiu: o servidor
mandava o nome partido em três (`("IAW ·", "60Hz", "RMS")`), e o nome passava a
existir em duas formas, com um teste só para garantir que as duas diziam a mesma
coisa. Uma forma só é mais barata que duas formas conferidas.

O subscrito VOLTOU em 12/10/2026, por escolha do Alexandre, **sem esse defeito**:
o servidor continua mandando UMA string — `IAW · 60Hz RMS`, a que vai para o
relatório, para a fórmula e para a busca — e quem a parte é a TELA, na hora de
desenhar (`escreverNome`, em `web/static/js/onda.js`). O `·` não é desenhado:
quem separa é a posição, e por isso o problema de leitura da versão antiga
(`IAW ·60Hz`, com o ponto colado no subscrito) não existe aqui.

As marcas são coloridas com as MESMAS cores das fatias da barra de energia do
cartão — turquesa é 60 Hz, rosa é contínua, e o RMS fica na cor do texto porque
não é fatia nenhuma: é o total. A cor reforça, não carrega — tamanho e posição
já distinguem as marcas sem ela, que é o que mantém o nome legível impresso em
preto e branco.

**Anotado para o futuro:** o Alexandre quer que essa notação vire **escolha do
usuário** — subscrito, pastilha, nome corrido. Por isso a partição mora em UM
lugar só na tela; trocar de família será trocar essa função, não caçar o nome
por vinte arquivos.

## Por que não `IA₁` para a fundamental

Porque no marco 0.4b entram as componentes simétricas, e ali `I1` é **sequência
positiva**. Os dois usos do subscrito 1 convivem no ofício (harmônico ×
sequência) e se distinguem pela letra de fase — uma letra de diferença
carregando uma troca inteira de significado, com os dois na mesma tela. O nome
explícito é mais longo e nunca é ambíguo.
"""

from __future__ import annotations

#: A frequência que os nomes usam quando ninguém disse qual é a do registro.
FREQUENCIA_PADRAO = 60.0

#: As quatro vistas e o sufixo de cada uma, em duas partes só para o `{f}` da
#: frequência poder ser preenchido. A ordem é a das operações: filtra-se
#: primeiro, mede-se depois.
_PARTES_DO_SUFIXO = {
    "instantaneo": ("", ""),
    "rms": ("", "RMS"),
    # A contínua não leva frequência no nome: ela é o que sobra DEPOIS de tirar
    # a alternada, e `IAW · 60Hz DC` se leria como "a DC da componente de
    # 60 Hz", que é zero por definição.
    "dc": ("", "DC"),
    "filtrado": ("{f}Hz", ""),
    "fundamental": ("{f}Hz", "RMS"),
}

GRANDEZAS = tuple(_PARTES_DO_SUFIXO)


def frequencia_no_nome(frequencia: float) -> str:
    """`60`, `50`, `59.94` — sem casa decimal quando não precisa."""
    valor = float(frequencia or FREQUENCIA_PADRAO)
    return f"{valor:g}"


def partes_do_sufixo(grandeza: str,
                     frequencia: float = FREQUENCIA_PADRAO) -> tuple[str, str]:
    """`("60Hz", "RMS")` — o que pode ir em subscrito e o que fica normal."""
    sub, resto = _PARTES_DO_SUFIXO.get(grandeza, ("", ""))
    return (sub.format(f=frequencia_no_nome(frequencia)), resto)


#: O que separa o nome do canal do que o OscLab fez com ele. Ponto médio, e
#: não hífen: o GE grava `J1 -IA` e `J2 -VX`, e `J1 -IA - RMS` põe dois hífens
#: de significados diferentes na mesma linha.
SEPARADOR = " · "


def sufixo(grandeza: str, frequencia: float = FREQUENCIA_PADRAO) -> str:
    """`RMS`, `60Hz`, `60Hz RMS` — o fim do nome, em texto puro."""
    return " ".join(x for x in partes_do_sufixo(grandeza, frequencia) if x)


#: Mantido para quem só quer o sufixo do caso comum de 60 Hz.
SUFIXOS = {g: sufixo(g) for g in GRANDEZAS}

#: A combinação dos dois controles da tela. O filtro é do registro inteiro (e
#: trava quando o relé já filtrou); a medida é de cada gráfico.
_COMBINACAO = {
    (False, "instantaneo"): "instantaneo",
    (False, "rms"): "rms",
    (True, "instantaneo"): "filtrado",
    (True, "rms"): "fundamental",
}

MEDIDAS = ("instantaneo", "rms")


def resolver(filtro: bool, medida: str) -> str:
    """A grandeza que sai de `filtro` ligado ou não mais a medida escolhida."""
    if medida not in MEDIDAS:
        medida = "instantaneo"
    return _COMBINACAO[(bool(filtro), medida)]


def aplicavel(filtro: bool, filtragem: str) -> bool:
    """O filtro de 60 Hz só vale para o que ainda não foi filtrado.

    Quando o relé filtrou antes de gravar, as amostras do arquivo **já são** a
    componente de 60 Hz. Rodar o filtro de novo não limparia nada que já não
    esteja limpo e acrescentaria mais um ciclo de atraso: a falta passaria a
    aparecer na tela dois ciclos depois de ter acontecido, e o valor lido no
    cursor seria o de dois ciclos atrás.

    A tela mostra o botão aceso e preso, porque esse é o estado do sinal — e o
    servidor não filtra. As duas coisas são verdade ao mesmo tempo.
    """
    return bool(filtro) and str(filtragem) != "filtrado"


#: O que separa o nome do canal do que o OscLab fez com ele. Ponto médio, e
#: não hífen: o GE grava `J1 -IA` e `J2 -VX`, e `J1 -IA - RMS` põe dois hífens
#: de significados diferentes na mesma linha.
SEPARADOR = " · "


def nome(base: str, grandeza: str,
         frequencia: float = FREQUENCIA_PADRAO) -> str:
    """O nome do sinal: o canal do arquivo e o que foi feito com ele.

        IAW              a amostra crua
        IAW · RMS        a mesma, medida em eficaz
        IAW · 60Hz       só a componente de 60 Hz, no tempo
        IAW · 60Hz RMS   o eficaz dessa componente

    Devolve `""` quando o canal não tem nome — arquivo torto, e um `" RMS"`
    solto seria pior que nada.
    """
    base = (base or "").strip()
    if not base:
        return ""
    fim = sufixo(grandeza, frequencia)
    return f"{base}{SEPARADOR}{fim}" if fim else base
