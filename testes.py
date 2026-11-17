"""Testes (unittest): o branch and bound é comparado com força bruta em instâncias pequenas.

A força bruta aqui serve só para conferir o resultado: enumera todas as seleções e,
para cada uma, testa c = 1, 2, ... cores por enumeração de colorações.
"""

import itertools
import random
import unittest
from pathlib import Path

from sgcp import ler_instancia, validar
from exato import branch_and_bound

PASTA = Path(__file__).parent


def gerar(n_grupos, tam_max, p, semente):
    """Instância aleatória: grupos com 1..tam_max vértices, cada aresta com probabilidade p."""
    rng = random.Random(semente)
    grupos, grupo_de = [[]], [0]
    v = 0
    for g in range(1, n_grupos + 1):
        tam = rng.randint(1, tam_max)
        grupos.append(list(range(v + 1, v + tam + 1)))
        grupo_de += [g] * tam
        v += tam
    n = v
    adj = [set() for _ in range(n + 1)]
    m = 0
    for a in range(1, n + 1):
        for b in range(a + 1, n + 1):
            if rng.random() < p:
                adj[a].add(b)
                adj[b].add(a)
                m += 1
    return {'nome': f'teste{semente}', 'n': n, 'm': m, 'k': n_grupos,
            'grupos': grupos, 'grupo_de': grupo_de, 'adj': adj}


def cromatico(vs, adj):
    """Número cromático por enumeração (só para grafos minúsculos)."""
    for c in range(1, len(vs) + 1):
        for cores in itertools.product(range(c), repeat=len(vs)):
            if all(cores[i] != cores[j] for i in range(len(vs)) for j in range(i + 1, len(vs))
                   if vs[j] in adj[vs[i]]):
                return c
    return 0


def forca_bruta(inst):
    return min(cromatico(list(sel), inst['adj'])
               for sel in itertools.product(*inst['grupos'][1:]))


class TestaExato(unittest.TestCase):
    def test_toy(self):
        inst = ler_instancia(PASTA / 'instancias' / 'exemplo' / 'toy.txt')
        r = branch_and_bound(inst)
        self.assertEqual(r['n_cores'], 2)
        self.assertTrue(r['otimo'])
        self.assertEqual(validar(inst, r['representantes'], r['cores']), [])

    def test_contra_forca_bruta(self):
        for semente in range(300):
            rng = random.Random(semente)
            inst = gerar(rng.randint(1, 7), rng.randint(1, 3), rng.choice([0.2, 0.4, 0.6, 0.8]), semente)
            r = branch_and_bound(inst, tempo_iterado=0.05)
            with self.subTest(semente=semente):
                self.assertTrue(r['otimo'])
                self.assertEqual(validar(inst, r['representantes'], r['cores']), [])
                self.assertEqual(max(r['cores'][1:]), r['n_cores'])
                self.assertEqual(r['n_cores'], forca_bruta(inst))

    def test_limites_com_tempo_curto(self):
        """Com o tempo esgotando no meio da busca, os limites continuam corretos:
        LB <= ótimo da literatura <= UB, e 'ótimo' só quando bate com a literatura."""
        import csv
        with open(PASTA / 'instancias' / 'referencias.csv', encoding='utf-8') as f:
            ref = {r['instancia']: int(r['valor']) for r in csv.DictReader(f) if r['otimo'] == 'sim'}
        nomes = ['random/n90p9t2s1', 'random/n100p5t2s1', 'random/n90p5t2s1',
                 'nsfnet/nsf_p0.5_s1', 'ring/ring_n15p0.5s1']
        for nome in nomes:
            inst = ler_instancia(PASTA / 'instancias' / f'{nome}.txt')
            otimo = ref[inst['nome']]
            for estrategia in ('hibrida', 'descendente', 'ascendente'):
                r = branch_and_bound(inst, limite_s=2, estrategia=estrategia)
                with self.subTest(instancia=nome, estrategia=estrategia):
                    self.assertEqual(validar(inst, r['representantes'], r['cores']), [])
                    self.assertLessEqual(r['lb'], otimo)
                    self.assertGreaterEqual(r['n_cores'], otimo)
                    if r['otimo']:
                        self.assertEqual(r['n_cores'], otimo)


if __name__ == '__main__':
    unittest.main()
