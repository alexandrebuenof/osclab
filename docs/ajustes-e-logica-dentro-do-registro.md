# Os ajustes e a lógica do relé vêm DENTRO do registro — anotado em 15/10/2026

**Não implementar ainda.** Pedido dele: «só anote isso para fazermos depois,
primeiro quero validar a parte dos layouts».

O `ideias.md` já dizia que vários itens do backlog (1, 2, 4, 5 e 6 —
localização de falta, direcionalidade, ajustes desenhados sobre o registro,
trajetória no plano R-X, ponto móvel no 51) dependem de **ler os ajustes do
relé**, e listava como pendência «de onde vêm os ajustes (RDB do AcSELerator,
arquivos SET_*, SCD, planilha, digitação)».

Esta anotação responde essa pendência: **em boa parte dos casos eles já estão
dentro do arquivo de oscilografia que o programa abre.** Nenhuma entrada nova,
nenhum cadastro, nenhum arquivo a mais para o usuário juntar.

---

## A distinção que organiza tudo

| | o que é | onde está |
|---|---|---|
| **estado da lógica** | o que cada elemento fez, amostra a amostra | já lido, nos canais digitais |
| **a lógica em si** | as equações e os ajustes que produziram aquilo | não lido |

O programa hoje mostra que o `TRIP` subiu em +331,25 ms. O que falta é poder
dizer **por que** ele subiu.

---

## No `.CEV` (SEL)

Os dois estão lá, no mesmo arquivo.

- **Estado:** os digitais — no registro de referência são 592 nomes por amostra
  (`TRIP`, `51G`, `LT01`, `SV01T`, `IN101`, `OUT101`…). Já lido.
- **Lógica:** o marcador `"SETTINGS"` no fim do arquivo. Dali para baixo vêm os
  ajustes do grupo ativo, e nos SEL isso inclui as **equações SELOGIC**
  (`TR`, `67P1TC`, `SV01`, `PSV…`).

**O leitor atual para exatamente nesse marcador.** Ver `_FIM_DOS_DADOS` e
`_ler_amostras`, em `src/osclab/formats/cev.py`: o bloco é reconhecido, usado
como fim das amostras e descartado. Está intacto no arquivo; é só começar a ler.

Forma do bloco (do registro de teste):

```
"SETTINGS","02E1"
"
Group 1

Z1MAG   := 2.14     Z1ANG   := 68.86
","0000"
```

Um campo CSV só, com quebras de linha dentro, e a soma de verificação no fim da
linha como em todo o resto do formato.

**Ressalva:** o que vem depende de como o evento foi extraído. Alguns relés e
algumas versões entregam o CEV só com o cabeçalho, sem o bloco de ajustes. O
leitor tem que tratar a ausência como normal, não como arquivo defeituoso —
regra do projeto: avisa, nunca bloqueia.

---

## No COMTRADE

**O padrão não prevê lógica nenhuma.** O que existe:

- **`.CFG`** — os canais digitais com nome. De novo o *estado*, não a lógica.
- **`.HDR`** — texto livre. É aqui que a SEL despeja o relatório de evento com
  os ajustes. Quando o arquivo vem junto, a lógica está nele — mas isso é
  **convenção de fabricante, não do padrão**: outro IED pode mandar `.HDR`
  vazio, ou nenhum.
- **`.INF`** — C37.111-1999/2013, com seções públicas e privadas para
  informação extra. Caberia ali de forma estruturada; na prática quase ninguém
  usa.
- **`.CFF`** — a versão 2013 empacota tudo num arquivo só, o HDR inclusive.

**O acervo já guarda `.hdr` e `.inf` quando vêm** (`EXTENSOES`, em
`src/osclab/library/acervo.py`); ninguém os abre ainda.

---

## Por que isso muda o programa, e não só acrescenta um recurso

Com os ajustes vindos do próprio registro, a «terceira classe de entrada»
prevista na arquitetura (ajustes, ao lado da oscilografia e do KMZ) deixa de
depender de o usuário achar e juntar um RDB ou um SCD. Para os registros que
trazem o bloco, o programa passa a poder:

- desenhar a curva do 50/51 e as zonas do 21 **com os valores daquele relé
  naquele dia**, e não com valores digitados;
- casar o instante de cada digital com a equação que o produziu;
- conferir o que o relé calculou contra o que o OscLab calcula — as colunas
  `ANAnn` do CEV (`V1M`, `3V0M`, `LI1M`…) já são a referência do próprio relé
  para as nossas componentes de sequência.

E mantém a independência de fabricante: o que se lê é um arquivo de evento, não
uma ferramenta proprietária.

---

## O primeiro passo, quando chegar a hora

Decisão pendente, para ele escolher:

1. **Começar pelo `SETTINGS` do `.CEV`** — fonte certa, formato já conhecido, já
   presente nos arquivos do acervo; ou
2. **Abrir primeiro os `.HDR` das amostras reais** — levantar o que o parque da
   distribuidora de fato entrega, antes de decidir onde investir.
