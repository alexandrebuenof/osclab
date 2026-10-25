# Ajustes manuais do plano de impedância — dez maquetes

Maquetes geradas em 20/10/2026, a pedido dele, antes de implementar.
**Todas funcionam**: digitar move a zona no desenho e a etiqueta de origem vira
«manual» na hora.

Artefato: <https://claude.ai/artifact/RDW2oMHeh8GcHojowGnNiv>

## O problema

O painel já sabia **ler** (bloco `SETTINGS` do `.CEV`, `.HDR`) e **sugerir**
(80 %, 120 %, 200 % dos parâmetros da linha). Faltava a terceira origem, que é
a mais usada: **digitar**. Quatro coisas precisam de entrada — os parâmetros da
linha `ZL`, o alcance de cada zona, o tempo de cada zona, e de qual dos seis
**grupos de ajustes** o painel puxou.

O risco não é ficar sem ajuste: é um número digitado parecer lido do relé.
Por isso toda maquete marca a origem por campo, e o traço do círculo muda
junto (cheio = lido, tracejado = sugerido, pontilhado = digitado).

## As dez

| nº | onde moram os ajustes | o que ela responde |
|---|---|---|
| A1 | menu suspenso do cabeçalho | **escolhida e implementada** |
| A2 | gaveta na coluna da tabelinha | dá para ver o desenho inteiro enquanto se digita |
| A3 | a própria ficha do rodapé vira campo | nenhum lugar novo para aprender |
| A4 | janela, como «editar grupos» | cabe tudo, mas tapa o desenho |
| A5 | arrastar a alça da zona no desenho | ajustar sem digitar |
| A6 | duas colunas: do relé × o seu | nunca apaga o lido; mostra a diferença em % |
| A7 | chips Z1/Z2/Z3 no cabeçalho | edita sem abrir nada |
| A8 | faixa de partida num COMTRADE puro | o painel abre pedindo, já com a sugestão |
| A9 | a % é o campo, o ohm é consequência | quem ajusta pensa em «80 % da linha» |
| A10 | seletor dos seis grupos de ajustes | conferir um grupo contra o outro |

Várias são combináveis: uma gaveta não briga com um chip no cabeçalho. As que
não foram implementadas seguem valendo como desenho pronto para quando o
assunto voltar — em especial a **A10**, que é a pendência dos grupos de ajustes.

## Defeitos achados rodando as maquetes

1. `const menu = caixaDeMenu(..., (m) => { menu.append(...) })` — o montar roda
   DENTRO do `caixaDeMenu`, antes de `menu` existir. Erro de inicialização.
2. A A6 usava a grade de cinco colunas da tabela normal; a coluna de 14 px —
   que ali é o «%» — engolia o campo onde se digita.
3. O ângulo de `ZL` caía na coluna do «% da LT», e um ângulo de 80 se lia como
   80 % da linha. **Apanhado por ele**, e foi o que separou os parâmetros da
   linha num bloco próprio e abriu lugar para o botão polar / R + jX.
