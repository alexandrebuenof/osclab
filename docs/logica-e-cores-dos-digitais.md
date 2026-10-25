# A lógica do relé e as cores dos digitais

Status: **em projeto.** As maquetes estão feitas; nada implementado ainda.

## De onde vem a lógica — a resposta curta

| | COMTRADE | `.CEV` (SEL) |
|---|---|---|
| **estado** da lógica (o que cada elemento fez, amostra a amostra) | sim, nos canais digitais do `.CFG` | sim, nos digitais |
| **a lógica em si** (ajustes e equações) | **não está no padrão** | sim, no bloco `"SETTINGS"` no fim do arquivo |

No COMTRADE, o que existe é convenção de fabricante, não padrão:

- **`.HDR`** — texto livre; é onde a SEL despeja o relatório de evento com os ajustes. Quando vem. Outro IED manda vazio, ou não manda.
- **`.INF`** — tem seções para informação extra; na prática quase ninguém usa.
- **`.CFF`** (2013) — empacota tudo num arquivo só, o HDR incluído. Mesma história, outra embalagem.

No `.CEV` os dois estão garantidos no mesmo arquivo, e nos SEL o bloco inclui as **equações SELOGIC** (`TR`, `PSV04`, `67P1TC`, `SV01`). O leitor de `.CEV` hoje reconhece esse bloco só para saber onde as amostras acabam e **descarta**; está intacto no arquivo.

Conclusão de projeto: a lógica é **oportunista**. Quando vem, enriquece; quando não vem, o programa segue igual. O database não substitui o que falta no arquivo — ele dá **nome** ao que vier.

## Decidido por ele em 19/10/2026

### Na engrenagem do painel de digitais

Duas opções novas, além da cor das tiras que já existe:

- **colorir por tipo** — trip em vermelho, partida em âmbar, estado em azul.
- **agrupar por tipo** — reordena as tiras: trips juntos, depois partidas, depois estados, e por fim os sem classificação.

As duas ficam **travadas quando não há database**, com a explicação no lugar: é ele que diz qual sinal é trip e qual é partida.

### O pincel — pintar um digital à mão

Requisito: funcionar **mesmo sem database**.

Forma escolhida por ele: **uma peça só, dois alvos** — um pincel e um círculo de cor. Clicar no pincel entra e sai do modo (o cursor vira pincel e as tiras ficam clicáveis); clicar **exatamente no círculo** abre as cores. Um não dispara o outro. **Sem quadradinho de cor nas tiras**: a cor da tira é a própria cor, no nome e no pulso.

Adotado: escolher uma cor na paleta já entra no modo de pintar. A pintura à mão **vence** a cor do tipo, e clicar de novo na mesma cor devolve o sinal à cor que ele teria.

Falta escolher como a paleta abre: pendurada no círculo, em anel, em fileira no cabeçalho, ou só o ícone com as últimas cores.

### O painel da lógica/ajustes

Nome definido por ele: **painel da lógica/ajustes** (na janela, «Lógica e ajustes»).

- Abre por um **ícone na barra principal**, ao lado do ímã e do primário/secundário — não no cabeçalho da página: é ferramenta de leitura do registro, como eles.
- A janela **flutua**: arrastável pela barra, redimensionável pelo canto, para ver a lógica ao mesmo tempo que os sinais. Nasce **abaixo** da fileira de chaves, para não tapar o botão que a abriu.
- **Buscador em todos os painéis** — procura por termo, ajuste e descrição; com o database desligado, só pelo nome.
- **Botão `database`** na barra da janela, com o ícone da pilha de discos e a palavra «database». Sem interruptor ao lado: aceso é ligado.
  - Desligar vale **só naquele painel**, e não mexe em mais nada do programa.
  - Desligado, a descrição **simplesmente não existe** — nenhum aviso de «desligado» entra no lugar. Pedido dele, e com razão: o recado repetido em toda linha é ruído.
  - **Sem database ativo, o botão fica travado** — visível e inerte, com a explicação no hover.
- Conteúdo: as equações como saem do arquivo (`PSV04 := IN104 OR (IN102 AND NOT 52A)`) e os ajustes, em duas seções.

Falta escolher como a equação é desenhada: em uma linha, quebrada por operador (como o AcSELerator mostra), ou com os termos coloridos por natureza (digital azul, variável SELOGIC roxo).

## Terminologia

Preferência dele (19/10/2026): **elemento 1, elemento 2** em vez de «estágio 1, estágio 2». A SEL chama de *level* no manual; a ABB chama de *stage*. **Decisão adiada** para quando a base estiver sendo montada de verdade — as maquetes já usam «elemento».

## Decisão pendente

**As cores pintadas à mão pertencem ao registro ou ao sinal?**

- **ao registro** — «neste evento, pintei o 67P2T de roxo». Some quando se abre outro registro; mora junto com o arranjo de painéis.
- **ao sinal, no database** — «67P2T do SEL-351 é sempre roxo». Vale para todos os registros daquele modelo — e aí a pintura à mão deixa de funcionar sem database.
- **os dois** — o database dá a cor padrão do sinal, o registro guarda a exceção daquele evento.

## As maquetes

- «A lógica do relé na tela da onda» — dez lugares, cada um com e sem database.
- «Pintar um digital à mão» — dez jeitos, com as opções da engrenagem no lugar.
- «O pincel e o painel da lógica» — o controle de dois alvos, em quatro variações, e a janela flutuante.
- «O painel da lógica/ajustes» — dez desenhos do painel, com buscador e o botão do database.
- «O painel com a lógica de verdade» — as equações SELOGIC, em três desenhos.
