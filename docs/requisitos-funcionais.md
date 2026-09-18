# Requisitos funcionais

Levantados com Alexandre em 17/09/2026. Não é ordem de implementação; é o que a
ferramenta precisa ter.

## 0. Leitura de arquivos

- **COMTRADE** (edições 1991/1999/2013; `.cfg`+`.dat` e `.cff`; ASCII e binário
  16/32 bits) — base, cobre os sete fabricantes do parque (SEL, Siemens, GE, ABB,
  Schneider, Ingeteam, NOJA).
- **SEL `.CEV`** — segundo formato; só se valida com arquivos reais do parque.
- **PL4 (ATP)** — para validar algoritmos de localização de falta contra resposta
  conhecida.

Cada formato é um leitor independente sob `formats/`, todos devolvendo o mesmo
modelo interno. `registry.py` escolhe o leitor pelo conteúdo do arquivo.

### A armadilha do "todo mundo gera COMTRADE"

Geram — mas em sabores diferentes da mesma norma:

- **três edições** (1991, 1999, 2013), com campos de cabeçalho distintos;
- **dois empacotamentos**: `.CFG`+`.DAT` separados, ou `.CFF` único (2013);
- **três formas de guardar amostras**: ASCII, binário 16 bits, binário 32 bits;
- **fatores de conversão por canal** (`a` e `b`): o `.DAT` guarda inteiros crus;
  errar a conversão dá um gráfico bonito e completamente errado.

## 1. Detecção de filtrado × não filtrado

Não existe campo na norma que declare isso — tem que ser deduzido, cruzando:

1. taxa de amostragem (4 amostras/ciclo ⇒ filtrado; ≥16 ⇒ provável bruto);
2. conteúdo espectral do trecho de falta (só fundamental ⇒ filtrado);
3. presença de componente DC de decaimento na corrente pós-falta (⇒ bruto);
4. cabeçalho e nomes de canal (alguns fabricantes escrevem "filtered"/"raw").

**Regra de projeto acordada: o programa mostra o diagnóstico e permite o usuário
corrigir na mão. Avisa, nunca bloqueia.** Um palpite errado escondido
corromperia a localização de falta em silêncio.

Ao coletar arquivos de teste, priorizar os brutos: dá para simular o filtrado a
partir do bruto, o contrário não.

## 2. Operações com sinais analógicos

Canais derivados criados pelo usuário — p.ex. `IA+IB+IC` (residual calculada),
`3V0`, diferença entre terminais, soma de barramento.

Decisão em aberto: **menu fixo de operações × editor de expressão**. O editor é
mais flexível e é o que atende o caso que não anteciparmos.

Cuidados obrigatórios: coerência de unidade (não somar V com A), escala primário
× secundário, e canais com taxas de amostragem diferentes ou de arquivos
diferentes (exigem alinhamento e reamostragem antes).

## 3. Componentes simétricas automáticas

V0, V1, V2 e as correntes correspondentes, por Fortescue.

- **Componentes simétricas existem para fasores, não para amostras.** Só aparecem
  depois do Fourier. Calculadas janela a janela, viram séries temporais V1(t),
  V2(t), V0(t) — é isso que mostra a sequência negativa surgindo no instante da
  falta.
- **Convenção V0 × 3V0:** relés exibem 3V0. Precisa ficar explícito na tela qual
  está sendo mostrada, para não haver fator 3 de diferença silencioso.
- **Sequência de fases ABC × ACB** configurável: numa instalação ACB, V1 e V2
  trocam de lugar.
- Razão V2/V1 como indicador de desequilíbrio.

## 4. Múltiplas oscilografias e alinhamento temporal

Abrir mais de um registro ao mesmo tempo e alinhá-los.

**Contexto que define a prioridade:** o GPS da distribuidora não é confiável, e
relés de linha em subestações diferentes podem ter diferenças de tempo
consideráveis. Por isso o alinhamento por descontinuidade é a via principal,
apesar de não ser o mais preciso em tese.

Estratégias:

1. **Carimbo de tempo absoluto** (GPS/IRIG-B) — exato quando existe sincronismo.
2. **Descontinuidade** — instante da falta em cada registro. A escolha principal
   aqui.
3. **Correlação cruzada** de um sinal comum — robusta, mas perde força entre dois
   terminais de uma linha, onde as correntes não são o mesmo sinal.
4. **Ajuste manual** — sempre presente como escape.

O usuário escolhe o método num seletor **visível** junto da barra de tempo, com o
método em uso sempre à vista. O padrão é automático: começa pelo carimbo de tempo
quando os dois arquivos declaram relógio sincronizado, e cai para descontinuidade
quando não — dizendo qual escolheu e por quê. A preferência fica salva na
configuração.

Cuidados:

- O melhor detector de descontinuidade não é "derivada grande" (ruído dispara), e
  sim a **diferença entre o ciclo atual e o ciclo anterior** (grandezas delta) —
  é o que os próprios relés usam — ou variação de RMS em janela deslizante.
- A falta **não chega ao mesmo instante nos dois terminais**: há tempo de
  propagação. Desprezível em linha curta, não em linha longa.
- Registros com taxas diferentes precisam ser **reamostrados para uma base
  comum** antes de qualquer comparação.
- **Precisão do alinhamento por evento é de uma amostra**: 1,0 ms (22,5°) a 16
  amostras/ciclo; 0,52 ms (11,25°) a 32; 0,17 ms (3,75°) a 96, em 60 Hz. Serve
  para olhar e comparar, **não** para calcular fasor sincronizado.
- Consequência: para localização de falta a dois terminais usar o método **não
  sincronizado** (sequência negativa), que estima o ângulo de defasagem dos
  próprios dados e não depende de alinhamento nenhum.

Ganho barato: o COMTRADE tem campo de qualidade de tempo no cabeçalho. Ler e
exibir "relógio sem sincronismo — não confie no carimbo de tempo".

## 5. Fourier e harmônicos

Janela deslizante de um ciclo → DFT → magnitude de cada harmônico ao longo do
tempo. Aplicação citada: energização (inrush), onde a **2ª harmônica** é o
marcador; a 5ª indica sobre-excitação.

**Para enxergar a 2ª harmônica a janela precisa ser de ciclo inteiro** — meia
janela responde mais rápido, mas não resolve harmônicos pares. Compromisso
explícito entre resolução no tempo e em frequência.

Exibir o conteúdo harmônico em **porcentagem da fundamental**, que é como a
equipe lê.

## 6. Localização de faltas

A discutir em conversa própria. Ver também `ideias.md`.

## Decisões em aberto

- Operações analógicas: menu fixo × editor de expressão.
- Exibir V0 ou 3V0 por padrão (ou ambas, rotuladas).
- Qual estratégia de alinhamento implementar primeiro.
- Se a detecção de descontinuidade será compartilhada entre o alinhamento e a
  análise automática (provavelmente sim — mesmo algoritmo, dois usos).
