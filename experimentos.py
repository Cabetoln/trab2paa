"""Execução em lote: roda o branch and bound e a heurística do Trabalho 1 em todas as
instâncias da literatura e gera as tabelas.

Uso (na pasta do projeto):
  python experimentos.py                         # limite de 60 s por instância, 1 processo
  python experimentos.py --limite 300 --processos 6
  python experimentos.py --conjuntos random nsfnet
  python experimentos.py --continuar             # pula as instâncias já em resultados/bb.csv

Gera resultados/bb.csv (uma linha por instância, gravada assim que a instância termina)
e resultados/tabela_bb.md (resumo por conjunto e tabela completa).
Com --processos > 1, várias instâncias rodam ao mesmo tempo, uma por processo; cada
uma continua com o seu próprio limite de tempo.
"""

import argparse
import csv
import platform
import sys
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

from sgcp import ler_instancia, guloso_classes, validar
from exato import branch_and_bound

REFERENCIAS = Path('instancias', 'referencias.csv')
CSV_SAIDA = Path('resultados', 'bb.csv')
MD_SAIDA = Path('resultados', 'tabela_bb.md')
COLUNAS = ['conjunto', 'instância', 'n', 'm', 'k', 'densidade', 'cores_t1', 'ub_inicial',
           'lb_raiz', 'lb', 'cores_bb', 'ótimo', 'nós', 'tempo_s', 'válido',
           'literatura', 'lit_ótimo', 'gap_bb', 'gap_t1']
AVISO_RING = ('Em ring, os arquivos ring_n{10,15,20}p1.0s{1..5} são cinco cópias idênticas de três '
              'instâncias (como notam Furini, Malaguti & Santini, 2018); as médias de ring contam '
              'cada uma dessas três instâncias cinco vezes.')


def ler_referencias():
    """{instância: (valor, é_ótimo, fonte)} a partir de instancias/referencias.csv."""
    if not REFERENCIAS.is_file():
        return {}
    with open(REFERENCIAS, encoding='utf-8', newline='') as f:
        return {l['instancia']: (int(l['valor']), l['otimo'] == 'sim', l['fonte'])
                for l in csv.DictReader(f)}


def rodar(tarefa):
    """Roda uma instância (executado em um processo separado quando --processos > 1)."""
    conjunto, caminho, limite, estrategia, ref = tarefa
    inst = ler_instancia(caminho)
    reps_h, cores_h = guloso_classes(inst)
    r = branch_and_bound(inst, limite, estrategia)
    valido = not validar(inst, r['representantes'], r['cores']) and not validar(inst, reps_h, cores_h)
    n, m = inst['n'], inst['m']
    cores_t1 = len(set(cores_h[1:]))
    linha = {'conjunto': conjunto, 'instância': inst['nome'], 'n': n, 'm': m, 'k': inst['k'],
             'densidade': f'{2 * m / (n * (n - 1)):.4f}' if n > 1 else '0',
             'cores_t1': cores_t1, 'ub_inicial': r['ub_inicial'], 'lb_raiz': r['lb_raiz'],
             'lb': r['lb'], 'cores_bb': r['n_cores'], 'ótimo': 'sim' if r['otimo'] else 'não',
             'nós': r['nos'], 'tempo_s': f'{r["tempo_ms"] / 1000:.3f}',
             'válido': 'sim' if valido else 'não',
             'literatura': '', 'lit_ótimo': '', 'gap_bb': '', 'gap_t1': ''}
    if ref:
        valor, otimo, _ = ref
        linha.update({'literatura': valor, 'lit_ótimo': 'sim' if otimo else 'não',
                      'gap_bb': f'{100 * (r["n_cores"] - valor) / valor:.2f}',
                      'gap_t1': f'{100 * (cores_t1 - valor) / valor:.2f}'})
    return linha


def ler_csv():
    if not CSV_SAIDA.is_file():
        return []
    with open(CSV_SAIDA, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def num(x, casas=2):
    return f'{x:.{casas}f}'.replace('.', ',')


def resumo(linhas):
    """Médias por conjunto (a primeira linha é o cabeçalho)."""
    tabela = [['Conjunto', 'Instâncias', 'Ótimo provado', 'Cores T1 (média)', 'Cores B&B (média)',
               'B&B melhor/igual que T1', 'Com referência', 'B&B = literatura', 'Gap T1 (%)',
               'Gap B&B (%)', 'Tempo médio (s)']]
    for conjunto in dict.fromkeys(l['conjunto'] for l in linhas):
        ls = [l for l in linhas if l['conjunto'] == conjunto]
        com_ref = [l for l in ls if l['literatura'] != '']
        melhor = sum(int(l['cores_bb']) < int(l['cores_t1']) for l in ls)
        igual = sum(int(l['cores_bb']) == int(l['cores_t1']) for l in ls)
        tabela.append([
            conjunto, str(len(ls)), str(sum(l['ótimo'] == 'sim' for l in ls)),
            num(sum(int(l['cores_t1']) for l in ls) / len(ls)),
            num(sum(int(l['cores_bb']) for l in ls) / len(ls)),
            f'{melhor}/{igual}', str(len(com_ref)),
            str(sum(int(l['cores_bb']) == int(l['literatura']) for l in com_ref)),
            num(sum(float(l['gap_t1']) for l in com_ref) / len(com_ref)) if com_ref else '',
            num(sum(float(l['gap_bb']) for l in com_ref) / len(com_ref)) if com_ref else '',
            num(sum(float(l['tempo_s']) for l in ls) / len(ls), 3)])
    total = [l for l in linhas]
    tabela.append(['**total**', str(len(total)), str(sum(l['ótimo'] == 'sim' for l in total))]
                  + [''] * (len(tabela[0]) - 3))
    return tabela


def tabela_md(tabela):
    texto = ['| ' + ' | '.join(str(c) for c in linha) + ' |' for linha in tabela]
    texto.insert(1, '|' + '---|' * len(tabela[0]))
    return texto


def salvar_md(linhas, args):
    linhas = sorted(linhas, key=lambda l: (l['conjunto'], l['instância']))
    texto = [
        '# Resultados do branch and bound', '',
        f'Gerado por `python experimentos.py` em {datetime.now():%Y-%m-%d %H:%M}.', '',
        f'- Limite de tempo por instância: {args.limite:g} s; estratégia: `{args.estrategia}`; '
        f'processos em paralelo: {args.processos}.',
        f'- Plataforma: Python {platform.python_version()}, {platform.system()} {platform.release()}, '
        f'{platform.processor() or platform.machine()}.',
        '- T1 = heurística gulosa do Trabalho 1 (`guloso_classes`).',
        '- ub_inicial = UB após o guloso iterado; lb_raiz = maior limite inferior da raiz '
        '(clique de grupos e cobertura por cliques).',
        '- lb / cores_bb = limites inferior e superior ao fim do B&B; ótimo = `sim` quando '
        'lb = cores_bb (ótimo provado).',
        '- literatura = valor de `instancias/referencias.csv` (Furini et al., 2018; '
        'lit_ótimo = `não` quando é só o melhor conhecido); gap = 100 · (cores − literatura) / literatura.',
        '', '## Resumo por conjunto', ''] + tabela_md(resumo(linhas))
    if any(l['conjunto'] == 'ring' for l in linhas):
        texto += ['', AVISO_RING]
    texto += ['', '## Todas as instâncias', '']
    texto += tabela_md([COLUNAS] + [[l[c] for c in COLUNAS] for l in linhas])
    MD_SAIDA.write_text('\n'.join(texto) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Experimentos do branch and bound para a SGCP.')
    parser.add_argument('--limite', type=float, default=60, help='segundos por instância (padrão 60)')
    parser.add_argument('--estrategia', default='hibrida',
                        choices=['hibrida', 'descendente', 'ascendente'])
    parser.add_argument('--processos', type=int, default=1, help='instâncias em paralelo (padrão 1)')
    parser.add_argument('--conjuntos', nargs='+', default=['random', 'nsfnet', 'ring'])
    parser.add_argument('--continuar', action='store_true',
                        help='mantém as linhas de resultados/bb.csv e roda só o que falta')
    args = parser.parse_args()

    referencias = ler_referencias()
    feitas = ler_csv() if args.continuar else []
    ja = {l['instância'] for l in feitas}
    tarefas = []
    for conjunto in args.conjuntos:
        for caminho in sorted(Path('instancias', conjunto).glob('*.txt')):
            if caminho.stem not in ja:
                tarefas.append((conjunto, str(caminho), args.limite, args.estrategia,
                                referencias.get(caminho.stem)))
    # as maiores primeiro, para o paralelismo não terminar com uma instância longa sozinha
    tarefas.sort(key=lambda t: -Path(t[1]).stat().st_size)

    Path('resultados').mkdir(exist_ok=True)
    novo = not (args.continuar and CSV_SAIDA.is_file())
    with open(CSV_SAIDA, 'w' if novo else 'a', encoding='utf-8', newline='') as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        if novo:
            escritor.writeheader()
        print(f'{len(tarefas)} instâncias a rodar (limite {args.limite:g} s, {args.processos} processo(s)).')
        resultados = feitas

        def gravar(i, linha):
            escritor.writerow(linha)
            f.flush()
            resultados.append(linha)
            print(f'[{i:3}/{len(tarefas)}] {linha["instância"]:20} T1={linha["cores_t1"]:>3} '
                  f'B&B={linha["cores_bb"]:>3} LB={linha["lb"]:>3} lit={linha["literatura"]!s:>3} '
                  f'ótimo={linha["ótimo"]} {linha["tempo_s"]:>8}s', flush=True)

        if args.processos > 1:
            with Pool(args.processos) as pool:
                for i, linha in enumerate(pool.imap_unordered(rodar, tarefas), 1):
                    gravar(i, linha)
        else:
            for i, tarefa in enumerate(tarefas, 1):
                gravar(i, rodar(tarefa))

    salvar_md(resultados, args)
    print('\n' + '\n'.join(tabela_md(resumo(resultados))))
    print(f'\nTabelas salvas em {CSV_SAIDA} e {MD_SAIDA}')


if __name__ == '__main__':
    sys.setrecursionlimit(10000)
    main()
