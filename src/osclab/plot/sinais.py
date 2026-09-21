"""Que sinal a tela está mostrando, e como ele se chama.

## Canal não é sinal

O arquivo traz **canais**: `Current IA`, amostra por amostra, como o relé
gravou. A tela mostra **sinais**, que são derivados deles por uma operação
conhecida — filtrar em 60 Hz, tomar o eficaz de um ciclo, os dois.

Um canal dá origem a quatro sinais, e eles são coisas diferentes:

    IA           a amostra crua
    IA RMS       eficaz verdadeiro da janela de um ciclo
    IA 60Hz      só a componente de 60 Hz, no tempo
    IA 60Hz RMS  o eficaz dessa componente — a "fundamental"

Cada um tem nome próprio porque cada um vai poder ser manipulado sozinho:
posto num gráfico separado, comparado com outro, usado numa conta. Sem nome
próprio, um relatório com "IA = 18,2 A" não diz se aquilo saiu do filtro ou
não — e a diferença entre os dois chega a 25 % numa falta assimétrica.

## Por que o nome nasce aqui, e não no navegador

Porque é **identidade**, não rótulo. O nome tem que ser o mesmo na legenda, na
tabelinha, no relatório e, mais adiante, na fórmula que o usuário escrever. Um
nome montado no JavaScript viveria só na tela e teria que ser remontado — igual,
com sorte — em cada um dos outros lugares.

## Por que não `IA₁` para a fundamental

Porque no marco 0.4b entram as componentes simétricas, e ali `I1` é **sequência
positiva**. Os dois usos do subscrito 1 convivem no ofício (harmônico ×
sequência) e se distinguem pela letra de fase — uma letra de diferença
carregando uma troca inteira de significado, com os dois na mesma tela. O nome
explícito é mais longo e nunca é ambíguo.
"""

from __future__ import annotations

#: As quatro vistas, e como cada uma se chama no fim do nome do sinal. A ordem
#: do sufixo é a ordem das operações: filtra-se primeiro, mede-se depois.
SUFIXOS = {
    "instantaneo": "",
    "rms": "RMS",
    "filtrado": "60Hz",
    "fundamental": "60Hz RMS",
}

GRANDEZAS = tuple(SUFIXOS)

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


def nome(padrao: str, grandeza: str, rotulo: str = "") -> str:
    """O nome do sinal: o canal, o que foi feito com ele, e de que conjunto é.

        IA            uma trinca de correntes só no registro
        IA RMS        a mesma, medida em eficaz
        IA RMS AT     num relé de trafo, onde há correntes de dois lados

    O apelido do conjunto (`AT`, `W`, `69kV`) vem por último e **só existe
    quando há mais de um conjunto da mesma grandeza** — ver
    `formats/conjuntos.py`. Sem ele, um registro de trafo teria dois canais
    chamados `IA` e a tela não diria qual é qual.

    Devolve `""` quando o canal não tem nome padronizado: o OscLab não batiza o
    que não conseguiu identificar, e um `" RMS"` solto seria pior que nada.
    """
    if not padrao:
        return ""
    partes = [padrao, SUFIXOS.get(grandeza, ""), (rotulo or "").strip()]
    return " ".join(p for p in partes if p)
