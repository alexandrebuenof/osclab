"""O catálogo de sinais que se pode acrescentar a um gráfico.

## As duas listas: IED e OscLab

    IED       os canais do arquivo, com o nome que o fabricante deu
    OscLab    tudo que saiu de uma conta nossa

## O nome do sinal é o nome do CANAL mais a conta

    IED       IAW                      o canal, com o nome que o relé deu
    OscLab    IAW · RMS                o que o relé NÃO gravou
              IAW · 60Hz
              IAW · 60Hz RMS

Já foi `IA`, `IB`, `IC` — a fundamental que o programa deduz do nome do canal.
Duas nomenclaturas para a mesma coisa na mesma tela (`IAW` na aba do IED, `IA`
na legenda), e num trafo dois canais diferentes viravam `IA`, o que obrigou a
inventar um apelido de trinca para desempatar. O nome do relé não empata: ele
já nomeia os terminais dele de forma única, em todo fabricante.

**O vínculo com a fase continua existindo** — é dele que saem as trincas, as
componentes e o agrupamento dos painéis, e ele continua deduzido de um nome que
cada fabricante escreve como quer. Se estiver errado, 3I0 e V1 saem errados
**sem dar erro nenhum**. O que mudou é que ele não aparece mais como nome de
sinal; corrige-se pelo lápis, na lista do IED.

## O nome do grupo (`G1`) só aparece no que sai de uma trinca

E aparece ali porque não há alternativa: `3I0` sai de TRÊS canais, então não há
um nome de arquivo a herdar. Todo o resto usa o nome do canal e não precisa de
desempate nenhum. De que trinca veio a componente está escrito no rodapé do
gráfico, com os nomes do arquivo entre aspas — e o mesmo `G1` é o que o editor
de grupos edita. Ver `formats/conjuntos.rotular`.

## E ela só oferece contas sobre GRANDEZA DE FASE ALTERNADA

Duas condições, e nenhuma delas é uma lista de nomes suspeitos — lista de nomes
envelhece a cada fabricante novo:

1. **é alternado** (`analysis/presenca.py`): o que decide é a unidade e a
   média. A unidade é lista BRANCA — só ampère e volt, com prefixo. Grau, hertz,
   `I/IrObj` e unidade nenhuma não entram, e é isso que barra os ângulos do GE,
   as magnitudes `V1M`/`3V2M`/`LIGM` do CEV e as correntes diferencial e de
   restrição em pu do SIPROTEC. A média barra a tensão da bateria.
2. **o programa reconheceu a fase** — `IA`…`IN`, `VA`…`VN`. É o que barra a
   tensão de sincronismo `VS1`, a de memória `V1MEM`, a `Voltage Vref` do
   Schneider e o terceiro banco de TC do 487E, nomeado `IY1`, `IY2`, `IY3`.

Fazer `V1M 60Hz RMS` seria filtrar em 60 Hz um número que já é o módulo do
fasor de 60 Hz: a conta roda, sai um número, e o número não quer dizer nada.

**Estar em trinca NÃO é condição.** Foi, e custava seis neutros de verdade: o
`J1 -IG` e o `J1 Ig` do GE e os dois `NEUTRO:Ix` do SIPROTEC ficam fora de
trinca porque o arquivo tem mais de uma trinca da mesma unidade e nada com que
decidir de qual delas eles são. São residuais de verdade e precisam de eficaz.

**Estar SEM SINAL também não é condição.** Um terminal de TC não cabeado ganha
as contas como qualquer outro; quem o tira da tela é a caixa «ocultar sinais
nulos», pelo campo `sem_sinal`. Fazer a conta deixar de existir daria um botão
de RMS que não faz nada quando o usuário desmarca a caixa para olhar a trinca
escondida — comportamento mudando com checkbox. E há um caso em que o zero é a
resposta: um transformador energizado de um lado só tem a trinca do outro lado
em zero legitimamente, e nenhuma medida sobre um registro só distingue isso de
uma entrada aberta.

O canal que não passa continua inteiro na aba do IED, desenhável como sempre.

## O filtro empurra para o grupo FILTRADO — tudo o que está na tela

O botão de filtro do cabeçalho responde a pergunta "qual sinal estou olhando":
o filtrado, que é só a componente de 60 Hz, ou o bruto, que é tudo o que o relé
gravou. Ele é do REGISTRO INTEIRO, e por isso vale também para o sinal que o
usuário escolheu à mão: com o filtro aceso, `IAW · RMS` desenha
`IAW · 60Hz RMS`.

Já mexeu só nos canais que abriam por padrão, pelo argumento de que o sinal
posto à mão carrega a própria medida no nome. O preço apareceu na tela: metade
do gráfico respondia ao botão e a outra metade não, com o cabeçalho dizendo
«filtrado» para as duas. Quem comparasse `IAW · RMS` com a onda ao lado estaria
comparando um eficaz COM harmônicos contra uma onda filtrada, sem nada na tela
denunciando.

O que protege o significado é o NOME, e ele continua protegendo: quem troca é
`efetivo`, num lugar só, e o nome do sinal que ele devolveu é o que vai para a
legenda, para a tabelinha do cursor e para o relatório. O sufixo `60Hz`
aparece nos três ao mesmo tempo.

**Apagar o filtro não empurra ninguém de volta.** A identidade escolhida não
muda — ela continua no arranjo da tela —, então acender e apagar devolve o que
estava, e esse é o caminho de volta. Arrastar o filtrado para o bruto seria
outra coisa, e apagaria a comparação que o modo avançado existe para fazer:
`IAW · 60Hz` ao lado de `IAW`, escolhidos com o filtro apagado, são duas curvas
que ficam duas.

E o botão só empurra o que tem par no grupo filtrado:

    IAW            → IAW · 60Hz        o canal, pelo botão de sempre
    IAW · RMS      → IAW · 60Hz RMS
    IAW · DC       → IAW · DC          a DC do filtrado é zero por definição
    IN G1          → IN G1 · 60Hz
    IN G1 · RMS    → IN G1 · 60Hz RMS  o mesmo número do 3I0 — ver abaixo
    3I0 G1         → 3I0 G1            já é fasor de 60 Hz

Num registro que o relé já gravou filtrado, as variantes `60Hz` não são
oferecidas: as amostras já SÃO a componente de 60 Hz, e filtrar de novo só
acrescentaria mais um ciclo de atraso. Ali o botão chega apagado a `efetivo`
(ver `sinais.aplicavel`) e não empurra nada.

A MEDIDA de cada painel — instantâneo × RMS — continua sendo outra coisa: ela
pega só nos canais do IED, porque `IAW · DC` com a medida em eficaz não é
`IAW · RMS`, é o eficaz da contínua, que ninguém pediu.

## `· DC` só existe no registro BRUTO, e pelo mesmo motivo

O relé tira a contínua antes de gravar, então num `.CEV` ela é zero por
construção. Medido nos três `.CEV` do parque, **só em regime**: mediana de
0,00 % a 0,02 % da fundamental. Nos COMTRADE brutos a mesma medida dá 0,2 % a
1,1 % de mediana, com máximos de 43 % a 1491 %.

Os poucos por cento que sobram no `.CEV` são o artefato de sempre — janela em
cima de uma borda —, e no arquivo de 4 amostras por ciclo uma "média de quatro
amostras" é um estimador de contínua ruim por natureza.

A DC sai **em unidade de engenharia, com sinal**. O percentual da fundamental
é a convenção do SIGRA e continua na tabelinha do cursor, onde já foi conferido
contra ele nos oito canais. Como CURVA ele seria razão de duas envoltórias:
quando o disjuntor abre, a fundamental vai a zero e a razão estoura.

## Por que nada entra sozinho

O programa sabe calcular 3I0, I1 e I2 desde que há três fases no arquivo. Ele
**não** põe nenhum deles na tela por conta própria, e isso é decisão tomada:
uma tela que se enche do que o programa sabe fazer vira um painel de números
que ninguém pediu, e o que importa some no meio. Quem analisa escolhe o que
olhar; o programa oferece.

Cada sinal escolhido é acrescentado a UM gráfico, por decisão de quem está
analisando.

## A identidade de um sinal cabe numa linha de texto

O navegador precisa dizer ao servidor "põe este sinal neste gráfico", e o
servidor precisa devolver o mesmo sinal com o mesmo nome. Um `id` de texto
resolve os dois lados e atravessa a URL sem ambiguidade:

    c3:instantaneo      o canal 3 do arquivo, cru, como o IED gravou
    v3:rms              o eficaz da janela de um ciclo daquele canal
    v3:fundamental      a componente de 60 Hz dele, em eficaz
    q0:1:rms            a sequência positiva do conjunto trifásico 0

O `q` é o índice do conjunto em `conjuntos.de_registro`, que é estável para um
mesmo arquivo. O `0`, `1`, `2` do meio são zero, positiva e negativa.

## Componente simétrica é fasor, e só existe em eficaz

`I1` e `I2` exigem girar `Ib` e `Ic` de 120°, e girar é multiplicar por um
complexo — operação que não existe sobre uma amostra sozinha. Só existe sobre o
fasor.

Por isso as componentes saem sempre como **módulo do fasor da janela de um
ciclo, em eficaz**, e as três seguem a mesma regra: `3I0` instantâneo ao lado de
`I1` só em eficaz seria uma tela em que dois números com a mesma cara vieram de
definições diferentes. Um ciclo de atraso na subida vale para todas elas, como
vale para qualquer curva de envoltória.

## `IN` e `VN`: o resíduo no tempo, que é outra coisa

`3I0` é módulo de fasor: passa pela janela de um ciclo e **só enxerga 60 Hz**.
A soma `ia+ib+ic` amostra a amostra não filtra nada — carrega a assimetria (a
DC da falta) e os harmônicos do resíduo, que é justamente o que um TC saturando
despeja ali.

São grandezas diferentes, e é por isso que ambas existem no catálogo:

    IN G1             ia+ib+ic amostra a amostra — a senoide, com DC e harmônicos
    IN G1 · RMS       o eficaz VERDADEIRO dessa soma, janela de um ciclo
    IN G1 · 60Hz      só a componente de 60 Hz da soma, no tempo
    IN G1 · 60Hz RMS  o eficaz dela — o MESMO número do 3I0
    3I0 G1            o módulo do fasor de 60 Hz da mesma trinca

Em regime senoidal puro `IN · RMS` e `3I0` dão o mesmo número. Quando não dão,
a diferença **é a medida**: é DC, harmônico ou saturação de TC. Ter os dois na
mesma tela é o que torna isso visível.

### As variantes `60Hz` do resíduo existem, e uma delas repete o `3I0`

`IN · 60Hz RMS` é, por definição, o próprio `3I0`: a DFT é linear, então o
fasor de `ia+ib+ic` é a soma dos três fasores — que é `3I0`. Número por número,
na mesma amostra. Já esteve fora do catálogo exatamente por isso.

Voltou a pedido do usuário (out/2026), pelo motivo que vale numa ferramenta
para a distribuidora inteira: nem todo mundo que abre uma oscilografia sabe que
`3I0` é a versão de 60 Hz do neutro. Com a linha `IN G1` tendo as mesmas
colunas que `IAW`, a leitura fica a mesma em todas as linhas, e o `3I0`
continua onde estava, com o nome do ofício. A descrição de cada um diz que o
número é o mesmo.

`IN · 60Hz`, a onda, é informação que não existia: é a senoide do `3I0` no
tempo, que dá para comparar em fase com `VN · 60Hz` e com as correntes.

### E num registro JÁ FILTRADO o eficaz sai pela DFT

O que segue explica por que ali o eficaz do resíduo NÃO usa a conta `rms` dos
canais: ele usa a DFT (`fundamental`), e por isso sai igual ao `3I0` em toda
amostra — inclusive nas bordas descritas abaixo.

Ali as amostras já são a componente de 60 Hz: não há DC nem harmônico para
`IN · RMS` enxergar, e ele vira o `3I0` com outro nome. Medido no `.CEV` do
alimentador: em regime a diferença é **+0,03 %**.

O que sobra são duas bordas — a entrada da falta e a extinção —, cada uma com
cerca de 1,4 ciclo em que as curvas se descolam (até 84 %). Isso **não é
grandeza**: é a resposta transitória de dois estimadores de janela de um ciclo
sobre o mesmo degrau. Com a janela metade cheia o eficaz marca 0,71 do valor
final e a DFT marca 0,50, porque um é energia e o outro é correlação com um
cosseno de ciclo inteiro. Por isso o erro medido é **positivo em 100 % das
amostras** — fenômeno de rede iria para os dois lados.

E há um motivo mais forte que o tamanho da diferença: no `.CEV` as amostras já
são a saída do filtro do relé, então `IN · RMS` ali seria um eficaz aplicado
EM CIMA daquele filtro — uma cadeia de medição que nenhum relé tem. Um 50N com
filtro de RMS mede as amostras BRUTAS. Naquelas bordas a curva não mostraria
como elemento nenhum viu a falta.

No registro bruto é o contrário: ali `IN · RMS` é uma cadeia real, e a
diferença para o `3I0` chega a 46 % por causa da DC — que é informação de
verdade sobre a falta.

`IN` **não** é o neutro medido. O canal do arquivo (`IG` no SEL, `J1 -IG` no
GE, `NEUTRO:Ix` no SIPROTEC) continua na aba do IED com o nome que o relé deu.
Comparar os dois é um ensaio de verdade: se o `IN` calculado não bate com o
neutro medido, ou a trinca está errada, ou um TC está saturado, ou o neutro
mede outro ponto do circuito.

Vale igual para tensão: `VN` é `va+vb+vc` no tempo — o resíduo que um TP em
delta aberto mede.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from osclab.dsp import envoltoria, potencia, simetricas
from osclab.formats import conjuntos, fases
from osclab.formats.base import Record
from osclab.plot import conversao, sinais, unidades

#: Índice da componente no resultado de `simetricas.de_fasores`, e como ela se
#: chama. O `{g}` vira `I` ou `V`, conforme a grandeza do conjunto.
COMPONENTES = {
    "0": (0, "3{g}0", "sequência zero — o resíduo das três fases"),
    "1": (1, "{g}1", "sequência positiva"),
    # O aviso do TRIPLO não é enfeite: o comissionamento de 22/09/2026 tropeçou
    # nele. A SEL grava `3V2M` e `L3I2M`, que são 3× este número, e comparar a
    # tela com a coluna do relé dava −67,89 % de "erro" que não era erro
    # nenhum. Mantivemos `{g}2` (é a componente de Fortescue de verdade) e
    # pagamos o preço aqui, onde quem for comparar está olhando.
    "2": (2, "{g}2", "sequência negativa — o relé costuma gravar 3{g}2, "
                     "que é o TRIPLO desta"),
}

#: A chave do resíduo dentro do id (`q0:n:instantaneo`). Fica no mesmo
#: espaço de nomes das componentes porque a origem é a mesma — a trinca —, mas
#: ele **não** é componente de Fortescue: é soma no tempo. Ver o cabeçalho.
RESIDUAL = "n"

#: O que o OscLab oferece sobre o resíduo de uma trinca num registro BRUTO.
#:
#: A onda `IN` se decompõe em três pedaços ORTOGONAIS, e a tela oferece os
#: três — cada um responde uma pergunta diferente:
#:
#:     IN             a senoide somada amostra a amostra
#:      ├─ 60 Hz      já se chama `3I0`, e por isso não se repete aqui
#:      ├─ 0 Hz       é o `IN · DC`
#:      └─ harmônicos
#:
#: Parseval os amarra: `IN·RMS² = 3I0² + IN·DC² + harmônicos²`. Medido no
#: alimentador, na entrada da falta: `3I0` 15 A e `IN · DC` 15 A ao mesmo
#: tempo — metade alternada, metade deslocamento. Quem olhasse só o `3I0`
#: levaria metade da história.
#:
#: **A DC do resíduo é a que satura TC de terra.** A de cada fase já estava na
#: tela; a que passa pelo TC de neutro é esta.
RESIDUO_DE_BRUTO = (("instantaneo", "instantaneo"), ("rms", "rms"),
                    ("dc", "dc"),
                    ("filtrado", "filtrado"), ("fundamental", "fundamental"))

#: Num registro que o relé JÁ gravou filtrado, as amostras do resíduo já são a
#: onda de 60 Hz, e o eficaz dela sai pela DFT — `fundamental`, e não `rms`.
#: Ver «E num registro JÁ FILTRADO» no cabeçalho.
RESIDUO_DE_FILTRADO = (("instantaneo", "instantaneo"), ("rms", "fundamental"))

#: O hover de cada uma. `{x}` vira `i` ou `v`; `{g}`, `I` ou `V`. A segunda
#: linha cita o `3I0` de propósito: a pergunta que o usuário faz ao ver os dois
#: na lista é justamente "qual é a diferença", e é ali que ela cabe.
_O_QUE_E_O_RESIDUO = {
    "instantaneo": "{x}a+{x}b+{x}c amostra a amostra — a senoide do resíduo, "
                   "com DC e harmônicos",
    "rms": "eficaz verdadeiro dessa soma, janela de um ciclo — difere de "
           "3{g}0 quando há DC ou harmônico",
    "dc": "a componente contínua do resíduo — a parte de 0 Hz, complementar "
          "ao 3{g}0, que é a de 60 Hz",
    "filtrado": "só a componente de 60 Hz da soma, no tempo — a ONDA do "
                "3{g}0, para comparar fase com as outras ondas",
    "fundamental": "o eficaz dessa componente: é o MESMO número do 3{g}0, "
                   "que continua no catálogo — está aqui para ficar ao lado "
                   "da onda dele",
}

#: O mesmo, num registro que o relé já gravou filtrado: ali a soma JÁ É a onda
#: de 60 Hz, e o texto do bruto ("com DC e harmônicos") seria falso.
_O_QUE_E_O_RESIDUO_FILTRADO = {
    "instantaneo": "{x}a+{x}b+{x}c amostra a amostra — o relé gravou "
                   "filtrado, então esta já é a onda de 60 Hz do resíduo",
    "rms": "o eficaz dessa onda, pela DFT de um ciclo: é o MESMO número do "
           "3{g}0, que continua no catálogo",
}

#: O que o OscLab oferece a partir de UM canal: `(o que o sinal É, que conta
#: aplicar para chegar nele)`. Os dois são coisas diferentes, e a diferença
#: aparece justamente num registro já filtrado — ver o cabeçalho.
#:
#: Num registro BRUTO, as quatro contas são de verdade:
OFERTA_DE_BRUTO = (("rms", "rms"),
                   ("dc", "dc"),
                   ("filtrado", "filtrado"),
                   ("fundamental", "fundamental"))

#: Num registro que o relé JÁ gravou filtrado, as amostras já SÃO a componente
#: de 60 Hz. Sobra UMA conta a oferecer: o eficaz da janela de um ciclo.
#:
#: Havia duas. A primeira se chamava `IA' 60Hz` e não calculava nada — era o
#: próprio canal com outro nome. Numa tela que diz «gravação já filtrada pelo
#: relé» no cabeçalho, oferecer «filtrar em 60 Hz» ao lado se lê como filtrar
#: duas vezes, e ninguém adivinha que aquilo é a mesma curva.
#:
#: A segunda se chamava `IA' 60Hz RMS`, pelo argumento de que `IA' RMS` — eficaz
#: COM harmônicos — não existe ali. O argumento vale ao contrário: o que está
#: no arquivo não tem harmônico, então o eficaz verdadeiro DELE é esse número.
#: A ressalva de que os harmônicos foram removidos pelo relé é do REGISTRO
#: inteiro, e é o cabeçalho que a diz — repeti-la no nome de cada sinal cobra
#: atenção onde já não há escolha a fazer.
OFERTA_DE_FILTRADO = (("rms", "rms"),)


#: Em que COLUNA da matriz cada grandeza mora: `grupo.coluna`.
#:
#: A tela separa duas perguntas que a lista antiga misturava — QUAL sinal
#: (o filtrado, que é só a componente de 60 Hz, ou o bruto, que é tudo o que o
#: relé gravou) e COMO olhar para ele (a onda, o eficaz, a contínua). Sem essa
#: separação, `onda` e `60 Hz` apareciam como duas irmãs, e nada na tela dizia
#: que eram sinais diferentes.
_COLUNA_DA_GRANDEZA = {
    "instantaneo": "bruto.onda",
    "rms": "bruto.rms",
    "dc": "bruto.dc",
    "filtrado": "filtrado.onda",
    "fundamental": "filtrado.rms",
}

#: A contínua só existe no bruto: a DC de um sinal filtrado é zero por
#: definição, e é justamente o que o filtro tirou.
_COLUNA_DE_FILTRADO = {"instantaneo": "filtrado.onda", "rms": "filtrado.rms"}


def coluna_da_grandeza(grandeza: str, ja_filtrado: bool) -> str:
    """Em que coluna da matriz este sinal aparece.

    **Num registro que o relé já gravou filtrado, as amostras SÃO a componente
    de 60 Hz.** O canal e o eficaz dele não são «o bruto»: não existe bruto
    naquele arquivo. Mandá-los para as colunas do filtrado é o que impede a
    tela de dizer que se está olhando a onda crua quando não se está — e era o
    que ela dizia num `.CEV`, com as duas caixinhas na coluna errada.

    O NOME do sinal não muda por isso (`IAW` continua `IAW`): a ressalva de que
    o relé filtrou é do registro inteiro, e quem a diz é o cabeçalho.
    """
    if ja_filtrado and grandeza in _COLUNA_DE_FILTRADO:
        return _COLUNA_DE_FILTRADO[grandeza]
    return _COLUNA_DA_GRANDEZA.get(grandeza, "bruto.onda")


@dataclass(frozen=True)
class Sinal:
    """Um sinal que se pode acrescentar a um gráfico."""

    id: str
    nome: str
    #: A unidade do ARQUIVO — é ela que diz a que grupo/gráfico o sinal
    #: pertence, e é a chave por onde a tela agrupa.
    unidade: str
    #: A unidade COM prefixo, que é a que a tela escreve (`kV`).
    unidade_mostrada: str
    #: `canal` (veio do arquivo) ou `calculado` (saiu de uma conta nossa).
    familia: str
    #: O que o sinal É: `instantaneo`, `rms`, `filtrado` ou `fundamental`. Vem
    #: no `id` e no nome, e NÃO muda com o botão de filtro.
    grandeza: str
    #: A conta que se aplica às amostras para chegar nele. Quase sempre igual a
    #: `grandeza` — e diferente num registro já filtrado, onde `IA 60Hz` é o
    #: próprio canal, sem conta nenhuma. Ver `OFERTA_DE_FILTRADO`.
    conta: str
    descricao: str
    #: O canal de origem não está lendo nada além do ruído do conversor. O
    #: buscador esconde estes por padrão: um SEL-487E com três terminais de TC
    #: livres rende dezoito linhas de sinal que nunca vão ter dado. Ver
    #: `analysis/presenca.py`.
    sem_sinal: bool = False
    #: Para `familia == "calculado"`: de que canal (ou canais) do IED ele saiu.
    origem: str = ""
    #: Só para componente simétrica: a trinca que a produziu, para a tela poder
    #: CORRIGI-LA. `{"chave": "I*W", "unidade": "A", "canais": {"A": 0, ...}}`.
    #:
    #: A componente é o único sinal cuja origem é um palpite: `IAW · RMS` sai
    #: do canal 0 por definição — o id dele diz isso —, enquanto `3I0 G1` sai
    #: de três canais que o programa escolheu olhando nomes. Por isso só ela
    #: leva o editor.
    conjunto: dict | None = None
    #: A fase que o OscLab vinculou ao canal (`IA`, `VB`), ou `""` quando não
    #: reconheceu. **Não é nome de sinal nenhum**: é o vínculo em que as
    #: trincas, as componentes e o agrupamento dos painéis se apoiam, e é o que
    #: o lápis da lista do IED corrige.
    fundamental: str = ""
    #: De onde veio esse vínculo: `escolhida` (o usuário corrigiu), `declarada`
    #: (o campo `ph` do arquivo), `deduzida` (do nome) ou `desconhecida`. A
    #: tela precisa disso para dizer "deduzi" em vez de afirmar.
    fundamental_origem: str = ""
    #: O índice do canal no registro, para a tela poder mandar a correção.
    canal: int = -1
    #: Só para `familia == "canal"`: `I` ou `V`, tirado da unidade. É o que
    #: permite a tela oferecer `IA, IB, IC, IN` na correção em vez das letras
    #: soltas — a grandeza não é palpite, vem da unidade do arquivo.
    grandeza_do_canal: str = ""
    #: A LINHA do catálogo a que este sinal pertence: o nome sem o sufixo da
    #: conta. `IAW`, `IAW · RMS` e `IAW · DC` são três sinais e UMA linha,
    #: `IAW` — e cada conta é uma coluna nela. É o que permite a tela ser uma
    #: matriz de canais × contas em vez de uma lista de cento e vinte nomes.
    linha: str = ""
    #: O grupo trifásico de onde este sinal vem: `G1`, `G2`. Vazio quando ele
    #: não sai de trinca nenhuma — um `IG` avulso, a tensão da bateria.
    #:
    #: **Só o nome do grupo entra aqui.** O apelido de um residual solto
    #: (`[1]`, `[2]`) não é grupo e não aparece: a tela põe esses canais em
    #: «fora de grupo», e prometer um grupo que não existe seria pior que não
    #: agrupar. Ver `formats/conjuntos.rotular`.
    grupo: str = ""
    #: Em que bloco da tela o sinal mora:
    #:
    #:   `alternado`   canal senoidal, resíduo — aceita as contas todas
    #:   `sequencia`   componente simétrica: é fasor, e só existe em eficaz
    #:   `outros`      não dá para tirar fasor dele; ver `motivo`
    #:
    #: O bloco é do PROGRAMA, não do gosto: quem decide é
    #: `analysis/presenca.alternados`, medindo média contra fundamental. A tela
    #: não afirma que um canal de `outros` é contínuo — afirma que não sabe
    #: tirar fasor dele, que é o que foi medido.
    bloco: str = "alternado"
    #: Por que o canal caiu em `outros`, em uma linha, para a tela mostrar ao
    #: lado dele. Vazio nos outros blocos.
    motivo: str = ""
    #: O que a conta do usuário tem de estranho mas NÃO impede — a tela escreve
    #: isto no ⓘ azul, ao lado do nome.
    #:
    #: Campo separado de `motivo` por uma razão de leitura: `motivo` explica
    #: por que o sinal NÃO serve para algo (e o sinal está em `outros`); o
    #: aviso acompanha um sinal que serve, e está no bloco normal. Juntar os
    #: dois faria a tela pintar de vermelho uma conta que funciona. Ver a regra
    #: do projeto: avisa, nunca bloqueia.
    aviso: str = ""
    #: A coluna da matriz em que este sinal mora: `filtrado.onda`,
    #: `filtrado.rms`, `bruto.onda`, `bruto.rms` ou `bruto.dc`. Ver
    #: `coluna_da_grandeza` — e repare que ela NÃO é a grandeza: num registro
    #: já filtrado, `rms` mora em `filtrado.rms`.
    coluna: str = "bruto.onda"
    #: A observação que a tela escreve ao lado do nome da LINHA, quando ela não
    #: é um canal do arquivo. Diz duas coisas de uma vez: que aquilo é conta
    #: nossa — e não um canal que o relé gravou — e QUAL conta é.
    #:
    #: Existe porque `IN G1` na fileira de `IAW`, `IBW`, `ICW` se lê como um
    #: quarto canal do relé. A cor ajuda e não basta: cor não se lê, e num
    #: relatório impresso em preto e branco ela não existe.
    nota: str = ""
    #: A expressão JÁ LIDA, quando este sinal é conta do usuário.
    #:
    #: Guardada aqui porque ler custa, e sem ela cada leitura de cursor
    #: reanalisava a conta — vinte contas na tela viravam vinte análises por
    #: movimento do mouse. O catálogo já leu uma vez; quem desenha aproveita.
    analise: object = None
    #: As contas criadas ANTES desta, quando este sinal é conta do usuário.
    #:
    #: Existe porque a conta pode usar outra conta, e quem for recalcular a
    #: série dela precisa saber quais nomes ela enxergava. Só as anteriores:
    #: é a ordem de criação que torna a referência circular impossível, sem
    #: grafo de dependência nenhum. Ver `plot/contas.analisar`.
    contas_antes: tuple = ()
    #: O DOMÍNIO da conta do usuário: `componente`, `modulo` ou `misto`.
    #: Vazio quando o sinal não é conta.
    #:
    #: `componente` é conta entre parcelas com sinal da onda — ela TEM onda,
    #: contínua e eficaz, como qualquer canal. `modulo` tem uma folha só: a
    #: série já É o valor, e aplicar eficaz ou contínua em cima dela seria
    #: suavizar um número que ninguém pediu para suavizar. `misto` é o que não
    #: sabemos: fica com tudo de pé e o ⓘ ao lado. Ver `contas.Analise`.
    dominio: str = ""
    #: A expressão que o usuário escreveu, quando este sinal é conta dele.
    #:
    #: Campo próprio, e não `origem`: `origem` responde "de que canais isto
    #: saiu" e é o que a tela mostra ao lado do nome — a expressão responde
    #: "como", e é o que o servidor precisa para refazer a onda. Guardar as
    #: duas no mesmo campo fez a conta sair vazia no primeiro teste, porque a
    #: série tentou interpretar "Current IA, Current IB" como expressão.
    expressao: str = ""


#: O que cada grandeza é, em uma linha, para o hover da lista.
_O_QUE_E = {
    "rms": "eficaz verdadeiro da janela de um ciclo — inclui harmônicos e DC",
    "dc": "componente contínua — a média da janela de um ciclo, com sinal",
    "filtrado": "só a componente de 60 Hz, no tempo — a saída do filtro do relé",
    "fundamental": "o eficaz da componente de 60 Hz — o número com que o relé "
                   "decide atuar",
}


def de_registro(registro: Record, lado: str = "arquivo",
                contas_do_usuario=()) -> list[Sinal]:
    """Tudo que se pode acrescentar a um gráfico deste registro.

    A lista sai inteira, das duas famílias, e a tela separa em abas. O servidor
    monta porque o nome de um sinal é identidade e nasce no Python — ver
    `plot/sinais.py`.
    """
    escalas = unidades.por_unidade(registro, lado)
    ja_filtrado = str(registro.filtering) == "filtrado"
    # A frequência é a do REGISTRO: um arquivo de 50 Hz escreve `IA 50Hz`.
    hz = registro.line_frequency
    mudos = conjuntos.canais_sem_sinal(registro)
    # Import adiado: `analysis` conversa com `plot` e `formats`, e no topo
    # fecharia um ciclo. Mesmo motivo de `formats/registry.py`.
    from osclab.analysis import presenca
    alternados = presenca.alternados(registro)
    # Índice do canal → nome do grupo trifásico dele. Só `G…`: o apelido de um
    # residual solto é `[1]` e não é grupo — ver o campo `grupo` de `Sinal`.
    grupos_por_canal = {i: r
                        for i, r in conjuntos.rotulos_por_canal(registro).items()
                        if conjuntos.ordinal(r) is not None}

    saida: list[Sinal] = []

    # --- IED: o arquivo, cru, e o vínculo com a fundamental ---------------
    for canal in registro.analog_channels:
        unidade = canal.unit.strip()
        _, mostrada = escalas.get(unidade, (1.0, unidade))
        padrao = fases.padrao(canal)
        _, origem_da_fase = fases.da_canal(canal)
        # Em que bloco este canal mora, e por quê. As duas condições são as
        # mesmas que decidem se ele ganha contas — ver o laço seguinte —, e a
        # tela mostra o motivo em vez de deixar o usuário adivinhar por que
        # aquele canal tem uma coluna só.
        if canal.index in alternados and padrao:
            bloco, motivo = "alternado", ""
        elif not unidade:
            bloco, motivo = "outros", "o arquivo não declara unidade"
        elif canal.index not in alternados:
            bloco, motivo = "outros", "não passou no teste de alternado"
        else:
            bloco, motivo = "outros", "o programa não reconheceu a fase"
        saida.append(Sinal(
            id=f"c{canal.index}:instantaneo",
            nome=canal.name,
            coluna=coluna_da_grandeza("instantaneo", ja_filtrado),
            linha=canal.name,
            grupo=grupos_por_canal.get(canal.index, ""),
            bloco=bloco,
            motivo=motivo,
            unidade=unidade,
            unidade_mostrada=mostrada,
            familia="canal",
            grandeza="instantaneo",
            conta="instantaneo",
            descricao="a amostra como o IED gravou",
            grandeza_do_canal=fases.grandeza_da_unidade(unidade),
            fundamental=padrao,
            fundamental_origem=str(origem_da_fase),
            canal=canal.index,
            sem_sinal=canal.index in mudos,
        ))

    # --- OscLab: o que o relé NÃO gravou ----------------------------------
    for canal in registro.analog_channels:
        # As duas condições do cabeçalho: alternado, e fase reconhecida. A
        # componente de 60 Hz de 132 V contínuos é zero, e o "eficaz de um
        # ciclo" de um número parado é o próprio número com cara de medida de
        # alternada. Ver `analysis/presenca.py`.
        padrao = fases.padrao(canal)
        if canal.index not in alternados or not padrao:
            continue
        unidade = canal.unit.strip()
        _, mostrada = escalas.get(unidade, (1.0, unidade))
        oferta = OFERTA_DE_FILTRADO if ja_filtrado else OFERTA_DE_BRUTO
        for grandeza, conta in oferta:
            saida.append(Sinal(
                id=f"v{canal.index}:{grandeza}",
                nome=sinais.nome(canal.name, grandeza, hz),
                unidade=unidade,
                unidade_mostrada=mostrada,
                familia="calculado",
                grandeza=grandeza,
                conta=conta,
                coluna=coluna_da_grandeza(grandeza, ja_filtrado),
                descricao=_O_QUE_E[grandeza],
                origem=canal.name,
                # A linha é o CANAL: `IAW · RMS` é a coluna RMS da linha `IAW`.
                linha=canal.name,
                grupo=grupos_por_canal.get(canal.index, ""),
                # De que canal ele SAIU. `IA RMS` continua sendo o canal 0
                # visto de outro jeito — e é por este campo que o desenho e a
                # tabelinha acham a fase, o lado e o nome do arquivo dele.
                canal=canal.index,
                grandeza_do_canal=fases.grandeza_da_unidade(unidade),
                sem_sinal=canal.index in mudos,
            ))

    nomes_de_canal = {c.index: c.name for c in registro.analog_channels}
    for i, conjunto in enumerate(conjuntos.de_registro(registro)):
        # A componente de uma trinca sem sinal EXISTE e fica escondida, como
        # os canais dela — mesma regra, mesmo motivo. Fortescue aplicado a
        # ruído de conversor não significa nada, mas fazer o sinal sumir do
        # catálogo deixaria a lista escondida pela metade, e Fortescue aplicado
        # a uma trinca legitimamente em zero dá zero, que é uma resposta.
        _, mostrada = escalas.get(conjunto.unidade, (1.0, conjunto.unidade))
        # De que canais do relé saiu a componente. O nome interno do conjunto
        # (`CURRENT I*`, com a letra da fase trocada por `*`) diz respeito ao
        # agrupamento e não a quem olha a tela: o que interessa ali é poder
        # conferir QUAIS três canais entraram na conta.
        origem = ", ".join(nomes_de_canal.get(x, f"#{x}") for x in conjunto.abc)
        # A trinca, para a tela poder CORRIGI-LA. Vale tanto para a componente
        # quanto para o resíduo: os dois saem dos mesmos três canais, que o
        # programa escolheu olhando nomes. Ver o campo `conjunto` de `Sinal`.
        trinca = {"chave": conjunto.nome,
                  "unidade": conjunto.unidade,
                  "base": conjunto.base,
                  "canais": {f: conjunto.canais[f] for f in conjunto.rotulos}}

        # --- o resíduo no tempo: `IN G1`, `IN G1 · RMS` ------------------
        #
        # Em DELTA ele não existe, e some da lista em vez de sair zerado:
        # `VAB + VBC + VCA ≡ 0` por identidade, e esse zero apareceria como
        # `VN G3` plano na tela — "não há falta à terra", medido em nada.
        # Some também o `3V0` logo abaixo, pelo mesmo motivo. Ver
        # `dsp/simetricas.de_lacos`.
        base = conjuntos.juntar(f"{conjunto.grandeza}N", conjunto.rotulo)
        oferta_do_residuo = () if conjunto.e_de_linha else (
            RESIDUO_DE_FILTRADO if ja_filtrado else RESIDUO_DE_BRUTO)
        for grandeza, conta in oferta_do_residuo:
            saida.append(Sinal(
                id=f"q{i}:{RESIDUAL}:{grandeza}",
                nome=sinais.nome(base, grandeza, hz),
                unidade=conjunto.unidade,
                unidade_mostrada=mostrada,
                familia="calculado",
                grandeza=grandeza,
                conta=conta,
                coluna=coluna_da_grandeza(grandeza, ja_filtrado),
                descricao=(_O_QUE_E_O_RESIDUO_FILTRADO if ja_filtrado
                           else _O_QUE_E_O_RESIDUO)[grandeza].format(
                    x=conjunto.grandeza.lower(), g=conjunto.grandeza),
                origem=origem,
                # O resíduo é UMA linha (`IN G1`) com as suas contas, e mora no
                # bloco dos alternados: é uma senoide somada no tempo, não um
                # fasor — e por isso tem as mesmas colunas de um canal.
                linha=base,
                grupo=conjunto.rotulo,
                nota="calculado: soma dos três canais, amostra por amostra",
                sem_sinal=conjunto.sem_sinal,
                conjunto=trinca,
            ))

        for chave, (_, molde, descricao) in COMPONENTES.items():
            if chave == "0" and conjunto.e_de_linha:
                continue
            nome = molde.format(g=conjunto.grandeza)
            descricao = descricao.format(g=conjunto.grandeza)
            inteiro = conjuntos.juntar(nome, conjunto.rotulo)
            saida.append(Sinal(
                id=f"q{i}:{chave}:rms",
                nome=inteiro,
                unidade=conjunto.unidade,
                unidade_mostrada=mostrada,
                familia="calculado",
                grandeza="fundamental",
                conta="fundamental",
                # A componente simétrica é fasor: ela nasce do filtro, e mora
                # na coluna do eficaz filtrado mesmo num registro bruto.
                coluna="filtrado.rms",
                descricao=f"{descricao} — módulo do fasor de um ciclo, eficaz",
                origem=origem,
                linha=inteiro,
                grupo=conjunto.rotulo,
                bloco="sequencia",
                nota="calculado: componente simétrica, sempre em eficaz",
                sem_sinal=conjunto.sem_sinal,
                conjunto=trinca,
            ))

    saida.extend(_potencias_dos_vinculos(
        registro, conjuntos.de_registro(registro), escalas))
    saida.extend(_contas_do_usuario(registro, lado, escalas, ja_filtrado, hz,
                                    contas_do_usuario))
    return saida


def _por_que_nao_e_senoide(analise) -> str:
    """Em quatro palavras, por que esta conta perdeu fasor e espectro.

    Vazio quando ela não perdeu. Antes disto só o caso do produto tinha
    motivo escrito, e as contas que caíam em «outros» por causa do DOMÍNIO —
    somar a contínua, usar um RMS — caíam caladas: quatro risquinhos e nenhuma
    palavra. Linha muda é pior que coluna a mais.
    """
    if analise.alternado:
        return ""
    if analise.tem_produto:
        return "não é senoidal: produto entre sinais"
    return "não é senoidal: usa RMS ou contínua"


def _oferecer(por_nome: dict, conta, analise, contas_mod) -> None:
    """Põe esta conta no mapa, para as PRÓXIMAS poderem usá-la pelo nome.

    Fica de fora a conta que não compila — quem a usasse herdaria o erro sem
    saber de onde ele veio — e o nome repetido vira `None`, que é como o
    leitor marca "existem dois com este nome, escolha outro".
    """
    chave = contas_mod.chave_do_nome(conta.nome or "")
    if not chave or not analise.vale:
        return
    if chave in por_nome:
        por_nome[chave] = None
        return
    por_nome[chave] = contas_mod.Referencia(
        linha=conta.nome,
        unidade=analise.unidade_escrita,
        bloco="alternado" if analise.alternado else "outros",
        analise=analise)


def _base_do_vinculo(tensao, vinculo) -> str:
    """Fase ou linha — e a TRINCA ganha do que o usuário marcou no vínculo.

    O botão «fase ou linha» do vínculo existia porque nada no programa sabia a
    resposta: `VAB` e `VA` são duas senoides, e só o nome do canal distingue.
    Agora a trinca sabe — ela é montada de `AB/BC/CA` ou de `A/B/C` —, e o que
    ela sabe não é palpite: é o vínculo canal→fase, que o usuário já conferiu
    na tela dos canais.

    Marcar «fase» num vínculo cuja tensão é de linha dividiria a potência
    trifásica por √3 e repartiria entre três fases que não existem ali. Por
    isso a trinca manda, e o botão só decide quando ela não tem opinião — que
    é o caso de hoje, em que `VAB` ainda é DEDUZIDO como fase A.
    """
    if getattr(tensao, "e_de_linha", False):
        return "linha"
    return str((vinculo or {}).get("base") or "fase")


def _potencias_dos_vinculos(registro: Record, achados, escalas: dict) -> list:
    """P, Q, S e FP de cada vínculo que o USUÁRIO fez.

    Sem vínculo, nada aqui existe — e é de propósito. O programa não casa
    corrente com tensão sozinho: dois vãos de uma subestação têm nomes
    parecidos, e o par errado produz uma potência na unidade certa, na ordem
    de grandeza certa, e errada. Quem sabe qual TC pertence a qual TP é quem
    leu o unifilar. Ver `Record.vinculos_de_potencia`.

    Saem como MÓDULO, na coluna do eficaz filtrado, como a componente
    simétrica: são contas entre fasores de 60 Hz, não ondas. Quem quiser a
    onda da potência instantânea escreve `[VAY] × [IAW]` na calculadora —
    ela mostra a ondulação de 120 Hz, que esta aqui não tem.
    """
    vinculos = getattr(registro, "vinculos_de_potencia", None) or {}
    if not vinculos:
        return []
    por_chave = {c.nome: c for c in achados}
    saida: list[Sinal] = []
    for chave, vinculo in sorted(vinculos.items()):
        conjunto = por_chave.get(chave)
        outro = por_chave.get(str(vinculo.get("com") or ""))
        if conjunto is None or outro is None:
            continue
        # UM lado só gera os sinais, senão cada potência apareceria duas
        # vezes — uma no grupo da corrente e outra no da tensão. O lado da
        # CORRENTE, porque é o vão que ela mede: a tensão de um barramento
        # pode servir a vários vãos, a corrente não.
        if conjunto.grandeza != "I":
            continue
        base = _base_do_vinculo(outro, vinculo)
        rotulos = potencia.GRANDEZAS_POR_BASE.get(base,
                                                  potencia.GRANDEZAS_POR_BASE["fase"])
        origem = f"{conjunto.rotulo} × {outro.rotulo}"
        # O nome carrega o PAR, não o grupo: `P G1↔G3`.
        #
        # `P G1` seria mentira por omissão — a potência não sai de G1, sai do
        # par. Num registro com dois vãos, duas linhas chamadas `P G1` e
        # `P G2` não diriam com que tensão cada uma foi calculada, e trocar o
        # vínculo mudaria o número sem mudar o nome. Com o par escrito, o
        # nome muda junto com a conta.
        par = f"{conjunto.rotulo}{SETA_DO_VINCULO}{outro.rotulo}"
        for grandeza in rotulos:
            unidade = potencia.UNIDADE[grandeza]
            _, mostrada = escalas.get(unidade, (1.0, unidade))
            nome = conjuntos.juntar(grandeza, par)
            saida.append(Sinal(
                id=f"w{conjunto.rotulo}:{grandeza}:rms",
                nome=nome,
                unidade=unidade,
                unidade_mostrada=mostrada,
                familia="calculado",
                grandeza="fundamental",
                conta="fundamental",
                coluna="filtrado.rms",
                descricao=_DESCRICAO_DA_POTENCIA[grandeza],
                origem=origem,
                linha=nome,
                # O grupo é o PAR, não G1: é dele que estes sinais saem, e é
                # com esse nome que a caixinha ao lado do nome tem de casar.
                grupo=par,
                bloco="sequencia",
                nota=f"calculado: vínculo {origem}, tensão de {base}",
                sem_sinal=conjunto.sem_sinal or outro.sem_sinal,
            ))
    return saida


#: O que liga os dois grupos no nome de uma potência: `P G1↔G3`.
#:
#: Seta de duas pontas porque o vínculo vale nos dois sentidos — ligar G1 a G3
#: é a mesma afirmação que ligar G3 a G1. Uma seta de uma ponta sugeriria uma
#: direção de fluxo, que é outra coisa e que este nome não diz.
SETA_DO_VINCULO = "↔"


#: O que cada potência é, em uma linha, para o hover da lista.
_DESCRICAO_DA_POTENCIA = {
    "P": "potência ativa trifásica — a que faz trabalho",
    "Q": "potência reativa trifásica — a que só circula",
    "S": "potência aparente trifásica — o módulo de P + jQ",
    "FP": "fator de potência — P dividido por S, entre −1 e 1",
    "Pa": "potência ativa da fase A",
    "Pb": "potência ativa da fase B",
    "Pc": "potência ativa da fase C",
}


def _contas_do_usuario(registro: Record, lado: str, escalas: dict,
                       ja_filtrado: bool, hz: float, pedidas) -> list[Sinal]:
    """As contas que o usuário escreveu, como linhas do catálogo.

    Uma conta é ONDA: entra com as mesmas cinco colunas de um canal, no bloco
    «Calculados», exatamente como o resíduo `IN` — que é, afinal, a conta
    `[IAW] + [IBW] + [ICW]` com nome fixo.

    Conta que não compila não some da lista: ela aparece com o motivo do erro,
    para o usuário poder corrigi-la. Some seria pior — o sinal desapareceria da
    tela sem dizer por quê.
    """
    from osclab.plot import contas as contas_mod

    saida: list[Sinal] = []
    anteriores: list = []
    # O mapa de nomes montado UMA vez e crescendo a cada conta: é o que mantém
    # o custo linear. Remontá-lo por conta fazia o tempo dobrar a cada elo de
    # uma cadeia — ver `contas.Referencia`.
    por_nome = contas_mod.referenciaveis(registro) if pedidas else {}
    for conta in (pedidas or ()):
        # Só as contas ANTERIORES: ver `Sinal.contas_antes`.
        antes = tuple(anteriores)
        anteriores.append(conta)
        analise = contas_mod.analisar_com(conta.expressao, registro, por_nome)
        _oferecer(por_nome, conta, analise, contas_mod)
        unidade = analise.unidade_escrita
        divisor, mostrada = escalas.get(unidade, (1.0, unidade))
        if not analise.vale:
            # Uma linha só, inerte, carregando o erro. Sem contas: não há
            # número nenhum a oferecer.
            saida.append(Sinal(
                id=f"{conta.id}:instantaneo", nome=conta.nome,
                unidade="", unidade_mostrada="", familia="conta",
                grandeza="instantaneo", conta="instantaneo",
                coluna=coluna_da_grandeza("instantaneo", ja_filtrado),
                descricao=f"conta do usuário: {conta.expressao}",
                origem=conta.expressao, expressao=conta.expressao,
                contas_antes=antes, analise=analise, linha=conta.nome,
                bloco="outros", motivo=analise.erro,
                nota="conta do usuário — não compilou"))
            continue
        # A oferta do RESÍDUO, e não a do canal: a conta é uma onda sem canal
        # no arquivo, exatamente como `IN`. A do canal não traz `instantaneo`
        # porque ali a onda crua É o canal — aqui não há canal nenhum a que
        # apontar, e sem essa linha a conta nasceria sem a própria onda.
        oferta = RESIDUO_DE_FILTRADO if ja_filtrado else RESIDUO_DE_BRUTO
        # Conta entre MÓDULOS tem uma folha só, e é a série como ela sai.
        #
        # `[IN G1 · RMS] − [3I0 G1]` já é um valor: cada amostra é a diferença
        # entre dois eficazes. Oferecer «eficaz» em cima dela recalcularia um
        # eficaz de um eficaz — uma janela de um ciclo passada num patamar, que
        # é suavizar; e «contínua» faria o mesmo com outro nome. A única conta
        # honesta ali é nenhuma.
        #
        # É `instantaneo` porque é a série sem conta aplicada — o nome da
        # coluna, não uma afirmação de que aquilo é onda. Quem diz o que é fica
        # em `dominio`, e é dele que a tela tira o rótulo «valor».
        if analise.tem_onda is False:
            oferta = (("instantaneo", "instantaneo"),)
        # MEDE o que a conta contém, em vez de deduzir da expressão. Sem 60 Hz
        # dentro, as colunas do filtrado desenhariam uma reta no zero com cara
        # de medida — `[VAY] - [VAY · 60Hz]` é a onda da distorção, e
        # `[VAY] × [IAW]` é potência: nenhuma das duas tem 60 Hz. Ver
        # `contas.tem_60hz`, que traz a medição do limiar.
        onda = contas_mod.serie(registro, analise, lado, divisor)
        com_60hz = contas_mod.tem_60hz(onda, registro)
        if not com_60hz:
            oferta = tuple((g, c) for g, c in oferta
                           if not coluna_da_grandeza(g, ja_filtrado)
                                   .startswith("filtrado."))
        sem_60hz = "" if com_60hz else (
            "não tem 60 Hz: o filtro não acha o que extrair daqui")
        origem = ", ".join(analise.fontes)
        for grandeza, qual in oferta:
            saida.append(Sinal(
                id=f"{conta.id}:{grandeza}",
                nome=sinais.nome(conta.nome, grandeza, hz),
                unidade=unidade,
                unidade_mostrada=mostrada,
                familia="conta",
                grandeza=grandeza,
                conta=qual,
                coluna=coluna_da_grandeza(grandeza, ja_filtrado),
                descricao=f"conta do usuário: {conta.expressao}",
                origem=origem,
                expressao=conta.expressao,
                contas_antes=antes,
                analise=analise,
                linha=conta.nome,
                # Produto entre sinais não é senoide: potência instantânea
                # oscila no dobro da frequência com nível contínuo, e fasor de
                # 60 Hz disso não significa nada. Ver `plot/contas.py`.
                #
                # E repare que o BLOCO aqui não é onde a tela LISTA a conta:
                # conta do usuário é sempre listada em «Calculados», porque
                # «Senoidais» e «Outros sinais» são do que o relé gravou. O
                # bloco responde a outra pergunta — se dá para tirar fasor e
                # espectro dela. Ver `blocosDoCatalogo` em `onda.js`.
                bloco="alternado" if analise.alternado else "outros",
                # O motivo tem que caber em três ou quatro palavras: ao lado do
                # nome ele divide a largura com ele, e um motivo longo come o
                # nome. A frase inteira fica no hover.
                # A falta de senoide vem primeiro: ela diz a CAUSA («produto
                # entre sinais»), e a falta de 60 Hz é consequência dela — que
                # os risquinhos nas duas colunas já mostram sem precisar de
                # palavra.
                motivo=_por_que_nao_e_senoide(analise) or sem_60hz,
                aviso="; ".join(analise.avisos),
                nota=f"calculado: {conta.expressao}",
                grandeza_do_canal=next(iter(analise.unidade), ""),
                dominio=("misto" if analise.tem_onda is None
                         else "componente" if analise.tem_onda else "modulo"),
            ))
    return saida


def energia_das_linhas(registro: Record, disponiveis, lado: str,
                       escalas: dict, trechos) -> dict:
    """Onde mora a energia de cada linha: 60 Hz, harmônicos e contínua.

    É a identidade de Parseval, medida no tempo em vez de somada no espectro::

        RMS² = DC² + RMS₆₀² + RMS_harmônicos²

    Conferida em `tests/test_harmonicos.py`: fecha com erro de 2,4·10⁻¹³ %.

    MEDE as amostras — não pergunta ao `Record.filtering`. A diferença
    importa: `filtering` é dedução (ver `analysis`, marco 0.5), e um inrush
    com 17 % de harmônico já foi deduzido como «já filtrado» aqui dentro.
    Uma barra que herdasse esse palpite diria 100 % de 60 Hz num sinal que
    tem 80 %, e seria a tela afirmando o que ninguém mediu. Medindo, o
    palpite errado fica VISÍVEL: cabeçalho dizendo «já filtrado» com a
    barra mostrando harmônico é a evidência contra ele.

    Medir também apaga o caso especial do `.CEV`, que nunca traz bruto: lá
    as amostras são a componente de 60 Hz de verdade, então a medição dá
    100 % sozinha, sem ninguém ter escrito `if cev`.

    Sobre o REGISTRO INTEIRO, e não sobre a janela à vista. A barra mora no
    menu, onde não há cursor nem tempo: uma barra que mudasse conforme o
    gráfico rolou atrás da janelinha seria uma medida sem pergunta. Quem
    quer a energia de um instante tem o painel de harmônicos, que é onde
    essa pergunta tem janela.

    Devolve `{linha: (f60, fharm, fdc)}`, frações que somam 1. Fica de fora
    a linha que não tem ONDA com que medir — a componente simétrica, a
    conta entre módulos —, e a tela não desenha barra nenhuma para ela:
    barra inventada é pior que barra ausente.
    """
    ondas: dict[str, Sinal] = {}
    for x in disponiveis:
        # A onda CRUA da linha, que é a mesma série nos dois nomes de coluna:
        # `bruto.onda` num registro bruto, `filtrado.onda` num já filtrado.
        # O que muda é o rótulo, não as amostras.
        if x.sem_sinal or x.grandeza != "instantaneo":
            continue
        if x.dominio == "modulo":
            continue
        ondas.setdefault(x.linha, x)

    n = registro.analog.shape[1]
    hz = registro.line_frequency
    saida: dict[str, tuple] = {}
    for linha, sinal in ondas.items():
        onda = serie(registro, sinal, 0, n, trechos, lado, escalas)
        if onda.size == 0:
            continue
        medidas = {}
        for grandeza in ("rms", "fundamental", "dc"):
            v = envoltoria.calcular(onda, trechos, hz, grandeza)
            v = v[np.isfinite(v)]
            medidas[grandeza] = float(np.mean(v * v)) if v.size else float("nan")
        total, f60, dc = (medidas["rms"], medidas["fundamental"],
                          medidas["dc"])
        if not (total > 0.0) or not np.isfinite(total) or not np.isfinite(f60):
            continue
        if not np.isfinite(dc):
            dc = 0.0
        # Os `max(0, ...)` não são covardia: as três envoltórias saem de
        # janelas que começam na mesma amostra mas arredondam diferente, e no
        # último dígito uma parcela pode passar o total. Recortar em zero é
        # dizer "nada", que é o que aquele resto significa.
        a60 = max(0.0, f60) / total
        adc = max(0.0, dc) / total
        aharm = max(0.0, 1.0 - a60 - adc)
        soma = a60 + adc + aharm
        if soma <= 0.0:
            continue
        saida[linha] = (a60 / soma, aharm / soma, adc / soma)
    return saida


def por_id(registro: Record, lado: str = "arquivo",
           contas_do_usuario=()) -> dict[str, Sinal]:
    return {s.id: s for s in de_registro(registro, lado, contas_do_usuario)}


#: A coluna do grupo `filtrado` que corresponde a cada coluna do `bruto`: é
#: para onde o botão do cabeçalho empurra o sinal.
#:
#: `dc` não está aqui, e não é esquecimento: a contínua do sinal filtrado é
#: zero por definição — é exatamente o que o filtro tirou. Empurrar
#: `IAW · DC` para o grupo filtrado daria uma reta no zero com cara de medida.
_PAR_FILTRADO = {"instantaneo": "filtrado", "rms": "fundamental"}


def efetivo(identidade: str, medida: str, filtro: bool,
            disponiveis: dict[str, Sinal]) -> Sinal | None:
    """O sinal que o gráfico desenha depois dos botões da tela.

    Os dois botões — o filtro de 60 Hz, no cabeçalho, e o instantâneo/RMS de
    cada painel — não mudam QUAL linha do catálogo está no gráfico: mudam o
    que se está olhando dela. `Current IA` com RMS ligado é `IA RMS`, que é um
    sinal do catálogo com id próprio.

    Fazer essa troca aqui, num lugar só, é o que impede o desenho e a
    tabelinha do cursor de responderem diferente à mesma combinação de botões.

    E os dois botões têm alcances diferentes, por motivo de domínio:

    * **o filtro é do registro inteiro**, então pega em todo sinal que tenha
      par no grupo filtrado — inclusive no que o usuário escolheu à mão.
      Metade do gráfico respondendo ao botão era uma comparação errada sem
      aviso na tela. Ver o cabeçalho do módulo.
    * **a medida é do painel**, e pega só nos canais do IED: ela escolhe entre
      a onda e o eficaz DAQUELE canal, e não há "eficaz do `IAW · DC`".
    """
    original = disponiveis.get(identidade)
    if original is None:
        return original

    if original.familia == "canal":
        grandeza = sinais.resolver(filtro, medida)
        if grandeza == "instantaneo":
            return original
        # Num registro já filtrado, `filtro` chega aqui desligado — quem o
        # desliga é `sinais.aplicavel`, e o que sobra é `instantaneo` ou `rms`,
        # os dois que existem ali. Num canal fora de trinca não existe conta
        # nenhuma, e o próprio canal responde: o botão não pega nele.
        return disponiveis.get(f"v{original.canal}:{grandeza}", original)

    # Daqui para baixo, sinal que o usuário escolheu à mão. Apagar o filtro
    # não empurra ninguém de volta: a identidade escolhida não muda, e é por
    # isso que acender e apagar o botão devolve o que estava.
    if not filtro:
        return original
    par = _PAR_FILTRADO.get(original.grandeza)
    if par is None:
        return original
    if original.canal >= 0:
        return disponiveis.get(f"v{original.canal}:{par}", original)
    # O resíduo é onda como um canal, e tem o par dele: `IN G1` →
    # `IN G1 · 60Hz`. A componente simétrica não tem: já é fasor de 60 Hz.
    trinca, chave, _ = original.id.split(":")
    if chave != RESIDUAL:
        return original
    return disponiveis.get(f"{trinca}:{RESIDUAL}:{par}", original)


# ---------------------------------------------------------------------------
# A série de um sinal acrescentado
# ---------------------------------------------------------------------------

def _canal_por_indice(registro: Record) -> dict:
    return {c.index: c for c in registro.analog_channels}


def serie(registro: Record, sinal: Sinal, j0: int, i1: int, trechos,
          lado: str, escalas: dict) -> np.ndarray:
    """Os valores do sinal na janela `[j0, i1)`, já convertidos e escalados.

    `j0` traz o ciclo de história que as envoltórias precisam; quem chama
    recorta o começo depois. A conversão de TC/TP e o prefixo `k` são
    multiplicações por escalar, então podem vir antes ou depois da DFT — aqui
    vêm antes, porque para a componente simétrica as três fases precisam estar
    na mesma base antes de serem somadas.
    """
    divisor, _ = escalas.get(sinal.unidade, (1.0, sinal.unidade))

    if sinal.familia == "conta":
        return _serie_de_conta(registro, sinal, j0, i1, trechos, lado,
                               escalas, divisor)

    if sinal.id[0] == "w":
        return _serie_de_potencia(registro, sinal, j0, i1, trechos, lado,
                                  divisor)

    if sinal.id[0] in ("c", "v"):
        canal = _canal_por_indice(registro).get(int(sinal.id[1:].split(":")[0]))
        if canal is None:
            return np.full(i1 - j0, np.nan)
        # A CONTA do sinal, não a grandeza que o nomeia: num registro já
        # filtrado `IA 60Hz` é o próprio canal, sem conta nenhuma.
        grandeza = sinal.conta
        bruto = envoltoria.calcular(registro.analog[canal.index, j0:i1],
                                    trechos, registro.line_frequency, grandeza)
        convertido, _, _ = conversao.converter(bruto, canal, lado)
        return convertido / divisor

    return _serie_de_componente(registro, sinal, j0, i1, trechos, lado, divisor)


def _serie_de_conta(registro: Record, sinal: Sinal, j0: int, i1: int,
                    trechos, lado: str, escalas: dict,
                    divisor: float) -> np.ndarray:
    """A série de uma conta do usuário, com a envoltória por cima.

    A onda sai do registro INTEIRO e só depois é recortada: as envoltórias
    precisam do ciclo que vem antes de `j0`, e para uma conta esse ciclo pode
    cair fora da janela — o mesmo motivo do resíduo.
    """
    from osclab.plot import contas as contas_mod

    # A análise que o catálogo já fez, quando há: ver `Sinal.analise`.
    analise = sinal.analise or contas_mod.analisar(
        sinal.expressao, registro, escalas, sinal.contas_antes)
    onda = contas_mod.serie(registro, analise, lado, divisor)
    if onda is None or onda.size < i1:
        return np.full(i1 - j0, np.nan)
    return envoltoria.calcular(onda[j0:i1], trechos, registro.line_frequency,
                               sinal.conta)


def residuo(registro: Record, conjunto, j0: int, i1: int, lado: str,
            divisor: float) -> np.ndarray | None:
    """`ia + ib + ic` amostra a amostra, na janela `[j0, i1)`.

    A conversão de TC/TP vem **antes** da soma, e tem que vir: nada garante que
    as três fases estejam gravadas na mesma relação. Somar primeiro e converter
    depois daria um número na unidade certa e na ordem de grandeza certa, sem
    nada na tela denunciando — exatamente o erro que o resíduo existe para
    mostrar.

    Devolve `None` quando algum dos três canais sumiu do registro, e quem chama
    transforma isso em `NaN`: uma soma de dois canais não é resíduo de nada.
    """
    canais = _canal_por_indice(registro)
    soma = None
    for indice in conjunto.abc:
        canal = canais.get(indice)
        if canal is None:
            return None
        convertido, _, _ = conversao.converter(registro.analog[indice, j0:i1],
                                               canal, lado)
        soma = convertido if soma is None else soma + convertido
    return None if soma is None else soma / divisor


def _serie_de_componente(registro: Record, sinal: Sinal, j0: int, i1: int,
                         trechos, lado: str, divisor: float) -> np.ndarray:
    _, chave, _ = sinal.id.split(":")
    conjunto = _conjunto_do(registro, sinal)
    if conjunto is None:
        return np.full(i1 - j0, np.nan)

    # O resíduo NÃO passa por Fortescue: é soma no tempo, e depois a mesma
    # envoltória de qualquer onda. Ver o cabeçalho.
    if chave == RESIDUAL:
        onda = residuo(registro, conjunto, j0, i1, lado, divisor)
        if onda is None:
            return np.full(i1 - j0, np.nan)
        return envoltoria.calcular(onda, trechos, registro.line_frequency,
                                   sinal.conta)

    posicao, _, _ = COMPONENTES[chave]
    canais = _canal_por_indice(registro)
    fasores = []
    for indice in conjunto.abc:
        canal = canais.get(indice)
        if canal is None:
            return np.full(i1 - j0, np.nan)
        convertido, _, _ = conversao.converter(registro.analog[indice, j0:i1],
                                               canal, lado)
        fasores.append(envoltoria.calcular_fasores(convertido, trechos,
                                                   registro.line_frequency))

    # `de_fasores` é escrita com escalares e roda igual sobre vetores: as
    # operações são soma e multiplicação por complexo, que o numpy faz elemento
    # a elemento. Uma implementação, dois usos — é assim que elas não divergem.
    componentes = _fortescue(conjunto)(*fasores)
    return np.abs(componentes[posicao]) / math.sqrt(2.0) / divisor


def _fortescue(conjunto):
    """Qual transformação esta trinca pede — pela BASE, não pelos números.

    Em delta os três fasores são diferenças entre fases, e a transformação
    crua devolveria `V1` e `V2` esticados de √3 e girados de 30°: números
    plausíveis, na unidade certa, errados por 73 %. `de_lacos` desfaz o giro e
    recusa a sequência zero. Ver `formats/conjuntos.Conjunto.base`.
    """
    return simetricas.de_lacos if conjunto.e_de_linha else simetricas.de_fasores


def _serie_de_potencia(registro: Record, sinal: Sinal, j0: int, i1: int,
                       trechos, lado: str, divisor: float) -> np.ndarray:
    """P, Q, S ou FP de um vínculo, janela a janela.

    Os fasores das seis ondas vão para `dsp/potencia`, que faz a conta. A
    conversão de TC/TP entra ANTES — como no resíduo e na componente
    simétrica —, porque somar um lado primário com um secundário erraria por
    mil sem nada na tela denunciando.

    O `divisor` do prefixo (`k`, `M`) entra DEPOIS, e só aqui: a potência é
    um PRODUTO de duas grandezas, então o prefixo dela não é o prefixo de
    nenhuma das duas. Dividir cada onda pelo seu prefixo antes do produto
    daria um número errado por mil ou por um milhão.
    """
    cabeca, grandeza, _ = sinal.id.split(":")
    vinculos = getattr(registro, "vinculos_de_potencia", None) or {}
    achados = conjuntos.de_registro(registro)
    por_rotulo = {c.rotulo: c for c in achados}
    por_chave = {c.nome: c for c in achados}
    # O rótulo do grupo da CORRENTE sai do id (`wG1:P:rms`), e não de
    # `sinal.grupo`: desde que o nome passou a carregar o par, `grupo` é
    # `G1↔G3` — que é o que a caixinha do nome precisa, e não esta busca.
    desta = por_rotulo.get(cabeca[1:])
    vinculo = vinculos.get(desta.nome) if desta else None
    outra = por_chave.get(str((vinculo or {}).get("com") or ""))
    if desta is None or outra is None:
        return np.full(i1 - j0, np.nan)

    canais = _canal_por_indice(registro)

    def fasores(conjunto):
        saida = []
        for indice in conjunto.abc:
            canal = canais.get(indice)
            if canal is None:
                return None
            convertido, _, _ = conversao.converter(
                registro.analog[indice, j0:i1], canal, lado)
            saida.append(envoltoria.calcular_fasores(
                convertido, trechos, registro.line_frequency))
        return saida

    tensoes, correntes = fasores(outra), fasores(desta)
    if tensoes is None or correntes is None:
        return np.full(i1 - j0, np.nan)
    base = _base_do_vinculo(outra, vinculo)
    valores = potencia.serie(grandeza, tensoes, correntes, base)
    # O fator de potência é razão entre dois VA: não tem unidade, e portanto
    # não tem prefixo para dividir.
    if grandeza == "FP":
        return valores
    return valores / divisor


def conjunto_do_sinal(registro: Record, sinal: Sinal):
    """A trinca de onde este sinal saiu, ou `None` se ele não vier de uma."""
    return _conjunto_do(registro, sinal)


def _conjunto_do(registro: Record, sinal: Sinal):
    achados = conjuntos.de_registro(registro)
    i = int(sinal.id[1:].split(":")[0])
    return achados[i] if 0 <= i < len(achados) else None


def fasor_de_componente(registro: Record, sinal: Sinal, i: int,
                        por_ciclo: float,
                        lado: str, divisor: float) -> tuple[float, float] | None:
    """Módulo (eficaz) e ângulo da componente no instante da amostra `i`.

    É o que a tabelinha do cursor mostra. Sai da MESMA conta da curva — as três
    fases viram fasor, a transformação de Fortescue combina os três — só que
    numa amostra só.
    """
    from osclab.dsp import fasor as dsp_fasor

    conjunto = _conjunto_do(registro, sinal)
    if conjunto is None:
        return None
    _, chave, _ = sinal.id.split(":")
    # O resíduo tem onda, então tem instantâneo, RMS, DC e distorção como
    # qualquer canal — a tabelinha dele sai por outro caminho, em `leitura`.
    if chave == RESIDUAL:
        return None
    posicao, _, _ = COMPONENTES[chave]

    canais = _canal_por_indice(registro)
    fasores = []
    for indice in conjunto.abc:
        canal = canais.get(indice)
        if canal is None:
            return None
        f = dsp_fasor.no_instante(registro.analog[indice], i, por_ciclo)
        if f is None:
            return None
        razao = conversao.relacao(canal)
        lado_do_canal = "primario" if canal.is_primary else "secundario"
        fator = 1.0
        if lado != lado_do_canal and razao > 0:
            fator = razao if lado == "primario" else 1.0 / razao
        # Fasor de PICO, como em `envoltoria.fasores`: o eficaz sai no fim, uma
        # vez só, depois de somar.
        pico = f.fundamental * math.sqrt(2.0) * fator / divisor
        fasores.append(pico * np.exp(1j * math.radians(f.angulo)))

    x = _fortescue(conjunto)(*fasores)[posicao]
    if not np.isfinite(x):
        return None
    return (float(abs(x)) / math.sqrt(2.0), float(np.degrees(np.angle(x))))
