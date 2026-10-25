# Comandos de teclado estratégicos — ideia do Alexandre (12/10/2026)

**Não implementar ainda.** O painel de harmônicos nasceu manual, pelo
«+ adicionar gráfico», como o fasorial. Os comandos vêm depois.

Separado de `ideias.md` porque é um assunto que vai crescer: ele já previu
comandos personalizáveis pelo usuário.

## A ideia

Com um **gráfico selecionado** — a mesma seleção que o arrastar já usa, clicando
em qualquer parte vazia do gráfico —, uma tecla gera outro painel a partir dos
sinais dele.

| tecla | o que faz |
|---|---|
| `f` | gera um **diagrama fasorial** com as variáveis do gráfico selecionado |
| `q` | faz o **filtro de Fourier** (harmônicos / qualidade de energia) do gráfico selecionado |

## As três ressalvas que ele mesmo levantou

1. **Tem que haver gráfico selecionado.** O comando não adivinha sobre o que
   agir, e agir sobre "o último" seria pior que não agir.
2. **Alguns comandos só fazem sentido no modo avançado.** O de Fourier é o
   caso: o filtrado apaga justamente o que ele mede. Fica a decidir se o
   comando é recusado com aviso ou se ele próprio troca de modo.
3. **Futuramente, permitir que o usuário crie comandos próprios.**

## Regra de precedência já combinada

Se houver **sinal destacado** (clique no traço ou no nome da legenda) e gráfico
escolhido ao mesmo tempo, **ganha o sinal** — é o pedido mais específico. Com
nada selecionado, o comando não faz nada.

## O que já existe e será reaproveitado

- `painelEscolhido` — a seleção de painel que o arrastar usa.
- `selecionados` — a lista de sinais destacados, que o `Delete` já consome.
- `criarPainel(tipo)` e `trocarSinais(id, ids)` — criar o painel e pôr sinais
  nele são duas chamadas que já existem.

Ou seja: o comando é cola entre coisas prontas. O que ele exige de novo é a
tabela de teclas e, no dia dos comandos personalizados, um lugar para guardá-la.

## Teclas já ocupadas nesta tela

`1` e `2` (cursores), `←` `→` (andar uma amostra; com Shift, um ciclo), `Esc`
(tira os cursores), `Delete` (tira os sinais destacados), `Ctrl+Z` (desfaz),
`t` (alterna milissegundos/ciclos na tabela). `f` e `q` estão livres.

Evitar `F`: nesta tela "F" puxa para *filtro*, que é o botão do cabeçalho — e o
comando de Fourier faz o oposto dele (olha o bruto). Se `f` virar o fasorial,
vale conferir se isso confunde na prática.
