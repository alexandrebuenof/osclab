# Estética e vários registros — OscLab

Continuação de `decisoes-de-interface.md`, que registra as escolhas de
12/10. Este guarda a rodada de estética de 14/10 e o vocabulário combinado para
quando houver mais de uma oscilografia aberta.

---

## Estética: o que ele escolheu na página de propostas — 14/10/2026

Sessenta e seis propostas numeradas foram apresentadas numa página própria
(artefato «Estética do OscLab»). O que ele escolheu, por seção. **Escolhido não
é implementado**: a última coluna diz onde cada uma está.

| seção | escolha | estado |
|---|---|---|
| Logotipo | **L4 · Trinca** — três ondas defasadas de 120°, nas cores de fase | decidido |
| Logotipo, reserva | **L12 · Cursores** — guardar para eventual troca | guardado |
| Tela inicial | **I1 · Mosaico** — os módulos como cartões iguais, o disponível aceso | decidido |
| Módulo 1 | Oscilografia · ícone **1.1** (onda com o risco do disparo) | decidido |
| Módulo 2 | Linhas · ícone **2.1** (dois vãos e o condutor) | decidido |
| Módulo 3 | Trafo e alimentadores · ícone **3.3** (trafo, barra e vãos) | decidido |
| Módulo 4 | Ondas viajantes · ícone **4.1** (diagrama de Bewley) | decidido |
| Cabeçalho | **C3 · com ícone** em cada chave | **feito** |
| Fasorial | **F1 · engrenagem**, com referência e calculadora FORA dela | **feito** |
| Harmônicos | **H1 · engrenagem** | aberto — ver abaixo |
| Ajuda | **A2 · janela com abas**, e as dicas saem do rodapé | decidido |
| Versão | **V2 · janelinha «sobre»** | **feito** (14/10) |
| Barra de informações | **B2 · fichas rotuladas**, mais TC, TP e modelo | **feito** (14/10) |
| Um e vários registros | **U1 · uma linha por registro** | decidido |
| Crachá do IED | **T4 · caixa preenchida de 11 px**, letra 7,5 px | decidido |

### Os módulos futuros aparecem apagados, e CLICÁVEIS

O clique abre uma nota dizendo o que o módulo vai fazer e em que versão. Botão
apagado que não responde a nada é a tela discutindo com quem clicou.

### A janelinha «sobre» (V2), como ficou

A versão no canto do cabeçalho da tela de arquivos virou **botão**. Ela
respondia «qual versão», e a pergunta de quem olha para ela é «que programa é
este, e de quem». A janelinha responde as três coisas que ninguém adivinha:

- **versão** e **formatos lidos** por esta instalação;
- **licença** AGPL-3.0-or-later, com o que ela exige de quem *serve* o programa
  pela rede — que é o caso de uma ferramenta web na subestação;
- **titularidade**: os direitos patrimoniais são da distribuidora.

O texto mora no `index.html`, com o resto das palavras da página: quem for pôr a
razão social no lugar da frase genérica procura por ela ali, não dentro do
JavaScript. Não há linha de «o que mudou» porque não existe CHANGELOG — seria
prometer o que o programa não tem.

---

## Mais de uma oscilografia aberta — 14/10/2026

Nada disto está implementado. É o vocabulário combinado antes de existir, para
não ser inventado no meio da implementação.

### Com UM registro não há letra nem cor

A tira mostra o nome do arquivo, a estação e as fichas — e nada mais. A letra e
a cor **nascem no segundo arquivo**, que é quando passam a significar alguma
coisa. Decisão dele, contra o argumento de que a tira muda de forma ao abrir o
segundo registro.

### Com vários: IED A, IED B, IED C

Nome **genérico**, não o do arquivo: é o que se usa para falar («o trip do B veio
antes»). O nome do arquivo e a estação descem para a segunda linha.

- **crachá preenchido de 11 px** (T4) com a letra, na cor do IED;
- o mesmo crachá na legenda dos analógicos e nas tiras digitais;
- barra de 3 px na cor do IED à esquerda da linha da tira;
- a ficha **deslocamento** só existe com mais de um registro — com um não há em
  relação a quê.

### Nos analógicos: cor, não tracejado

Cada sinal pega a **próxima cor livre**, que é a regra que o programa já segue
(um gráfico nunca repete cor). As três primeiras são as de fase do IED A; as do
B saem de `CORES_NEUTRAS`, na ordem em que `corDoSinal` já as distribui —
laranja, verde, roxo.

Isso **abre mão da convenção azul-A / âmbar-B / vermelho-C no segundo IED**, e é
o crachá que paga a conta: ele diz de qual arquivo o traço veio, então a cor não
precisa mais dizer a fase sozinha.

**Medido antes de decidir:** `tools/paleta.py --sugerir` diz que não há folga
para cores novas — o melhor candidato guarda 0,94 do piso. Por isso a identidade
do IED não pode ser uma cor nova de traço: ela é a **letra**, e a cor do crachá
vem do cromo da interface (turquesa, roxo, verde), que nunca encosta num traço.

### TC e TP são de CADA CANAL, não do registro

No COMTRADE a relação sai de `primary`/`secondary` de cada canal analógico. A
ficha mostra um número só **quando todos os canais de corrente concordarem** (e
idem para tensão); quando discordarem, ela diz «vários» e abre a lista. Escolher
um e apresentá-lo como se fosse do registro inteiro seria o erro silencioso de
sempre.

### O modelo do equipamento é DEDUZIDO

Sai do `rec_dev_id` do cabeçalho — no SEL, a FID
(`FID=SEL-451-5-R316-V1-Z021012-D20160504` → `SEL-451-5`). Dedução, e a tela
precisa dizer isso.

---

## O que ficou aberto — 14/10/2026

- **O `tudo.py` não sabe fixtures, e isso esconde 239 testes.** Toda função de
  teste que peça uma fixture (`cliente`, `tmp_path`) é **pulada em silêncio** —
  nem entra na conta de «pularam». São 239 de 646. Eles existem, estão escritos
  e nunca rodam. Pendente: ensinar o harness a montar as duas fixtures, ou
  reescrever os testes sem elas.
- **Harmônicos (H1).** O cabeçalho só tem «janela» e «+ sinal»; uma engrenagem
  ali abriria vazia. O que há de ajustável está nas tarjas do rodapé, e elas são
  informação, não controle. Pergunta pendente: mover as tarjas para dentro da
  engrenagem, ou deixar como está até aparecer o que pôr lá?
- **Categorias de digitais.** O COMTRADE **não tem** campo de categoria: a linha
  é `Dn, id, ph, ccbm, y`. `ph` e `ccbm` existem, são texto livre e quase sempre
  vêm vazios. Agrupar por função exige deduzir pelo nome (a SEL é regular:
  `51P`, `50GF`, `67P2` são elementos; `TRIP`, `52A` são estado; `TLED_n` são
  LEDs) ou deixar o usuário definir. Esperando ele mandar linhas de digitais de
  um `.cfg` real para saber se o `ccbm` vem preenchido.
- **Moldura de baixo nos harmônicos.** Ela cai depois das tarjas do rodapé,
  longe do gráfico, e ali quase não é vista.
- **Dois IEDs num gráfico só.** Seis traços sobrepostos ficam cheios; com dois
  registros o «um por gráfico» deixa de ser preferência e vira o arranjo que
  funciona. Não desenhado ainda.
