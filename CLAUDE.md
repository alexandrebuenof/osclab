# OscLab — instruções para o Claude

Leia este arquivo antes de mexer em qualquer coisa. Ele é lido automaticamente
pela extensão do VS Code a cada sessão.

## Quem é o usuário

Alexandre, engenheiro de proteção numa distribuidora de energia. Fala português.
Conhece proteção de sistemas elétricos a fundo; está aprendendo programação e
Git agora. Parque de IEDs da empresa: SEL, Siemens, GE, ABB, Schneider, Ingeteam
e NOJA.

## O leitor é universal (decidido em 25/10/2026)

O OscLab tem que servir a **qualquer relé**, inclusive um modelo que nunca
abrimos — o de outra distribuidora, o de um fabricante que nunca vimos.
Abrir, desenhar e analisar não dependem de reconhecer o fabricante. O que o
arquivo não disser (ajuste, relação, fase, trinca) vira **campo para
digitar**, nunca barreira. Os relés do parque da Energisa MT ficam mais
otimizados — mais coisa lida sozinha —, mas nada específico deles pode virar
condição para uma função existir. Ao escrever ou revisar código: todo ajuste
lido por nome de fabricante é um ATALHO com o caminho manual ao lado, e a
tela diz a origem (lido, digitado, sugerido).

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
6. **Dez maquetes antes de implementar coisa nova** *(decidido em 19/10/2026)*.
   Antes de escrever o código de uma função nova, entregar **dez maquetes
   funcionais, com dados fictícios**, mostrando como o programa se comportaria
   com ela. Funcionais quer dizer que se clica e se vê o resultado — não
   desenho parado —, e os dados fictícios existem para a maquete mostrar os
   casos difíceis (o canal sem sinal, o nome comprido, a falta que satura o
   TC) sem depender de achar um registro que os tenha. Dez porque a terceira
   ideia raramente é a melhor, e porque é olhando a quinta ao lado da nona que
   ele decide. Ajuste pequeno e correção de defeito não precisam de maquete.

## Versionamento — decidido pelo Alexandre em 12/10/2026

`X.Y.Z`, e quem decide o dígito é o TAMANHO da mudança:

| dígito | quando | exemplo |
|---|---|---|
| `Z` — último | detalhe: um ajuste de tela, um texto, um bug pequeno | o rótulo da régua, o botão do modo sem destaque |
| `Y` — meio | função nova | o diagrama fasorial inteiro → `0.5.0` |
| `X` — primeiro | mudança muito grande | lançar a ferramenta para o público → `1.0.0` |

**E o `Z` só sobe quando o Alexandre aprova a rodada, não a cada ajuste.**
Ele pede um detalhe, eu implemento e mostro; ele pede o seguinte, eu
implemento e mostro. A versão sobe UMA vez, no fim, quando ele disser que
está bom — senão a lista de marcos vira uma linha por clique e nenhuma delas
conta nada.

Até a aprovação, o que muda é só o código: `VERSION` e a tabela de marcos
ficam como estão.

## Onde o trabalho parou

Antes de começar qualquer coisa, leia **`docs/estado-do-trabalho.md`**: o ponto
exato em que a última rodada parou, a fila do que vem depois e as pendências
conhecidas. O registro completo das discussões vive no projeto "Leitor de
Oscilografia" no Claude; o `docs/` é a cópia versionada do que pode ser
público.

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

**O Claude faz o commit** (decidido pelo Alexandre em 25/10/2026; antes era
ele quem fazia). Antes de cada commit o Claude confere o `git status`: nada
de `docs-privados/`, `config/config.ini`, acervo (`library/`) ou oscilografia
real pode entrar — o repositório é público. A suíte tem de estar passando.
A mensagem diz o que mudou e por quê, em português. O **`git push`** publica
no GitHub, e esse continua pedindo a confirmação do Alexandre.

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
├── tools/paleta.py        valida a paleta de cores (ΔE2000, daltonismo)
├── data/  samples/  docs/  tests/
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
- **O gráfico é um PAINEL, e a lista de painéis é da TELA.** Um painel é
  `{id, tipo, nome, sinais, medida}` (ver `plot/paineis.py`): a tela manda a
  lista inteira no corpo do pedido e o servidor desenha o que veio, na ordem em
  que veio. Ele não guarda arranjo nenhum — abrir de novo o mesmo registro
  recomeça no padrão. O `padrao()` (um painel por unidade do arquivo mais um
  com os digitais que mudaram) é só o ponto de partida, e é o que sai quando a
  tela ainda não tem arranjo: na PRIMEIRA janela, que é um GET.
- **O arranjo vai no CORPO do pedido, nunca na URL.** As duas rotas atendem
  `GET` e `POST`. Arranjo é estrutura — lista de painéis, cada um com a lista
  de sinais dele —, nome de gráfico tem vírgula e acento, e URL tem teto de
  tamanho. Empacotar isso numa `query string` seria inventar um formato só para
  ter que desfazê-lo do outro lado.
- **Nome e ordem são rótulo e arrumação: não passam pelo servidor.** Renomear e
  reordenar são instantâneos, sem ida e volta, porque não mudam número nenhum.
  A exceção é o nome que o SERVIDOR deu: enquanto `do_padrao` estiver de pé, é
  ele quem escreve o nome, e por isso `Correntes (A)` vira `Correntes (kA)`
  quando se troca para primário. Renomear apaga a marca — a partir daí o nome é
  do usuário e o servidor devolve o que recebeu.
- **Painel digital é painel.** Poderia ser um bloco fixo no fim, como era; mas
  aí "mudar a ordem dos gráficos" não poderia pôr digitais ENTRE duas trincas
  de corrente — que é exatamente o que se quer olhando um religamento: a
  corrente, o trip, a corrente de novo.
- **Gráfico novo nasce com nome genérico** (`Gráfico analógico 2`), vazio, e
  com um texto dizendo como pôr sinal nele. Obrigar a batizar um gráfico antes
  de ver o que tem dentro é pedir decisão na hora errada.
- **A leitura do cursor casa por ID DE SINAL, nunca por posição.** Com painéis,
  o mesmo canal pode estar em dois gráficos com medidas diferentes: posição
  deixou de identificar coisa nenhuma. `cursor["sinais"]` é um dicionário
  `id → linha`, e a leitura só responde o que ALGUM painel pediu — tela vazia,
  tabelinha vazia.
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
  do registro, sai da LISTA DE SINAIS do painel (e por isso vai ao servidor: a
  escala vertical depende de quem está desenhado), e volta pelo `+ sinal`, na
  aba IED, onde aparece desmarcado. O painel continua existindo mesmo ficando
  vazio: é dele que sai o botão que traz o canal de volta.
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
- **Tabela e traço têm a MESMA cor, por construção.** A tabelinha pintava pela
  fase, com classe de CSS, e o desenho por `corDoSinal` — as componentes
  simétricas saíam coloridas no gráfico e cinzas na tabela. Hoje os dois
  chamam a mesma função. Duas implementações da mesma decisão é como elas
  divergem, e aqui a divergência é justamente a pista que liga o número ao
  traço.
- **O ímã põe o cursor num ponto NOTÁVEL, e nunca interpola.** Com ele aceso
  (o botão de ferradura no cabeçalho), os cursores 1 e 2 grudam no ponto
  notável mais próximo — sempre numa amostra de verdade, pela mesma razão que o
  cursor sempre cai numa amostra. Fora do raio (14 px) ele não age: cursor que
  salta para um ponto que ninguém estava mirando é pior que cursor solto. São
  os cursores de sempre; não há cursor novo.
- **QUEM decide em que o ímã gruda é o usuário, na setinha ao lado dele**:
  transições de digital, início da falta, picos de analógico (a crista **e** o
  vale — o pico negativo de uma corrente é tão pico quanto o positivo) e
  passagens por zero. **Só as transições vêm ligadas** — é o ponto que serve à medida
  mais comum do ofício e o único que nunca é ambíguo; tela que já vem com tudo
  ligado é tela em que o cursor gruda onde ninguém pediu. A escolha fica
  guardada no navegador. A última opção ligada fica **travada, visível e com a
  explicação no hover** — a primeira versão desmarcava e remarcava em silêncio,
  e clique que não faz nada sem dizer por quê é pior que clique proibido (além
  de impedir trocar de "só A" para "só B").
- **A passagem por zero é a AMOSTRA MAIS PRÓXIMA do cruzamento.** A passagem
  verdadeira quase nunca cai numa amostra: a 16 por ciclo ela cai, em média, a
  um terço de amostra da vizinha. Interpolar daria um instante mais exato no
  papel e um cursor apontando para onde não há medida. Das duas que cercam o
  cruzamento fica a que está mais perto do zero. Curva que não muda de sinal
  (uma envoltória de RMS) não tem passagem nenhuma, e a lista sai vazia.
- **Com seleção, o ímã só obedece ao que foi selecionado. Sem seleção, os
  EVENTOS do registro ganham dos picos — por existirem dentro do raio, não por
  estarem mais perto.** A ordem importa porque um pico é de UMA curva e há dois
  por ciclo: numa janela de quarenta e cinco ciclos com seis canais são
  quinhentos e quarenta pontos, e qualquer lugar onde se ponha o mouse tem um
  pico a meio pixel — numa disputa por distância o trip nunca ganharia.
  Transição e início da perturbação são poucos, e cada um é um lugar onde
  alguém quer medir. Longe de qualquer evento os picos voltam a valer (medir
  amplitude na pré-falta), e dentro do raio de um evento eles se alcançam
  selecionando a curva — que é o gesto de "onde foi o pico da tensão".
- **O ímã DIZ no que grudou.** A etiqueta sai ao lado do número do cursor, e só
  no cursor ativo (duas etiquetas a nove pixels uma da outra não se leem). É a
  resposta à única dúvida que o ímã cria: com dois pontos próximos, ele pega um
  e sem isso escrito ninguém sabe qual — e o número que sai dali vai para o
  laudo. Empate exato é desempatado por precedência fixa (transição, início,
  pico), nunca pela ordem da lista.
- **O início da perturbação é PALPITE, e serve só para pôr o cursor.** Sai da
  grandeza incremental (`x[n] − x[n−N]`, um ciclo atrás): em regime permanente
  um ciclo é igual ao seguinte e a diferença é quase zero; quando a rede muda
  de estado, ela salta. **Não é a derivada simples** — essa é grande em toda
  passagem por zero de uma senoide saudável, e o limiar teria que ficar acima
  da inclinação normal da onda. O limiar sai da **mediana de `|d|` do registro
  inteiro**, que é estimador honesto aqui por um motivo de domínio: `d` é perto
  de zero na pré-falta, **durante a falta sustentada** e no pós-falta — ele só
  é grande nas transições, que são breves. O detector de perturbação de
  verdade continua sendo o marco 0.5.
- **O DISPARO DO RELÉ NÃO ENTRA NESSA CONTA.** O relé dispara *por causa* da
  falta: o início dela está no trecho de pré-falta, sempre.
- **Um gráfico NUNCA repete cor.** Duas curvas da mesma cor no mesmo eixo não
  se distinguem — e era o que acontecia com `Current IA` e `Voltage A-G` no
  mesmo painel, porque as duas são fase A. A cor é decidida para o painel
  inteiro de uma vez (`coresDoPainel`), nesta ordem: a escolha do usuário
  manda e é reservada primeiro; um canal fica com a cor da fase dele se ela
  estiver livre; todo o resto pega a primeira cor NEUTRA livre — e as neutras
  estão ordenadas por **croma**, da mais viva para a mais apagada, com o cinza
  em último: quem chega primeiro merece a cor que mais se separa do fundo e
  das vizinhas. Há teste que mede o croma e confere a ordem. **Cor de fase
  nunca entra por sobra**: ela afirma de que fase o sinal é, e um sinal que a
  vestisse por falta de opção estaria mentindo. Passando de dez sinais as
  cores repetem — cor que se separa de outras nove sob daltonismo é recurso
  escasso, e a legenda sempre nomeia o sinal.
- **A paleta é validada, e o validador está no repositório.** `tools/paleta.py`
  confere ΔE2000 entre todos os pares, em ambos os temas, sob visão normal,
  protanopia, deuteranopia e tritanopia, mais o contraste contra o fundo. Cor
  nova passa por ele antes de entrar no CSS; tritanopia entra como aviso, não
  como reprovação, porque a simulação dela por matriz linear é grosseira. Há
  teste que impede o validador e o CSS de divergirem.
- **Sinal no segundo eixo NÃO é tracejado.** Era, como aviso de que a altura
  dele não se compara com a dos outros. Saiu quando as cores passaram a ser
  únicas: a cor já separa as curvas, e o tracejado gastava a única variação de
  traço que restava. O segundo eixo continua dito na legenda (`→ kV`), na
  unidade de cada linha da tabelinha e no próprio eixo.
- **Todo eixo escreve a sua unidade**, na folga de cima, menor e mais apagada
  que os números — a unidade é a legenda da medida, não uma medida. Vale para
  o eixo da esquerda e para o da direita.
- **A cor de um sinal pode ser escolhida, e a escolha é da TELA.** Quadrinho
  ao lado do sinal na janela do `+ sinal`, na parte do que já está no gráfico;
  clicar abre as cores em BOLINHAS — nome de cor não ajuda a escolher cor.
  Guarda-se o TOKEN (`--fase-a`), não o código, para a escolha acompanhar o
  tema claro e o escuro. Não vai ao servidor — cor não muda número nenhum —,
  entra no Ctrl+Z junto com o resto do arranjo, e some quando o sinal sai do
  gráfico: se ele voltar, volta na cor automática. As cores de fase estão na
  paleta de propósito: o padrão protege, a escolha é de quem analisa.
- **Toda linha da tabelinha diz a sua unidade, e a unidade nunca é o que
  corta.** Desde que um gráfico pode misturar sinais, a unidade deixou de ser
  dedutível do título: `81,67` numa linha de `V1` se lê como 81 V secundários
  quando são 81 kV primários — três ordens de grandeza, sem nada na tela
  denunciando. O nome encolhe com reticências; a unidade é `flex: none`.
- **O nome do ARQUIVO só aparece quando o sinal É o canal do arquivo.** Com o
  gráfico em RMS o traço não é mais `Current IA`: é `IA RMS`, que é conta nossa
  com um ciclo de janela em cima. Escrever os dois nomes lado a lado ali
  afirmava que a curva era a que o relé gravou. Na legenda e na tabelinha vale
  o `familia` do sinal — `canal` mostra o nome do fabricante mais a
  fundamental; `calculado` mostra só o nome nosso, e o canal de origem fica no
  hover. O aviso de TC/TP não segue essa regra: ele é sobre o CANAL, então
  aparece sempre que há índice de canal por trás.
- **Botão que acende e não faz nada é pior que botão travado.** Num painel só
  de componentes simétricas, o instantâneo/RMS não tem em que pegar — elas são
  fasor e já saem em eficaz —, e clicar nele trocava o rótulo da tabelinha de
  `valor` para `RMS` deixando os valores iguais: a tela afirmando uma mudança
  que não houve. O servidor manda `medida_aplicavel` em cada painel analógico
  e a tela trava o botão, visível e inerte, com a explicação no `title` — igual
  ao botão do filtro num registro que o relé já filtrou. **Painel vazio é a
  exceção**: ali não há contradição ainda, e travar um controle antes de haver
  conteúdo é dizer "não pode" sem ter por quê.
- **Os botões do painel pegam o canal do IED; não pegam o sinal do OscLab.**
  Um canal do IED (`c0:instantaneo`) é a amostra crua, e o filtro do cabeçalho
  mais a medida do painel existem para dizer o que fazer com ela: com o filtro
  ligado, `IA` vira `IA 60Hz`. Um sinal do OscLab (`v0:rms`, `q0:0:rms`) foi
  escolhido pelo nome, com a grandeza DENTRO do nome, e não muda de significado
  com um clique em outro lugar da tela. É o que permite `IA` e `IA RMS` no
  mesmo gráfico — a comparação que mostra o atraso de um ciclo do filtro. A
  tradução de (id pedido + filtro + medida) para o sinal que de fato se
  desenha é `catalogo.efetivo`, e ela é a MESMA no desenho e na leitura.
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
  fora. **A única exceção é o digital que a placa do relé não tem** (seção
  `[IOBOARDS]` do `.hdr` da SEL): um 487E-3 com placa de 8 entradas grava
  IN301–IN324 assim mesmo, com um contador de amostras em IN317–IN324. Fica
  fora da tela padrão e aparece riscado na busca, com o porquê
  (`formats/ajustes.digitais_sem_placa`, 24/10/2026).
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
- **O nome do sinal é o nome do CANAL**, como o relé o escreveu, mais o que o
  OscLab fez com ele: `IAW · RMS`, `TC BUC 69kV:I A · 60Hz`. Nenhum sinal se
  chama `IA` — o relé já nomeia os terminais dele de forma única, e um nome
  nosso por cima seria uma segunda nomenclatura para a mesma coisa.
- **O ordinal `[1]` só existe na componente de sequência**, que sai de TRÊS
  canais e por isso não tem nome de arquivo a herdar. Ele é a posição do
  conjunto dentro da grandeza, naquele arquivo, e vem sempre acompanhado da
  origem — os três canais que entraram na conta.
- **O programa nunca diz alta nem baixa, nem tendo o nível de tensão no
  nome.** Inverter os lados num laudo é erro que só aparece tarde. O ordinal
  não afirma nada, e quem precisa saber lê a **origem**: o rodapé do gráfico e
  a coluna da direita do OscLab dizem de que canais do arquivo aquilo saiu,
  com os nomes entre aspas.
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
  tela. — **feito**
- **Depois**, o usuário cria novos diagramas — analógicos e fasoriais —
  acrescenta e remove sinais de cada um dinamicamente, e monta a análise dele.
  — **feito para analógico e digital** (criar, reordenar, renomear, apagar,
  pôr e tirar sinais). **O fasorial entrou na 0.4.6** — em pu pelas bases
  de RTC/RTP, com o cursor e a referência angular escolhidos por painel
  (ver `plot/fasorial.py`). Falta o de Fourier.
- **Por fim**, uma calculadora cria sinais novos a partir dos existentes.

A ordem que ele pediu em 20/09/2026, depois dos painéis: **cursores magnéticos**
(ele explica), **gráfico fasorial**, **gráfico de Fourier** (com a DC como
*curva ao longo do tempo* — escolha dele entre as alternativas que ofereci),
**calculadora** e então uma etapa pesada de **comissionamento** contra outros
analisadores, incluindo a mesma oscilografia filtrada e não filtrada para
validar o nosso filtro. Ver `claude/ideias-do-alexandre.md`.

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
| **Ondas viajantes (TWFL)** | **Adiado, e de propósito.** O `.CFG` do SEL-TWFL abre e é lido como qualquer COMTRADE — e é só isso que se espera dele hoje. Ondas viajantes não se analisam com janela de um ciclo: a 10 kHz, o que interessa são as frentes de onda em microssegundos, não fasor, não RMS, não componente simétrica. Vai ganhar **um modo de oscilografia próprio**, no futuro. Enquanto isso, **não gastar conversa com ele** — nem em comissionamento, nem em rodada de SIGRA, nem em nada que cobre dele um número de proteção convencional. (Combinado com o Alexandre, e repetido por ele em 22/09/2026 porque eu tinha esquecido de anotar.) |

## Detalhes que já custaram caro (não redescobrir)

- **A falta vem ANTES do disparo, e todo sintético a injetava depois.** O
  detector de início de perturbação descartava qualquer candidato anterior ao
  disparo — achando que era ruído de pré-falta — e ainda calibrava o limiar
  numa janela que ia até o disparo. Nos testes sintéticos ele acertava em
  cheio; em registro de relé de verdade **não achava nada, nunca**, e quem
  reportou foi o Alexandre. A lição maior não é sobre o algoritmo: é que um
  sintético construído com a suposição errada confirma a suposição errada.
  Quando um detector depende de ONDE o evento está, o teste precisa varrê-lo
  por todo o registro — hoje há teste com a falta antes, em cima e depois do
  disparo.
- **`CONTRATO` é um número em DOIS arquivos.** Subir um e esquecer o outro
  aconteceu três vezes: a tela se recusa a desenhar e manda reiniciar o
  programa — aviso correto para um problema que não existe. Há teste que
  compara `plot/janela.py` com `onda.js`; ele falha no pytest em vez de no
  navegador.

- **`display: flex` num `<th>` tira a célula do cálculo de colunas.** Com
  `table-layout: fixed`, a largura vem da célula; virando contêiner flex ela
  deixa de ser `table-cell` e a coluna encolhe para o conteúdo — a primeira
  coluna da tabelinha caiu de 107 px para 43 px e o nome do sinal sumiu. O
  flex vai num invólucro dentro do `th`.
- **Campo que some do pacote não dá erro no navegador — dá tela errada.** A
  refatoração para painéis tirou `dados.digitais` do pacote e `ajustarMargem`
  continuou lendo: o resultado não foi exceção nenhuma, foi a margem esquerda
  parada no mínimo e TODO nome de digital cortado. Há teste agora
  (`test_a_tela_nao_le_campo_que_o_servidor_nao_manda`): ele varre os
  `dados.<campo>` e `medida.<campo>` de `onda.js`, fora dos comentários, e
  confere contra as chaves que as rotas devolvem.
- **`re.S` vale para o PADRÃO INTEIRO.** Tirar comentário de JavaScript com
  `re.sub(r"//.*|/\*.*?\*/", "", texto, flags=re.S)` come do primeiro `//` até
  o fim do arquivo, e o teste que depende disso passa sempre sem olhar nada —
  o pior tipo de teste. Duas passadas: bloco primeiro, depois `//[^\n]*`.
- **Nome repetido vira defeito, e no JavaScript ele vira defeito MUDO.**
  Aconteceu duas vezes. `medida` era o pacote da leitura dos cursores E o botão
  instantâneo/RMS dentro de `bloco` (hoje `botaoMedida`). Depois eu declarei um
  `encaixar(t, a)` para o ímã sem ver que já havia um `encaixar(texto, largura)`
  que corta nome de tira digital: declaração de função sobe e a última vence, o
  nome de toda tira virou `null` na tela, e nada deu erro. **Antes de declarar
  uma função nova, procure o nome no arquivo.**
- **Função referenciada e não definida é invisível até o clique.** A
  refatoração perdeu `alternarSelecao` — o JavaScript não reclama na carga, só
  ao clicar, e o sintoma que chega é "não consigo mais destacar um sinal". Se
  uma refatoração mexeu em muitos trechos, clique em cada gesto antes de
  entregar; o console não vai avisar sozinho.
- **Não pôr um alvo de APAGAR colado no alvo de ESCOLHER.** O × de tirar o
  sinal foi posto ao lado do nome na legenda e saiu: o nome é o alvo de
  selecionar, e dois botões a poucos pixels um do outro, com efeitos opostos,
  é o par que mais se erra. Tirar sinal é selecionar e apertar Delete, ou
  desmarcar no «+ sinal».

- **Script de remendo com uma substituição que falha no fim não escreve NADA.**
  Um `patch` de doze trocas levantou `AssertionError` na última e perdeu as
  onze anteriores — e o arquivo ficou com metade da refatoração, o que é pior
  que nenhuma. **Escreva o arquivo a cada passo**, ou verifique todas as trocas
  antes de escrever qualquer uma.
- **Nunca substituir uma região de arquivo por ÍNDICE de linha.** Uma troca por
  faixa apagou em silêncio o bloco de estado dos painéis que estava no meio
  dela, e o defeito só apareceu no navegador (`pedidoComLayout is not
  defined`). Casar por texto, sempre.
- **Quem digita num campo não está dando atalho.** O `keydown` global da página
  engolia os dígitos de quem renomeava um gráfico: teclar `1` punha um cursor
  na oscilografia e chamava `preventDefault`, e o nome "01" saía "0". O
  primeiro teste do handler é se o alvo é `INPUT`, `TEXTAREA` ou
  `contentEditable`.
- **`blur` dispara DENTRO do `replaceWith`.** Terminar a edição do nome por
  `Enter` trocava o campo pelo botão, o que tirava o foco, o que chamava o
  `terminar` de novo — "The node to be removed is no longer a child". Uma
  variável `pronto` resolve; `isConnected` não, porque no meio da troca o nó
  ainda está ligado.
- **Cor de sinal não sai de nada do id.** A cor dos calculados vinha do
  COMPRIMENTO do id, e `q0:0:rms` e `q0:2:rms` — um par que se põe junto o
  tempo todo — caíam na mesma cor: duas curvas indistinguíveis no mesmo
  gráfico, sem nada denunciando. Sai da posição entre os calculados daquele
  painel.
- **Teste que usa o acervo tem que trocar `paths` antes.** Rodar
  `tests/test_acervo.py` fora do pytest (sem a fixture que aponta
  `LIBRARY_DIR` para um diretório temporário) grava registros no acervo DE
  VERDADE — e já gravou. Se for rodar à mão, troque os caminhos antes.

- **Servidor velho com tela nova.** Os `.py` **e os templates `.html`** só são
  lidos quando o programa SOBE — o Jinja guarda o template compilado em
  memória, e o programa não roda em modo `debug`. O `.js` e o `.css`, sim, o
  navegador recarrega sozinho. Trocar de versão sem reiniciar
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
| 0.4b+++ | Painéis: criar, reordenar, renomear; cor única por gráfico; unidade nos eixos | **feito** |
| 0.4b++++ | Cursores magnéticos: transição de digital, pico e passagem por zero da onda, início da perturbação | **feito** |
| 0.4b+++++ | Resíduo no tempo (`IN`/`VN`), componente contínua, janela de um ciclo de TEMPO | **feito** — `0.4.2` |
| 0.4b++++++ | Comissionamento: testes contra o gabarito do próprio relé e contra o SIGRA | **feito** |
| 0.4b+++++++ | Grupos trifásicos nomeados (`G1`), editor de grupos, tela «canais» | **feito** |
| 0.4b++++++++ | Catálogo em matriz (linha por canal, coluna por conta), modo tradicional/avançado, apelido do registro e exportação | **feito** — `0.4.3` |
| 0.4b+++++++++ | O filtro empurra para o filtrado TUDO que está no gráfico (inclusive o escolhido à mão) e o catálogo marca o sinal desenhado; menus suspensos fecham pela setinha, que vira para cima quando aberto; `.js`/`.css` com `?v=` no link | **feito** — `0.4.4` |
| 0.4b++++++++++ | `IN`/`VN` com as mesmas colunas de um canal: `· 60Hz` (onda) e `· 60Hz RMS` (≡ `3I0`, pela linearidade da DFT); num `.CEV`, `IN · RMS` pela DFT; rodapé distingue resíduo filtrado | **feito** — `0.4.5` |
| 0.4c | **Diagrama fasorial**: painel novo, em pu pelas bases de RTC/RTP do arquivo (com a correção √3 do TP fase-fase, medida na pré-falta), cursor escolhido por painel, referência angular por painel (saiu da tabelinha das ondas), módulo e ângulo ao lado | **feito** — `0.4.6` |
| 0.4c+ | Fasorial: base do pu **editável** e com duas peneiras (par `x / 1` é relação, não nominal; na tensão a pré-falta tem que bater) — sem base utilizável, 1 pu é o maior fasor daquela grandeza no registro inteiro; botão da referência angular com menu; catálogo do fasorial com «ocultar sinais nulos» e os calculados em cor | **feito** — `0.4.7` |
| 0.4c++ | Fasorial: seta de comprimento MÍNIMO, tracejada, para o fasor pequeno demais não sumir no centro (canal sem sinal não ganha seta); «+ ao lado» põe um segundo diagrama na mesma linha, já no outro cursor; a base digitada passou a valer também no desenho | **feito** — `0.4.8` |
| 0.4c+++ | Fasorial: o diagrama ao lado nasce VAZIO e independente; referência angular com busca e sobre TODOS os sinais com fasor — inclusive os que não estão no diagrama (ela vai ao servidor, porque muda o que ele calcula); `G1` colado no nome no seletor | **feito** — `0.4.10` |
| 0.4c++++ | **Arrastar pelo título** muda a ordem dos gráficos; soltar um fasorial sobre outro põe os dois lado a lado; «+ ao lado» virou «+ diagrama ao lado»; a nota do pu diz de onde o número saiu sem depender do hover | **feito** — `0.4.11` |
| 0.4c+++++ | Um botão só, «+ adicionar gráfico», com o tipo no menu; arrastar exige ESCOLHER o gráfico antes, rola a tela perto da borda e marca o destino com linha tracejada; rodapé do grupo sem o «de» e presente também no fasorial | **feito** — `0.4.12` |
| 0.4c++++++ | Base do pu derivada da RELAÇÃO mais o secundário nominal (`120 / 1` → `600 / 5` e `13800 / 115`), conferida na pré-falta para a tensão; escolher o gráfico vale em qualquer parte vazia dele; linha de solta centrada no vão | **feito** — `0.4.13` |
| 0.4c+++++++ | Base do pu conferida contra a ORDEM DE GRANDEZA do que o registro mede: pega o par escrito em volt/ampère num canal gravado em kV/kA (corrige pelo prefixo) e o par que não é nominal de nada; «+ diagrama lateral» | **feito** — `0.4.14` |
| 0.4c++++++++ | O anel tracejado do fasorial passou a ser **1 pu** (era metade da escala, que não significa nada) e leva o nome escrito | **feito** — `0.4.15` |
| 0.4c+++++++++ | Fasorial com botão **sem escala | em pu**, sem escala por padrão (toda seta do mesmo tamanho: só o ângulo); fora de escala passou a ser **ponta vazada** (o tracejado não se via numa seta de 17 px); o número da escala encostou no círculo dele | **feito** — `0.4.16` |
| 0.4c++++++++++ | O 1 pu de uma componente de sequência passou a sair da FASE da trinca também no caminho sem placa (era o pico da própria componente: `V2` de 2 % enchia o círculo igual a um de 30 %) | **feito** — `0.4.17` |
| 0.4c+++++++++++ | **Uma régua por grandeza** no fasorial: o círculo vale tantos pu de corrente E tantos de tensão, cada um com o seu anel de 1 pu. Régua única era o erro de origem — numa falta a corrente vai a 8 pu e a tensão da fase com defeito a 0,35 pu, e cinco das seis setas travavam no centro. A seta travada virou **haste atenuada** (sólido até o módulo real, apagado o resto): a ponta vazada tinha 8 px e sumia. A legenda das réguas passou a ser desenhada DEPOIS das setas, com fundo e no quadrante mais vazio, para não ficar atrás de um fasor | **feito** — `0.4.18` |
| 0.4c++++++++++++ | Rótulo da régua enxuto (`1,5 pu (kV)`, sem «círculo = ») e encostado na borda quando não cabe; e a **pré-falta que confere a base derivada passou a sair do LADO DA TELA** — em secundário ela era comparada com o valor de primário do arquivo, 120× maior, e um RTP perfeitamente declarado caía no «maior do registro» | **feito** — `0.4.19` |
| 0.4c+++++++++++++ | A régua do fasorial passou a sair do **registro inteiro**, não do instante do cursor: a mesma corrente de carga ocupava metade do círculo na pré-falta e virava um toco na falta, sem nada ter acontecido com ela. Régua agrupada por **grandeza** e não pela unidade escrita (`kV` e `V` dividem uma só); degraus 4, 6 e 8 na escada; mínimo da seta de 0,15 para 0,20 | **feito** — `0.4.20` |
| 0.4c++++++++++++++ | Catálogo do fasorial igual ao analógico: a **cor do traço** nas linhas que já estão no diagrama (clicável, troca a cor) e o **símbolo da família** em cada linha — senoide para o que o relé gravou, `ƒx` para o que o OscLab contou | **feito** — `0.4.21` |
| 0.4c+++++++++++++++ | Catálogo do fasorial dobrado em **blocos** («Senoidais», «Calculados»), com o símbolo da família no cabeçalho e não repetido em cada linha; e a base do pu passou a mostrar TRÊS algarismos significativos — `0,07 kV` arredondava 0,0664 kV (66,4 V) e apagava justo a precisão que faz o pu valer | **feito** — `0.4.22` |
| 0.4c++++++++++++++++ | O botão do modo não fica mais destacado no «avançado»: destaque nesta barra quer dizer «ligado» (ímã, filtro), e o modo é uma chave de duas posições — o rótulo dele já diz em qual está | **feito** — `0.4.23` |
| **0.5** | **Diagrama fasorial fechado.** Painel próprio, em pu com uma régua por grandeza tirada do registro inteiro, base derivada do RTC/RTP e conferida contra o que o registro mede, cursor e referência angular por diagrama, diagrama lateral, arrastar para reordenar, e o catálogo em blocos | **feito** — `0.5.0` |
| 0.5+ | Marcar um sinal no catálogo já o manda para «já na tela», com a cor; e **a leitura do cursor passou a ser refeita quando a lista de sinais muda** — `carregar()` traz a janela e as séries, mas o pacote do cursor é outro pedido, e sem ele o sinal novo entrava sem módulo nem ângulo: só desenhava quando o usuário mexia o cursor | **feito** — `0.5.1` |
| **0.6** | **Painel de harmônicos.** Espectro em barras no instante de um cursor, em % da fundamental de cada sinal, com o THD das barras ao lado; janela de 1 ciclo (a do relé) ou do TRECHO entre os dois cursores, cortado em ciclos inteiros; só entra onda (canal e resíduo), o teto de ordens é o Nyquist da taxa e vai escrito, e o painel só se cria no modo avançado | **feito** — `0.6.0` |
| **0.7** | **Calculadora de sinais — domínio ONDA.** `([VAY] - [VBY]) / 1.732` vira um sinal novo, amostra por amostra, no bloco «Calculados» com as cinco colunas de um canal. Tem teclado de calculadora (operações, √2, √3, ÷√3, ÷3) e completa o nome do canal com Tab. Unidades conferidas, mas **nada é bloqueado** — a regra do projeto: A+A passa em A, V×A vira V·A, e A+V faz a conta assim mesmo, sem unidade e com ⓘ ao lado; só o que não se LÊ é erro (parêntese aberto, canal inexistente). A conversão de TC/TP vem ANTES da conta; divisão sinal÷sinal e produto entre sinais caem em «Outros» porque não são senoidais. A expressão é conferida pelo servidor enquanto se digita, para a gramática morar num lugar só. E o painel de harmônicos ganhou a mesma largura e o mesmo alinhamento do analógico | **feito** — `0.7.0` |
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

#### O arquivo sintético precisa PARECER de relé

A fábrica batizava os canais de `CH1`, `CH2`, `CH3`. O nome de um canal não é
enfeite: é de onde `formats/conjuntos.py` deduz a que equipamento o canal
pertence — tira a letra da fase do nome e junta quem sobrou igual. De `CH1`,
`CH2`, `CH3` sobram três nomes diferentes, nenhuma trinca fechava, e **todo
registro sintético exercitava um caminho que nenhum arquivo de relé percorre**.

Só apareceu quando a lista do OscLab passou a depender da trinca: treze testes
caíram de uma vez, e nenhum deles era sobre o que estava sendo mudado. Hoje a
fábrica escreve `IAW`, `IBW`, `ICW`, `IAX`, ... — sufixo alfabético a cada três
canais, como um relé nomeia terminais —, então `na=3` sai com uma trinca e
`na=6` com duas, que é um transformador.

### O que o primeiro comissionamento pegou (22/09/2026)

Na primeira vez que o `test_comissionamento.py` rodou sobre o acervo inteiro,
ele reprovou — e reprovou certo. Dois defeitos, os dois do tipo que não dá
erro na tela.

#### 1. Um `.CEV` do parque que o leitor não abria

O **SEL-787** escreve outra primeira linha:

    SEL-451, sem versão:    "FID","RID","SID",<soma>
    SEL-787, CEV_VER 2.0.1: "FID","CEV_VER",<soma>

A assinatura exigia a primeira forma, o `sniff` recusava e nenhum leitor
assumia o arquivo. O esqueleto dos dois dialetos é o mesmo — mudam três campos
do cabeçalho (`REC_NUM`/`NUM_CH_A`/`NUM_CH_D` no lugar de
`EVENT_NUM`/`LOCATION`/`SER_NUM`) e o 787 não traz `SID`, então a estação fica
vazia, que é o honesto.

A assinatura lista os dois dialetos **na mão**, e não um `"FID",.*`: um `sniff`
que assume demais sequestra arquivo dos outros leitores, e o erro aparece longe
dali — como formato lido errado, não como formato recusado.

#### 2. Duas trincas que não existiam, e nada dizia isso

`fases._SEL` aceitava **um** caractere de terminal depois da letra da fase
(`IAW`, `VBY`). O SEL-787, sendo diferencial de transformador, nomeia os
enrolamentos com **dois**: `IAW1`, `IAW2`, `IGW1`, `IN1`.

Resultado: naquele arquivo o programa não reconhecia fase em nenhum dos nove
canais de corrente, as duas trincas não se formavam, e **3I0, I1, I2, IN e a
localização de falta simplesmente não existiam** — enquanto os canais
apareciam na tela e desenhavam normalmente. É exatamente o modo de falha que a
aba do IED e o lápis de correção existem para combater.

O limite passou para **dois** caracteres (`_TERMINAL`), e não para livre: com
sufixo livre, `VALORES` viraria fase A e um canal de potência reativa entraria
em Fortescue. Há teste fixando os dois lados — `IAW1` → A e `ICAPACITOR` → "".

Efeito colateral conferido canal a canal nos dez arquivos do acervo: só as
colunas `3V0M` e `3V0A` do 451 passaram a deduzir fase N. São colunas SEM
UNIDADE, então não entram em conjunto, nem em resíduo solto, nem em conta
nenhuma — a lista de sinais do 451 é idêntica antes e depois.

#### 3. E uma afirmação nossa que era falsa

O comentário do `FILTRADO_ATE` dizia que amostras em valor eficaz seriam prova
de relatório filtrado, "porque só o relatório filtrado é escrito assim". O
`.CEV` do 787 derruba: 16 amostras por ciclo, THD de 0,9 a 1,8 % em regime
(onda CRUA — o filtrado dá ~0 %) e ainda assim escrito em eficaz. Conferido
contra o cabeçalho do próprio relé: com o ×√2 os sete canais fecham dentro de
1,3 %; sem ele, erram 30 %.

**O eficaz é do formato CEV, não do relatório filtrado.** A taxa é o único
critério.

### Comissionamento: o relé escreve o próprio gabarito (22/09/2026)

Todo arquivo traz, além das amostras, medidas que o relé calculou por dentro.
**Esses números são um gabarito escrito pelo fabricante**, e conferir contra
eles não precisa de arquivo de referência nenhum. Mora em
`tests/test_comissionamento.py`, ligado por `OSCLAB_AMOSTRAS`.

Descartou o plano anterior — um `gabarito.json` chaveado por sha256 —, e o
motivo vale guardar: **um gabarito que a gente mesmo escreve prova que a conta
não mudou, não que ela está certa.**

#### As três camadas, e o que cada uma prende

1. **Sintéticos** (`tests/fabrica.py`): resposta CONHECIDA. Prendem a
   MATEMÁTICA, de forma absoluta — melhor que comparar com software, porque
   não há segunda implementação para estar errada.
2. **`test_comissionamento.py`**: matemática MAIS leitura (escala de TC/TP,
   ordem de canal, base de tempo) contra o que o relé afirma.
3. **SIGRA**: terceiro independente, manual. Cobre os arquivos da SEL que não
   trazem gabarito nenhum dentro. **O 487E já foi conferido** (22/09/2026,
   13 canais, 0,05 % de mediana — ver abaixo). Sobra o **COXIPO**, e mesmo ele
   tem um `.CEV` do mesmo evento que já passa nas conferências. O SEL-TWFL
   também não traz gabarito, mas está fora de escopo — ver «Decisões já
   tomadas».

#### As oito conferências

    1. resíduo calculado x o MEDIDO pelo relé        (todos os formatos)
    2. fasor de PRÉ-FALTA do cabeçalho               (.CEV)
    3. fasor de FALTA do cabeçalho                   (.CEV, com trecho parado)
    4. colunas V1M / 3V0M / 3V2M em regime           (.CEV)
    5. o mesmo evento exportado nos dois formatos    (par .CEV + COMTRADE)
    6. a hora do TRIP x a amostra em que o digital muda   (.CEV)
    7. o instantâneo por coluna do cabeçalho         (.CEV do SEL-787)
    8. I1 x a coluna lenta LI1M, em regime           (.CEV)

**A 6 é a única que prende a BASE DE TEMPO.** Todas as outras comparam número
com número na mesma amostra e passariam igual com o registro inteiro deslocado
no tempo. Ali não: o relé carimba uma hora de RELÓGIO (`HOUR_T1`…), e para ela
virar índice de amostra passam a hora do disparo, o recuo pela marca `>` e a
taxa. Prende o desempacotamento dos digitais junto. Medido no alimentador: o
relé carimba 13:36:57,980 → amostra 208, e é exatamente onde `TRIP` muda. Das
481 amostras, só 40 têm mudança alguma, e a 208 é a maior rajada (17 digitais).

**A 7 casa campo do cabeçalho com coluna pelo nome EXATO, unidade inclusive.**
É o que separa os dois dialetos sem lista de nomes: no 451 os campos são `IA`,
`IA_PF` (sem unidade) e nenhum casa com a coluna `IA(A)`; no 787 os campos SÃO
`IAW1(A)` e casam os doze.

**O neutro que a dedução do programa deixa solto é emparelhado AQUI DENTRO**
(`_neutros_pelo_nome`), pela chave do nome: `IGW1` → `I*W1`, `J1 -IG` →
`J1 -I*`. São quatro pares a mais de graça. Fazer a mesma dedução no
`conjuntos.py` mexeria no que alimenta `3I0`, `I1` e a localização de falta —
risco desproporcional para um ganho que é só de conferência. **Decidido em
22/09/2026, e o argumento é do Alexandre:** o `N` de um conjunto não entra em
conta nenhuma (toda conta passa por `conjunto.abc`, que devolve só A, B e C),
então pendurá-lo não compra cálculo, compra só agrupamento.

#### O que foi medido

    resíduo MEDIDO x nosso IN calculado
      SIPROTEC, 4 grandezas (3I0 e 3V0 dos dois enrolamentos)   0,001 %
      SEL .CEV, IG                                              0,000 %
      MiCOM, Current IN                                          15,6 %  (*)
    fasores do cabeçalho do .CEV
      8 am/ciclo, pré-falta            0,60 % de módulo, 0,13° de ângulo
      8 am/ciclo, falta                0,42 %,           0,37°
      4 am/ciclo, pré-falta            1,09 %,           0,41°
      4 am/ciclo, falta                  não confere — ver abaixo
    colunas do relé, em regime
      V1M                              +0,04 %
      3V0M                             +1,12 %
      3V2M (com o fator 3)             −4,90 %
    mesmo evento em dois arquivos (.CEV filtrado x COMTRADE bruto)
      casam por carimbo de disparo com Δt = 63 µs; pré-falta dentro de 0,5 %

(*) **O MiCOM não é defeito nosso.** O `Current IN` dele é entrada própria,
que pode estar num TC toroidal noutro ponto do circuito; as relações de TC
declaradas são idênticas, então não há como saber isso pelo arquivo. O
`Voltage VNG` do mesmo relé é pior: declara TP de 79.674 V contra 138.000 V
das fases — é 138000/√3, ou seja, bases diferentes, e esse o teste detecta e
pula sozinho.

#### Três limites que viraram guarda no teste

**As colunas `L*` do `.CEV` são média móvel de 10 CICLOS.** `LI1M`, `L3I2M` e
`LIGM` só mudam uma vez por ciclo, sobem e descem em rampa linear e continuam
caindo dez ciclos depois de o disjuntor abrir. Ajustadas contra a nossa conta,
as três dão a mesma janela de 10 ciclos com 2 % de erro rms. **Só comparáveis
em regime** — foi por isso que `LI1M` fechou e `L3I2M`/`LIGM` não.

**O `.CEV` de 4 amostras por ciclo não serve para fasor de FALTA.** O curto do
arquivo dura 1,5 ciclo e não existe janela de um ciclo inteiramente dentro
dele; o relé calculou o dele por dentro, a 16 amostras por ciclo ou mais, e só
depois decimou o relatório para 4. Erro medido: 18,9 %. Isso é resolução do
relatório, não defeito do leitor. A pré-falta continua valendo (1,09 %).

**O `.CEV` grava corrente como INTEIRO TRUNCADO.** Simulado com senoide limpa:
−1,16 % no fasor a 82 A de pico, −0,39 % a 200 A, −0,03 % a 2500 A. Foi o que
explicou o −1,24 % do `I1` contra o `LI1M`. A tensão tem 2 decimais, e por isso
o `V1` fecha em +0,04 %. Consequência prática: **o `.CEV` perde precisão em
corrente de carga**, e isso importará na localização de falta.

#### O fator 3 da sequência negativa

A SEL grava `3V2M` e `L3I2M`; nós chamamos de `V2` e `I2`. Sem o fator 3 a
comparação dava −67,89 % de "erro" que não era erro nenhum. **Decidido em
22/09/2026 manter `I2`/`V2`** — são as componentes de Fortescue de verdade, e
`3I0` só leva o 3 porque é igual ao resíduo. O preço foi pago no `descricao`
do sinal, que agora diz "o relé costuma gravar 3I2, que é o TRIPLO desta".

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

#### O eixo de tempo do SIGRA conta a partir do DISPARO

Não do início do registro. Custou uma comparação inteira errada em 22/09/2026:
o cursor marcava «898,3 ms» e eu procurei a amostra 1797 (898,3 ms do início do
arquivo), quando o instante era 898,3 ms **depois do disparo** — que naquele
registro fica a 101,6 ms do início, ou seja, a amostra 1999.

A conversão, sempre:

    amostra = (disparo − início + o que o SIGRA mostra) × taxa

Com a amostra errada o erro deu 1,8 % e parecia defeito nosso. Com a certa, deu
0,05 %.

#### Caso conferido — LT COXIPO (SEL-421), 22/09/2026, 9 canais

`LT COXIPO I UPC1 - 08_18_2026 - ... - BC.CFG`, 2000 Hz, cursor em +231,6 ms do
disparo (amostra 666), os dois em **secundário**.

    erro de módulo da fundamental:  máximo 0,11 %   mediano 0,10 %
    erro de ângulo RELATIVO:        máximo 0,10°    mediano 0,06°

Três correntes e seis tensões. **Com isto, todo arquivo do parque que não traz
gabarito dentro de si está conferido contra um terceiro independente.**

#### Caso conferido — SEL-487E, 22/09/2026, 13 canais

Segundo registro conferido contra o SIGRA, e o primeiro num arquivo que **não
traz gabarito nenhum dentro** — era justamente o que faltava para ele.

`QPC1-TR4-UPC2SEL-487E-317_09_202600_28_30_878_170.CFG`, 2000 Hz, cursor em
+898,3 ms do disparo (amostra 1999), os dois programas em **secundário**.

    erro de módulo da fundamental:  máximo 0,28 %   mediano 0,05 %
    erro de ângulo RELATIVO:        máximo 0,80°    mediano 0,16°

Canal a canal, as seis correntes de fase dos dois bancos (`IAS`…`ICT`) ficam em
0,01 a 0,09 %, e as seis tensões (`VAV`…`VCZ`) em 0,01 a 0,12 %. O pior caso,
0,28 % e 0,80°, é o `IY2` — 60 mA com 8 % de contínua, onde o ângulo de um
sinal pequeno se mexe mais.

**O `Extremum` bate em módulo mas NÃO em sinal.** Em `IBS`, `VAV` e `VBZ` os
dois programas dão o mesmo número com sinais opostos: nós devolvemos a amostra
de maior valor ABSOLUTO da janela, e o SIGRA parece preferir outra convenção.
Em `ICS` e `IY2` a diferença passa de 2 % — provavelmente porque a nossa janela
de um ciclo de TEMPO leva 34 amostras onde a dele leva 33, e a amostra extra
pode conter o extremo. Como a fundamental fecha em 0,05 %, a onda é a mesma;
isto é definição, não leitura. **Fica em aberto**, e não vale como conferência
até alguém decidir qual convenção seguir.

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

### O fuso do COMTRADE: mostrar, nunca converter (22/09/2026)

O mesmo curto do COXIPO aparece com **quatro horas de diferença** entre os dois
arquivos que o relé gerou:

    .CEV   disparo = 18/08/2026 14:52:03.061      (hora local)
    .CFG   disparo = 18/08/2026 18:52:03.061601   (UTC)

A resposta está na última linha do `.cfg`, que a edição 2013 da norma reserva
para isto — **quatro campos em duas linhas**:

    time_code , local_code      o fuso dos CARIMBOS e o da instalação
    tmq_code  , leapsec         a qualidade do relógio e o segundo bissexto

No COXIPO: `0,-4` e `0,0` — carimbos em UTC, instalação em UTC−4 (Cuiabá),
relógio travado. E o nome que o próprio relé deu ao arquivo traz `14_52_03`,
hora local. **Não é caso isolado e não é um fuso só**: no parque o SEL-421
carimba em UTC e o SIPROTEC carimba em hora local (`-4,...` no `time_code`).

**Guardávamos a primeira linha inteira como texto (`"0,-4"`) e jogávamos três
dos quatro campos fora.** O que sobrava não dizia nada a quem lia.

#### A decisão, e o gabarito que a decidiu

**A hora NÃO é convertida.** O carimbo fica como o arquivo escreveu, e os
códigos aparecem ao lado, no cabeçalho.

Não foi preferência: é a convenção do SIGRA, conferida contra ele no `.CFG` do
COXIPO. Ali o `Start time` que ele exibe é o mesmo `18:52:02.960` que nós
exibimos, e o fuso aparece em campos separados (`Time Code: 00h00`,
`Local Code: -04h00`, `Time Quality Code: Normal operation, clock locked`).
Converter por conta própria faria a nossa hora divergir do gabarito — e do
nome que o relé deu ao arquivo.

A linha sai em português, e o código `F` do `tmq_code` — relé sem sincronismo —
é escrito com todas as letras, porque ali a hora do arquivo deixa de servir
para cruzar com outro registro:

    carimbos em UTC; hora local UTC−04:00; relógio travado, operação normal
    carimbos em UTC−04:00; erro abaixo de 1 ms
    ... relógio sem sincronismo — a hora do arquivo NÃO é confiável

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
- **Siemens SIPROTEC** escreve o NÚMERO DO CANAL no campo `ccbm` (`1`, `2`, `3`
  para IA, IB, IC). O `ccbm` da norma é o equipamento vigiado e é o mesmo nas
  três fases; um número por fase põe cada uma num conjunto só dela, nenhum
  conjunto fecha, e o registro de um transformador fica **sem componente
  simétrica nenhuma e com dois canais chamados `IA` na mesma tela** — sem erro,
  sem aviso. Corrigido: `ccbm` só de dígitos não é nome de equipamento.
- **Relé tem mais entrada do que a instalação usa.** Um SEL-451 grava dois
  terminais de TC e dois de TP com só um de cada par cabeado; um SEL-487E tem
  cinco terminais de TC e três livres. A trinca não cabeada é reconhecida pela
  medição e não entra no gráfico padrão — ver `analysis/presenca.py`. Sem isso,
  o programa também achava que precisava distinguir duas trincas e carimbava
  sufixo em todo canal. Hoje a trinca morta **conta** para a numeração, de
  propósito: o nome não pode mudar quando o usuário desmarca «ocultar sinais
  nulos» — ver `conjuntos.precisa_numerar`.
- **Siemens SIPROTEC** deixa o campo `ph` (fase) VAZIO e escreve a fase no fim
  do nome do canal ("TC BUC 69kV:I A"). Para componentes simétricas (marco 0.4)
  vai ser preciso deduzir a fase do nome quando o campo não vier preenchido.
- Alguns registros trazem o disparo na **amostra 0**, sem janela de pré-falta —
  a detecção por grandezas delta (marco 0.5) precisa tratar esse caso.

### O arranjo de abertura (marco 0.4)

Um painel por TRINCA de corrente e de tensão, na ordem do arquivo — que é, na
prática, a ordem em que se conta um evento. Três decisões dentro disso:

- **Só corrente e tensão.** Um relé grava muito mais — tensão da bateria,
  frequência, ângulos que ele mesmo calculou, corrente diferencial em pu — e
  cada unidade dessas virava um gráfico na abertura. O resto é escolha de quem
  analisa, e está a um clique no «+ sinal».
- **A separação é por trinca, não por unidade.** É isso que tira a tensão da
  bateria do caminho: ela é volt e não é uma das três fases de nada.
- **O residual solto entra na trinca.** O `IG` de um SEL e o `3I0` de um
  Siemens não saem do nome das fases trocando uma letra, mas são do mesmo vão —
  e num evento à terra são a primeira coisa que se procura. Com mais de uma
  trinca da mesma unidade, só entram quando o nível de tensão do nome casa com
  o de uma delas; pendurar o residual no lado errado do trafo é pior que não
  mostrá-lo.

Quando nenhuma trinca é reconhecida, vale o arranjo antigo (um painel por
unidade): sem trinca não há com que escolher, e tela vazia é pior que tela
cheia demais.

### O nome do sinal é o nome do CANAL

    IED       IAW                      o canal, com o nome que o relé deu
    OscLab    IAW · RMS                o que o relé NÃO gravou
              IAW · 60Hz
              IAW · 60Hz RMS

Já foi `IA`, `IB`, `IC` — a fundamental que o programa deduz do nome do canal —
e antes disso `IA'`, `IA [1]`, `IA AT`. Todas essas versões tinham o mesmo
defeito de raiz: **duas nomenclaturas para a mesma coisa na mesma tela**,
`IAW` na aba do IED e `IA` na legenda do gráfico. E como num trafo dois canais
diferentes viravam `IA`, foi preciso inventar um apelido de trinca só para
desempatar — apóstrofo, colchete, letra do terminal, cada um com o seu
problema.

O nome do relé não empata: ele já nomeia os terminais dele de forma única, em
todo fabricante. Some o desempate, some a segunda nomenclatura, e o nome fica
sendo o que o engenheiro já lê no relatório do relé.

**O separador é ` · `, não hífen.** O GE grava canais chamados `J1 -IA` e
`J2 -VX`: `J1 -IA - RMS` põe dois hífens de significados diferentes na mesma
linha.

**O vínculo com a fase continua existindo** — é dele que saem as trincas, as
componentes simétricas e o agrupamento dos painéis. O que saiu foi a
nomenclatura: nenhum sinal se chama `IA`.

**O nome é UM, e é desenhado inteiro.** Houve uma versão em que a frequência
ia em subscrito: o servidor mandava o nome partido em três (`("IAW ·", "60Hz",
"RMS")`) e a tela encolhia o do meio. Saiu. O que se ganhava em largura se
perdia em leitura — `IAW ·60Hz`, com o ponto colado no subscrito, lê pior que
`IAW · 60Hz` — e o nome passava a existir em duas formas, com um teste só para
garantir que as duas diziam a mesma coisa.

### O ordinal `[1]` só existe no que sai de uma TRINCA

E existe ali porque não há alternativa: `3I0` e `IN` saem de TRÊS canais, então
não há um nome de arquivo a herdar. Por grandeza, na ordem do arquivo — `3I0 [1]`,
`3I0 [2]` —, e só quando o arquivo tem mais de um conjunto daquela grandeza.

**A contagem inclui os conjuntos SEM SINAL**, senão a componente escondida e a
visível se chamariam igual quando o usuário desmarcasse «ocultar sinais nulos».

**Um residual sem dono conta como conjunto de um canal só.** O GE grava dois
(`J1 -IG` e `J1 Ig`) e o SIPROTEC outros dois (`NEUTRO:Ix`).

#### E o ordinal vem acompanhado da origem

Um ordinal não diz nada sozinho — é essa a propriedade que o faz servir a
qualquer fabricante. O programa paga o preço escrevendo de que canais a
componente saiu, em dois lugares:

- **no rodapé do gráfico**, que aparece **só** quando há componente ou resíduo
  no painel: `[1] — de "IAS", "IBS", "ICS"`;
- **na coluna da direita da aba do OscLab**, ao lado do sinal.

**São os TRÊS canais que entram na conta**, não os do conjunto: o residual
(`TC BUC 69kV:3I0`, `IG`) pertence ao mesmo vão e aparece no mesmo painel, mas
não entra em Fortescue — citá-lo ali prometeria que ele foi somado.

**Os nomes vão entre aspas.** Sem elas, um `TC BUC 69kV:I A` no meio de uma
lista — com espaço e dois-pontos dentro — vira sopa, e um `J1 -IA` parece
subtração.

**E é lista de canais, não fórmula.** `IAW + IBW + ICW` mentia duas vezes: o
`+` entre eficazes sugere soma de módulos (três fases de 400 A somariam 1200 A,
quando o 3I0 verdadeiro é zero), e para `I1` e `I2` a conta nem é soma — exige
girar duas fases de 120°, que é multiplicar por complexo.

#### A trinca da componente é a ÚNICA origem que se corrige

Na aba do OscLab, **só a componente simétrica** mostra a origem à direita, e só
ela ganha lápis ao lado. A assimetria é de propósito:

- `IAW · RMS` não mostra origem nenhuma. Ela existe — o canal 0 —, mas
  **repete o começo do próprio nome** e não é palpite: o id do sinal é
  literalmente "o canal 0, em eficaz". Não há como errar, então não há o que
  corrigir nem o que informar; escrever `IAW` ao lado de `IAW · RMS` só
  gastaria tela.
- `3I0 [1] → IAW, IBW, ICW` é uma **dedução**: o programa olhou os nomes e
  decidiu que aqueles três formam uma trinca. Quando erra, 3I0, I1, I2 e a
  localização de falta erram junto — na unidade certa, na ordem de grandeza
  certa, sem nada na tela denunciando. Medido num registro real: trocar uma
  fase levou o 3I0 de 302 A para 4262 A.

A correção fica gravada em `trincas.json` ao lado do registro, pelo mesmo
motivo da correção de fase: quem corrigiu corrigiu para sempre, não até fechar
o navegador. Correção vazia apaga e a dedução volta a valer.

**A chave é o NOME do conjunto** (`I*W`, `CURRENT I*`), não a posição dele. A
posição é o `q{i}` que os arranjos salvos usam; amarrar a correção a ela faria
uma correção mudar o alvo de outra.

**E a ordem da lista sai dos canais DEDUZIDOS, não dos corrigidos.** Se
corrigir uma trinca a fizesse trocar de lugar com outra, um gráfico salvo
passaria a desenhar a corrente de outro equipamento — sem erro nenhum na tela.

Só A, B e C se corrigem: são os que entram em Fortescue. Os candidatos
oferecidos são os canais da MESMA unidade, e duas fases no mesmo canal são
recusadas — a matriz aplicada a isso devolve número, e o número não quer dizer
nada.

#### O título do painel é só a unidade

`Correntes (A)`, `Tensões (kV)`. Num trafo os dois painéis de corrente se
chamam igual, e quem os distingue é o nome dos canais dentro deles — `IAW` num,
`IAX` no outro.

#### Não há mais rotulagem manual de trinca

Houve: o usuário escrevia `alta`/`baixa` e o nome ficava gravado em
`rotulos.json`. Ela existia para **consertar um palpite do programa**, de
quando a tela afirmava qual era a alta. O programa não palpita mais. Saíram
junto: `rotulos.json`, a rota `/api/onda/<sha>/rotulos`, o `rotulo_escolhido`
do canal, o `OrigemDoRotulo.ESCOLHIDO` e o lápis de rotular.

#### O programa não diz "alta" nem "baixa"

Ele já disse, e foi um erro. `AT`/`BT` afirmava **duas** coisas: que existe um
transformador ali, e qual lado é qual. A segunda saía da primeira, e a primeira
nunca era verificada — um relé que grava uma linha de 138 kV e o serviço
auxiliar de 13,8 kV tem dois níveis diferentes e nenhum transformador no meio.

E o modo de falha era o pior possível: **silencioso**. Dois defeitos reais no
leitor de nível, os dois em produção, nenhum dando erro:

- **`L1V` lido como "1 volt"** e `L2V` como "2 volts". As duas linhas de um
  TWFL — as duas no MESMO nível — apareciam com tensões diferentes. Só não
  viraram `AT` e `BT` por acidente: aquele arquivo tem quatro trincas de tensão
  e a regra de lados só atuava com duas ou três.
- **`TC EXT 34-5kV` lido como 5 kV.** A Siemens escreve `34-5kV` para 34,5 kV
  porque o ponto decimal não cabe no nome do canal. Errava por um fator de sete
  e acertava o lado por acidente, só porque o outro enrolamento era 69 kV.

Os dois estão corrigidos (o número não pode vir colado a uma letra; o hífen
entre dígitos é vírgula decimal) e `nivel_de_tensao` continua servindo para
casar o residual solto com a trinca certa — o que é um EMPARELHAMENTO, não um
ranqueamento. Mas a dedução de lado saiu.

#### O número não é lado

`[1]` é ordinal DENTRO da grandeza: num relé com duas trincas de corrente e
duas de tensão que o arquivo não relaciona, `3I0 [1]` e `3V0 [1]` são a
primeira corrente e a primeira tensão, e não há como afirmar que são do mesmo
lado do equipamento. Corrente e tensão só se intercalam no arranjo quando os
apelidos de uma grandeza correspondem aos da outra.

Quem sabe é quem abriu o arquivo, e o rodapé do gráfico dá a ele o que precisa
para saber: os nomes dos canais, como o relé os escreveu.

### `IN` e `VN`: o resíduo no TEMPO, que não é o `3I0` (decidido em 22/09/2026)

`3I0` é módulo de fasor: passa pela janela de um ciclo e **só enxerga 60 Hz**.
A soma `ia+ib+ic` amostra a amostra não filtra nada — carrega a assimetria (a
DC da falta) e os harmônicos do resíduo, que é justamente o que um TC saturando
despeja ali. São grandezas diferentes, e por isso as duas existem:

    IN [1]          ia+ib+ic amostra a amostra — a senoide, com DC e harmônicos
    IN [1] · RMS    o eficaz VERDADEIRO dessa soma, janela de um ciclo
    3I0 [1]         o módulo do fasor de 60 Hz da mesma trinca

Em regime senoidal puro `IN · RMS` e `3I0` dão o mesmo número. **Quando não dão,
a diferença é a medida**: é DC, harmônico ou saturação de TC. Medido no
COMTRADE bruto de um curto real do alimentador: em regime a diferença é
+0,21 %; no instante de maior DC do resíduo (694 A) `IN · RMS` marca 1275 A e
`3I0` marca 871 A — **46 % de diferença**, e os dois números estão certos.

É isso que permite explicar por que dois relés no mesmo vão atuaram diferente:
um de terra com filtro de RMS vê o primeiro número, um com filtro de
fundamental vê o segundo.

**A contínua do resíduo (`IN · DC`) é oferecida no registro bruto** desde
27/09/2026, e é a parte de **0 Hz** do `IN` — complementar ao `3I0`, que é a
de 60 Hz. A onda do resíduo se parte em três pedaços ortogonais, e Parseval
amarra os três:

    IN·RMS² = 3I0² + IN·DC² + harmônicos²

Medido no alimentador, na entrada da falta: `3I0` 15 A e `IN · DC` 15 A **ao
mesmo tempo** — metade alternada, metade deslocamento. Quem olhasse só o `3I0`
levaria metade da história.

**A DC do resíduo é a que satura TC de terra.** A de cada fase já estava na
tela desde 22/09; a que passa pelo TC de neutro é esta. Num `.CEV` ela não é
oferecida, pela mesma razão da contínua dos canais: o relé a remove antes de
gravar.

**A variante `60Hz` do resíduo não é oferecida.** `IN · 60Hz RMS` é, por
definição, o próprio `3I0` — seriam duas linhas com o mesmo número e nomes
diferentes, e quem olhasse teria de descobrir sozinho que são a mesma conta.

**E num registro JÁ FILTRADO (`.CEV`) sobra só a senoide** — `IN`, sem
`IN · RMS`. Ali as amostras já são a componente de 60 Hz: não há DC nem
harmônico para o eficaz enxergar, e ele vira o `3I0` com outro nome. Medido no
`.CEV` do alimentador, **em regime a diferença é +0,03 %**.

O que sobra são duas bordas — entrada da falta e extinção —, cada uma com
~1,4 ciclo em que as curvas se descolam (até 84 %). **Isso não é grandeza**: é
a resposta transitória de dois estimadores de janela de um ciclo sobre o mesmo
degrau. Com a janela metade cheia o eficaz marca 0,71 do valor final e a DFT
marca 0,50, porque um é energia e o outro é correlação com um cosseno de ciclo
inteiro. O erro medido é **positivo em 100 % das amostras** — fenômeno de rede
iria para os dois lados.

E há um motivo mais forte que o tamanho da diferença: **no `.CEV` as amostras
já são a saída do filtro do relé**, então `IN · RMS` ali seria um eficaz
aplicado EM CIMA daquele filtro — uma cadeia de medição que nenhum relé tem.
Um 50N com filtro de RMS mede as amostras BRUTAS. Naquelas bordas a curva não
mostraria como elemento nenhum viu a falta.

No registro bruto é o contrário: ali `IN · RMS` é uma cadeia real, e a
diferença para o `3I0` chega a 46 % por causa da DC — informação de verdade.

**`IN` não é o neutro medido.** O canal do arquivo (`IG` no SEL, `J1 -IG` no
GE, `NEUTRO:Ix` no SIPROTEC) continua na aba do IED com o nome que o relé deu.
Comparar os dois é um ensaio de verdade: se o `IN` calculado não bate com o
neutro medido, ou a trinca está errada, ou um TC está saturado, ou o neutro
mede outro ponto do circuito. Conferido contra o `.CEV` do alimentador, amostra
a amostra: **erro mediano 0,000 A e máximo 1,414 A num pico de 2659 A** — o
máximo é a quantização inteira do CEV somada nos três canais.

**A conversão de TC/TP vem ANTES da soma.** Nada garante que as três fases
estejam gravadas na mesma relação; somar primeiro e converter depois daria um
número na unidade certa e na ordem de grandeza certa, sem nada denunciando.

**O resíduo começa na PRIMEIRA amostra**, diferente de toda componente
simétrica: soma de três números não precisa de histórico nenhum.

**Ele leva o lápis da trinca**, pela mesma razão que a componente: sai de três
canais que o programa escolheu olhando nomes. Os dois compartilham a mesma
trinca, então corrigi-la por qualquer um deles arruma os dois.

**O rodapé cita só os resíduos que estão NO PAINEL** (`IN`, `VN`, ou os dois),
e a nota do resíduo é separada da nota das componentes: dizer «módulo do fasor
de um ciclo» embaixo de uma senoide somada no tempo descreveria a conta errada.

Vale igual para tensão: `VN` é `va+vb+vc` no tempo — o resíduo que um TP em
delta aberto mede.

### A janela de medida é UM CICLO DE TEMPO, não um número inteiro de amostras (22/09/2026)

Um SEL a 2000 Hz num sistema de 60 Hz grava **33,3333 amostras por ciclo**.
A janela de 33 amostras é 0,99 ciclo, e a média de 0,99 ciclo de uma senoide
**não é zero**: sobra 1,01 % do pico, girando a 60 Hz.

Isso aparecia como ondulação de 1 % no RMS e na fundamental — tolerável — e
**como o gráfico inteiro** na componente contínua, cujo valor verdadeiro é
zero. Foi assim que o problema foi descoberto: a curva de `VAY · DC` desenhou
uma senoide de ±0,1 kV em cima do zero.

**Não é caso raro.** 2000 Hz é a taxa de quase todo COMTRADE do parque:

    arquivo            taxa    am/ciclo   vazamento da janela arredondada
    MiCOM Schneider    1200      20,000                           0,000 %
    SEL-451 .CEV        480       8,000                           0,000 %
    SEL-451 COMTRADE   2000      33,333                           1,011 %
    SEL-487E           2000      33,333                           1,011 %
    SEL COXIPO         2000      33,333                           1,011 %
    SIPROTEC           2000      33,333                           1,011 %
    SEL-TWFL          10000     166,667                           0,200 %

#### A correção

`fasor.pesos_do_ciclo(n)` devolve os pesos de uma janela de **um ciclo de
tempo**: trapézio sobre as amostras cheias, mais a ponta fracionária
interpolada entre as duas amostras que a cercam. Os pesos somam exatamente
`n`. Tudo sai dali — `envoltoria.media_do_ciclo` é a primitiva única, e a
contínua é ela sobre o sinal, o eficaz é a raiz dela sobre o quadrado, e o
fasor é ela sobre o sinal girado.

Medido, num registro real (tensões do alimentador, trecho em regime):

    grandeza      janela de 33   um ciclo de tempo
    DC                 1,010 %             0,048 %
    RMS                0,497 %             0,165 %
    60Hz RMS           0,495 %             0,166 %

O que sobra no RMS e na fundamental já não é vazamento: numa senoide sintética
pura a ondulação cai para **0,003 %**. O resto é harmônico e ruído do próprio
sinal.

#### Com taxa que FECHA, nada muda — e isso é deliberado

Com `n` inteiro os pesos são todos 1: o Fourier de ciclo cheio de sempre, que é
o que o relé roda por dentro. **Todo número já conferido contra o SIGRA e
contra os relés saiu de arquivo com taxa inteira** — o MiCOM a 20 amostras por
ciclo, os `.CEV` a 4 e a 8 — e essa conferência continua valendo dígito a
dígito. Há teste fixando os pesos em 1 nesse caso.

#### O que NÃO mudou

`fasor.amostras_por_ciclo` (o arredondado) continua existindo e continua certo
para o que é contagem de ÍNDICE: andar um ciclo com a tecla, a margem de
história, o passo de "comparar com um ciclo atrás". O que mudou é só a janela
de MEDIDA, e ela agora vem de `fasor.ciclo_em_amostras`, sem arredondar.

A janela fracionária ocupa uma ou duas amostras a mais que o ciclo, então o
começo de cada trecho fica sem curva por essas amostras a mais. É o mesmo
preço, pela mesma razão, do primeiro ciclo que nunca teve envoltória.

Custo de tempo, no maior arquivo do parque (SEL-TWFL, 50 canais × 5000
amostras, 166,7 por ciclo): RMS 8 ms, fundamental 14 ms, contínua 4 ms — todos
os canais de uma vez. A conta é `O(n)` porque os pesos são 1 no miolo: só as
três pontas são tratadas uma a uma.

### `· DC`: a contínua em ampère, e só no registro BRUTO (22/09/2026)

`IAW · DC` é a **média da janela de um ciclo**, em unidade de engenharia e
**com sinal**. Numa senoide pura dá zero; o que sobra é a assimetria da falta,
`i_dc(t) = I₀·e^(−t/τ)`.

**Só existe em registro bruto.** O relé tira a contínua antes de gravar, então
num `.CEV` ela é zero por construção. Medido nos três `.CEV` do parque, **só
em regime**: mediana de 0,00 % a 0,02 % da fundamental, contra 0,2 % a 1,1 %
nos COMTRADE (com máximos de 43 % a 1491 %). Os poucos por cento que sobram no
`.CEV` são artefato de janela em cima de borda, e no arquivo de 4 amostras por
ciclo uma "média de quatro amostras" é um estimador ruim por natureza.

**Em ampère, não em percentual, e isto foi decidido com argumento.** O SIGRA
mostra "DC %" relativa à fundamental eficaz, em módulo — e o percentual
continua na tabelinha do cursor (`Fasor.dc_percentual`), já conferido contra
ele nos oito canais de um registro real. Como CURVA o percentual seria razão de
duas envoltórias: quando o disjuntor abre, a fundamental vai a zero e a razão
estoura. A divisão de trabalho é a que a tela já usa — **curva para o que varia
no tempo, tabelinha para índice num instante**.

**A DC é a única envoltória que traça uma grandeza FÍSICA e não um índice**, e
é dela que se lê o τ. Medido num curto real do alimentador: **τ = 6,5 ms,
X/R = 2,5**. O estimador atrasa meio ciclo e subestima o pico (marcou 2890 A
onde a exponencial ajustada dá 3585 A), **mas isso não estraga o τ**:
exponencial atrasada é a mesma exponencial escalada, mesma inclinação.

O que a curva mostra, no mesmo curto (fase A, primário):

    amostra   inst      DC     RMS   60Hz RMS
       190   -7460   -1325    2712     1703      ← entra a falta, DC forte
       200   -1004   -2890    4144     2881      ← pico da DC: 100 % da fund.
       230   -4017    -335    4093     4078
       260   -5503      70    4034     4033      ← DC extinta: RMS = fund.

É a demonstração de por que o `RMS` passa por cima da `60Hz RMS` e depois
encosta nela: a diferença entre as duas **é** a DC.

### Eficaz e filtro só para o que é alternado

Um relé grava contínua junto com alternada: a tensão da bateria, a frequência
medida, as magnitudes e os ângulos que ele mesmo calculou. O catálogo oferecia
`VDC1 RMS`, `VDC1 60Hz` e `V1M RMS` — contas que não significam nada: a
componente de 60 Hz de 132 V contínuos é zero, e o eficaz de um ciclo de um
número parado é o próprio número com cara de medida de alternada.

**Alternado é o que oscila em torno do zero**: a fundamental não fica abaixo da
média. TC e TP não passam contínua, então um canal de verdade tem média
praticamente zero mesmo numa falta assimétrica. Medido: a maior razão
`|média|/fundamental` num canal alternado real foi 0,9; a menor num contínuo,
84.

Duas condições acompanham, cada uma por um caso real:

- **sem unidade declarada não é alternado** — é o que pega os ÂNGULOS do CEV,
  que giram de −180° a +180° e por isso têm cara de fundamental;
- **sem fundamental nenhuma, a unidade decide** — um vão com o disjuntor aberto
  o registro inteiro tem corrente zero, e zero não é contínua: é alternada que
  não está passando.

### O que ganha conta do OscLab: fase alternada, e só

Ser alternado não bastava. Um relé grava as sequências que ele MESMO calculou
(`V1M`, `3V2M`, `LIGM`, `LI1M`), a tensão de sincronismo, a de memória. Filtrar
em 60 Hz um número que já É o módulo do fasor de 60 Hz é a mesma conta feita
duas vezes: o resultado sai na unidade certa e tem cara de medida.

São **duas** condições, e nenhuma é lista de nomes suspeitos — lista de nomes
envelhece a cada fabricante novo:

1. **é alternado** — e o teste de peso aqui é a **unidade, que é lista
   BRANCA**: só ampère e volt, com prefixo. Grau, hertz, `I/IrObj` e unidade
   nenhuma não entram. É o que barra os ângulos do GE, as magnitudes do CEV e
   as correntes diferencial e de restrição em pu do SIPROTEC — estas últimas
   com letra de fase no nome (`87T:I diff.:phs A`), e foi a unidade que as
   pegou;
2. **a fase foi reconhecida** — `IA`…`IN`, `VA`…`VN`. Barra `VS1`, `VS2`,
   `V1MEM`, `Voltage Vref` e o terceiro banco de TC do 487E, nomeado `IY1`,
   `IY2`, `IY3`.

Auditado canal por canal nos seis arquivos do parque, quatro fabricantes: zero
lixo entrando, zero canal de fase saindo.

**Estar em trinca não é condição.** Foi, e custava seis neutros de verdade:
`J1 -IG` e `J1 Ig` do GE e os dois `NEUTRO:Ix` do SIPROTEC ficam fora de trinca
porque o arquivo tem mais de uma trinca da mesma unidade e nada com que decidir
de qual delas eles são. São residuais, e num evento à terra são a primeira
coisa que se procura.

**Estar sem sinal também não é condição.** Um terminal de TC não cabeado ganha
as contas como qualquer outro; quem o tira da tela é a caixa «ocultar sinais
nulos». Três motivos, em ordem de peso:

- **é a única incerteza que não dá para auditar.** Um transformador energizado
  de um lado só tem a trinca do outro lado em zero legitimamente, e nenhuma
  medida sobre um registro só distingue isso de uma entrada aberta. Alternado e
  fase reconhecida erram por dado estranho ou fabricante novo, e o erro aparece
  na tela; este erra por física que o arquivo não separa. **Teste que não se
  pode conferir nunca decide se a coisa existe, só o que se mostra.**
- **botão morto.** Sem a conta, o RMS não faz nada quando o usuário desmarca a
  caixa para conferir que a entrada está mesmo aberta.
- **custa nada e não mente.** RMS de zero é zero, e esse zero é a resposta que
  alguém foi procurar no arquivo.

Vale para as componentes simétricas também: a de uma trinca muda existe e fica
escondida, como os canais dela.

Medido, para dimensionar: dos canais alternados e nulos dos seis arquivos, 18
estão em trinca e 5 fora — e desses 5, quatro já não têm fase reconhecida. O
teste de validade comprava **um** canal no parque inteiro.

Num registro que o relé JÁ gravou filtrado (o `.CEV`), sobra **uma** conta: o
eficaz da janela de um ciclo. As duas variantes `60Hz` saíram — a primeira não
calculava nada (era o canal com outro nome, e ao lado de «gravação filtrada
pelo relé» no cabeçalho se lia como filtrar duas vezes) e a segunda prometia
uma ressalva sobre harmônicos que é do registro inteiro, não de cada sinal.
Um `.CEV` de alimentador tem 13 linhas no OscLab.

### Aviso do LEITOR e relato do RELÉ são coisas diferentes

Os dois saem do leitor e aparecem no cartão do acervo, e só um leva triângulo:

- **aviso** (`Record.notes`, `⚠`): o que o programa fez, deixou de fora ou não
  conseguiu confirmar — soma de verificação que não bateu, colunas vazias que
  ficaram de fora, a conversão de eficaz para instantâneo do CEV.
- **relato** (`Record.relatos`, sem triângulo): o que o RELÉ concluiu sozinho e
  gravou no arquivo — a classificação do evento (`AB T`), a distância que ele
  calculou para a falta.

Os dois já foram a mesma lista, e o resultado era um `⚠` em cima de "o relé
classificou o evento como AB T". **Aviso que aparece quando não há nada errado
ensina a ignorar o triângulo** — e aí o aviso que importa passa despercebido
junto. É a mesma regra do `bruto` que saiu do cabeçalho.

Os textos são de uma linha, de propósito: quem abre uma oscilografia não vai
ler um parágrafo, e um aviso não lido é igual a aviso nenhum.

### O cabeçalho só anuncia a filtragem quando ela muda alguma coisa

O diagnóstico de bruto × filtrado continua sendo **medido** — distorção
harmônica em trecho de amplitude parada, `analysis/filtragem.py` — e continua
travando o botão do filtro. O que saiu da tela foi o veredito `bruto`.

Ele é o caso comum: todo COMTRADE do parque cai nele, e `gravação bruta
(deduzido)` aparecia em cima de toda oscilografia. **Aviso que aparece sempre
deixa de ser lido** — e, pior, passa a ser lido como defeito do programa.

Ficam na tela os dois que mudam o que se pode fazer: `filtrado`, que trava o
botão, e `desconhecido`, que diz que o programa não decidiu e por isso deixou o
botão livre.

Não é o mesmo que deduzir pela extensão. `.CEV` declara (pelas amostras por
ciclo) e COMTRADE é medido, com três vereditos possíveis; um COMTRADE exportado
já filtrado sai `filtrado` e trava o botão, sem a extensão dizer nada.

### Coluna de pixel é pixel DE VERDADE, não pixel de CSS

Sintoma: com o zoom do navegador fora de 100 %, a onda ganhava um **batimento
no envelope** — o pico desenhado variava de um ciclo para o outro muito mais do
que o sinal varia. Medido no registro do alimentador: no arquivo o pico de
ciclo varia ~1 %; na tela variava muito mais.

Duas causas somadas, e as duas são a mesma ideia mal aplicada:

1. **A tela pedia colunas em pixel de CSS.** O canvas é criado com
   `largura × devicePixelRatio`, e o Chrome multiplica esse fator pelo zoom: a
   80 % ele vale 0,8 numa tela comum. O servidor mandava ~1 ponto por pixel de
   CSS e o canvas tinha 0,8 pixel real para cada um — mais pontos que pixels, e
   o traçador escolhia. Vale para os dois lados: acima de 100 %, ou em tela
   HiDPI, o traço saía mais grosseiro do que a tela mostraria.
2. **A redução só entrava acima de DUAS amostras por coluna.** Dois pontos por
   pixel é exatamente o que não se desenha: a linha sobe e desce dentro do
   mesmo pixel. Hoje reduz com mais de UMA.

Com as duas, cada coluna carrega o mínimo e o máximo do que aconteceu dentro
dela, e o número de colunas é o de pixels que existem. Nada é escolhido.

**O batimento não estava no arquivo** — e vale desconfiar sempre que um
envelope "respirar" na tela: a primeira pergunta é quantas amostras estão
caindo em cada pixel.

### Oito amostras por ciclo desenham um polígono

Ligar duas amostras com uma RETA desenha menos onda do que existe: no meio do
caminho entre duas amostras, a corda passa abaixo da senoide, e quanto depende
só de quantas amostras há por ciclo.

| amostras/ciclo | a reta fica abaixo |
|---|---|
| 4 | 29,3 % |
| 8 | 7,6 % |
| 16 | 1,9 % |
| 33 | 0,4 % |

É por isso que um CEV filtrado (8 por ciclo) aparecia pontudo e o COMTRADE
bruto do MESMO evento (33 por ciclo) aparecia redondo. Não era defeito do
arquivo nem da leitura — era o que oito pontos ligados por retas desenham.

O traço agora é uma curva de Catmull-Rom quando há **8 amostras por ciclo ou
menos**: ela reconstrói a senoide com 0,9 % de erro (trinta vezes melhor que a
reta), passa exatamente por todas as amostras e não ultrapassa o pico delas.

**Só onde há pouca amostra**, e o motivo é o oposto do estético: num sinal com
descontinuidade de verdade — a entrada de uma falta num registro bruto — uma
curva suave passaria por fora do degrau e desenharia um pico que não existe.
Registro filtrado não tem degrau, porque o filtro do relé os removeu. E nunca
sobre traço reduzido: ali o desenho já é mínimo e máximo por coluna de pixel, e
arredondar isso inventaria forma onde há estatística.

### E as do `.CEV` da SEL (marco 0.4)

Nenhuma está escrita em campo nenhum do arquivo. As três primeiras foram
confirmadas contra o COMTRADE **bruto do mesmo evento do mesmo relé** — um
SEL-451 do ALIMENTADOR 11 de SE BARRO DURO.

- **A amostra vem em valor EFICAZ, não instantâneo.** A coluna `VA(kV)` oscila
  como senoide, mas o pico dela é o eficaz: 8,030 kV no filtrado contra
  11,355 kV no bruto — razão 1,4141. O leitor multiplica por raiz de 2; sem
  isso o filtrado aparece 41 % menor que o bruto e o botão de RMS da tela
  devolve o valor dividido por raiz de 2, tudo sem erro na tela.
- **A hora do cabeçalho é a do DISPARO**, não a da primeira amostra. A amostra
  disparada é a que traz `>` na coluna `TRIG`; o início sai da conta e bateu com
  o do COMTRADE em 0,3 ms.
- **As colunas `ANAnn` não são canais de onda.** São as grandezas que o próprio
  relé calculou amostra a amostra, e o nome de cada uma está no campo `ERAQnn`
  do cabeçalho: `V1M`, `V1A`, `3V2M`, `3V2A`, `3V0M`, `3V0A`, `LI1M`, `LI1A`,
  `L3I2M`, `L3I2A`, `LIGM`, `LIGA`, `DC1`, `FREQ` — magnitude em eficaz e
  ângulo em grau. **É a referência do próprio relé para as nossas componentes
  de sequência**, sem depender de nenhum outro programa.
- **O arquivo termina com os ajustes do relé**, depois de um marcador
  `"SETTINGS"`. Dali para baixo ele deixa de ser CSV: é um campo só, com
  quebras de linha dentro.
- O bit de cada digital vai do **mais significativo para o menos**, na ordem dos
  nomes. Conferido contra o COMTRADE: o `TRIP` sobe em +331,25 ms no CEV e em
  +331,5 ms no bruto — dentro de um intervalo de amostragem.
- A dedução de bruto × filtrado (`analysis/filtragem.py`) **não conclui nada num
  CEV de 8 amostras por ciclo**: o arquivo imprime a corrente com 3 algarismos
  (`-46`, `57`) e essa precisão de impressão vira 0,46 % de distorção aparente,
  acima do limiar de ruído de quantização que foi calibrado para um COMTRADE
  binário de 16 bits.

  Resolvido pelo FORMATO, não pela medição: um CEV a 4 ou 8 amostras por ciclo
  é o relatório de evento filtrado da SEL — não daria para gravar onda crua com
  tão pouco, e as amostras vindo em valor eficaz são a outra prova. O leitor
  declara `filtrado` e o botão do filtro trava. Acima de 8 por ciclo pode ser o
  relatório bruto em CEV, e aí volta a valer a dedução.

## Contexto completo

`docs/` traz a íntegra: requisitos funcionais, o backlog de ideias do Alexandre,
e a análise da PAC CT, que é a ferramenta usada como referência de arquitetura.
