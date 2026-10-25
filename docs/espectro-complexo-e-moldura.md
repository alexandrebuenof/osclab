# O espectro, o gráfico complexo e a moldura do cursor

Decidido com o Alexandre em 20/10/2026, em cima das maquetes.

## A moldura do cursor, em todos os gráficos novos

O sulco com as etiquetas numeradas `1` e `2`, acima e abaixo do desenho — o
mesmo `moldura-do-cursor` do painel de onda (`SULCO = 7 px`, etiqueta 11 px).

Nos quatro gráficos novos (impedância, complexo, espectro, plano alfa) o
tempo **não está no eixo**. Sem a moldura, mudar de instante obrigaria a
voltar ao painel de onda, rolar a tela até achá-lo e arrastar lá — e o
gráfico que se quer ver fica fora da vista justamente na hora de mexer. Por
isso ela entra em todos eles. **Pedido dele, 20/10/2026.**

## O gráfico complexo

    cursor 1 · ver em pu · + sinal · ⚙

- **«por amostra» saiu do painel**: subiu para o menu de cima, no botão
  `fasor`, porque é cálculo e vale para todos os sinais (mesma regra do
  filtro).
- **A seta** (o vetor da origem até o ponto do cursor — o fasorial clássico)
  desceu para a engrenagem.
- **O tracejado âmbar é o círculo de 1 pu**: onde o módulo vale uma vez a
  nominal do canal. Só pode ser desenhado quando a nominal é conhecida; sem
  ela o painel avisa e o raio passa a querer dizer amperes, não «vezes a
  nominal».

## O espectro

    cursor 1 · ver em dB · + sinal · ⚙   + chip da janela

O **chip da janela** não é botão: é o que o gráfico está medindo —
`6 ciclos · 10,0 Hz · 32/ciclo`. A janela sai dos **cursores**: arrastar 1 e
2 na moldura é o que escolhe o trecho analisado.

### As duas coisas independentes que o espectro precisa dizer

| | de onde vem | o que muda |
|---|---|---|
| **resolução** | a **duração** da janela, 1/T | separar duas raias vizinhas |
| **frequência máxima** | a **taxa de amostragem**, fs/2 (Nyquist) | até que harmônico dá para olhar |

Dez ciclos dão 6 Hz de resolução com **qualquer** amostragem. E a amostragem
decide a ordem máxima:

| amostras/ciclo | fs | Nyquist | ordem máxima |
|---|---|---|---|
| 32 | 1920 Hz | 960 Hz | 16º |
| 16 | 960 Hz | 480 Hz | 8º |
| 8 | 480 Hz | 240 Hz | 4º |
| 4 | 240 Hz | 120 Hz | 2º |

**Pergunta dele, 20/10/2026:** mostrar só os harmônicos que a frequência de
amostragem permite calcular. Fechado — o eixo **termina em fs/2**, com a
reta vermelha e a ordem escrita. Desenhar eixo além de Nyquist seria
oferecer espaço para informação que não existe; o que aparecesse ali seria
rebatimento, não harmônico. Com o `.CEV` filtrado pelo relé a 8 amostras por
ciclo, o 5º harmônico **não está no arquivo** e nada no programa pode
inventá-lo.

### A janela tem de ficar de um lado só da falta

Uma janela que **atravessa** o instante da falta mistura os dois regimes e
espalha energia por todo o espectro — vira uma floresta de raias que não é
harmônico de nada. É a mesma armadilha do crest com 4,68 numa tela e 16,00
na outra.

Por isso a comparação **janela na carga × janela na falta** usa duas janelas
do mesmo tamanho, cada uma inteiramente de um lado. É ela que separa «este
harmônico veio da falta» de «este harmônico já estava na linha» — e era o
que faltava explicar na legenda da primeira versão.

## Estado

Dez maquetes publicadas em cada artefato (galerias «Dez cabeçalhos»).
**Nada foi implementado ainda no programa.** É a próxima etapa, escolhida por
ele em 21/10/2026.
