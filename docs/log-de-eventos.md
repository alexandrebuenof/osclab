# O log de eventos do relé — a fazer

Pedido dele em 20/10/2026. **Nada implementado.** Esta nota existe para o
recurso não ser inventado no meio da implementação.

## O que é

A lista de eventos que o relé grava com tempo absoluto e relativo — partida,
trip, abertura do disjuntor, atuação de cada elemento. É a **história** do
evento, em texto, ao lado das ondas.

Por que vale: 582 digitais são tira demais para ler uma sequência; 121 eventos
ordenados no tempo são a história. Para um registro Schneider, onde a lógica
não vem no arquivo, a lista de eventos é a única coisa que explica **por que**
o relé atuou.

## De onde vem, por fabricante

| fabricante | onde está | como entra |
|---|---|---|
| **Schneider/MiCOM** | `.hdr` («Fault log FT_RC») e `.txt`, lado a lado com o COMTRADE | ler o `.hdr`, que já acompanha o registro |
| **SEL** | o `.HDR` pode trazer o despejo de ajustes e SELOGIC; o histórico de eventos sai do comando `HIS` ou do `.CEV` | ler o que vier no registro; o resto é importação |
| **outros** | arquivo à parte, exportado do software do fabricante | **importar** `.txt` ou o que o relé der |

Ou seja, duas portas: **ler do registro quando o arquivo já traz**, e
**importar um arquivo de eventos** quando não traz.

**Confirmado por ele em 22/10/2026:** além do que vier dentro do registro,
tem de ser possível IMPORTAR o arquivo de eventos que alguns IEDs exportam à
parte — a Schneider e a GE fazem isso — e também um **`.txt`** qualquer. Ele
vai atrás dos fault logs de exemplo.

**O botão já tem lugar:** «eventos», na fileira de baixo do cabeçalho, logo
depois de «lógica». Por enquanto ele é cinza e clicável, e o clique diz que a
função ainda não existe — a mesma regra do dicionário sem dicionário. A segunda é a que vale
para o parque inteiro — é a mesma ideia do painel de lógica, que lê o bloco
`SETTINGS` quando existe e avisa quando não existe.

## O formato que a Schneider dá, como referência

    tAbs         | tRel(s) | xxx.yyy Descrição               | Valor
    20:11:36.443 |   0.972 | 040.041 DTOC  Starting IN>>     | Start
    20:11:36.458 |   0.987 | 035.071 MAIN  Gen. trip command | Start
    20:11:36.503 |   1.032 | 031.040 MAIN  CB open 3p        | Start

Quatro campos: tempo absoluto, tempo relativo ao início da gravação, endereço
numérico + descrição, e o valor/estado. O endereço `xxx.yyy` é estável entre
relés do mesmo modelo; no COMTRADE ele não aparece, então casar as duas listas
é pelo texto.

## Como deve aparecer na tela

- **Ligado ao cursor**: a linha do evento mais próximo do cursor fica marcada,
  e clicar num evento leva o cursor até ele. É o que liga a história à onda.
- **Terceiro conteúdo do painel de lógica**, ao lado de ajustes e lógica: para
  a SEL o painel mostra ajustes e SELOGIC; para a Schneider mostra eventos.
- **Com mais de um registro aberto**, cada evento carrega o crachá do IED, e a
  lista é uma só, ordenada no tempo — que é justamente o que responde «o trip
  do B veio antes ou depois?».
- Quando o registro não traz eventos e nenhum arquivo foi importado, o painel
  **avisa e diz o que importar** — nunca fica vazio sem explicação.

## O que isso também destrava

O bloco **Fault data** do `.txt` da Schneider traz duração da falta, tempo de
atuação, impedância medida e **localização de falta em % e em distância** — o
número do próprio relé. É a referência para comparar com o nosso localizador,
e entra pela mesma porta.
