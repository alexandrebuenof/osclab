# Os gráficos que o SynchroWave tem e nós não

Levantado em 19/10/2026 a partir das telas do SynchroWave Event (SEL-451) que o
Alexandre mandou. A lista de gráficos do programa tem nove; temos cinco.

| gráfico | temos? | veredito |
|---|---|---|
| Analog Chart | sim | — |
| Digital Chart | sim | — |
| Phasor Diagram | sim | — |
| Harmonic Analysis | sim, com THD | faltam **K-factor** e **crest** — duas contas |
| Spectral Analysis | não | vale, com a ressalva da resolução |
| **Mho Circle (plano de impedância)** | **sim**, desde 20/10/2026 | o de maior valor |
| Complex Chart | não | barato: é o fasorial no tempo |
| Alpha Plane (87L) | não | depende de ter 411L/487E no parque |
| Bewley (ondas viajantes) | não | **impossível com 2 kHz** — fica no modo de ondas viajantes |

## O que cada um precisa

**Plano de impedância (Mho).** Fasores de V e I (temos), o laço em falta (o
relé escreve no cabeçalho do evento) e os **ajustes das zonas** — que vêm do
bloco `SETTINGS` do `.CEV`, já lido pelo painel de lógica. Para um registro
SEL com `.CEV`, dá para desenhar as zonas **reais** daquele relé. Sem os
ajustes, a trajetória sozinha já vale. **Implementado em 20/10/2026** — ver
`plano-de-impedancia.md`.

**Complex Chart.** Nada além do que já existe: os fasores por ciclo. É o mais
barato dos quatro. Revela o que gráfico de tempo esconde — giro de frequência,
espiral da contínua, laço de saturação, elipse de oscilação de potência.
Detalhe apanhado num print dele: o losango no Complex Chart do SynchroWave é o
fasor girando por causa dos `60.03 Hz` do cabeçalho.

**Spectral.** Só as amostras. A transformada já existe (alimenta os
harmônicos); muda o que se faz com o resultado. **Ressalva obrigatória:** a
resolução é `1/duração da janela` — 5 ciclos dão 12 Hz. A tela tem de mostrar
a resolução, senão o gráfico inventa precisão.

**Alpha Plane.** Precisa da corrente dos **dois terminais** no mesmo arquivo,
o que só existe em evento de 411L/487E. Pergunta pendente: há esses relés no
parque? É também a característica da SEL; outros fabricantes usam operação ×
restrição, que sai dos mesmos dados.

**Bewley.** Precisa de ~1 MHz de amostragem; o registro do 451 vem a 2 kHz e o
`.CEV` filtrado a 4–8 amostras por ciclo. 500 vezes menos. Não é esforço: é
dado que não existe. Decisão dele: fica para o modo de ondas viajantes.

## K-factor e crest, que faltam nos harmônicos

    THD   = √(I₂² + I₃² + …) / I₁          quanto do sinal não é 60 Hz
    K     = Σ (I_h / I_rms)² · h²          quanto aquece um transformador
    Crest = I_pico / I_rms                 forma da onda · senoide = 1,414

O **K** pesa cada harmônico pelo quadrado da ordem porque a perda parasita
cresce com o quadrado da frequência: um 13º de 5 % aquece 169 vezes mais que
um 1º de 5 %. Senoide pura dá K = 1; transformador «K-13» aguenta até 13.

O **crest** acima de 1,41 é onda pontuda (retificador, inrush); **abaixo** é
onda achatada, que para proteção é sintoma de **saturação de TC**. É o
detector mais barato que existe, uma divisão.

**A armadilha, vista num print dele:** a mesma corrente aparece com crest 4,68
numa tela e 16,00 na outra. Nenhum é «o crest da corrente» — são o crest
*daquela janela*. Janela que pega o instante da falta mistura pré-falta com
pico e o número perde sentido. Regra de projeto: **crest e K só aparecem junto
com a janela que os gerou.**

## A regra do que pode ser escrito dentro do desenho

Escolha dele, 20/10/2026: **«não precisa escrever por cima do gráfico; só
escreve no gráfico as informações úteis»**. A linha de corte ficou assim:

- **Dentro do desenho** fica o que é *operacional* — a palavra que diz o que o
  relé faz naquela região (`RESTRINGE`, `TRIP`), os nomes das zonas (`Z1`,
  `Z2`), a régua de `|k|`, a marca de `100 % da LT`, o `MTA`, os eixos e os
  números dos picos.
- **Fora do desenho** vai tudo o que é *explicação*: nome da série (vai para a
  legenda), o que significa estar naquela região, o aviso do ponto cego, a
  janela e a resolução do espectro (viram chip no cabeçalho), o veredito.

Vale para os quatro gráficos novos e deve valer para os que já existem.

## As apresentações

Cinco artefatos publicados em 19/10/2026, cada um com a explicação do gráfico,
para que serve na análise, o que precisa para ser desenhado e **vinte layouts
funcionais** (seis arranjos, no caso dos harmônicos). Dados fictícios
genéricos; no espectral a DFT é calculada de verdade no navegador.

### As maquetes em painel de verdade

Pedido dele em 20/10/2026: ver os gráficos **dentro do painel do programa**.
Os quatro artefatos ganharam uma galeria de **dez painéis** cada um, acima da
dos layouts. A moldura (`.grafico`, `.grafico-titulo`, `.medida`, `.arranjo`
com ▲▼×, `.legenda`, `.mini`) é o CSS do `osclab.css` **copiado**, não
reescrito — a maquete erra pouco sobre o espaço que o desenho vai ter.

As dez variações são as mesmas nos quatro, de propósito, para a regra sair uma
só: inteiro · com tabelinha do cursor · com o pé que explica · par lado a lado ·
meia tela · tema claro · **sem os ajustes do relé** · debaixo do painel de onda ·
painel alto · tudo ligado.

### O que a maquete do painel encontrou (e já foi corrigido)

1. **Colisão de cor no plano de impedância.** A trajetória e a Z3 eram as duas
   `--destaque`. O Z medido passou para `--tinta`: ele é o assunto, as zonas
   são referência.
2. **Trajetória do plano alfa saindo pela borda.** A saturação chega a
   `|k| = 8,5` e o alcance era 7. Alcance 9 nos painéis, e recorte no desenho.
3. **Espectro rotulando cada pico duas vezes.** Com a janela de comparação
   ligada, cada pico vinha escrito uma vez por série. Só o traço principal
   rotula.
4. **Espectro rotulando vazamento como pico.** As três maiores raias eram 54,
   60 e 66 Hz — o vazamento da janela de Hann. Agora pico é máximo local sobre
   ±3 raias, acima de 3 % da fundamental, fora da saia da contínua (< 20 Hz) e
   a pelo menos 40 Hz do pico anterior.
