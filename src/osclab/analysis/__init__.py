"""Interpretação da perturbação.

Detecção de descontinuidade (comparando o ciclo atual com o anterior, que é o
que os próprios relés fazem — e não derivada grande, que o ruído dispara),
classificação da falta, ângulo de incidência, inrush, cabos batendo.

O detector de descontinuidade nasce aqui, e não dentro do alinhamento, porque
serve a dois donos: alinhar registros de subestações diferentes e disparar a
análise automática. Um algoritmo, dois consumidores.

Entra no marco 0.5.
"""
