"""Compara findings com o gabarito e calcula TP, FP, FN, precisão, recall e F1.

Regra de casamento (vai para o relatório):
1. Só contam findings das 3 categorias (OUT_OF_SCOPE é ignorado).
2. Findings iguais (mesmo arquivo, categoria e linha) contam uma vez só.
3. Um finding casa com um item do gabarito do MESMO arquivo e MESMA categoria,
   se a distância de linhas for <= tolerância. Cada item casa no máximo uma vez
   (primeiro os pares mais próximos).
4. Finding sem par = FP, exceto se estiver a <= tolerância de um item que já foi
   casado (mesma falha apontada duas vezes): conta como "duplicado", não como FP.
5. Item do gabarito sem par = FN.
"""
import random
from collections import defaultdict

from .comum import CATEGORIAS


def casar(achados, gabarito, tol):
    """Devolve lista de eventos: (tipo, item) com tipo em TP/FP/FN/DUP."""
    ach = {}
    for f in achados:
        if f["category"] in CATEGORIAS:
            ach.setdefault((f["file"], f["category"], int(f["line"])), f)
    grupos_a, grupos_g = defaultdict(list), defaultdict(list)
    for (arq, cat, _), f in ach.items():
        grupos_a[(arq, cat)].append(f)
    for g in gabarito:
        grupos_g[(g["file"], g["category"])].append(g)
    eventos = []
    for chave in set(grupos_a) | set(grupos_g):
        fs, gs = grupos_a.get(chave, []), grupos_g.get(chave, [])
        pares = sorted((abs(int(f["line"]) - int(g["line"])), i, j)
                       for i, f in enumerate(fs) for j, g in enumerate(gs)
                       if abs(int(f["line"]) - int(g["line"])) <= tol)
        usados_f, usados_g = set(), set()
        for _, i, j in pares:
            if i not in usados_f and j not in usados_g:
                usados_f.add(i)
                usados_g.add(j)
                eventos.append(("TP", fs[i], gs[j]))
        for i, f in enumerate(fs):
            if i in usados_f:
                continue
            perto = any(abs(int(f["line"]) - int(gs[j]["line"])) <= tol for j in usados_g)
            eventos.append(("DUP" if perto else "FP", f, None))
        for j, g in enumerate(gs):
            if j not in usados_g:
                eventos.append(("FN", None, g))
    return eventos


def metricas(eventos, categoria=None):
    c = defaultdict(int)
    for tipo, f, g in eventos:
        cat = (f or g)["category"]
        if categoria is None or cat == categoria:
            c[tipo] += 1
    tp, fp, fn = c["TP"], c["FP"], c["FN"]
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "DUP": c["DUP"], "precisao": p, "recall": r, "f1": f1}


def ic_bootstrap(eventos, arquivos, categoria=None, n=1000, semente=451):
    """Intervalo de confiança de 95% do F1, reamostrando ARQUIVOS (bootstrap)."""
    por_arq = defaultdict(list)
    for e in eventos:
        por_arq[(e[1] or e[2])["file"]].append(e)
    arquivos = list(arquivos)
    if not arquivos:
        return 0.0, 0.0
    rnd = random.Random(semente)
    valores = []
    for _ in range(n):
        amostra = [e for a in (rnd.choice(arquivos) for _ in arquivos) for e in por_arq.get(a, [])]
        valores.append(metricas(amostra, categoria)["f1"])
    valores.sort()
    return valores[int(0.025 * n)], valores[int(0.975 * n) - 1]
