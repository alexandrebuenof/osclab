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

from osclab.dsp import envoltoria, simetricas
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


#: O que cada grandeza é, em uma linha, para o hover da lista.
_O_QUE_E = {
    "rms": "eficaz verdadeiro da janela de um ciclo — inclui harmônicos e DC",
    "dc": "componente contínua — a média da janela de um ciclo, com sinal",
    "filtrado": "só a componente de 60 Hz, no tempo — a saída do filtro do relé",
    "fundamental": "o eficaz da componente de 60 Hz — o número com que o relé "
                   "decide atuar",
}


def de_registro(registro: Record, lado: str = "arquivo") -> list[Sinal]:
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
                  "canais": {f: conjunto.canais[f] for f in ("A", "B", "C")}}

        # --- o resíduo no tempo: `IN G1`, `IN G1 · RMS` ------------------
        base = conjuntos.juntar(f"{conjunto.grandeza}N", conjunto.rotulo)
        oferta_do_residuo = (RESIDUO_DE_FILTRADO if ja_filtrado
                             else RESIDUO_DE_BRUTO)
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

    return saida


def por_id(registro: Record, lado: str = "arquivo") -> dict[str, Sinal]:
    return {s.id: s for s in de_registro(registro, lado)}


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
    componentes = simetricas.de_fasores(*fasores)
    return np.abs(componentes[posicao]) / math.sqrt(2.0) / divisor


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

    x = simetricas.de_fasores(*fasores)[posicao]
    return (float(abs(x)) / math.sqrt(2.0), float(np.degrees(np.angle(x))))
