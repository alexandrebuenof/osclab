# OscLab — instruções para o Claude

Leia este arquivo antes de mexer em qualquer coisa. Ele é lido automaticamente
pela extensão do VS Code a cada sessão.

## Quem é o usuário

Alexandre, engenheiro de proteção numa distribuidora de energia. Fala português.
Conhece proteção de sistemas elétricos a fundo; está aprendendo programação e
Git agora. Parque de IEDs da empresa: SEL, Siemens, GE, ABB, Schneider, Ingeteam
e NOJA.

## Regras de trabalho — valem sempre

1. **Não escrever código sem pedido explícito.** Discutir, analisar e propor
   arquitetura é livre. Criar ou editar arquivo de código, só quando ele pedir.
2. **Revisar depois de executar.** Terminada a tarefa, conferir o resultado —
   rodar os testes, reler o que foi escrito — antes de dizer que acabou.
3. **Consultar antes de decidir.** Dúvida no meio de uma implementação vira
   pergunta, com alternativas e prós e contras. Nunca uma escolha silenciosa.
4. **Respostas curtas e didáticas**, salvo pedido em contrário. Explicar o
   porquê, não só o quê.
5. **Precisão na frente da estética** — sem abrir mão da estética. Diante da
   escolha entre um número mais exato e uma tela mais bonita, ganha o número;
   o trabalho é então fazer o número caber bem. Um dígito a mais que reduz o
   erro de leitura vale a largura que custa.

## O que é o programa

Leitor e analisador de oscilografia: lê vários formatos e fabricantes, analisa
perturbações automaticamente, localiza faltas por diferentes métodos e gera
relatórios. Interface web local; o usuário abre no navegador.

## Comandos

```bash
python app.py --preparar     # cria o venv e instala as dependências
python app.py --web          # sobe a interface em http://localhost:8770/
python app.py --versao       # imprime a versão
python app.py --testes       # roda os testes; instala pytest/ruff se faltarem
python app.py --ler ARQ.cfg  # descreve uma oscilografia no terminal

pytest                       # direto, quando o ambiente já está pronto
pytest tests/test_formats.py # um arquivo só
ruff check .                 # lint
ruff check . --fix
```

No Windows há também o `osclab.cmd`, que abre um menu.

## Git — quem faz o quê

O Claude **grava os arquivos** na pasta; **o Alexandre faz o commit**. É de
propósito: o commit é a chance de conferir o que entrou antes de virar
história. Ao entregar uma mudança, o Claude sugere a mensagem.

```bash
git status              # o que mudou desde a última fotografia
git add -A              # põe tudo na mesa de preparação
git commit -m "..."     # fotografa a mesa
git push                # envia para o GitHub
```

Regras que já custaram caro neste repositório:

- **Padrão de `.gitignore` sem barra na frente vale em qualquer nível.**
  `library/` barrou também `src/osclab/library/`, e o primeiro commit subiu sem
  o `acervo.py` — um clone que não roda. Os padrões de pasta da raiz são
  ancorados: `/cache/`, `/library/`, `/vendor/`, `/dist/`, `/build/`.
- **`.gitattributes` fixa o fim de linha em LF.** Sem ele, cada gravação do
  Claude (LF) contra uma cópia em CRLF faria o Git enxergar o arquivo inteiro
  alterado, e os diffs virariam lixo.
- **`--amend` só em commit que ninguém recebeu.** Ele não edita: cria outro no
  lugar, com identificador novo.

## Estrutura

```
osclab/
├── app.py                 launcher: venv, dependências, modo
├── osclab.cmd / .sh       menu (Windows / Linux)
├── VERSION                só o número, X.Y.Z
├── config/                config.ini.example é versionado; config.ini NÃO
├── src/osclab/
│   ├── paths.py           TODO caminho sai daqui
│   ├── version.py         comparação de versões
│   ├── formats/           um leitor por formato; base.py é o contrato
│   ├── dsp/               fasor.py: DFT de um ciclo, RMS, DC, THD
│   ├── analysis/          perturbação, descontinuidade    (marco 0.5)
│   ├── faultloc/          localização de faltas           (marco 0.6)
│   ├── network/           impedâncias, TC/TP, KMZ
│   ├── library/           acervo por sha256 (acervo.py)
│   ├── plot/              amostragem, escalas, eixos, zoom/arrasto, cursores
│   ├── report/            mini relatório                  (marco 0.7)
│   ├── cli/               modo lote
│   └── web/               SÓ apresentação
├── data/  samples/  docs/  tests/  tools/
└── cache/  library/       tempo de execução, fora do git
```

## Invariantes — quebrar qualquer um destes é um bug

- **Lógica de domínio nunca dentro de `web/`.** Ler formato, processar sinal e
  localizar falta têm que rodar sem navegador — em teste, em lote e na geração
  do relatório.
- **Todo caminho sai de `paths.py`.** Nenhum outro módulo monta um caminho.
- **Nunca percorrer amostra a amostra em Python.** Sempre vetorizado com numpy.
  Um registro tem centenas de milhares de amostras por canal.
- **Nada de import dinâmico por string.** O empacotador não enxerga, e o
  programa pode virar um `.exe` no futuro. Leitores novos são importados
  explicitamente em `src/osclab/formats/__init__.py`.
- **Templates, CSS e JS ficam dentro do pacote**, não procurados por caminho
  relativo a partir do diretório atual.
- **Sem relação de TC/TP declarada, não se converte** — e isso aparece: o canal
  ganha etiqueta de aviso na legenda e é nomeado no rodapé. Converter por
  palpite viraria ampère secundário lido como primário no relatório.
- **O leitor entrega unidade de engenharia**, nunca o inteiro cru do conversor
  A/D. Os fatores de conversão são aplicados no leitor.
- **Diagnóstico automático se mostra e se deixa corrigir.** O programa avisa,
  nunca bloqueia; e nunca apresenta um palpite como certeza — vale em especial
  para a detecção bruto × filtrado, que corromperia a localização de falta em
  silêncio.
- **`config/config.ini` nunca vai para o git.** Tem IP e senha de equipamento.
- **O JavaScript não decide número nenhum.** Janela, escala vertical,
  marcações de eixo e redução de amostras vêm prontos de `plot/`, onde há
  teste. O navegador converte valor em pixel e pinta.
- **Reduzir amostras é por mínimo e máximo de cada coluna de pixel**, nunca
  pegando uma a cada N: o jeito ingênuo apaga o pico da falta.
- **Digital reduz pelo MÁXIMO da coluna.** Um pulso de duas amostras num
  registro de 500 mil tem uma chance em 550 de sobreviver a uma redução
  ingênua. Pelo máximo ele sempre aparece — mais largo do que é, e isso é o
  certo: **trip que some da tela é pior que trip gordo demais.** Colunas
  ligadas seguidas viram um retângulo só, senão o antialiasing abre fresta e
  um trip contínuo se lê como intermitente.
- **As duas listas são `IED` e `OscLab`.** `IED` traz os canais do arquivo,
  crus, com o nome do fabricante — e continuam crus mesmo com o filtro de
  60 Hz ligado, porque filtrar é conta nossa. `OscLab` traz o que o relé NÃO
  gravou: `IA RMS`, `IA 60Hz`, `IA 60Hz RMS`, `3I0`, `I1`, `I2`, com o canal
  de origem escrito ao lado.
- **O vínculo canal → fase é CORRIGÍVEL, e a correção fica gravada.** Vai num
  `vinculos.json` ao lado do registro, não no `meta.json` (que é cache e pode
  ser refeito) e não na tela (que fecha). Quem corrigiu uma fase corrigiu para
  sempre. A escolha do usuário vence a declaração do arquivo e a dedução pelo
  nome — ele olhou o arquivo e o unifilar; a nossa expressão regular olhou um
  nome. `"-"` é a escolha explícita de "nenhuma" e NÃO cai de volta na
  dedução; vazio é "não mexeram". A tela mostra a origem: moldura pontilhada
  para o deduzido (palpite bom, e palpite), cheia para o declarado e para o
  corrigido.
- **A variável fundamental fica do lado do IED, como CONFERÊNCIA do vínculo.**
  `IA`, `IB`, `IC`, `IN`, `VA`, `VB`, `VC`, `VN` são de onde sai todo o resto —
  RMS, componentes simétricas, localização de falta. Elas não são um canal:
  são um vínculo que o programa DEDUZIU do nome (`Current IA` → `IA`), e cada
  fabricante escreve esse nome como quer. **Vínculo errado corrompe tudo sem
  dar erro nenhum** — 3I0 sai na unidade certa, na ordem de grandeza certa.
  Por isso ele aparece ao lado do canal, e um canal sem vínculo diz
  "não reconhecido" em vez de ficar calado. A lista do OscLab não repete `IA`:
  seria o mesmo canal com outro nome, e o vínculo já está do lado de lá.
- **O que o sinal É e a CONTA que leva até ele são campos diferentes.** Num
  registro já filtrado, `IA 60Hz` é o próprio canal (conta nenhuma) e
  `IA 60Hz RMS` é o eficaz de um ciclo dele — e `IA RMS`, eficaz verdadeiro
  com harmônicos, **não é oferecido**: não há harmônico ali para incluir, e o
  nome prometeria uma medida que o arquivo não permite. Num registro bruto as
  três contas são de verdade. Ver `OFERTA_DE_BRUTO` e `OFERTA_DE_FILTRADO`.
- **Gesto e cursor têm que combinar.** A mãozinha só aparece dentro da moldura
  do desenho, e o arrasto só começa lá — os dois usam a mesma conta
  (`noDesenho`). Cursor de arrastar sobre um lugar que não arrasta é promessa
  que a tela não cumpre; e arrastar de um lugar sem mãozinha movia a
  oscilografia sem nada ter avisado que aquilo era arrastável.
- **A roda só é nossa DENTRO da moldura do desenho.** A caixa do gráfico é bem
  maior que o desenho — cobre a margem dos rótulos do eixo e as folgas de cima
  e de baixo —, e capturar a roda ali fazia a oscilografia saltar de escala
  quando o usuário só queria descer a página. Fora da moldura não há
  `preventDefault`, e o navegador faz o que sempre fez. Vale para as ondas e
  para as tiras digitais (`noDesenho`).
- **Todo sinal tem um alvo de clique que não se move.** O traço é o gesto
  natural e é o que erra: num gráfico com oito curvas sobrepostas na pré-falta,
  ou numa tela de quarenta tiras de 15 px, acertar a certa com o mouse é mira.
  Então o NOME também seleciona — na legenda das ondas e na etiqueta da tira
  digital. Um comportamento só nos três lugares (`alternarSelecao`): sem Ctrl
  troca e desmarca, com Ctrl acumula. Clique em qualquer outro lugar limpa.
- **A etiqueta numerada do cursor mora FORA da moldura e continua sendo alvo.**
  Restringir o gesto à área de desenho tirou dela o clique, e ela é justamente
  o pedaço mais óbvio para pegar o cursor. `sobreEtiqueta` é a exceção que o
  `pointerdown` consulta junto com `noDesenho`.
- **A legenda é alvo de clique tanto quanto o traço.** Num gráfico com oito
  curvas sobrepostas na pré-falta, acertar o traço certo com o mouse é sorte;
  o nome na legenda está sempre no mesmo lugar e não se move. Os dois gestos
  fazem a mesma coisa, e **Ctrl** em qualquer um deles acumula a seleção —
  comparar duas fases é o gesto mais comum do ofício.
- **Ctrl+Z desfaz o que está na TELA, não o que foi decidido.** Sinal tirado,
  acrescentado, digital escondido: tudo volta. Correção de fase não, porque
  aquilo é dado gravado ao lado do registro e se desfaz no próprio lápis —
  misturar as duas coisas numa tecla só faria o Ctrl+Z às vezes mexer no
  arquivo e às vezes não.
- **Clicar num traço escolhe aquele sinal; Delete tira ele da tela.** Os
  outros traços perdem opacidade em vez de sumir — tirar os vizinhos tiraria
  justamente a comparação que fez alguém clicar ali. Canal do arquivo não sai
  do registro, sai da TELA (`ocultos`, que vai ao servidor porque a escala
  vertical depende de quem está desenhado), e volta pelo `+ sinal`, na aba IED,
  onde aparece desmarcado. O grupo continua existindo mesmo ficando vazio: é
  dele que sai o botão que traz o canal de volta.
- **A grandeza é do SINAL, não do botão.** Cada variante tem id próprio
  (`v0:rms`, `v0:filtrado`, `v0:fundamental`), e o botão de filtro do cabeçalho
  não mexe nelas: `IA RMS` não pode mudar de significado com um clique em
  outro lugar da tela. Num registro já filtrado, as variantes `60Hz` não são
  nem oferecidas.
- **Busca mostra primeiro o que FALTA, e no fim o que já está.** Quem procura
  está procurando entre os que ainda não estão na tela. Então a busca e as abas
  filtram só a parte de cima; a de baixo lista tudo que está escolhido, junto,
  sem separar por aba — ali o que importa é poder tirar, e de onde veio o sinal
  não muda isso. Vale para os analógicos e para os digitais.
- **A janela de busca tem altura FIXA.** Com altura elástica ela pulava de
  tamanho a cada letra digitada e a cada troca de aba, e o botão de aplicar
  fugia de debaixo do mouse.
- **Nada entra num gráfico porque o programa sabe calcular.** 3I0, I1 e I2
  estão prontos e testados desde o marco 0.4b e só aparecem quando alguém os
  acrescenta pelo `+ sinal`. Tela que se enche do que o programa sabe fazer
  vira painel de números que ninguém pediu, e o que importa some no meio.
- **Sinal acrescentado à mão carrega a PRÓPRIA medida.** O botão
  instantâneo/RMS do gráfico manda nos canais que abriram por padrão; o que foi
  acrescentado fica como foi pedido. É o que permite `IA` e `IA RMS` no mesmo
  gráfico — a comparação que mostra o atraso de um ciclo do filtro.
- **Unidade diferente, eixo diferente.** Um sinal de outra unidade vai para a
  escala da DIREITA e é desenhado tracejado, porque a altura dele não se
  compara com a dos outros traços. Um terceiro eixo não existe: o sinal é
  recusado com aviso, em vez de ser desenhado numa escala que não está escrita
  em lugar nenhum. A margem direita, como a esquerda, é uma só para todos os
  gráficos.
- **Componente simétrica só existe em EFICAZ.** `I1` e `I2` exigem girar `Ib` e
  `Ic` de 120°, e girar é multiplicar por um complexo — operação que não existe
  sobre uma amostra sozinha, só sobre o fasor. `3I0` poderia ser somado no
  tempo, e mesmo assim segue a mesma regra: duas componentes com a mesma cara
  vindas de definições diferentes seria pior que a limitação.
- **O digital é UMA linha que muda de espessura, não uma barra que sobe.** Fina
  em 0, grossa em 1, na mesma altura do começo ao fim e no mesmo azul (o token
  `--digital`, mais escuro que o `--destaque` dos botões: duas dúzias de tiras
  acesas no azul dos botões viravam um bloco luminoso e as ondas sumiam de
  importância). O olho corre a tira inteira sem subir e descer, e o que salta é
  a espessura. Clarear o estado 0 foi tentado e desfeito: **canal apagado
  precisa se ver tanto quanto aceso** — é ele que prova que o sinal existe e
  não mudou.
- **A margem esquerda é UMA SÓ para todos os gráficos** (`MARGEM.esq`, que
  cresce a partir de `MARGEM_BASE` quando os nomes digitais estão inteiros).
  Alargar só o bloco das tiras seria o caminho óbvio e está errado: as tiras
  dividem o eixo do tempo com as ondas, e dois eixos que começam em `x`
  diferentes põem o mesmo instante em dois lugares da tela. Nome de digital de
  IED chega a 27 caracteres (`MAIN : Timer stage N elaps.`), então há o botão
  `nome curto`/`nome inteiro`, o corte é pela largura MEDIDA (não por número de
  letras) e o nome completo está sempre no hover da tira.
- **Todos os digitais que mudaram entram, sem corte.** Cortar nos primeiros N
  esconderia o religamento e o segundo trip, que são o fim da história. O
  `limite` continua a um argumento de distância para o registro esquisito (ruído
  em entrada binária), e quem o usar tem que dizer na tela quantos ficaram de
  fora.
- **Só os digitais que MUDARAM entram na tela, ordenados pela hora da primeira
  mudança.** Um SEL-487E tem 5760 entradas binárias; foi a falta deste critério
  que segurou este marco. A ordem faz a tela contar a sequência do evento de
  cima para baixo. Os parados continuam na busca — **escondido não é o mesmo
  que inexistente**: num laudo, às vezes o que importa é provar que um sinal
  NÃO mudou.
- **Os gestos do gráfico são fixos**: roda amplia no ponto do cursor, arrastar
  anda, Shift+arrastar seleciona uma faixa, botão direito volta ao registro
  inteiro. Teclas `1` e `2` põem e tiram os cursores de medição no ponto do
  mouse, `←`/`→` andam uma amostra (com Shift, um ciclo), `Esc` tira os dois. O navegador manda o *gesto* em segundos; quem decide a janela que
  sai disso é `plot/navegacao.py` — inclusive o piso de amostras e as bordas.
- **A escala vertical se ajusta à janela visível**, por grupo. Ampliar a
  pré-falta tem que mostrar a corrente de carga, não um fio reto no zero.
- **Tema escuro é o padrão**, por escolha do projeto; o claro é um botão no
  cabeçalho, guardado no navegador.
- **Nada de CDN.** Toda biblioteca de front-end viaja dentro do pacote: uma
  subestação sem internet não pode depender de um `<script src="https://...">`.
- **Cores de fase são token CSS** (`--fase-a/b/c/n`), validadas para daltonismo
  e contraste nos dois temas. A identidade nunca é so' a cor: legenda e leitura
  do cursor sempre nomeiam o canal.
- **A cor da fase segue a convenção de campo da distribuidora**: azul na A,
  vermelho na C. O branco da fase B virou âmbar — branco some no tema claro.
- **A janela do fasor é o ciclo que TERMINOU no cursor**, nunca centrada. O
  relé só conhece o passado; uma janela centrada usaria amostras que, no
  instante da decisão, ainda não existiam, e o número deixaria de ser
  comparável com o do relé. A consequência visível e correta: depois da falta o
  módulo leva um ciclo inteiro para subir.
- **`fundamental` é EFICAZ, não amplitude.** Conferido contra o SIGRA nos
  números de um registro real — a coluna "Fundamental" dele só fecha com a
  "Extremum" lendo-se eficaz. Implementar como amplitude daria √2 de diferença,
  erro que se procura por horas porque o gráfico continua parecendo certo.
- **O ângulo é absoluto dentro do `dsp/`; a referência é subtração na
  `leitura`.** É o que torna a troca de referência barata e o que vai permitir,
  no marco 0.5, comparar ângulos de dois registros na mesma base.
- **A referência de 0° é escolhida por SIGNIFICADO**: a tensão da fase A, não
  "o primeiro canal". Um relé que liste a tensão de barra antes da de linha
  mudaria a referência sem ninguém notar. Quedas: tensão A → corrente A →
  primeiro canal. Um clique no nome do canal sobrepõe tudo, como no SIGRA.
- **Reto é do relé, inclinado é nosso.** O nome padronizado aparece em
  **itálico dentro da moldura**; o nome do arquivo, reto e fora dela. Uma regra
  só, que vai valer também para `3I0`, `V1` e `V2` no 0.4b — grandezas que não
  existem em canal nenhum do arquivo. Quando um relé gravar o próprio canal de
  3I0, os dois vão aparecer na tela escritos de formas diferentes, e a
  diferença entre eles é diagnóstico (erro de TC, saturação).
- **O nome do arquivo e o nome do OscLab aparecem os dois, sempre.** Cada
  fabricante nomeia como quer (`IAW`, `Current IA`, `TC BUC 69kV:I A`); o nome
  padronizado (`IA`, `IB`, `IC`, `IN`, `VA`, `VB`, `VC`, `VN`, em
  `fases.padrao`) é o mesmo venha de onde vier, e é por ele que o resto do
  programa vai falar dos canais nas componentes simétricas e na localização de
  falta. Ele fica **ao lado** do nome do arquivo, numa moldura, nunca no lugar
  dele: o nome original é o que o engenheiro reconhece e o que consta do
  relatório do relé. Quando a grandeza ou a fase não dá para determinar, o nome
  padronizado é `""` — um palpite com cara de nome nosso entraria nas
  componentes simétricas como se fosse fase de verdade.
- **A tabelinha casa linha com leitura por ÍNDICE do canal**, nunca por
  posição: os grupos reordenam (correntes juntas, tensões juntas) e a leitura
  vem na ordem do arquivo. Num registro que intercale as duas, casar por
  posição poria a tensão na linha da corrente.
- **O valor do cursor vem do servidor, nunca do traço desenhado.** O traço é
  mínimo e máximo por coluna de pixel: nenhum dos dois é "o valor no instante".
  Ver `plot/leitura.py`.
- **O cursor cai sempre em cima de uma amostra.** Entre duas amostras não há
  medida, há interpolação — e a 16 amostras/ciclo meia amostra são 11°.
- **Percentual só se mostra quando o denominador significa algo.** `DC %` e
  `THD` são percentuais DA FUNDAMENTAL; quando a fundamental é menor que um
  quarto do RMS da janela (`fasor.MINIMO_FUNDAMENTAL`), a janela não é um sinal
  de 60 Hz e os dois saem `None` — a tela mostra traço, e o hover dá a DC em
  unidade de engenharia, que é medida honesta em qualquer janela. As MEDIDAS
  (`fundamental`, `rms`, `dc`, `angulo`) nunca são suprimidas.
- **Componente simétrica só sai de um CONJUNTO trifásico identificado.**
  Somar `IA` de um TC com `IB` de outro dá um 3I0 sem sentido e com cara de
  número bom. `formats/conjuntos.py` agrupa pelo campo `ccbm` do arquivo
  quando ele vem preenchido (é para isso que a norma o criou) e, quando não
  vem, pelo resto do nome depois de tirar a **última** ocorrência da letra da
  fase — a última porque em `BARRA A` a fase é o segundo `A`. Sem A, B e C
  completos, zero conjuntos: dois terços da informação não autorizam mostrar
  um número.
- **Num relé de trafo há dois `IA`.** Correntes de alta e de baixa, na mesma
  unidade. Por isso o nome do sinal carrega o **apelido do conjunto**:
  `IA RMS AT`, `3I0 BT`. O apelido só aparece quando há mais de um conjunto da
  mesma grandeza — sufixo que não distingue nada é ruído.
- **`AT`/`BT` só se o arquivo disser o nível de tensão.** Quando os nomes
  trazem os kV, o maior é a alta e a dedução é segura. Quando não trazem
  (`IAW` e `IAX`, da SEL), o apelido sai do que **difere** entre os nomes —
  corta-se o começo e o fim comuns e o miolo distingue. Sai `W` e `X` sem o
  programa saber o que é enrolamento. **Nunca se inventa AT/BT**: inverter os
  lados num laudo é erro que só aparece tarde.
- **`3I0` é a SOMA, não a média.** É ela que circula pelo neutro e é ela que se
  compara com o ajuste do elemento de terra. `I0` obrigaria a multiplicar por
  três de cabeça toda vez.
- **Canal não é sinal.** O arquivo traz canais; a tela mostra sinais, que são
  derivados deles por uma operação conhecida. Um canal dá quatro: `IA`,
  `IA RMS`, `IA 60Hz`, `IA 60Hz RMS`. Cada um tem **nome próprio, montado no
  Python** (`plot/sinais.py`), porque é identidade e não rótulo: o mesmo nome
  vale na legenda, na tabelinha, no relatório e, mais adiante, na fórmula que o
  usuário escrever. Sem isso, "IA = 18,2 A" num relatório não diz se saiu do
  filtro ou não — e a diferença chega a 25 % numa falta assimétrica.
- **O filtro é do registro; a medida é de cada gráfico.** A chave `60 Hz` no
  cabeçalho vale para tudo (meia tela filtrada e meia não seria armadilha, e
  ela trava quando o relé já filtrou). O `instantâneo/RMS` fica no topo de cada
  gráfico e vale só para ele — corrente em RMS e tensão em instantâneo ao mesmo
  tempo é leitura comum numa falta. No servidor: `filtro` global e `medidas`
  por unidade do grupo.
- **Nada de `IA₁` para a fundamental.** No 0.4b `I1` é sequência positiva. Os
  dois usos do subscrito 1 convivem no ofício e se distinguem só pela letra de
  fase — uma letra carregando uma troca inteira de significado, com os dois na
  mesma tela. O nome explícito é mais longo e nunca é ambíguo. Gráfico em RMS com tabela em
  instantâneo seria a tela se contradizendo no mesmo instante. A tabelinha tem
  **sempre as mesmas três colunas** (cursor 1, cursor 2, 2−1) — largura que
  muda empurra o gráfico no meio de uma medição e a onda foge de debaixo do
  mouse. O que não cabe (ângulo, DC, distorção, e o instantâneo quando não é
  ele que está na tela) vai para o hover do valor.
- **`bruto` e `filtrado` são propriedade do ARQUIVO, não escolha da tela.** O
  botão do filtro diz em que estado está o sinal que se está vendo; quem
  filtrou aparece na tira de cima. Quando o relé já filtrou antes de gravar, o
  botão **trava em on** e nós NÃO filtramos por cima: filtrar duas vezes não
  limpa nada, só acrescenta mais um ciclo de atraso, e a falta passaria a
  aparecer dois ciclos depois de ter acontecido. Quem garante isso é
  `sinais.aplicavel(filtro, filtragem)`, consultado por `janela.montar` e por
  `leitura.em` — **no servidor**, para que nenhum pedido da tela (nem uma URL
  digitada à mão) consiga filtrar duas vezes.
- **Travar sobre palpite é pior que não travar.** O veredito só sai `filtrado`
  com evidência forte; na dúvida é `desconhecido` e o botão fica livre. Ver
  `analysis/filtragem.py`: o custo de não travar é o usuário filtrar duas vezes
  e ver o atraso; o de travar errado é ele não conseguir filtrar um registro
  que precisava.
- **As curvas de `fundamental`, `rms` e `filtrado` não mostram o INSTANTE da
  falta.** Elas
  levam um ciclo inteiro para subir, porque cada ponto é a janela que termina
  ali. Quem olhar só elas erra o início da falta em até um ciclo — **filtro off
  + instantâneo é a única das quatro vistas que dá a hora.** O primeiro ciclo do registro
  fica **sem curva**: não há janela antes dele, e um zero ali lê-se como "não
  havia corrente".
- **Taxa de amostragem é uma LISTA, nunca um número.** A norma permite vários
  trechos e o relé usa: grava a falta a 96 amostras/ciclo e o resto a 16, para
  o arquivo não ficar gigante. Quem calcula fasor, envoltória ou componente
  simétrica usa `Record.trechos`, nunca `base_rate_hz` — este último serve só
  para identificar o registro na tira e no acervo. **Nenhuma janela atravessa a
  fronteira entre dois trechos**: metade das amostras de um lado e metade do
  outro não é um ciclo de coisa nenhuma. O preço é o primeiro ciclo de cada
  trecho ficar sem curva, pela mesma razão que o primeiro ciclo do registro. E
  "andar um ciclo" com Shift+seta são 16 amostras num trecho e 96 no outro — a
  tecla é a mesma, a conta não.
- **Envoltória é soma móvel, nunca uma DFT por amostra.** Ver
  `dsp/envoltoria.py`: o expoente da DFT se parte em um fator que depende do
  cursor e outro que não, e o que sobra é uma soma móvel resolvida por soma
  acumulada. Uma passada pelo canal em vez de 48 milhões de multiplicações num
  registro de 500 mil amostras. Os expoentes usam `m % n` — sem isso o
  argumento do seno chega a milhões de radianos e a fundamental erra no fim do
  registro (há teste com 500 mil amostras).

## Para onde a tela vai (decidido em 20/09/2026)

O OscLab não é uma tela fixa com gráficos fixos. O rumo é **painéis que o
usuário compõe a partir de sinais**:

- **Ao abrir um registro**, aparecem por padrão: um gráfico analógico das
  correntes, um das tensões, e os **digitais que mudaram** ao longo do
  registro. Digital que ficou parado o tempo todo não conta nada e não ocupa
  tela.
- **Depois**, o usuário cria novos diagramas — analógicos e fasoriais —
  acrescenta e remove sinais de cada um dinamicamente, e monta a análise dele.
- **Por fim**, uma calculadora cria sinais novos a partir dos existentes.

Três consequências para quem programa isto:

1. **Sinal é a unidade, não canal.** Já vale hoje (`plot/sinais.py`): `IA` e
   `IA RMS` são sinais diferentes, com nome próprio, derivados do mesmo canal.
   Componente simétrica é sinal derivado de três canais. A calculadora vai
   produzir mais.
2. **Nada entra num gráfico automaticamente porque o programa calculou.** As
   componentes simétricas NÃO são despejadas no gráfico das correntes — o
   usuário as acrescenta onde quiser. Decidido em 20/09/2026, depois de eu
   propor o contrário.
3. **O casamento tabela × leitura vai ser por identificador de sinal**, não por
   índice de canal: componente e sinal calculado não têm índice no arquivo.

## Decisões já tomadas — não reabrir sem conversar

| Assunto | Decisão |
|---|---|
| Linguagem | Python; interface HTML/CSS/JS em localhost |
| Servidor | Flask |
| Gráficos | **canvas próprio, sem biblioteca de front-end** (decisão de 18/09/2026: nada a baixar, nada que envelhece, manutenção só nossa) |
| Distribuição | v1 exige Python instalado; `.exe` é possibilidade futura |
| Repositório | GitHub público: **github.com/alexandrebuenof/osclab** |
| Licença | AGPL-3.0-or-later; direitos da distribuidora |
| Formatos | COMTRADE é a base; depois SEL `.CEV`; PL4 para validar algoritmos |

## Detalhes que já custaram caro (não redescobrir)

- **Servidor velho com tela nova.** Os `.py` só são lidos quando o programa
  SOBE; o `.js` o navegador recarrega sozinho. Trocar de versão sem reiniciar
  deixa a tela nova conversando com o servidor velho — e o resultado não é
  erro, é uma tela plausível e errada (campo que falta vira `undefined`, e
  `undefined` na tela não parece defeito, parece dado). Custou três rodadas de
  "não vi a mudança". Agora o pacote da janela traz `contrato` e a tela compara
  com o dela: se não baterem, ela para e manda reiniciar o `osclab.cmd`.
  **Suba `CONTRATO` nos dois lados sempre que o formato do pacote mudar.**
- **`<select>` não avisa quando se escolhe o que já estava.** Sem evento
  `change`, a listinha da correção de fase ficava aberta para sempre no lugar
  da etiqueta do vínculo: quem abriu o lápis, olhou e escolheu "automático" —
  que já era o estado — perdia a etiqueta de vista e achava que o canal tinha
  deixado de ser reconhecido. O `blur` devolve a etiqueta, tendo mudado ou não.
- **Botão aceso não é pedido.** O botão do filtro travado punha `filtro = true`
  na tela; o primeiro desenho saía certo (a tela ainda não sabia do travamento)
  e o SEGUNDO — qualquer recarga, como a do botão de nomes — já ia com
  `filtro=1` e o servidor filtrava por cima do que o relé já tinha filtrado. Um
  ciclo de atraso em tudo que se lê, sem aviso nenhum, e só aparecia depois de
  um clique em outro botão. O estado do SINAL e o PEDIDO da tela são coisas
  diferentes e agora estão em variáveis diferentes (`aceso` × `filtro`), com a
  recusa repetida no servidor.
- **A fábrica de testes gerava ACB.** `_senoides` defasava as fases de `+120°`,
  o que põe B ADIANTADA de A — sequência negativa. Todo registro sintético
  tinha, portanto, 100 % da corrente em `I2` e zero em `I1`, e qualquer
  conferência de componentes simétricas contra ele sairia de cabeça para baixo
  **sem dar erro nenhum**. Descoberto ao pôr I1/I2 na tela pela primeira vez.
  O teste `test_equilibrado_em_abc_poe_tudo_na_positiva` é o que impede a
  volta.
- **Senoide pura é, pelo critério do detector, um sinal já filtrado** — e com
  razão: não há harmônico nenhum nela. Por isso os testes do filtro declaram
  `Filtering.BRUTO` no registro sintético (`_cru`, em `tests/test_plot.py`);
  sem isso, eles pedem ao servidor que filtre o que ele corretamente recusa.
- Para saber se já se está dentro do venv, comparar `sys.prefix` — **não** os
  executáveis. O `python` do venv é link simbólico para o interpretador base, e
  a comparação ingênua dá falso positivo.
- No Windows, re-executar com `subprocess.call` (recebe lista, faz quoting) e
  não com `os.execv`: o caminho do projeto tem espaço ("06 - Ferramentas").
- `requirements.txt` com referência PEP 508 (`nome @ git+...`): o nome do pacote
  é o que vem antes do `@`, senão o pip reinstala a cada boot.
- Só chamar o pip quando um `import` falhar, nunca para conferir versão: o
  usuário trabalha em subestação sem internet.
- Alinhar registros pelo instante da falta tem precisão de **uma amostra** —
  11° a 32 amostras/ciclo. Serve para olhar, não para calcular fasor.
- Arquivo órfão **não se recusa**. O usuário solta o `.cfg` e depois o `.dat`,
  em envios separados; quem chega sozinho fica na *antessala*
  (`library/_aguardando/`) até o par aparecer. Recusar o órfão foi o primeiro
  bug relatado em uso real.
- `DC 5.484,9 %` num registro real: depois de o disjuntor abrir, o canal ficou
  com 0,15 A de offset do conversor A/D e 0,0028 A de fundamental. A conta
  estava certa e a informação era lixo — quem lesse aquilo procuraria um
  defeito que não existe. Daí a guarda acima. A lição geral: **antes de dividir,
  perguntar se o denominador é medida ou é ruído.**
- **Transitório não serve para medir distorção.** Uma janela de um ciclo que
  pega uma mudança de amplitude não é senoide, por mais filtrado que o sinal
  esteja: num degrau de 60 Hz PURO a distorção aparente chega a 189 %, igual à
  de uma falta bruta. Foi isso que derrubou a primeira ideia de detector, e é
  por isso que `analysis/filtragem.py` mede só onde a amplitude está parada.
  Ali a separação é de 500×: 0,004 % num sinal filtrado com ruído de 16 bits
  contra 2,2 % num registro real de distribuição.
- `SampleRate.last_sample` do COMTRADE conta em **base 1 e é inclusivo**;
  `Trecho` usa base 0 com fim exclusivo. A tradução mora num lugar só
  (`Record.trechos`) de propósito: errar esse `+1` desloca a janela do fasor em
  uma amostra — 18° a 20 amostras por ciclo — e nada na tela denuncia.
- Gerar onda sintética com uma taxa e carimbar com outra faz o arquivo de teste
  **mentir sobre si mesmo**, e o teste passa a testar a mentira. Na
  `tests/fabrica.py` os carimbos e a própria senoide saem do mesmo vetor de
  instantes.
- **JavaScript novo com HTML velho em memória** é o acidente mais provável
  deste projeto: o Flask compila o template uma vez por processo, então trocar
  de versão sem reiniciar o servidor deixa o `.js` novo procurando elementos
  que o `.html` em memória não tem. Aconteceu de verdade em 19/09/2026: o
  `getElementById("filtro")` devolveu `null`, a exceção matou o script inteiro,
  e a página ficou em "Carregando o registro…" para sempre. Daí duas defesas:
  todo acesso a controle do cabeçalho usa `?.`, e há um tratador de `error`
  global que troca o "carregando" eterno por uma frase que manda reiniciar o
  servidor. **Um "carregando" eterno é o pior aviso de erro que existe.**
- Trocar o modo da tabelinha muda a LARGURA do gráfico (`valor` tem uma coluna
  por cursor, os outros dois têm duas, e o CSS reage sozinho à classe
  `mini-duplo`). O canvas não reage: ele continuaria desenhado na largura
  antiga, passando por baixo da tabela. Por isso `trocarModo` pede a janela de
  novo quando entra ou sai do modo de duas colunas — foi assim que o modo fasor
  do 0.4a apareceu quebrado na primeira vez que o Alexandre clicou nele.
- A rota da janela devolve a janela **pedida**, não o instante da primeira e da
  última amostra dentro dela. A tela manda esses números de volta no gesto
  seguinte; arredondar para a amostra mais próxima a cada ida e volta encolhia a
  janela uma amostra por gesto, e o desenho escorregava sozinho.
- **A leitura é uma tabelinha por gráfico, ao lado dele** — só os canais
  daquele gráfico, sem moldura própria. Por cima da onda esconderia o trecho em
  análise; num painel único e alto vira uma coluna de números longe do gráfico
  de que falam.
- **A tabelinha só existe enquanto houver cursor na tela.** Sem cursor ela não
  diz nada e rouba largura da onda. Abrir e fechar estreita e alarga o gráfico,
  então nesses dois instantes — e só neles — se pede a janela de novo, porque o
  número de colunas de pixel mudou. Durante a medição a largura fica parada: a
  tela não pode se mexer com o cursor já posto.
- **As casas decimais seguem a ordem de grandeza** (`leitura.casas`), mirando
  **cinco dígitos significativos**. Uma casa fixa erra dos dois lados: sobra em
  `6743,2 A` de falta e falta em `0,3 A` de corrente de fuga. Cinco dígitos e
  não quatro porque o arredondamento é pior no começo de cada década: com
  quatro, `10,0` erra 0,5 % — a mesma ordem do erro do próprio relé, e a tela
  não pode contribuir tanto quanto o instrumento. Com cinco, 0,05 %.
- **A resolução real de uma amostra é o fator `a` do canal**, declarado no
  `.cfg`: os valores são múltiplos dele, não existe nada entre dois. Em
  primário esse passo é multiplicado pela relação de TC/TP — com 600/5, um
  degrau de 0,01 A vira 1,2 A. Hoje o leitor aplica `a` e o descarta; guardá-lo
  no canal permitiria limitar as casas ao que o conversor de fato produziu.
- **As casas decimais do tempo vêm do intervalo entre amostras**
  (`leitura.casas_do_tempo`), não de um número fixo. A 1200 Hz duas amostras
  distam 0,833 ms: `225,000 ms` promete microssegundo que não existe, e ainda
  trunca na coluna. A regra devolve a menor quantidade de casas em que duas
  amostras vizinhas ainda saem diferentes.
- **A última linha da tabelinha é o tempo, e o rótulo dela é o botão da
  unidade** (`t (ms)` ⇄ `t (ciclos)`). A unidade fica no rótulo e nunca nas
  células: assim a linha inteira converte junto e o que está escrito à esquerda
  vale para os três números. A escolha fica guardada no navegador.
- **O prefixo `k` é do REGISTRO, não do valor** (`plot/unidades.py`). Escolher
  pelo número mostrado faria a unidade mudar enquanto o cursor anda e o eixo
  trocar de `kA` para `A` ao ampliar a pré-falta — unidade que pisca é pior que
  número comprido. Decidido uma vez por grupo, pelo maior valor absoluto do
  registro inteiro naquele lado; vale para o eixo e para a tabelinha, que
  chamam a **mesma** função.
- **O limiar do prefixo é 10 000, não 1 000.** `6743 A` cabe e se lê de
  imediato; `6,743 kA` é o mesmo escrito pior. E um arquivo que já declara `kA`
  não vira `kkA`: só `A` e `V` ganham prefixo.
- **Não se calcula frequência a partir do intervalo entre cursores.** `1/Δt`
  engana duas vezes: lê-se como "a frequência do sistema na falta", e a precisão
  não sustenta — a 20 amostras/ciclo, uma amostra são ±5 % de um período, ou
  ±3 Hz. Frequência medida exige muitos ciclos e implementação própria.
- O roxo que parecia a cor óbvia para o cursor ficava a **ΔE 3,6 do azul da
  fase A sob protanopia** — o validador de paleta pegou; o olho não pegaria.
- O servidor Flask **compila o template uma vez por processo** fora do modo
  debug: mexeu no `.html`, reinicia, senão se depura um HTML que não existe
  mais.
- **A etiqueta numerada do cursor fica ACIMA da moldura, fora da área de
  desenho.** Por dentro ela tapava a crista da onda justamente quando se põe o
  cursor no pico para medir amplitude. Por isso `MARGEM.topo` é maior do que
  parece necessário — é o espaço dela.
- **Resposta atrasada não corrige posição que a mão está segurando.** Os pedidos
  de leitura são engargalados (um em voo por vez), então a resposta é de alguns
  milissegundos atrás. Aplicá-la durante o arrasto puxava o cursor para trás —
  um cabo de guerra entre a mão e a rede. Enquanto se arrasta, a linha é da mão;
  o encosto na amostra acontece ao soltar.
- Com `setPointerCapture`, o navegador passa a entregar os eventos ao elemento
  que capturou: `evento.target` deixa de ser o canvas no meio do arrasto. Medir
  pelo alvo do evento dava deslocamento zero — o arrasto não saía do lugar.
- Um `.dat` de OUTRO registro pode **dividir certinho** no layout errado (7A/9D
  = 24 bytes por amostra; 3A/4D = 16 — 240 bytes cabem nos dois). A prova de que
  o par confere é a **coluna do número da amostra ser crescente**, não o tamanho
  do arquivo.

## Marcos

| | Entrega | Estado |
|---|---|---|
| 0.1 | Esqueleto que roda | **feito** |
| 0.2 | Leitor COMTRADE + modelo interno | **feito** |
| 0.3a | Acervo de arquivos na interface web | **feito** |
| 0.3b | Formas de onda: desenho estático | **feito** |
| 0.3c | Zoom e arrastar | **feito** |
| 0.3d | Dois cursores com leitura de valor | **feito** |
| 0.3e | Canais digitais — só os que mudaram, na ordem em que mudaram | **feito** |
| 0.3f | Alternar primário/secundário na tela, com prefixo k | **feito** |
| 0.4a | Fasor e RMS no cursor | **feito** |
| 0.4a+ | Curvas de fundamental e RMS no gráfico | **feito** |
| 0.4a++ | Filtro on/off, onda de 60 Hz, detecção bruto × filtrado | **feito** |
| 0.4a+++ | Taxa múltipla de amostragem tratada trecho a trecho | **feito** |
| 0.4b | Componentes simétricas (3V0/3I0) | **feito** — entram na tela pela mão do usuário, pelo catálogo, nunca automaticamente |
| 0.4b+ | Catálogo de sinais (IED × OscLab), segundo eixo, vínculo canal→fase corrigível | **feito** |
| 0.4b++ | Selecionar sinal por clique, tirar da tela, desfazer | **feito** |
| 0.4c | Harmônicos | |
| 0.5 | Bruto/filtrado, descontinuidade, alinhamento | |
| 0.6 | Localização de faltas (um e dois terminais) | |
| 0.7 | Mini relatório | |

### Testes com arquivos reais

Os registros reais do parque **não entram no repositório** (identificam
instalação, data e comportamento da rede, e o repositório é público). Os testes
sintéticos de `tests/test_comtrade.py` cobrem o leitor com resposta conhecida;
`tests/test_comtrade_reais.py` roda contra os arquivos de verdade e fica
desligado até alguém apontar onde eles estão:

```
set OSCLAB_AMOSTRAS=C:\Users\alexa\Documents\06 - Ferramentas\Oscilografias
python app.py --testes
```

### O gabarito: comparar com o SIGRA

O Alexandre usa o **SIGRA** (Siemens) no dia a dia e ele é a referência para
validar os números. O jeito de conferir: abrir o mesmo registro nos dois, pôr o
cursor no mesmo instante, clicar no mesmo canal para ser a referência e comparar
linha a linha.

Convenções do SIGRA já decifradas a partir de um registro real:

- **"Fundamental"** é o valor eficaz da componente fundamental.
- **"Extremum"** é o pico instantâneo real da janela — maior que o pico da
  fundamental quando há componente DC.
- **"DC %"** é relativa à fundamental eficaz, e o SIGRA a mostra **em módulo**;
  nós mostramos com sinal. Os módulos batem nos oito canais.
- Clicar num valor faz aquele canal virar **0°**; os demais giram junto.

#### Caso conferido — registro `26.09.05 12.39.30.248`, cursor em 214,2 ms

Validação completa de 19/09/2026, na região de **pré-falta** (escolhida de
propósito: nada muda rápido ali, então meia amostra de erro no cursor não
estraga a comparação). Referência angular: `Current IA`.

| canal | \|F\| SIGRA | \|F\| nosso | ∠ SIGRA | ∠ nosso | DC SIGRA | DC nosso |
|---|---:|---:|---:|---:|---:|---:|
| Current IA | 1,0179 | 1,018 | 0,0° | 0,0° | 2,1 | −2,1 |
| Current IB | 0,9892 | 0,9892 | −119,5° | −119,6° | 1,5 | −1,5 |
| Current IC | 0,9874 | 0,9873 | 121,2° | 121,1° | 2,4 | −2,4 |
| Current IN | 0,0257 | 0,0257 | −9,9° | −10,0° | 15,9 | 16,0 |
| Voltage A-G | 67,932 | 67,93 | −169,8° | −169,8° | 0,1 | −0,1 |
| Voltage B-G | 68,114 | 68,11 | 70,4° | 70,4° | 0,0 | 0,0 |
| Voltage C-G | 68,136 | 68,14 | −49,6° | −49,7° | 0,0 | 0,0 |
| Voltage VNG | 0,0346 | 0,0346 | 143,7° | 143,6° | 1,9 | 1,9 |

Erro máximo: **0,1°** e o último dígito do módulo — arredondamento de tela.
RMS verdadeiro conferido também, contra a reconstrução pelas harmônicas que o
próprio SIGRA lista (1,019 · 0,9898 · 0,9883 · 0,0266 · 67,93 · 68,12 · 68,14 ·
0,0372).

O que isto prova, e que nenhuma mudança futura pode quebrar: a janela de um
ciclo **termina no cursor**, a `fundamental` é **eficaz**, a DFT gira no mesmo
sentido do SIGRA (um sinal trocado no expoente espelharia todos os ângulos), e a
DC fecha em módulo.

**Como conferir com o SIGRA sem se enganar.** O ângulo do SIGRA usa a
referência interna dele, e o nosso usa o canal que se clicou — comparar os
ângulos direto não diz nada. Comparam-se as **diferenças** entre canais, que é
uma conferência mais forte, porque não depende de nenhuma das duas referências.
E antes de comparar qualquer fasor, garantir que os dois cursores estão na
**mesma amostra**: o instantâneo de cada canal é a impressão digital da amostra
(modo `valor` aqui, coluna *Instantaneous* lá). No transitório, uma amostra de
diferença muda a DC em vários pontos percentuais — foi o que produziu uma
divergência de 75 % na `Current IA` em 233 ms, e não era bug nenhum.

### Esquisitices que os arquivos reais revelaram

- **Schneider MiCOM P139** escreve `2001` no campo da edição — que não é edição
  nenhuma da norma. Lido assim mesmo, com aviso.
- **GE 850** não declara taxa (`nrates = 0`); o tempo vem do carimbo de cada
  amostra. E grava o `.cfg` com fim de linha do Unix.
- **Schneider** não escreve a linha do `timemult`.
- **SEL-TWFL** fecha o `.dat` com 64 bytes `0x1A` (fim-de-arquivo do DOS). Sobra
  de bytes no fim não é erro.
- **SEL-487E** tem 5760 canais digitais: a matriz de estados fica com dezenas de
  MB. Se virar problema, desempacotar sob demanda.
- Nomes de subestação com acento vêm em **cp1252**, não UTF-8.
- **Siemens SIPROTEC** deixa o campo `ph` (fase) VAZIO e escreve a fase no fim
  do nome do canal ("TC BUC 69kV:I A"). Para componentes simétricas (marco 0.4)
  vai ser preciso deduzir a fase do nome quando o campo não vier preenchido.
- Alguns registros trazem o disparo na **amostra 0**, sem janela de pré-falta —
  a detecção por grandezas delta (marco 0.5) precisa tratar esse caso.

## Contexto completo

`docs/` traz a íntegra: requisitos funcionais, o backlog de ideias do Alexandre,
e a análise da PAC CT, que é a ferramenta usada como referência de arquitetura.
