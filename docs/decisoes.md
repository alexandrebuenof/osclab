# Decisões de projeto

Registro do que já está resolvido, do que está em aberto e do porquê de cada
escolha. Atualizar aqui sempre que uma decisão for tomada — é o que evita
rediscutir a mesma coisa daqui a três meses.

## Resolvido

| Assunto | Decisão | Por quê |
|---|---|---|
| **Nome** | OscLab | Nome próprio, neutro, sem herança de outro programa |
| **Linguagem** | Python | É onde estão as bibliotecas de sinal e de leitura de COMTRADE |
| **Interface** | HTML/CSS/JS servido em localhost | Sem instalar toolkit gráfico; o usuário abre no navegador que já tem |
| **Servidor** | Flask | Uma dependência, puro Python, traz roteamento/upload/JSON prontos |
| **Gráficos** | uPlot | ~45 KB, feito para séries temporais longas; zoom e pan fluidos com centenas de milhares de amostras |
| **Cálculo** | numpy, sempre vetorizado | Laço amostra a amostra em Python é inviável nesta escala |
| **Distribuição v1** | Exige Python instalado | Simplifica a v1; o `.exe` fica como possibilidade |
| **Repositório** | GitHub público | É o que dispensa token embarcado na atualização automática |
| **Licença** | AGPL-3.0-or-later | Impede fechar o código e comercializar, sem proibir uso comercial; a §13 cobre o caso de servir pela rede |
| **Titularidade** | Distribuidora | Aval da empresa obtido para publicar sob AGPL |
| **Formatos** | COMTRADE primeiro | Norma aberta; os sete fabricantes do parque a geram |
| **Arquitetura** | Modelo PAC CT, com ajustes | Ver `referencia-pac-ct.md` |
| **Alinhamento** | Descontinuidade como via principal | O GPS da distribuidora não é confiável |
| **Diagnósticos** | Mostrar e permitir corrigir | Avisa, nunca bloqueia; palpite nunca vira certeza |
| **Onde o cursor está** | A barra da onda, espelho do analógico | A tela é alta e o gráfico sai por cima; a barra aparece só com o cursor em movimento e sem analógico à vista, e espelha em vez de recalcular — se as duas discordassem, não haveria como saber qual acreditar |

## Para manter a porta do `.exe` aberta

Custam pouco agora e são caras de consertar depois:

1. **Todo caminho sai de `paths.py`** — o empacotamento muda onde os arquivos
   ficam; assim é um arquivo para ajustar, não cinquenta.
2. **Nada de import dinâmico por string** — o empacotador não enxerga a
   dependência e ela some do executável.
3. **Templates, CSS e JS declarados como recursos do pacote**, não procurados no
   disco por caminho relativo.

## Verificado contra a realidade (marco 0.2)

O leitor COMTRADE foi escrito depois de examinar registros reais do parque, e
não a partir da norma sozinha. O que apareceu e teve que ser tratado:

| Fabricante | O que o arquivo faz de estranho |
|---|---|
| Schneider MiCOM P139 | declara a edição `2001`, que não existe |
| Schneider | não escreve a linha do `timemult` |
| GE 850 | `nrates = 0`: taxa não declarada, tempo vem do carimbo por amostra |
| GE 850 | `.cfg` com fim de linha do Unix, não CRLF |
| SEL-TWFL | `.dat` termina com 64 bytes `0x1A`, enchimento do DOS |
| SEL-487E | 5760 canais digitais — a matriz de estados passa de 30 MB |
| vários | nome de subestação em cp1252, não UTF-8 |
| Siemens SIPROTEC | escreve o número do canal no campo `ccbm`, que a norma reserva ao equipamento vigiado |
| SEL-451, SEL-487E | gravam os terminais de TC/TP que ninguém cabeou, lendo ruído do conversor |

E o que apareceu no `.CEV` da SEL (marco 0.4), nenhum deles escrito em campo
nenhum do arquivo:

| O que o arquivo faz | Por que importa |
|---|---|
| a amostra vem em valor **eficaz**, não instantâneo | sem a raiz de 2 o filtrado aparece 41 % menor que o bruto do mesmo evento |
| a hora do cabeçalho é a do **disparo** | tomá-la como a da primeira amostra desloca o registro inteiro |
| as colunas `ANAnn` não são onda | são as grandezas que o próprio relé calculou; o nome delas está nos campos `ERAQnn` |
| o arquivo acaba com os **ajustes do relé** | depois do marcador `SETTINGS` ele deixa de ser CSV |

As três primeiras foram confirmadas contra o COMTRADE **bruto do mesmo evento
do mesmo relé** — a razão dos picos deu 1,4141, o início bateu em 0,3 ms e o
`TRIP` bateu dentro de um intervalo de amostragem.

Nenhuma dessas coisas está na norma. É por isso que o leitor não foi escrito
antes de os arquivos existirem.

## Em aberto

- **Operações com sinais:** menu fixo de operações × editor de expressão
  (`IA+IB+IC` digitado pelo usuário).
- **V0 ou 3V0** por padrão nas telas. Relés mostram 3V0; um fator 3 escondido
  gera confusão.
- **Pacote offline** (`vendor/`): se haverá, e para quais plataformas. Com numpy
  o pacote passa de poucos MB para dezenas, específico por plataforma e versão
  de Python.
- **De onde vêm os ajustes dos relés e os parâmetros de impedância de linha** —
  terceira classe de entrada do programa, além da oscilografia e do KMZ.
- **Sessão por visitante**: necessária se mais de uma pessoa usar a mesma
  instância, como na PAC CT. Hoje o programa escuta só em 127.0.0.1.

## Histórico das conversas

O registro completo das discussões está no projeto "Leitor de Oscilografia" no
Claude. Este `docs/` é a cópia versionada junto com o código.
