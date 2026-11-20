"""Dia 7 — Gera a apresentação (slides em HTML) com os seus resultados: apresentacao/index.html

Uso:  python 09_apresentacao.py
Antes: 05_avaliar.py, 06_graficos.py, 07_painel.py e 08_demonstracao.py (o que faltar vira um aviso no slide).
Edite os textos em apresentacao.json (nome, conclusões, limitações) e rode de novo.

A pasta apresentacao/ é um site completo e sem dependências: abra index.html com dois cliques,
ou publique a pasta (por exemplo, no GitHub Pages). Teclas: → ← para navegar, F tela cheia, P painel.
Para PDF: abra no Chrome, Ctrl+P, "Salvar como PDF" (cada slide vira uma página).
"""
import argparse
import base64
import html
import json
import shutil
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451.comum import CATEGORIAS, ler_csv, ler_jsonl, ler_manifesto  # noqa: E402
from sin451.conhecimento import CATEGORIAS_INFO  # noqa: E402

e = html.escape
ROTULO = {"A0": "A0 · Hadolint + Checkov", "A1": "A1 · A0 + regras próprias", "regras_proprias": "Só regras próprias",
          "IA-pequeno": "IA · modelo pequeno", "IA-medio": "IA · modelo médio", "IA-grande": "IA · modelo grande"}
MODOS = {"1": "formato não coberto", "2": "tag não reconhecida", "3": "pacote sem verificação", "4": "valor indireto",
         "5": "IA: linha errada/inventada", "6": "IA: categoria trocada"}


def ler(caminho, padrao=None, func=None):
    try:
        return func(caminho) if func else Path(caminho).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, ValueError, SystemExit):
        return padrao


def aviso(texto):
    return f'<p class="aviso">⚠ {e(texto)}</p>'


def fig(res, nome, alt):
    p = res / "figuras" / f"{nome}.png"
    if not p.exists():
        return aviso(f"Figura {nome}.png não encontrada: rode python 06_graficos.py")
    return f'<img class="fig" alt="{e(alt)}" src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}">'


def lista(itens):
    return "<ul>" + "".join(f"<li>{e(i)}</li>" for i in itens) + "</ul>"


def slide(conteudo, classe=""):
    return f'<section class="slide {classe}">{conteudo}</section>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--gabarito", default="gabarito/gabarito.jsonl")
    ap.add_argument("--resultados", default="results")
    ap.add_argument("--config", default="apresentacao.json")
    ap.add_argument("--saida", default="apresentacao")
    a = ap.parse_args()
    res, out = Path(a.resultados), Path(a.saida)
    out.mkdir(exist_ok=True)
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    man = ler(a.corpus, [], ler_manifesto)
    gab = ler(a.gabarito, [], ler_jsonl)
    conj = "teste" if (res / "metricas_teste.csv").exists() else "todos"
    met = ler(res / f"metricas_{conj}.csv", [], ler_csv)
    modelos = {k: v for k, v in (json.loads(ler("modelos.json", "{}")) or {}).items() if not k.startswith("_")}
    ev = json.loads(ler(res / "evidencias" / "evidencias.json", "null") or "null")
    S = []

    # 1 capa
    S.append(slide(f'<p class="kicker">{e(cfg["disciplina"])}</p><h1>{e(cfg["titulo"])}</h1>'
                   f'<p class="sub">{e(cfg["subtitulo"])}</p><p class="autor">{e(cfg["autora"])} · {e(cfg["data"])}</p>', "capa"))
    # 2 problema
    S.append(slide('<h2>O problema</h2><div class="duas"><div>'
                   '<p class="grande">Quase toda aplicação hoje roda em contêiner, e a segurança começa no arquivo que monta esse contêiner.</p>'
                   '<p>Um <code>Dockerfile</code> ou <code>docker-compose.yml</code> mal escrito leva a falha para todo ambiente onde a imagem rodar.</p></div><div>'
                   '<h3>Pergunta do trabalho</h3><p class="destaque">Para detectar configuração insegura, ferramentas clássicas de análise estática '
                   'são melhores ou piores que modelos de linguagem? O tamanho do modelo importa?</p></div></div>'))
    # 3 visão geral das 3 falhas
    cards = "".join(f'<div class="card"><h3>{e(i["nome"])}</h3><p>{e(i["pergunta"])}</p><pre>{e(i["ruim"])}</pre></div>'
                    for i in CATEGORIAS_INFO.values())
    S.append(slide(f'<h2>As 3 falhas analisadas</h2><div class="tres">{cards}</div>'))
    # 4-6 impacto e mitigação por categoria (+ evidência da demonstração)
    evv = (ev or {}).get("versoes", {}).get("vulneravel", {}).get("execucao", {})
    evidencia = {
        "ROOT_USER": (f'No laboratório vulnerável: <code>{e(str(evv.get("usuario", "")))}</code>, {evv.get("capacidades")} capacidades do Linux.'
                      if "usuario" in evv else ""),
        "HARDCODED_SECRET": ("No laboratório vulnerável, a senha foi lida da imagem com <code>docker history</code>: "
                             f'<code>{e((evv.get("segredo_evidencia") or ["?"])[0][:70])}</code>' if evv.get("segredo_na_imagem") else ""),
        "UNPINNED_VERSION": (f'Hoje <code>{e(evv.get("imagem_base", ""))}</code> aponta para <code>{e(evv.get("digest_hoje", "")[-24:])}</code>; '
                             'amanhã pode ser outro.' if evv.get("digest_hoje") else ""),
    }
    for cat, i in CATEGORIAS_INFO.items():
        ev_html = f'<p class="evid">▶ {evidencia[cat]}</p>' if evidencia[cat] else ""
        S.append(slide(f'<h2>{e(i["nome"])}: impacto e mitigação</h2><div class="duas"><div><h3>Impacto</h3>{lista(i["impacto"])}'
                       f'{ev_html}</div><div><h3>Mitigação</h3>{lista(i["mitigacao"])}<div class="par"><div><span>Inseguro</span><pre>{e(i["ruim"])}</pre></div>'
                       f'<div><span>Corrigido</span><pre>{e(i["bom"])}</pre></div></div></div></div><p class="ref">{e(i["referencia"])}</p>'))
    # 7 corpus e gabarito
    if man:
        repos = sorted({m["repo"] for m in man})
        cont = Counter(g["category"] for g in gab)
        nums = (f'<div class="nums"><div><b>{len(man)}</b>arquivos</div><div><b>{len(repos)}</b>repositórios públicos</div>'
                f'<div><b>{len(gab)}</b>falhas no gabarito</div><div><b>{sum(m["conjunto"] == "teste" for m in man)}</b>arquivos de teste</div></div>')
        S.append(slide(f'<h2>Corpus e gabarito</h2>{nums}<div class="duas"><div><h3>Repositórios</h3><p>{e(", ".join(repos))}</p>'
                       f'<p>{sum(m["tipo"] == "dockerfile" for m in man)} Dockerfiles e {sum(m["tipo"] == "compose" for m in man)} docker-compose; '
                       'commit de cada um registrado.</p></div><div><h3>Gabarito anotado à mão, antes de rodar as ferramentas</h3>'
                       + lista([f'{CATEGORIAS_INFO[c]["nome"]}: {cont[c]}' for c in CATEGORIAS] + [cfg["concordancia_gabarito"],
                               "~30% dos arquivos (dev) para ajustar regras e prompt; ~70% (teste) só para medir."]) + '</div></div>'))
    else:
        S.append(slide('<h2>Corpus e gabarito</h2>' + aviso("Rode 01_coletar.py e 02_gabarito.py")))
    # 8 métodos
    versoes = ler(res / "versoes.txt", "") or ""
    mods = "".join(f"<li>{e(k)}: <code>{e(v)}</code></li>" for k, v in modelos.items())
    S.append(slide('<h2>Os dois métodos</h2><div class="duas"><div class="metodo"><h3>Clássico</h3><ul>'
                   '<li><b>A0</b>: Hadolint + Checkov, regras mapeadas para as 3 categorias</li>'
                   '<li><b>A1</b>: A0 + regras próprias em Python (tags resolvidas via ARG, compose lido como YAML, USER do estágio final)</li></ul>'
                   f'<p class="ref">{e(" · ".join(l for l in versoes.splitlines() if l.startswith(("hadolint", "checkov "))))}</p></div>'
                   '<div class="metodo ia"><h3>IA (NVIDIA, API compatível com OpenAI)</h3><ul>' + mods +
                   '<li>mesmo critério do gabarito no prompt, resposta em JSON, temperature 0</li><li>cache, nova tentativa em erro 429/5xx</li></ul></div></div>'
                   '<p class="fluxo">repositórios → corpus → <b>A0 · A1 · IA ×3</b> → schema comum (JSON) → avaliador → métricas</p>'))
    # 9 avaliação
    S.append(slide('<h2>Como medimos</h2><div class="duas"><div>' + lista([
        "Acerto (TP): mesmo arquivo, mesma categoria, até 2 linhas de distância do gabarito.",
        "Alarme falso (FP): apontou e não era falha. Escape (FN): falha que ninguém apontou.",
        "Cada falha do gabarito só pode ser acertada uma vez; repetições não contam como acerto.",
        "Intervalo de confiança de 95% por bootstrap (1000 reamostragens dos arquivos)."]) +
        '</div><div class="formulas"><p><b>Precisão</b> = TP ÷ (TP + FP)<br><small>do que apontou, quanto era verdade</small></p>'
        '<p><b>Recall</b> = TP ÷ (TP + FN)<br><small>das falhas reais, quantas achou</small></p><p><b>F1</b> = média harmônica das duas</p></div></div>'))
    # 10 tabela de resultados
    if met:
        linhas = "".join(
            f'<tr><td>{e(ROTULO.get(l["metodo"], l["metodo"]))}</td><td>{l["TP"]}</td><td>{l["FP"]}</td><td>{l["FN"]}</td>'
            f'<td>{float(l["precisao"]):.0%}</td><td>{float(l["recall"]):.0%}</td><td><b>{float(l["f1"]):.0%}</b></td>'
            f'<td>{float(l["f1_ic_inf"]):.0%}–{float(l["f1_ic_sup"]):.0%}</td></tr>' for l in met if l["categoria"] == "TOTAL")
        S.append(slide(f'<h2>Resultados (conjunto {conj})</h2><table><tr><th>Método</th><th>TP</th><th>FP</th><th>FN</th><th>Precisão</th>'
                       f'<th>Recall</th><th>F1</th><th>IC 95% F1</th></tr>{linhas}</table>'))
    else:
        S.append(slide('<h2>Resultados</h2>' + aviso("Rode python 05_avaliar.py")))
    S.append(slide('<h2>F1 por método</h2>' + fig(res, "f1_por_metodo", "F1 por método")))
    S.append(slide('<h2>O tamanho do modelo importa?</h2>' + fig(res, "f1_por_nivel", "F1 por nível de modelo")))
    S.append(slide('<h2>Por categoria de falha</h2>' + fig(res, "prf_por_categoria", "Precisão, recall e F1 por categoria")))
    # 14 onde cada método erra (matriz de modos, se preenchida)
    blocos = []
    for p in sorted((res / "erros").glob(f"{conj}_*.csv")) if (res / "erros").exists() else []:
        metodo = p.stem.split("_", 1)[1]
        erros = ler_csv(p)
        c = Counter((r["category"], (r.get("modo") or "").strip()) for r in erros if (r.get("modo") or "").strip())
        if c:
            modos = sorted({m for _, m in c})
            cab = "".join(f"<th>{e(MODOS.get(m, m))}</th>" for m in modos)
            corpo = "".join(f'<tr><td>{e(CATEGORIAS_INFO[cat]["nome"])}</td>' + "".join(f"<td>{c[(cat, m)] or ''}</td>" for m in modos) + "</tr>"
                            for cat in CATEGORIAS)
            blocos.append(f'<h3>{e(ROTULO.get(metodo, metodo))}</h3><table class="peq"><tr><th></th>{cab}</tr>{corpo}</table>')
    S.append(slide('<h2>Onde cada método erra</h2>' + ("".join(blocos[:2]) if blocos else
                   aviso("Preencha a coluna 'modo' em results/erros/teste_*.csv (passo 37) e rode de novo"))))
    # 15 demonstração antes/depois
    if ev:
        vv, cc = ev["versoes"].get("vulneravel", {}), ev["versoes"].get("corrigido", {})
        def soma(x):
            return sum(x.get("estatico", {}).get("por_categoria", {}).values())
        lin = [("Achados estáticos (3 categorias)", soma(vv), soma(cc))]
        for cat in CATEGORIAS:
            lin.append((f"  {CATEGORIAS_INFO[cat]['nome']}", vv.get("estatico", {}).get("por_categoria", {}).get(cat, 0),
                        cc.get("estatico", {}).get("por_categoria", {}).get(cat, 0)))
        xv, xc = vv.get("execucao", {}), cc.get("execucao", {})
        if xv or xc:
            sim = lambda b: "sim" if b else "não"  # noqa: E731
            lin += [("Usuário do processo", xv.get("usuario", "—"), xc.get("usuario", "—")),
                    ("Capacidades do Linux", xv.get("capacidades", "—"), xc.get("capacidades", "—")),
                    ("Senha legível na imagem", sim(xv.get("segredo_na_imagem")), sim(xc.get("segredo_na_imagem"))),
                    ("Imagem base", xv.get("imagem_base", "—"), xc.get("imagem_base", "—"))]
        corpo = "".join(f'<tr><td>{e(str(n))}</td><td class="mal">{e(str(v))}</td><td class="bem">{e(str(c))}</td></tr>' for n, v, c in lin)
        nota = "" if ev.get("docker") else aviso("Execução com Docker não rodou: abra o Docker Desktop e rode 08_demonstracao.py")
        S.append(slide(f'<h2>Demonstração em ambiente controlado</h2><table><tr><th></th><th>Vulnerável</th><th>Corrigido</th></tr>{corpo}</table>'
                       f'{nota}<p class="ref">Laboratório próprio (pasta demo/), executado em {e(ev["data"])}. Os arquivos do corpus nunca são executados.</p>'))
    else:
        S.append(slide('<h2>Demonstração em ambiente controlado</h2>' + aviso("Rode python 08_demonstracao.py")))
    # 16 custo e tempo
    tempos = json.loads(ler(res / "tempos.json", "{}") or "{}")
    custo = []
    if tempos:
        custo.append(("Clássico (Hadolint + Checkov + regras)", f'{sum(v for v in tempos.values()):.0f} s no corpus', "—"))
    for nivel in modelos:
        log = ler(res / f"ia_log_{nivel}.csv", [], ler_csv)
        if log:
            seg = [float(r["segundos"]) for r in log if r.get("segundos") not in ("", None)]
            tok = sum(int(r["tokens_entrada"] or 0) + int(r["tokens_saida"] or 0) for r in log if r.get("tokens_entrada") not in ("", None))
            erros = sum(r["status"] != "ok" for r in log)
            custo.append((f"IA {nivel.replace('medio', 'médio')} ({modelos[nivel].split('/')[-1]})",
                          f"{statistics.mean(seg):.1f} s por arquivo" if seg else "—", f"{tok:,} tokens · {erros} resposta(s) inválida(s)".replace(",", ".")))
    S.append(slide('<h2>Custo e tempo</h2>' + (
        "<table><tr><th>Método</th><th>Tempo</th><th>Uso da API</th></tr>" +
        "".join(f"<tr><td>{e(a_)}</td><td>{e(b)}</td><td>{e(c)}</td></tr>" for a_, b, c in custo) + "</table>"
        if custo else aviso("Rode 03_classico.py e 04_ia.py"))))
    S.append(slide('<h2>Limitações</h2>' + lista(cfg["limitacoes"])))
    S.append(slide('<h2>Conclusão</h2>' + lista(cfg["conclusoes"])))
    extra = f'<p>Código e dados: {e(cfg["link_repositorio"])}</p>' if cfg.get("link_repositorio") else ""
    S.append(slide(f'<h1>Obrigada!</h1><p class="sub">Perguntas?</p>{extra}'
                   '<p class="links"><a href="painel.html">Painel de resultados</a> · <a href="http://127.0.0.1:8451/analisar">Análise ao vivo (app local)</a></p>', "capa"))

    pagina = MODELO.replace("__TITULO__", e(cfg["titulo"])).replace("__SLIDES__", "\n".join(S))
    (out / "index.html").write_text(pagina, encoding="utf-8")
    if Path("painel.html").exists():
        shutil.copyfile("painel.html", out / "painel.html")
    print(f"Apresentação: {out / 'index.html'} ({len(S)} slides). Teclas: → ← navegar, F tela cheia, P painel.")
    if not Path("painel.html").exists():
        print("Aviso: painel.html não existe ainda (rode 07_painel.py e depois este script de novo).")


MODELO = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITULO__</title><style>
:root{--tinta:#1b1b1a;--suave:#52514e;--fundo:#fcfcfb;--linha:#e4e3df;--azul:#2a78d6;--laranja:#eb6834;--verde:#0d8a5a;--vermelho:#c0392b}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#2b2b29;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--tinta)}
#palco{position:absolute;width:1280px;height:720px;left:50%;top:50%;transform-origin:center}
.slide{position:absolute;inset:0;background:var(--fundo);padding:58px 72px;display:none;flex-direction:column;overflow:hidden}
.slide.ativo{display:flex}
h1{font:600 52px/1.1 Georgia,"Times New Roman",serif;margin:0 0 18px}h2{font:600 36px/1.15 Georgia,serif;margin:0 0 26px}
h3{font-size:20px;margin:0 0 10px;color:var(--suave);font-weight:600}
p,li{font-size:21px;line-height:1.45}ul{margin:0;padding-left:24px}li{margin:6px 0}
code,pre{font-family:"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace}code{font-size:.85em;background:#efeee9;padding:1px 6px;border-radius:4px}
pre{background:#f1f0eb;border-radius:8px;padding:12px 14px;font-size:15px;line-height:1.45;margin:8px 0;white-space:pre-wrap}
.capa{justify-content:center}.capa h1{font-size:56px;max-width:1000px}.kicker{color:var(--azul);font-weight:600;font-size:18px;letter-spacing:.02em}
.sub{font-size:26px;color:var(--suave);margin:0 0 30px}.autor{font-size:22px}
.duas{display:grid;grid-template-columns:1fr 1fr;gap:48px;flex:1}.tres{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}
.card{border:1px solid var(--linha);border-radius:12px;padding:22px;background:#fff}.card p{font-size:18px}
.grande{font-size:28px;line-height:1.35}.destaque{font-size:25px;line-height:1.4;border-left:5px solid var(--azul);padding-left:18px}
.evid{background:#fdf1ea;border-left:4px solid var(--laranja);padding:10px 14px;font-size:17px;border-radius:0 8px 8px 0;margin-top:16px}
.par{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}.par span{font-size:14px;font-weight:600;color:var(--suave)}
.par pre{font-size:12.5px}.par div:first-child pre{border-left:3px solid var(--vermelho)}.par div:last-child pre{border-left:3px solid var(--verde)}
.ref{position:absolute;bottom:26px;left:72px;right:72px;font-size:14px;color:var(--suave)}
.nums{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-bottom:26px}.nums div{border:1px solid var(--linha);border-radius:12px;padding:16px;background:#fff;font-size:17px;color:var(--suave)}
.nums b{display:block;font:600 44px Georgia,serif;color:var(--tinta)}
.metodo{border-top:5px solid var(--azul);padding-top:14px}.metodo.ia{border-color:var(--laranja)}.metodo li{font-size:19px}
.fluxo{text-align:center;font-size:19px;color:var(--suave);background:#f1f0eb;border-radius:30px;padding:10px}
.formulas p{font-size:24px;margin:0 0 18px}.formulas small{color:var(--suave);font-size:17px}
table{border-collapse:collapse;width:100%;font-size:19px}th{color:var(--suave);font-weight:600;text-align:left;border-bottom:2px solid var(--linha);padding:8px 10px}
td{padding:8px 10px;border-bottom:1px solid var(--linha)}table.peq{font-size:16px;margin-bottom:18px}
td.mal{color:var(--vermelho);font-weight:600}td.bem{color:var(--verde);font-weight:600}
.fig{max-width:100%;max-height:540px;object-fit:contain;align-self:center;background:#fff;border-radius:8px}
.aviso{background:#fff6dc;border:1px solid #f0d58a;border-radius:8px;padding:12px 16px;font-size:18px}
.links a{color:var(--azul);font-size:20px}
#barra{position:fixed;left:0;bottom:0;height:4px;background:var(--azul);transition:width .2s}#num{position:fixed;right:14px;bottom:10px;color:#bbb;font-size:13px}
@media print{@page{size:1280px 720px;margin:0}html,body{background:#fff}#palco{position:static;transform:none!important;width:auto;height:auto}
.slide{display:flex!important;position:relative;width:1280px;height:720px;page-break-after:always}#barra,#num{display:none}}
</style></head><body><div id="palco">__SLIDES__</div><div id="barra"></div><div id="num"></div><script>
const s=[...document.querySelectorAll('.slide')],palco=document.getElementById('palco');let i=Math.max(0,Math.min(s.length-1,(parseInt(location.hash.slice(1))||1)-1));
function ajusta(){const k=Math.min(innerWidth/1280,innerHeight/720);palco.style.transform=`translate(-50%,-50%) scale(${k})`}
function vai(n){i=Math.max(0,Math.min(s.length-1,n));s.forEach((x,j)=>x.classList.toggle('ativo',j===i));history.replaceState(null,'','#'+(i+1));
document.getElementById('barra').style.width=((i+1)/s.length*100)+'%';document.getElementById('num').textContent=(i+1)+' / '+s.length}
addEventListener('keydown',ev=>{if(['ArrowRight','PageDown',' ','Enter'].includes(ev.key))vai(i+1);else if(['ArrowLeft','PageUp','Backspace'].includes(ev.key))vai(i-1);
else if(ev.key==='Home')vai(0);else if(ev.key==='End')vai(s.length-1);else if(ev.key==='f'||ev.key==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}
else if(ev.key==='p'||ev.key==='P')window.open('painel.html','_blank')});
palco.addEventListener('click',ev=>{if(!ev.target.closest('a'))vai(ev.clientX>innerWidth/2?i+1:i-1)});addEventListener('resize',ajusta);ajusta();vai(i);
</script></body></html>"""

if __name__ == "__main__":
    main()
