"""Dia 6 — Gráficos para o relatório e os slides (PNG em results/figuras).

Uso:  python 06_graficos.py            (conjunto teste)
      python 06_graficos.py --conjunto todos
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches  # noqa: E402,F401
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401

sys.path.insert(0, str(Path(__file__).parent))
from sin451.comum import CATEGORIAS, ler_csv  # noqa: E402

AZUL, LARANJA, VERDE = "#2a78d6", "#eb6834", "#1baf7a"
TINTA, CINZA, GRADE = "#0b0b0b", "#52514e", "#e4e3df"
NIVEIS = ["IA-pequeno", "IA-medio", "IA-grande"]
ROTULO = {"A0": "A0\nHadolint+Checkov", "A1": "A1\nA0 + regras", "regras_proprias": "Só regras\npróprias",
          "IA-pequeno": "IA\npequeno", "IA-medio": "IA\nmédio", "IA-grande": "IA\ngrande"}
CURTO = {"A0": "A0", "A1": "A1", "regras_proprias": "Regras", "IA-pequeno": "IA peq.", "IA-medio": "IA méd.", "IA-grande": "IA gr."}
CAT_PT = {"UNPINNED_VERSION": "Versão não fixada", "ROOT_USER": "Roda como root",
          "HARDCODED_SECRET": "Segredo no arquivo", "TOTAL": "Total"}


def estilo(ax, titulo):
    ax.set_title(titulo, loc="left", fontsize=12, color=TINTA, pad=12)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(CINZA)
    ax.tick_params(colors=CINZA, labelsize=9, length=0)
    ax.yaxis.grid(True, color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)


def cor(metodo):
    return LARANJA if metodo.startswith("IA") else AZUL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", default="results")
    ap.add_argument("--conjunto", default="teste")
    a = ap.parse_args()
    res = Path(a.resultados)
    linhas = ler_csv(res / f"metricas_{a.conjunto}.csv")
    for l in linhas:
        for k in ("precisao", "recall", "f1", "f1_ic_inf", "f1_ic_sup"):
            l[k] = float(l[k])
    metodos = list(dict.fromkeys(l["metodo"] for l in linhas))
    total = {l["metodo"]: l for l in linhas if l["categoria"] == "TOTAL"}
    pasta = res / "figuras"
    pasta.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans"})

    # 1) F1 total por método, com intervalo de confiança
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=200)
    xs = range(len(metodos))
    f1 = [total[m]["f1"] for m in metodos]
    err = [[total[m]["f1"] - total[m]["f1_ic_inf"] for m in metodos], [total[m]["f1_ic_sup"] - total[m]["f1"] for m in metodos]]
    ax.bar(xs, f1, width=0.6, color=[cor(m) for m in metodos], edgecolor="white", linewidth=2)
    ax.errorbar(xs, f1, yerr=err, fmt="none", ecolor=CINZA, elinewidth=1, capsize=3)
    for x, v in zip(xs, f1):
        ax.text(x, 0.02, f"{v:.0%}", ha="center", va="bottom", color="white", fontsize=10, fontweight="bold")
    ax.set_xticks(list(xs), [ROTULO.get(m, m) for m in metodos])
    ax.set_ylim(0, 1.14)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    estilo(ax, f"F1 por método (conjunto {a.conjunto}; barras = IC 95%)")
    ax.legend(handles=[matplotlib.patches.Patch(color=AZUL, label="Clássico"),
                       matplotlib.patches.Patch(color=LARANJA, label="IA (NVIDIA)")], frameon=False, loc="upper left", ncol=2, fontsize=9)
    fig.tight_layout()
    fig.savefig(pasta / "f1_por_metodo.png")
    plt.close(fig)

    # 2) Precisão, recall e F1 por categoria (um painel por categoria)
    fig, eixos = plt.subplots(1, 3, figsize=(11, 3.8), dpi=200, sharey=True)
    for ax, cat in zip(eixos, CATEGORIAS):
        dados = {l["metodo"]: l for l in linhas if l["categoria"] == cat}
        largura = 0.26
        for k, (med, c) in enumerate((("precisao", AZUL), ("recall", LARANJA), ("f1", VERDE))):
            ax.bar([i + (k - 1) * largura for i in range(len(metodos))], [dados[m][med] for m in metodos],
                   width=largura, color=c, edgecolor="white", linewidth=1.5,
                   label={"precisao": "Precisão", "recall": "Recall", "f1": "F1"}[med])
        ax.set_xticks(range(len(metodos)), [CURTO.get(m, m) for m in metodos], rotation=45, ha="right", fontsize=8)
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        estilo(ax, CAT_PT[cat])
    h, r = eixos[0].get_legend_handles_labels()
    fig.legend(h, r, frameon=False, fontsize=9, loc="upper right", ncol=3)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(pasta / "prf_por_categoria.png")
    plt.close(fig)

    # 3) F1 × nível de modelo, com as linhas de referência do clássico
    niveis = [n for n in NIVEIS if n in total]
    if niveis:
        fig, ax = plt.subplots(figsize=(7, 4), dpi=200)
        ax.plot(range(len(niveis)), [total[n]["f1"] for n in niveis], color=LARANJA, linewidth=2, marker="o", markersize=8)
        for i, n in enumerate(niveis):
            ax.annotate(f"{total[n]['f1']:.0%}", (i, total[n]["f1"]), textcoords="offset points", xytext=(0, 9), ha="center", color=TINTA)
        for ref, estilo_l in (("A0", "--"), ("A1", ":")):
            if ref in total:
                ax.axhline(total[ref]["f1"], color=AZUL, linestyle=estilo_l, linewidth=1.5)
                ax.text(len(niveis) - 0.45, total[ref]["f1"] + 0.015, f"{ref} ({total[ref]['f1']:.0%})", va="bottom", color=CINZA, fontsize=9)
        ax.set_xticks(range(len(niveis)), [n.replace("IA-", "").replace("medio", "médio") for n in niveis])
        ax.set_xlim(-0.4, len(niveis) + 0.1)
        ax.set_ylim(0, 1.08)
        ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.set_xlabel("Nível do modelo", color=CINZA)
        estilo(ax, "F1 da IA por nível de modelo × método clássico")
        fig.tight_layout()
        fig.savefig(pasta / "f1_por_nivel.png")
        plt.close(fig)

    # 4) Sensibilidade à tolerância de linhas
    caminho = res / f"tolerancia_{a.conjunto}.csv"
    if caminho.exists():
        tol = ler_csv(caminho)
        fig, ax = plt.subplots(figsize=(7, 4), dpi=200)
        paleta = [AZUL, "#6250d6", VERDE, "#eda100", LARANJA, "#e34948"]
        for i, m in enumerate(metodos):
            pts = [(int(t["tolerancia"]), float(t["f1"])) for t in tol if t["metodo"] == m]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", markersize=5, linewidth=2,
                    color=paleta[i % len(paleta)], label=ROTULO.get(m, m).replace("\n", " "))
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.set_xlabel("Tolerância de linhas (±)", color=CINZA)
        ax.legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(1.02, 0.5))
        estilo(ax, "F1 conforme a tolerância de linhas")
        fig.tight_layout()
        fig.savefig(pasta / "sensibilidade_tolerancia.png", bbox_inches="tight")
        plt.close(fig)
    print(f"Figuras em {pasta}:")
    for p in sorted(pasta.glob("*.png")):
        print("  ", p.name)


if __name__ == "__main__":
    main()
