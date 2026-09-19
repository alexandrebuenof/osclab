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
- **A tabelinha tem três modos em rodízio**, no botão do canto: `valor`
  (instantâneo dos dois cursores e a diferença), `fasor` (eficaz da
  fundamental e ângulo) e `rms` (eficaz VERDADEIRO da janela e DC %, com a
  distorção no hover). Os três saem da MESMA leitura; trocar de modo troca as
  colunas, não os dados.

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
| 0.3e | Faixas dos canais digitais | próximo |
| 0.3f | Alternar primário/secundário na tela, com prefixo k | **feito** |
| 0.4a | Fasor e RMS no cursor | **feito** |
| 0.4b | Componentes simétricas (3V0/3I0) | próximo |
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
- **"DC %"** é relativa à fundamental eficaz.
- Clicar num valor faz aquele canal virar **0°**; os demais giram junto.

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
