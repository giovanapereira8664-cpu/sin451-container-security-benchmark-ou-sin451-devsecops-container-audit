"""Dia 6 — Painel (interface gráfica) para a demonstração: um único painel.html.

Uso:  python 07_painel.py  (depois de 05_avaliar.py e 06_graficos.py)
Abre no navegador com dois cliques; funciona sem internet. Mostra as métricas, os gráficos
e um visualizador: escolha um arquivo e veja, linha a linha, o gabarito e o que cada método apontou.
"""
import argparse
import base64
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451.avaliador import casar  # noqa: E402
from sin451.comum import ler_csv, ler_jsonl, ler_manifesto, ler_texto, mascarar  # noqa: E402

PAGINA = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<title>SIN 451 — Painel de resultados</title><style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;color:#1b1b1a;background:#fcfcfb}
header{padding:20px 32px;border-bottom:1px solid #e4e3df}h1{font-size:22px;margin:0}header p{margin:4px 0 0;color:#52514e}
main{padding:20px 32px;max-width:1200px}h2{font-size:17px;margin:28px 0 10px}
table{border-collapse:collapse;font-size:13px}th,td{padding:5px 10px;border-bottom:1px solid #eceae5;text-align:right}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}th{color:#52514e;font-weight:600}
tr.total td{font-weight:600;background:#f4f3ef}.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px}
.figs img{width:100%;border:1px solid #eceae5;border-radius:6px;background:#fff}
select{font-size:14px;padding:4px 6px;max-width:100%}.leg{font-size:12px;color:#52514e;margin:8px 0}
pre{background:#fff;border:1px solid #e4e3df;border-radius:6px;padding:8px 0;overflow-x:auto;font-size:12.5px;line-height:1.55}
.l{display:flex;padding:0 10px}.l.marc{background:#fff7e6}.n{color:#9a988f;width:36px;flex:none;text-align:right;margin-right:12px}
.c{white-space:pre;flex:1}.b{display:inline-block;font:600 10.5px system-ui;padding:1px 6px;border-radius:9px;margin-left:6px;white-space:nowrap}
.TP{background:#dff3ea;color:#0d6b47}.FP{background:#fde4dc;color:#a33a12}.FN{background:#eee;color:#444;border:1px dashed #888}.G{background:#e3ecfb;color:#1e4f91}
</style></head><body><header><h1>Detecção de configuração insegura em Docker: clássico × IA</h1>
<p>SIN 451 — Segurança da Informação · UFV Rio Paranaíba · conjunto <b>__CONJ__</b> · __NARQ__ arquivos · __NGAB__ falhas no gabarito · tolerância ±__TOL__ linhas</p></header>
<main><h2>Métricas</h2>__TABELA__<h2>Gráficos</h2><div class="figs">__FIGS__</div>
<h2>Visualizador de arquivos</h2><select id="arq"></select> <select id="met"></select>
<p class="leg"><span class="b G">G</span> falha no gabarito · <span class="b TP">TP</span> acerto · <span class="b FP">FP</span> alarme falso · <span class="b FN">FN</span> falha que escapou · valores de segredos mascarados</p>
<pre id="cod"></pre></main><script>
const D=__DADOS__;const sa=document.getElementById('arq'),sm=document.getElementById('met'),cod=document.getElementById('cod');
Object.keys(D.arquivos).forEach(f=>sa.add(new Option(f,f)));D.metodos.forEach(m=>sm.add(new Option(m,m)));
const ab={UNPINNED_VERSION:'versão',ROOT_USER:'root',HARDCODED_SECRET:'segredo'};
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function mostra(){const a=D.arquivos[sa.value],ev=(D.eventos[sm.value]||{})[sa.value]||[];const marcas={};
 (a.gab||[]).forEach(g=>(marcas[g.line]=marcas[g.line]||[]).push(['G','G '+ab[g.category]]));
 ev.forEach(e=>(marcas[e.line]=marcas[e.line]||[]).push([e.tipo,e.tipo+' '+ab[e.category]+(e.rule?' · '+e.rule:'')]));
 cod.innerHTML=a.linhas.map((l,i)=>{const m=marcas[i+1]||[];return `<div class="l${m.length?' marc':''}"><span class="n">${i+1}</span><span class="c">${esc(l)}${m.map(x=>`<span class="b ${x[0]}">${esc(x[1])}</span>`).join('')}</span></div>`}).join('');}
sa.onchange=mostra;sm.onchange=mostra;mostra();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--gabarito", default="gabarito/gabarito.jsonl")
    ap.add_argument("--resultados", default="results")
    ap.add_argument("--conjunto", default="teste")
    ap.add_argument("--tolerancia", type=int, default=2)
    ap.add_argument("--saida", default="painel.html")
    a = ap.parse_args()
    res = Path(a.resultados)
    man = [m for m in ler_manifesto(a.corpus) if a.conjunto == "todos" or m["conjunto"] == a.conjunto]
    nomes = {m["file"] for m in man}
    gab = [g for g in ler_jsonl(a.gabarito) if g["file"] in nomes]

    arquivos = {}
    for m in sorted(man, key=lambda m: m["file"]):
        arquivos[m["file"]] = {"linhas": [mascarar(l) for l in ler_texto(Path(a.corpus) / m["file"]).splitlines()],
                               "gab": [{"line": g["line"], "category": g["category"]} for g in gab if g["file"] == m["file"]]}
    eventos, metodos = {}, []
    for p in sorted((res / "normalized").glob("*.jsonl")):
        if p.stem.rpartition("_")[2] in ("parcial", "dev", "teste"):
            continue
        metodos.append(p.stem)
        por = {}
        for tipo, f, g in casar([f for f in ler_jsonl(p) if f["file"] in nomes], gab, a.tolerancia):
            if tipo == "DUP":
                continue
            it = f if tipo != "FN" else g
            por.setdefault(it["file"], []).append({"tipo": tipo, "line": it["line"], "category": it["category"],
                                                   "rule": (f or {}).get("rule_id", "")})
        eventos[p.stem] = por

    tab = ["<table><tr><th>Método</th><th>Categoria</th><th>TP</th><th>FP</th><th>FN</th><th>Precisão</th><th>Recall</th><th>F1</th><th>IC 95% (F1)</th></tr>"]
    for l in ler_csv(res / f"metricas_{a.conjunto}.csv"):
        cls = ' class="total"' if l["categoria"] == "TOTAL" else ""
        tab.append(f"<tr{cls}><td>{html.escape(l['metodo'])}</td><td>{l['categoria']}</td><td>{l['TP']}</td><td>{l['FP']}</td><td>{l['FN']}</td>"
                   f"<td>{float(l['precisao']):.1%}</td><td>{float(l['recall']):.1%}</td><td>{float(l['f1']):.1%}</td>"
                   f"<td>{float(l['f1_ic_inf']):.0%}–{float(l['f1_ic_sup']):.0%}</td></tr>")
    tab.append("</table>")
    figs = "".join(f'<img alt="{p.stem}" src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}">'
                   for p in sorted((res / "figuras").glob("*.png")))
    pagina = (PAGINA.replace("__CONJ__", a.conjunto).replace("__NARQ__", str(len(man))).replace("__NGAB__", str(len(gab)))
              .replace("__TOL__", str(a.tolerancia)).replace("__TABELA__", "".join(tab)).replace("__FIGS__", figs or "<p>Rode 06_graficos.py</p>")
              .replace("__DADOS__", json.dumps({"arquivos": arquivos, "eventos": eventos, "metodos": metodos}, ensure_ascii=False).replace("</", "<\\/")))
    Path(a.saida).write_text(pagina, encoding="utf-8")
    print(f"Painel salvo em {a.saida}. Abra com dois cliques.")


if __name__ == "__main__":
    main()
