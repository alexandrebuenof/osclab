# O plano alfa (87L) — decisões do painel

Decidido com o Alexandre em 20/10/2026, em cima das maquetes.

## É por fase

O 87L é por fase: 87LA, 87LB, 87LC — cada uma com o seu `k` e a sua decisão.
Uma falta AT põe a fase A fora da região e deixa B e C em −1; num plano só,
as três misturadas, a leitura deixaria de dizer *qual* fase.

**Entrada:** dois grupos trifásicos de corrente, um por terminal
(`grupo 1 · local`, `grupo 2 · remoto`), mais um **seletor de fase**.

**O seletor tem A, B, C, 3I₀ e I₂** (escolha dele). As sequências entram
porque os elementos 87LG (terra) e 87LQ (sequência negativa) são justamente
os que atuam quando a falta é resistiva e o plano da fase não chega a sair da
região de restrição.

**Ressalva que o painel tem de honrar:** os dois grupos precisam estar na
**mesma base**. TC de 600/5 de um lado e 1200/5 do outro, sem normalizar,
desloca todo o traçado por um fator 2 — e isso se lê no plano exatamente como
outfeed. O painel diz em que base está.

**Corrente insuficiente:** quando as duas correntes de um ciclo estão abaixo
do limiar (≈ 0,05 pu), a razão é ruído dividido por ruído. Esses ciclos **não
recebem ponto**, e o pé do painel diz quantos foram e *quando* — antes da
falta ou depois da abertura do disjuntor. Isso aparece o tempo todo em 3I₀ e
I₂, que só existem durante a falta.

## O cabeçalho

    cursor 1 · grupo 1 · grupo 2 · fase · ⚙

Na engrenagem: escala **linear/logarítmica**, referência
(`k = I_rem/I_loc` ou `k = I_loc/I_rem`), e as camadas — **região do ponto
cego**, numerar ciclos, marcar onde atuaria.

**Padrão recomendado: escala logarítmica.** A região de restrição vai de
**1/6 a 6**. No linear o lado de baixo (0,167) vira um ponto colado na origem
e o de cima ocupa meio desenho — outfeed no terminal remoto literalmente não
cabe na tela. No log os dois lados ficam simétricos.

**«Trocar lado»** inverte a razão e espelha o plano: o que era |k| > 1 passa a
|k| < 1. Serve para conferir com o relatório do relé do outro terminal, que
calcula do ponto de vista dele.

## O botão «fasor» sobe para o menu de cima

`por amostra / por ciclo` **não fica no painel**: vai para a fileira de chaves
do cabeçalho da tela, ao lado do `filtro`, com setinha. É a regra que já
tínhamos — *se muda o número, é da família do filtro; se muda só como o número
aparece, é da engrenagem do painel.* O cálculo do fasor muda o número e vale
para todos os sinais, como o filtro.

**Padrão recomendado: por amostra**, com os pontos de ciclo desenhados por
cima. É o que faz a trajetória ser trajetória; «por ciclo» puro é a leitura
limpa, de relatório.

## Verde é da SEL; amarelo é nosso

O **setor de coroa verde** é a característica da SEL e nasce de dois ajustes
do relé: `87LR` (a razão, tipicamente 6) e `87LANG` (a abertura, 195°). Só se
desenha quando esses ajustes foram lidos do arquivo, e **nunca** sobre evento
de outro fabricante.

A **hachura amarela** não é ajuste de ninguém: é camada nossa, desenhada a
partir dos mesmos dois números, mostrando o trecho do eixo negativo que está
*dentro* da restrição e onde uma falta interna com outfeed se esconde. Por
isso ela é ligável/desligável na engrenagem.

## Outros fabricantes usam outro desenho

O plano alfa é a forma da SEL. O desenho dominante no resto do mercado é o
**diferencial percentual no plano operação × restrição** — `Iop = |I_loc +
I_rem|` no eixo vertical, `Irest` no horizontal, e uma reta (ou duas, com
joelho) separando restringir de atuar. Sai dos mesmos dados, então podemos
desenhar os dois a partir do mesmo registro; o que não podemos é cobrar de um
relé um critério que ele não usa. Os detalhes de cada fabricante ficam para
confirmar na hora de implementar.

## Estado

Dez maquetes publicadas no artefato do plano alfa (galeria «Dez cabeçalhos»,
C1…C10), sobre a moldura **P2** — a que tem a tabelinha do cursor ao lado, que
foi a escolhida. **Nada foi implementado ainda no programa.**

Depende de haver 411L ou 487E no parque — pergunta ainda em aberto.
