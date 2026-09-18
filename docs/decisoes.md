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
