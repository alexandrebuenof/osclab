"""Localização de faltas.

Um módulo por método, todos cumprindo a mesma interface: entra um registro (ou
dois) e os parâmetros da linha, sai uma estimativa com a incerteza declarada.

Nota de projeto que vem da conversa com o Alexandre: o GPS da distribuidora não
é confiável, então o método de dois terminais a ser priorizado é o NÃO
sincronizado (sequência negativa), que trata o ângulo de defasagem como
incógnita e o estima dos próprios dados. Alinhar registros por descontinuidade
serve para OLHAR, não para calcular — a precisão de uma amostra vale 11 graus a
32 amostras por ciclo.

Entra no marco 0.6.
"""
