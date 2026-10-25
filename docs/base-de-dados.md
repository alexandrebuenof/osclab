# Base de Dados

Status: **implementada em 19/10/2026** — a pasta, as duas gavetas com chave de habilitar e a tabela dos sinais digitais. Falta ligar o dicionário ao leitor (os digitais ainda aparecem com o nome cru na tela da onda) e a gaveta de linhas, que chega com o módulo que a usa.

## As gavetas

| gaveta | nome na tela | pasta | estado |
|---|---|---|---|
| 1 | **Sinais digitais** | `digitais/` | editável pelo programa |
| 2 | **Linhas e estruturas** | `linhas/` | pasta criada, espera o módulo de linhas |

A terceira — **histórico de oscilografias** — foi **adiada por decisão dele em 19/10/2026**. Adiar não custou nada, e voltar também não vai custar: `Base.gaveta()` cria a pasta que faltar na hora de usar, e o `base.json` carrega a versão do formato.

O que ficou desenhado para quando ela voltar: dentro de `registros/` a hierarquia é **do usuário** (regional → subestação → equipamento → data), ao contrário das outras duas, que são tabela. Medido: esse caminho com um `.cfg` de nome longo dá 126–182 dos 260 caracteres do Windows, com folga.

## Pedido dele em 20/10/2026: POPULAR as duas gavetas

Não é mais o formato: é o **conteúdo**. Duas frentes, e as duas têm a mesma pergunta de origem — de onde sai o dado, já que manual de fabricante não entra no repositório e dado da empresa também não.

**Linhas.** Todas as LTs do parque, com: nome, tensão, comprimento, `Z1` e `Z0` (módulo e ângulo, ou R e X por km), os terminais e, quando houver, o KMZ das estruturas para dar vão a vão. É o que alimenta o plano de impedância (régua de «% da LT») e o localizador de falta. Fonte provável: os estudos de proteção e a planilha de parâmetros da empresa — **fora do repositório**, apontada por caminho como as amostras reais.

**Sinais digitais.** Todos os digitais dos relés do parque, por fabricante e modelo, com descrição e categoria. O formato já existe (`dicionario.csv`). O que falta é o volume — e a regra conservadora continua: **classificar só o que tem certeza**, campo vazio é valor legítimo.

Caminho que faz a base crescer sem ninguém sentar para catalogar: cadastrar **da própria tela da onda** e importar CSV em lote.

## Opcional por princípio

Regra dele: **nada na base é obrigatório.** Nenhuma função pode exigi-la — a base acelera, nunca destrava.

| gaveta | com base | sem base |
|---|---|---|
| sinais digitais | o digital aparece com nome e significado | aparece o nome cru que veio no arquivo |
| linhas / KMZ | escolhe a linha e os parâmetros vêm prontos | digita impedância e comprimento na tela |

É a regra de diagnóstico do projeto («avisa, nunca bloqueia») aplicada à base. Desligar uma gaveta não apaga nada: só faz o programa parar de consultá-la.

Consequência ainda por fazer: toda tela que consome a base precisa do **caminho manual ao lado**, e o que o usuário digitar à mão deve poder virar verbete com um clique.

## Onde mora a pasta

A pasta tem nome **fixo**: `database`.

```
<a pasta que o usuário escolher>/
└── database/
    ├── base.json         o nome na lista e a versão do formato
    ├── digitais/digitais.csv
    └── linhas/
<dados do usuário>/bases.json    qual base está ativa, quais já foram abertas, quais gavetas ligadas
```

- **Nome fixo** porque é por ele que o programa reconhece uma base que veio de outra pessoa; porque um `.gitignore` consegue barrar um nome fixo e não um inventado (o repositório é público); e porque tira uma decisão do caminho de quem só quer começar.
- O `bases.json` fica **fora** da base: é preferência desta máquina, e a base viaja num zip sem levar a opinião de quem a montou.
- A **camada da equipe** (pasta de rede) fica para depois. Precedência quando existir: **sua > equipe > programa**, com selo de procedência por linha.

**Buraco aberto, levantado por ele:** o `osclab.cmd` manda `OSCLAB_ROOT` e `OSCLAB_DATA_DIR` para a mesma pasta, então o padrão ainda aponta para dentro da pasta do programa — junto com o acervo (`library/`) e o cache. Decisão pendente: (A) mudar só a base de lugar, (B) mover a pasta de dados inteira para uma pasta do usuário no lançador, (C) deixar como está e digitar o caminho. Recomendação registrada: **B**.

## Na tela

- **Ícone:** pilha de discos (escolhido entre oito), em `--ic-base`. Cada gaveta tem o desenho de quem vai usá-la: grade (digitais), torres (linhas).
- **Tela inicial:** sem base, uma tarja âmbar que já diz que o programa funciona sem ela; com base, o mesmo lugar vira linha de estado com as contagens, e a gaveta desligada aparece riscada em vez de sumir.
- **Tela da base** (`/base`): criar ou escolher; depois, as gavetas com chave de habilitar e a tabela dos digitais em janela, com busca, edição da descrição, classificação do tipo e importação de CSV.
- **Escolher onde:** o botão `…` abre a janela de pasta **do próprio sistema** (processo à parte, via `tkinter`, nascendo por cima do navegador). Quando ela não abre, a tela cai num navegador de pastas desenhado na página, servido por `GET /api/base/pastas` — o navegador não entrega caminho absoluto de pasta a página nenhuma, e quem lista é o servidor, que está na máquina do usuário.
- **Prévia antes de criar:** a pasta escolhida em turquesa, `database/` e as gavetas marcadas como nome fixo, e a medida do caminho mais fundo contra os 260 caracteres do Windows — âmbar acima de 200, vermelho em 260, sem nunca bloquear o botão.
- Uma base cujo caminho sumiu **continua na lista**, inerte e explicada.

## Restrições que seguem valendo

- **Direito autoral:** manuais de fabricante não entram no repositório. O que entra é o dado factual escrito com as nossas palavras.
- **Dado da empresa:** a base e o histórico não entram no repositório, que é público. `/base/`, `/database/`, `/base-*/` e `/bases.json` estão no `.gitignore`, com a barra na frente para não barrarem `src/osclab/formats/base.py`.

## O que vem depois

1. Resolver o buraco do `OSCLAB_DATA_DIR` (decisão A/B/C acima).
2. Ligar o dicionário ao leitor: o digital da tela da onda passa a mostrar a descrição e a cor da categoria; o que não estiver catalogado continua com o nome cru.
3. Cadastrar da própria tela da onda: achou um digital sem nome, descreve ali e vira verbete.
4. A gaveta de linhas, junto com o módulo de localização de falta.
5. **Popular as duas gavetas** — todas as linhas e todos os sinais digitais (pedido dele em 20/10/2026, detalhado acima).
6. A gaveta de registros (histórico e análise de longo prazo).
7. A camada da equipe.
