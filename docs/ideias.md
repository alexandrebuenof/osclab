# Backlog de ideias

Lista do Alexandre, 17/09/2026. **Nada aqui está implementado.** Está registrado
para não se perder. A interpretação do Claude aparece em itálico.

## Localização de faltas

1. **Calcular em tempo real a posição da falta** pelo método de um terminal e pelo
   de dois terminais (sequência negativa), ao vivo, e se possível **pegando os
   parâmetros de impedância da linha automaticamente**.
   - *O método de dois terminais por sequência negativa é o não sincronizado —
     encaixa com o problema de GPS da distribuidora.*
2. **Mostrar se a falta está para trás ou para frente** na linha
   (direcionalidade) e **identificar se houve recepção de teleproteção**.
3. **Mostrar a estrutura da falta pelo KMZ** — cruzar a distância estimada com o
   arquivo KMZ de estruturas para apontar o poste provável.
   - *A ideia de maior valor prático da lista: sai de "falta a 8,3 km" para
     "estrutura 147", que é a diferença entre um número e uma equipe sabendo para
     onde ir.*

## Ajustes dos relés desenhados sobre o registro

4. **Desenhar os ajustes das funções ao vivo:** 50/51 (curva tempo × corrente),
   21 mho e 21 quadrilateral, entre outras.
5. **Trajetória da impedância ("bolinha") no plano R-X:** conforme o usuário move
   o cursor sobre a oscilografia, um ponto percorre o plano R-X mostrando a
   impedância calculada se aproximando da região de atuação do ajuste.
6. **Ponto móvel sobre a curva do 51**, acompanhando a corrente ao longo do
   registro.
7. **Mostrar o estado do disjuntor** ao longo do registro.

## Análise da perturbação

8. **Identificar se a falta ocorreu no ponto máximo da tensão** ou não (ângulo de
   incidência).
9. **Identificar cabos batendo na distribuição** (conductor clashing) — faltas
   transitórias repetitivas, de curta duração.
10. **Filtro de Fourier para comparar os harmônicos em um inrush de trafo.**
11. **Identificar o grupo de ligação do transformador** (Dyn11 etc.) pela
    defasagem entre os lados no registro.
12. **Identificar se o sistema está radializado ou em anel**, para constar no
    relatório.
    - *A mais difícil da lista: provavelmente não se resolve só com a
      oscilografia. Pistas possíveis: contribuição pelos dois lados, sentido do
      fluxo pré-falta. Pode exigir dado externo (topologia do SCADA). Vale saber
      disso antes de prometer no relatório.*

## Escalas e unidades

16. **Alternar entre ampère secundário e primário** (pedido em 18/09/2026, ao
    conferir um registro do MiCOM P139).
    - O dado necessário **já vem no arquivo**: cada canal analógico do COMTRADE
      declara `primary` e `secondary` — no MiCOM, 600 e 5, ou seja relação 120.
      O `AnalogChannel` já guarda os dois, e o campo `scaling` diz em qual lado
      os valores estão.
    - Duas regras a embutir junto: **a tela sempre diz qual escala está
      mostrando** e de onde veio a relação (a relação vale o que o projetista
      digitou nos ajustes do relé); e quando o arquivo não declarar relação
      utilizável, a conversão fica indisponível com a explicação, em vez de
      converter em silêncio.

## Entrada de arquivos

17. **Escolher só o `.cfg` e o programa achar o `.dat` na mesma pasta** (pedido em
    18/09/2026).
    - **O navegador não permite**: uma página web recebe só os arquivos que o
      usuário escolheu, sem o caminho e sem acesso à pasta. É barreira de
      segurança do navegador, não limitação nossa.
    - Três saídas, em ordem de custo: (a) aceitar o arrastar de uma **pasta
      inteira**, que o navegador permite; (b) botão **"escolher uma pasta"**
      (`webkitdirectory`); (c) um **navegador de arquivos servido pela própria
      aplicação** — funciona porque o servidor roda na máquina do usuário e tem
      o acesso ao disco que o navegador não tem. A (c) entrega exatamente o que
      foi pedido, e exige cuidado para não virar porta aberta se a ferramenta um
      dia for exposta na rede.
    - Combinado: (a) e (b) junto com o zoom; (c) quando decidirmos se a
      ferramenta é só do Alexandre ou da equipe.

## Visualização

13. **Alternar entre variáveis do relé (word bits) e variáveis do software** — as
    do software sendo genéricas, iguais para IED de qualquer fabricante.
14. **Desenhar o triângulo de tensões** (diagrama fasorial das três tensões).
16. **Marcar cada amostra com um pontinho** no traço — opcional, **desligado por
    padrão**, num botão junto aos gestos do gráfico.

    O detalhe que decide a implementação: com a janela ampla, o traço **não é
    feito de amostras** — é o mínimo e o máximo de cada coluna de pixel
    (`plot/serie.py`). Pôr um ponto em cada vértice ali seria desenhar amostra
    onde não há, e mentir justamente sobre o que o recurso promete mostrar.

    Regra proposta: o ponto só aparece quando a janela **não** foi reduzida — o
    servidor já informa isso no campo `reduzido` da janela. Fora disso o botão
    fica marcado como "amplie para ver as amostras". Isso vira um efeito
    colateral útil: **o ponto aparecendo é o sinal de que se está vendo amostra
    de verdade**, e o espaçamento entre eles mostra de relance quantas amostras
    por ciclo o relé gravou — 4 (dado já filtrado) ou 32 (sinal bruto).
17. **Ler fasor e RMS no cursor**, ao lado do valor instantâneo (depende do
    marco 0.4). Hoje a tabelinha mostra a **amostra**: `95,1 A` e, meio ciclo
    depois, `-95,1 A` são o mesmo sinal. Com a janela de um ciclo terminando no
    cursor, a coluna "2 − 1" das tensões vira afundamento de verdade, em módulo
    e ângulo, e a defasagem entre canais passa a ser legível.

## Alinhamento

15. **Alinhar oscilografias automaticamente**, identificando pontos em comum —
    tanto para linha quanto para **"trafo com als"**. *Termo "als" a confirmar.*

## Consequência de arquitetura que esta lista revela

Vários itens (1, 2, 4, 5, 6) dependem de **ler os ajustes do relé**, não só a
oscilografia. Isso é uma **terceira classe de entrada** do programa, ao lado da
oscilografia e do KMZ:

- de onde vêm os ajustes (RDB do AcSELerator, arquivos SET, SCD, planilha,
  digitação);
- como são normalizados entre fabricantes diferentes.

Vale ser previsto na arquitetura mesmo que só seja implementado depois.

Os itens 5 e 6 reaproveitam a mesma cadeia de fasores prevista para as
componentes simétricas — não são cálculo novo, são visualização nova sobre o
mesmo resultado. O item 5 depende ainda da **seleção do laço** (AG, BG, CG, AB,
BC, CA), que é o mesmo dado que decide a direcionalidade do item 2.

## Pendências de esclarecimento

- O que é "trafo com als" no item 15.
- De onde viriam os parâmetros de impedância de linha no item 1 (cadastro
  próprio, ajustes do relé, planilha existente?).
- O que "em tempo real / ao vivo" significa no item 1: conexão com o relé, ou
  recálculo instantâneo conforme o usuário move os cursores sobre o registro já
  aberto?
