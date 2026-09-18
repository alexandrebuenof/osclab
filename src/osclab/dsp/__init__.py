"""Processamento de sinal: a cadeia que transforma amostras em fasores.

    amostras -> remove a componente DC -> janela de 1 ciclo -> DFT -> fasor

Tudo que vem depois no programa — componentes simétricas, harmônicos do inrush,
a trajetória da impedância no plano R-X, localização de falta — lê o resultado
desta cadeia. Ela é calculada UMA vez por registro.

O nome é `dsp/` e não `signal/` de propósito: `signal` é um módulo da biblioteca
padrão do Python, e ter um pacote com o mesmo nome confunde qualquer pessoa que
leia um traceback, mesmo o import absoluto do Python 3 resolvendo certo.

Entra no marco 0.4.
"""
