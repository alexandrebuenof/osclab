# O dicionário

Status: **implementado** (o CSV, o editor e as categorias). Falta a aba de consulta a partir da tela da onda e as duas opções da engrenagem.

Nome oficial, escolhido por ele em 19/10/2026: **dicionário**. Não «sinais digitais», não «wordbits».

## O arquivo

`database\dicionario\dicionario.csv`

```csv
fabricante;modelo;sinal;descricao;categoria
;;TRIP;saída de trip do relé;trip
SEL;;51P1T;trip temporizado da sobrecorrente de fase, elemento 1;trip
SEL;351;IN101;entrada do 86BF da subestação;io
```

- UTF-8 **com BOM** e `;` — o par que faz o Excel brasileiro abrir nas colunas certas e com acento.
- A importação aceita `,` quando o arquivo vem com `,`, **acrescenta e corrige mas nunca apaga** o que já estava escrito, e uma categoria desconhecida vira vazia em vez de derrubar o arquivo.
- A chave é `(fabricante, modelo, sinal)`, sem olhar maiúscula.

## fabricante e modelo são opcionais

Decidido em 19/10/2026. **Em branco = vale para todos**, e o mais específico vence:

1. `SEL;351` — só naquele modelo
2. `SEL;(todos)` — qualquer relé da marca
3. `(todos);(todos)` — qualquer relé

O programa procura do mais específico para o mais genérico e para no primeiro que casar. Quando nada casa, mostra o nome cru e não inventa. É a mesma regra de precedência das camadas da base (sua > equipe > programa).

Por que assim: `fabricante` quase nunca desempata (a SEL escreve `51P1T`, a ABB escreve `OC4PTOC-TRIP`), e `modelo` cobraria o mesmo verbete quatro vezes para a família SEL. Mas os dois servem para o programa **casar sozinho** o dicionário com o registro aberto — o `.cfg` declara o equipamento no cabeçalho (`<ESTAÇÃO>,SEL-351,1999`).

Caso que nenhuma das duas resolve: `IN101` numa SE está ligada ao 86BF, noutra a outra coisa. Isso é por **instalação**, não por modelo — fica para quando houver banco de subestações.

## As categorias

O teste de cada uma: **ao olhar um registro, eu quero esses sinais juntos e nessa cor?**

| categoria | o que é | cor |
|---|---|---|
| `trip` | o relé mandou abrir | vermelho |
| `partida` | um elemento viu e começou a contar — é o que explica o trip | âmbar |
| `bloqueio` | impediu alguém de atuar: 86, LOP, torque control | roxo |
| `estado` | não age, é: 52A, religador pronto, local/remoto | azul |
| `io` | fio físico: IN101, OUT201 — significado da instalação | verde |
| `auxiliar` | variável interna: temporizador, latch, SELOGIC, gatilho | apagado, borda inteira |
| vazio | ainda não sei | apagado, borda tracejada |

**Bloqueio em roxo e não em laranja:** laranja ficaria a um passo do âmbar da partida, e são justamente essas duas que não podem ser confundidas quando se pergunta por que um elemento não atuou.

**Não existe `outros`.** Balde compete com o vazio, e tudo que dá dúvida acaba nele. Se um sinal real não couber em nenhuma das seis, falta **outra categoria com nome**.

**Saiu `alarme`:** ou o sinal bloqueia alguém, e é bloqueio, ou só anuncia, e é estado.

**Não entram categorias por função** (sobrecorrente, distância, diferencial): isso já está no nome do sinal (51, 21, 87). A categoria diz **o que o sinal fez no evento**, não de que proteção ele é.

**A pendência de catalogação é a descrição vazia, não a categoria vazia.** Um verbete descrito e sem categoria está pronto — só não vai ser colorido nem agrupado.

## O que falta

1. **A aba de consulta**: um ícone de dicionário ao lado do ícone da lógica, na barra principal. **Cinza quando não houver dicionário.** Abre uma busca; procura-se um sinal e vem a descrição e a categoria cadastradas. A descrição **não é escrita em mais lugar nenhum** por enquanto — nem nas tiras, nem nas equações.
2. **Duas opções na engrenagem** do painel de digitais, ativas só com dicionário:
   - **agrupar por categoria** — reordena as tiras;
   - **pintar por categoria** — só a cor, deixando a ordem como está.
3. Cadastrar a partir da consulta: procurou e não achou, oferece cadastrar ali, com o nome já preenchido.

## Fora de escopo, por decisão dele

- **Nada de descrição dentro do painel de lógica/ajustes.** O painel é seco: o que está na tela é o que está no arquivo.
- **Nada de conversão primário/secundário nos ajustes.** Ficam no valor que vierem. (O arquivo dá as relações TC/TP, mas não diz em que lado cada ajuste foi escrito — e a maioria dos ajustes nem é conversível: dial, tempo, curva e ângulo não mudam de lado.)
