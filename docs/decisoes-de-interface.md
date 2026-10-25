# Decisões de interface — OscLab

Registro das escolhas visuais já decididas pelo Alexandre, para não se perder nem
ser reaberto sem motivo. Cada uma traz a data e o que ficou para o futuro.

---

## Notação dos nomes de sinal — família H (subscrito), 12/10/2026

**Escolhida por ele entre dez famílias apresentadas.**

O nome do sinal continua sendo **um só**, em texto puro, montado no Python
(`plot/sinais.nome`): `IAW · 60Hz RMS`. É esse que vai para o relatório, para a
fórmula da calculadora e para a busca. O que muda é só como a **tela** o desenha:
o nome, com as marcas (`60Hz`, `RMS`, `DC`) em **subscrito**.

O `·` **não é desenhado** — quem separa é a posição. Ele continua valendo no que
se **digita**: `iaw60`, `iaw rms` e `IAW · 60Hz` acham a mesma coisa.

### As cores

As marcas usam as **mesmas cores das fatias da barra de energia** do cartão de
sinal. Uma cor, um significado, nos dois lugares:

| cor      | variável CSS      | significa            |
|----------|-------------------|----------------------|
| turquesa | `--energia-60`    | 60 Hz (fundamental)  |
| roxo     | `--energia-harm`  | harmônicos           |
| rosa     | `--energia-dc`    | contínua             |
| cor do texto | —             | RMS — é o **total**, não uma fatia |

O RMS ficar sem cor própria é o que mantém a regra legível de um jeito só:
**colorido é uma parcela da energia; sem cor é o todo.**

A cor **reforça, não carrega**: tamanho e posição já distinguem as marcas sem
ela. É o que mantém o nome legível num relatório impresso em preto e branco —
foi essa a prova de fogo aplicada às dez famílias antes de escolher.

### Onde mora

Em **uma função só**: `escreverNome` / `criarNome`, em
`web/static/js/onda.js`, usada pela legenda, pela tabelinha, pela lista de
sinais, pelos atalhos da calculadora e pelas etiquetas do fasorial. O CSS é
`.marca-do-nome` em `osclab.css`.

### Pendente — pedido dele na mesma conversa

> «no futuro deixarei essa opção personalizável para o usuário»

Trocar de família deve ser trocar **essa função**, não caçar o nome por vinte
arquivos. As outras nove famílias apresentadas, para quando isso for feito:
sobrescrito, pastilha de contorno, pastilha preenchida, figurinha no lugar da
sigla, notação de engenharia (`|IAW₆₀|`), prefixo (`~IAW`), mesma altura só com
cor, sem cor nenhuma, e as duas marcas empilhadas.

---

## O menu de sinais: cartões compactos e escuros — 12/10/2026

A matriz de canais × contas (cinco colunas, um risquinho em cada cruzamento
vazio) virou **um cartão por sinal**, com três folhas dentro — onda, RMS e DC —
e um interruptor de filtro no cabeçalho.

O interruptor é o que faz `IAW` e `IAW · 60Hz` deixarem de ser duas linhas: são
o mesmo cartão em dois estados, que é o que o filtro de 60 Hz é.

Escolhas de acabamento, entre seis apresentadas:

- **compacto** (metade do respiro, fonte um ponto menor): 14 cartões visíveis
  onde cabiam 9;
- **cartão mais escuro que a janela** (`--cartao`, tom médio). Cartão mais claro
  se lê como objeto pousado em cima — que é como a tela marca o que está
  **selecionado**. Afundando, ele lê como compartimento aberto, que é o que é.

Outras decisões do mesmo dia, todas dele:

- **Bolinha colorida no lugar de símbolo**, e **nome sempre branco**. O sigma se
  lia como somatório e ninguém identificou a antena — desenho pequeno ou é
  símbolo que a pessoa já conhece, ou é charada. Cor na letra, no meio de nomes
  brancos, se lê como estado; cor numa bolinha ao lado se lê como etiqueta.
- **`⋯` no lugar da engrenagem**: engrenagem promete ajuste, e ali não se ajusta
  nada — lê-se.
- **Seções por procedência**, não por forma de onda: canais do relé / calculados
  pelo OscLab / suas contas.
- **Sem «nova conta» neste menu**: a calculadora já tem o botão dela no
  cabeçalho do gráfico. Esta tela é de escolher o que ver.

---

## Busca tolerante em todos os menus — 12/10/2026

Um casador só (`combinaNome`, em `onda.js`) para **todos** os buscadores da tela:
sinais, calculadora, digitais, atalhos. Duas regras, nesta ordem:

1. **Por palavra, em ordem, com buracos.** Cada palavra digitada aparece dentro
   de alguma palavra do nome, na ordem, sem precisarem ser vizinhas. É o que faz
   `IAW RMS` achar **tanto** `IAW · 60Hz RMS` **quanto** `IAW · RMS`.
2. **Tudo colado.** Junta as palavras dos dois lados e procura: `iaw60` acha
   `IAW · 60Hz`.

A ordem importa: é ela que impede `RMS IAW` de achar qualquer coisa e mantém a
lista curta. Antes eram quatro `includes` soltos, com quatro comportamentos, e
nenhum deles achava `IAW · 60Hz RMS` a partir de `IAW RMS`.

---

## A calculadora: tira de capacidades — 12/10/2026

O parágrafo corrido do veredito virou **cinco pastilhas numa linha** —
unidade · onda · RMS · DC · filtro — e **uma linha de texto que comenta só o que
NÃO dá**:

- `filtro: a operação não tem 60 Hz.`
- `onda, DC e filtro: a operação usa RMS.`
- conta que dá tudo certo → **linha vazia**, nada é explicado.

Explicar o que funciona dobra a frase sem acrescentar decisão: ninguém muda a
conta porque leu que o RMS funciona.

A **altura é fixa** — cinco pastilhas sempre, linha de texto sempre, cheia ou
vazia. Sem isso a janelinha mudava de tamanho a cada tecla e o botão «criar
sinal» escorregava debaixo do clique.

Mais duas: a **queda de sugestões** cai assim que há um colchete aberto (↑↓,
Enter, `·` opcional) e some fora dos colchetes; e os **atalhos rápidos seguem o
filtro**, não só o modo — no avançado com o filtro aceso eles ofereciam `IAW`
cru, que é o que a tela não estava mostrando.

---

## A barra de energia MEDE, não herda — 12/10/2026

A partição de energia de cada sinal (`catalogo.energia_das_linhas`) é a
identidade de Parseval medida nas amostras:

    RMS² = DC² + RMS₆₀² + RMS_harmônicos²

**Não pergunta ao `Record.filtering`.** O motivo é concreto: o arquivo de inrush
de teste está classificado como «já filtrado» e mede **80 % de 60 Hz, 17 % de
harmônico e 3 % de contínua**. Uma barra que herdasse esse veredito diria 100 %.

Dois efeitos que valem registrar:

- **O palpite errado fica visível.** Cabeçalho dizendo «já filtrado» com a barra
  mostrando harmônico é a evidência contra ele.
- **Some o caso especial do CEV.** Num `.CEV` as amostras são a componente de
  60 Hz de verdade, então a medição dá 100 % sozinha — ninguém escreveu `if cev`.

Custa ~3 ms por registro. A medida é sobre o **registro inteiro**, não sobre a
janela à vista: no menu não há cursor, e uma barra que mudasse conforme o gráfico
rolou atrás da janelinha seria medida sem pergunta.

**Pendente:** a classificação do inrush como «já filtrado» parece errada, e é
anterior a este trabalho. Investigar `analysis` (marco 0.5).

---

## Conta entre módulos tem UMA folha — 12/10/2026

`[IN G1 · RMS] − [3I0 G1]` já **é** um valor: cada amostra é a diferença entre
dois eficazes. Oferecer «eficaz» em cima dela recalcularia um eficaz de um
eficaz — uma janela de um ciclo passada num patamar, que é suavizar. «Contínua»
faria o mesmo com outro nome.

A decisão é **estrutural e exata**, não medida: cada coluna do catálogo nasce
rotulada como **componente** (instantâneo, 60 Hz, DC — parcela com sinal) ou
**módulo** (RMS, fundamental — jogaram fora sinal e fase), e o rótulo sobe pela
árvore da expressão. Nenhum operador transforma módulo em componente, então vale
para qualquer conta, por mais estranha que seja.

- todas as folhas componente → tem onda, RMS e DC
- qualquer módulo dentro, e só módulos → **uma folha só**
- **mistura** → não se sabe: fica tudo de pé com o ⓘ ao lado. «Não sei» não é
  «não existe», e a regra do projeto é avisar, nunca bloquear.

Deduzir pelo número erraria: num sinal unipolar o RMS e a DC dão valores
parecidos.

---

## O vínculo de potência — 12/10/2026

**Pedido dele.** O usuário liga uma trinca de corrente a uma trinca de tensão no
editor de grupos, e só então aparecem `P`, `Q`, `S` e `FP`.

- O botão **vincular** fica ao lado de «trocar os canais». Num grupo de corrente
  ele lista só os de tensão; num de tensão, só os de corrente.
- O par vale **nos dois sentidos**: ligar G1 a G3 grava G3→G1 junto. Desfazer
  tira os dois lados — um vínculo é um par, não duas anotações.
- Fica gravado **com o registro** (`potencia.json`, ao lado de `trincas.json`),
  pela **chave estável do conjunto** (`CURRENT I*`) e não pelo `G1`, que é
  posição.
- Sem vínculo, **nenhuma potência existe**.

### O programa não casa sozinho, de propósito

Dois vãos de uma subestação têm nomes parecidos, e o par errado produz uma
potência na unidade certa, na ordem de grandeza certa, e errada — o tipo de erro
que não aparece no gráfico. Quem sabe qual TC pertence a qual TP é quem leu o
unifilar.

### O nome carrega o par: `P G1↔G2`

E não `P G1`, que seria mentira por omissão: num registro com dois vãos, duas
linhas `P G1` e `P G2` não diriam com que tensão cada uma foi calculada, e trocar
o vínculo mudaria o número sem mudar o nome. Seta de **duas pontas** porque o
vínculo não tem direção — uma seta simples sugeriria sentido de fluxo, que é
outra coisa.

### Fasorial, não produto de ondas (escolha dele, entre três)

`P = Σ V·I·cos(θ)` a partir dos fasores de 60 Hz. **Q e FP só existem assim**:
os dois são ângulo entre fasores, e o produto de duas ondas destrói o ângulo.
Saem como módulo, uma folha só, como o `3I0`.

A onda da potência instantânea continua disponível na calculadora, com
`[VAY] × [IAW]` — e é a única que mostra a ondulação de 120 Hz, que mede
desequilíbrio.

### Fase ou linha muda a conta

- **fase** (fase-neutro) → `P, Q, S, FP, Pa, Pb, Pc`
- **linha** (fase-fase) → `P, Q, S, FP` apenas. Sem referência de neutro não há
  como repartir; o total sai pelo **método dos dois wattímetros**.

Medido: com carga **desequilibrada** a três fios, os dois wattímetros batem com
a soma por fase com erro de **0,0000000000 %**. É o teorema de Blondel, e está
amarrado em `tests/test_potencia.py` — se ele não valesse com desequilíbrio, o
número sairia certo na carga e errado na falta, que é justamente quando se olha.

A base é **palpitada pelo nome** (`VAB`, `VBC` → linha) e **corrigida num
clique** na janelinha do vínculo. É palpite porque `V1` e `Va_bus` não dizem
nada, e assumir fase-neutro em silêncio numa medição em delta daria uma potência
√3 vezes errada.

---

## A unidade da potência: cabeçalho × grandeza — 12/10/2026

Metade da resposta vem do COMTRADE e metade das amostras:

- **O cabeçalho já diz** que `kV × A` é **kVA**. Determinístico, sem olhar
  amostra nenhuma (`unidades.fator_do_prefixo`).
- **Só as amostras dizem** se aquilo aparece como kVA ou MVA.

O prefixo segue a regra que o módulo já tinha para A e V — **decidido uma vez
pelo registro inteiro, nunca pelo valor sob o cursor**, senão a unidade piscaria
enquanto o cursor anda pela onda. A escada ganhou `k`, `M` e `G`, porque potência
passa do bilhão numa interligação e tensão nunca passa do `k`.

Conferido em quatro escalas:

| registro | arquivo | P |
|---|---|---|
| linha 230 kV · 1000 A | kV × A | 398,384 MW |
| alimentador 13,8 kV · 300 A | kV × A | 7,172 MW |
| secundário 115 V · 5 A | V × A | 1725,000 W |
| **mesmo sistema, em V e kA** | V × kA | **398,367 MW** |
| interligação 765 kV · 2000 A | kV × A | 2,650 GW |

A quarta linha é o teste que importa: **o mesmo sistema declarado de dois jeitos
diferentes dá o mesmo número e a mesma unidade**. Era onde se erraria por mil sem
nada na tela denunciando.

Duas decisões dentro dela:

- **P, Q e S compartilham um prefixo só** — mesma ordem de grandeza do mesmo vão;
  prefixos independentes poriam `P` em MW ao lado de `S` em kVA.
- **Abaixo de 10 000 não há prefixo**, igual a A e V: `1725 W` se lê de imediato,
  `1,725 kW` é a mesma coisa escrita pior.

O `FP` não tem unidade — é razão entre dois VA — e escapa dessa conta inteira.

### Onde ela falha, e como

- **Arquivo sem unidade reconhecível** (`uu` vazio, ou «VOLTS»/«AMPS»): o grupo
  nem é identificado como trinca de tensão ou corrente, não há o que vincular, e
  **nada aparece**. Falha para o lado seguro.
- **Sem relação de TC/TP declarada**: o programa não inventa — mostra o lado que
  o arquivo tem e diz qual é.
- **O prefixo pode ficar um degrau grosso.** O teto é estimado por
  `1,5 × |V|máx × |I|máx`, e numa falta a tensão afunda enquanto a corrente sobe —
  os dois máximos não são do mesmo instante. Pode sair `0,4 MW` onde `400 kW`
  caberia. O número continua certo; perde um dígito de leitura. O caminho exato
  custaria seis DFTs só para escolher a letra.
