# O plano de impedância (mho) — decisões do painel

Decidido com o Alexandre em 20/10/2026, em cima das maquetes.
**Implementado no programa em 20–21/10/2026**, com os ajustes manuais.

## Nome: PARÂMETROS DA LINHA, não «réplica»

Escolha dele, 21/10/2026. O que a literatura chama de réplica da linha
(`Z1MAG`/`Z1ANG`) aparece em toda a tela e no código como **parâmetros da
linha** — `parametros_da_linha`, classe `Parametros`, chave `parametros` do
JSON.

## O cabeçalho

    cursor 1 · laço AN ▾ · G1↔G2 · ajustes: do arquivo ▾ · ⚙

**«secundário» saiu do painel.** Trocar primário/secundário muda o número e
vale para a tela toda — pela regra do projeto é do menu de cima, onde o `lado`
já existe. Era botão repetido.

**«+ laço» sumiu, fundido no botão do laço.** Numa falta só o laço em falta
entra na zona; os outros medem carga — ver dois juntos é o que responde «foi
mesmo AN?».

**Ajustes são botão no cabeçalho**, e o rótulo é o próprio aviso: `do arquivo`,
`do arquivo + sugeridos`, `do arquivo + manuais` ou `manuais` aparece sem
ninguém clicar — e quando não é tudo lido, o botão fica âmbar.

## Todo número carrega a origem

| origem | de onde vem | como é desenhada |
|---|---|---|
| **lido** | bloco `SETTINGS` do `.CEV`, ou o `.HDR` | traço cheio, com preenchimento |
| **sugerido** | padrão nosso sobre os parâmetros da linha | **tracejado**, escrito «Z1 sugerida» |
| **digitado** | o usuário | pontilhado, escrito «Z1 digitada» |

O caso perigoso é uma zona inventada parecer uma zona lida do relé, e é esta
tabela que impede.

## A caixa de ajustes manuais

**A caixa NÃO é filha do painel.** Cada tecla digitada pede a janela ao
servidor de novo (com 320 ms de espera depois da última), e a resposta refaz os
painéis inteiros — um menu pendurado no cabeçalho sumiria debaixo do dedo a
cada letra. Pendurada no `body` e posicionada em coordenadas de viewport, ela
sobrevive à repintura, e o desenho se mexe atrás dela enquanto se digita.

**Os parâmetros da linha têm bloco e grade próprios.** `ZL` é um número
complexo (dois campos) e uma zona é um alcance (um campo + % + tempo). Na mesma
grade, o segundo campo de `ZL` caía na coluna do «% da LT» — e ali um ângulo de
80 se lê como 80 % da linha.

**Polar ou R + jX**, com o botão junto dos campos que governa. O relé escreve
`Z1MAG`/`Z1ANG`, que é polar; o estudo de curto quase sempre chega em `R + jX`.
O mesmo número na outra forma fica escrito em cinza embaixo — é ali que um seno
trocado por um cosseno salta à vista.

**O valor digitado é SECUNDÁRIO**, como todo ajuste de distância. O servidor
converte para primário junto com os lidos, pelo mesmo caminho; é isso que
impede digitado e lido de divergirem de base. Por isso o JSON traz um campo
`ajuste` separado, com os valores ANTES da conversão: é o que o formulário
edita. Sem ele, o campo abriria com o número multiplicado por RTP/RTC e, ao
salvar, multiplicaria de novo.

O que o usuário digita vive em `Painel.manuais`:
`{"zl": {"modulo", "angulo"}, "zonas": {"Z1": {"alcance", "tempo"}}}`.
Peneirado em `impedancia.manuais_de` — alcance > 0 e finito, ângulo entre −90°
e 90°, nome de zona conhecido —, porque a tela manda texto.

Regras do mesclar:

- **Por cima, não no lugar:** quem digitou só o módulo fica com o ângulo do
  arquivo, e o campo que não tocou continua dizendo que veio do relé.
- **Os parâmetros antes das zonas:** a sugestão sai de `% sobre o módulo`,
  então corrigir a linha à mão tem de chegar às zonas sugeridas.
- **Uma zona que o arquivo não traz nasce do teclado** — é o caso do COMTRADE
  puro.
- **«voltar ao do arquivo»** apaga tudo o que foi digitado.

## A sugestão padrão

**Z1 = 80 %, Z2 = 120 %, Z3 = 200 %** dos parâmetros da linha, configuráveis na
engrenagem. *A confirmar com a proteção.*

## A BASE — o defeito mais perigoso deste painel

`Z = V / I`. A conta só fecha se os dois estiverem na **mesma base** e **sem
prefixo**. Três armadilhas, as três encontradas rodando o painel nas amostras
fictícias, e as três resolvidas em `plot/impedancia.py`:

1. **O prefixo.** O relé grava tensão em `kV` e corrente em `A`. Dividir as
   amostras cruas dá **kΩ** — e um plano em kΩ com zonas em Ω põe a falta mil
   vezes mais longe, sem nada denunciando. As amostras entram na conta já
   multiplicadas pelo fator do prefixo (`unidades.fator_do_prefixo`).
2. **`1/1` não é relação.** Num `.CEV` o cabeçalho do canal não declara
   RTC/RTP: fica `1`. O conversor do programa divide por 1 e devolve o lado
   *pedido* — inofensivo para desenhar uma onda, fatal aqui. O painel calcula o
   lado real pela relação declarada (`> 1`), não pelo lado pedido.
3. **Quem muda de base são as ZONAS, nunca a trajetória.** O ajuste do relé é
   secundário por definição. Com o plano em primário, as zonas e os parâmetros
   são multiplicados por RTP/RTC e isso vai escrito numa ficha. A trajetória é
   medida, e medida não se reescreve para caber no desenho.

E a relação, quando o cabeçalho do canal não traz, sai dos **ajustes**
(`CTR`/`PTR` da SEL) — num `.CEV` o número está no mesmo arquivo, só que no
outro bloco.

Separado disso: `entradas[zona] = None` significava **duas** coisas — «não
entrou» e «não dá para comparar». Virou um campo próprio (`comparavel`).

## O rodapé: três fichas, não seis

Enxugado a pedido dele. A primeira versão punha uma ficha por zona, mais os
parâmetros, mais o k0, mais o par, mais o aviso por extenso — e o rodapé ficou
mais comprido que o gráfico.

    linha 20,80 Ω ∠76° · k0 0,666  |  entrou Z1 · amostra 71  |  ⚠ zonas × RTP/RTC = 10

- O **k0** saiu de aviso e virou parte da régua, ao lado do número que ele
  corrige. Falta num laço de terra → a ficha inteira fica vermelha.
- As três fichas de zona viraram **uma**: a zona mais interna em que a
  trajetória entrou. Alcance, tempo, % e origem das três continuam no hover.
- **Todo aviso tem duas alturas**: um `curto` (até 46 caracteres) na ficha e um
  `longo` no hover. Há teste travando isso.

Pendente, levantado por ele: «amostra 71» é o índice cru. Provavelmente seria
mais útil em **ms depois do início da falta** ou em **ciclos**.

## De onde saem os seis canais

Do **vínculo** corrente×tensão, a mesma fonte do triângulo de tensões — e não
de «a trinca de corrente e a de tensão com o mesmo rótulo». O rótulo (`G1`,
`G2`) é contado entre todos os conjuntos do registro, então a corrente de um
vão é `G1` e a tensão do mesmo vão é `G2`: casar pelo rótulo pegava a tensão do
outro lado do equipamento e desenhava uma trajetória plausível e inteiramente
falsa.

Ordem de certeza: o vínculo escolhido → o único vínculo que serve → o par único
do registro. Com duas trincas de cada e nenhum vínculo o painel **não
adivinha**: não desenha e diz por quê.

## Os pontos da trajetória

Só aparecem **enquanto a mão está no cursor** (arrastando ou nas setas), e
somem 0,9 s depois da última tecla, no mesmo ritmo da barra da onda. Cada um
tem halo da cor do fundo e miolo da cor do traço: só o miolo sumia dentro da
linha, e ponto que não se distingue da linha não diz onde a amostra caiu.

## Ainda falta, por ordem

1. **Mais de um laço no mesmo plano** — a caixinha de marcar dos seis.
2. **Quadrilátero** — o relé declara (`E21MG`, `XG1`/`RG1`) e o painel só
   desenha mho.
3. **Grupos de ajustes** — o relé guarda seis e comuta em operação; o painel lê
   um só e não diz qual (maquete A10 mostrou como seria).
4. **Laço de fase a partir de tensão de linha** — hoje um vínculo em delta é
   recusado inteiro, mas `Z_AB = V_AB / (I_A − I_B)` sai direto de uma trinca
   de linha. Só o laço de terra é que não.
5. O ciclo de entrada na zona é medido na trajetória **decimada** (600 pontos).
6. Ligar o `Z` da linha à gaveta de **linhas** da base de dados.
