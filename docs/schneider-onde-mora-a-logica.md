# Schneider/MiCOM: o que vem no registro e onde mora a lógica

Lido em 19/10/2026 num registro real do Alexandre — um **P139** exportado pelo
**Easergy Studio V9.3.7**. Cinco arquivos com o mesmo nome, na pasta de
oscilografias fora do repositório.

## Os cinco arquivos

| arquivo | o que é |
|---|---|
| `.cfg` + `.dat` | COMTRADE gerado pelo Studio — 9 analógicos, **582 digitais** |
| `.sfd` | o registro **nativo** do relé, binário. Cabeçalho `PX 139 000 AEG · Daten-Rev: 634` (linhagem AEG → Alstom → Schneider). É dele que o Studio gera o COMTRADE |
| `.hdr` | **lista de eventos** («Fault log FT_RC»), 121 eventos numerados |
| `.txt` | a mesma lista, mais o bloco **Fault data** |

O `.cfg` traz `P139-634-732; F: 3.620782.9` na linha da estação e os digitais
com nome descritivo no formato `FUNÇÃO : Descrição` —
`DTOC : Trip signal tIN>>`, `LOGIC: Input 17 EXT`, `PSS  : PS 1 active`.

## A conclusão: a lógica NÃO vem no registro

Nenhum dos cinco arquivos traz equação nem ajuste. O que vem é o **resultado**
da lógica, evento a evento, com tempo absoluto e relativo ao início da
gravação:

    tAbs         | tRel(s) | xxx.yyy Descrição              | Valor
    20:11:36.443 |   0.972 | 040.041 DTOC  Starting IN>>    | Start
    20:11:36.458 |   0.987 | 035.071 MAIN  Gen. trip command| Start
    20:11:36.503 |   1.032 | 031.040 MAIN  CB open 3p       | Start

Dá para ler a cadeia inteira — partida da sobrecorrente de neutro, trip 15 ms
depois, abertura em 45 ms. Mas **quanto vale `IN>>`** e **a que `LOGIC Output
17` é igual** moram no arquivo de parâmetros do Easergy Studio, que não
acompanha o registro.

Os três mundos, lado a lado:

- **SEL**: ajustes + lógica dentro do registro (`.CEV`, bloco `SETTINGS`; ou
  despejados no `.HDR`).
- **Schneider**: só o que **aconteceu** — nenhum ajuste, nenhuma equação.
- **COMTRADE puro**: nada dos dois, por norma.

## O endereço `xxx.yyy`

Cada evento vem com um endereço numérico estável (`040.028 DTOC Trip signal
tIN>>`). É o identificador do sinal no relé, igual entre P139s. No COMTRADE o
endereço **não** aparece: lá o canal digital tem só o texto
(`DTOC : Trip signal tIN>>`). Quem quiser casar as duas listas casa pelo texto.

## O que isto vale para o OscLab

1. **O bloco «Fault data» é o relato do relé.** Traz duração da falta, tempo de
   atuação, impedância, reatância e **localização de falta em % e em
   distância** — o número do próprio relé, para comparar com o nosso
   localizador. No registro lido vieram vazios (`....`) porque foi falta à
   terra resolvida pela `IN>>` e o `FT_DA` não fechou o laço; numa falta de
   fase vêm preenchidos.
2. **A lista de eventos é melhor que a tira digital para ler a sequência.**
   582 digitais são tira demais; 121 eventos ordenados no tempo são a
   história. Sugere um terceiro conteúdo para o painel de lógica/ajustes:
   para a Schneider ele mostraria **eventos**, nos mesmos tempos do cursor.
3. **O dicionário quase não é preciso na Schneider.** O nome do digital já vem
   descritivo. Onde a SEL dá `51P1T` e exige cadastro, a Schneider entrega a
   descrição pronta.
4. **O `.sfd` não precisa ser lido.** Binário, sem documentação pública, e o
   próprio Studio já exporta o COMTRADE. Só valeria para quem não tem o Studio
   instalado.
