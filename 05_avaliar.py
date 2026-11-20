"""Dia 5 — Avaliador: compara cada método com o gabarito.

Uso:
    python 05_avaliar.py                       # conjunto teste, tolerância 2 linhas
    python 05_avaliar.py --conjunto todos
    python 05_avaliar.py --conjunto dev        # use SÓ este para ajustar regras e prompt
Lê todos os results/normalized/*.jsonl (menos os _parcial).
Saída:
    results/metricas_<conjunto>.csv           método × categoria: TP, FP, FN, DUP, P, R, F1, IC 95%
    results/tolerancia_<conjunto>.csv         F1 com tolerância 0, 1, 2, 3, 5, 10
    results/erros/<conjunto>_<metodo>.csv     cada FP e FN, para a análise de erros
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451.avaliador import casar, ic_bootstrap, metricas  # noqa: E402
from sin451.comum import CATEGORIAS, ler_jsonl, ler_manifesto, salvar_csv  # noqa: E402

ORDEM = ["A0", "A1", "regras_proprias", "IA-pequeno", "IA-medio", "IA-grande"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--gabarito", default="gabarito/gabarito.jsonl")
    ap.add_argument("--resultados", default="results")
    ap.add_argument("--conjunto", default="teste", choices=["teste", "dev", "todos"])
    ap.add_argument("--tolerancia", type=int, default=2)
    a = ap.parse_args()

    res = Path(a.resultados)
    arquivos = {m["file"] for m in ler_manifesto(a.corpus) if a.conjunto == "todos" or m["conjunto"] == a.conjunto}
    gab = [g for g in ler_jsonl(a.gabarito) if g["file"] in arquivos]
    # Arquivos X_dev.jsonl / X_teste.jsonl (IA rodada só num conjunto) substituem X.jsonl naquele conjunto.
    escolhidos = {}
    for p in sorted((res / "normalized").glob("*.jsonl")):
        base, _, suf = p.stem.rpartition("_")
        if suf in ("parcial", "dev", "teste") and base:
            if suf == a.conjunto:
                escolhidos[base] = p
        else:
            escolhidos.setdefault(p.stem, p)
    caminhos = sorted(escolhidos.items(), key=lambda kv: (ORDEM.index(kv[0]) if kv[0] in ORDEM else 99, kv[0]))
    if not caminhos:
        raise SystemExit("Nenhum resultado em results/normalized. Rode 03_classico.py e 04_ia.py antes.")
    print(f"Conjunto '{a.conjunto}': {len(arquivos)} arquivos, {len(gab)} falhas no gabarito, tolerância ±{a.tolerancia}\n")

    tabela, sens = [], []
    print(f"{'método':16s} {'categoria':18s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'DUP':>4s} {'Prec':>6s} {'Rec':>6s} {'F1':>6s}  IC95% F1")
    for metodo, p in caminhos:
        achados = [f for f in ler_jsonl(p) if f["file"] in arquivos]
        ev = casar(achados, gab, a.tolerancia)
        for cat in CATEGORIAS + ("TOTAL",):
            c = None if cat == "TOTAL" else cat
            m = metricas(ev, c)
            lo, hi = ic_bootstrap(ev, arquivos, c)
            tabela.append({"metodo": metodo, "categoria": cat, **m, "f1_ic_inf": round(lo, 4), "f1_ic_sup": round(hi, 4),
                           "precisao": round(m["precisao"], 4), "recall": round(m["recall"], 4), "f1": round(m["f1"], 4)})
            print(f"{metodo:16s} {cat:18s} {m['TP']:4d} {m['FP']:4d} {m['FN']:4d} {m['DUP']:4d} "
                  f"{m['precisao']:6.1%} {m['recall']:6.1%} {m['f1']:6.1%}  [{lo:.1%}; {hi:.1%}]")
        print()
        for tol in (0, 1, 2, 3, 5, 10):
            sens.append({"metodo": metodo, "tolerancia": tol, "f1": round(metricas(casar(achados, gab, tol))["f1"], 4)})
        erros = []
        for tipo, f, g in ev:
            if tipo in ("FP", "FN"):
                it = f or g
                erros.append({"tipo": tipo, "file": it["file"], "line": it["line"], "category": it["category"],
                              "rule_id": (f or {}).get("rule_id", ""), "evidence": it.get("evidence", ""),
                              "modo": "", "observacao": ""})
        erros.sort(key=lambda e: (e["tipo"], e["category"], e["file"], e["line"]))
        salvar_csv(res / "erros" / f"{a.conjunto}_{metodo}.csv", erros,
                   ["tipo", "file", "line", "category", "rule_id", "evidence", "modo", "observacao"], excel=True)

    campos = ["metodo", "categoria", "TP", "FP", "FN", "DUP", "precisao", "recall", "f1", "f1_ic_inf", "f1_ic_sup"]
    salvar_csv(res / f"metricas_{a.conjunto}.csv", tabela, campos)
    salvar_csv(res / f"tolerancia_{a.conjunto}.csv", sens, ["metodo", "tolerancia", "f1"])
    print(f"Tabelas: {res / f'metricas_{a.conjunto}.csv'} | erros: {res / 'erros'}")


if __name__ == "__main__":
    main()
