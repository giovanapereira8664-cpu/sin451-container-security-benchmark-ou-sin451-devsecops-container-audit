"""App local para a apresentação: http://127.0.0.1:8451

Uso:  python 10_app.py            (abre o navegador sozinho; Ctrl+C para parar)
      python 10_app.py --porta 9000 --sem-navegador

Páginas:
  /                 início, com os links abaixo
  /apresentacao/    os slides (gerados por 09_apresentacao.py)
  /painel.html      o painel de resultados (07_painel.py)
  /analisar         ANÁLISE AO VIVO: cole ou edite um Dockerfile/compose e veja os achados,
                    com impacto e mitigação de cada falha (regras próprias; Hadolint e Checkov se estiverem instalados)
Só escuta no seu computador (127.0.0.1). Nada é executado: a análise é estática.
"""
import argparse
import json
import mimetypes
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).parent.resolve()
sys.path.insert(0, str(RAIZ))
from sin451 import normalizar, regras_proprias  # noqa: E402
from sin451.comum import FORA, ler_texto  # noqa: E402
from sin451.conhecimento import CATEGORIAS_INFO  # noqa: E402

LIMITE = 200_000


def hadolint_cmd():
    if shutil.which("hadolint"):
        return ["hadolint"]
    if shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0:
        return ["docker", "run", "--rm", "-i", "hadolint/hadolint", "hadolint"]
    return None


def analisar(nome, texto, ferramentas, mapa):
    nome = "docker-compose.yml" if regras_proprias.eh_compose(nome) else "Dockerfile"
    arq = f"ao-vivo/{nome}"
    textos = {arq: texto}
    achados, avisos = [], []
    if "regras" in ferramentas:
        achados += regras_proprias.analisar(arq, texto)
    if "hadolint" in ferramentas and nome == "Dockerfile":
        cmd = hadolint_cmd()
        if cmd is None:
            avisos.append("Hadolint indisponível (instale ou abra o Docker Desktop).")
        else:
            r = subprocess.run(cmd + ["-f", "json", "-"], input=texto, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            try:
                achados += normalizar.hadolint({arq: json.loads(r.stdout or "[]")}, mapa, textos)
            except json.JSONDecodeError:
                avisos.append("Hadolint não conseguiu ler o arquivo.")
    if "checkov" in ferramentas:
        if not shutil.which("checkov"):
            avisos.append("Checkov não encontrado (ative o ambiente virtual antes de abrir o app).")
        else:
            with tempfile.TemporaryDirectory() as tmp:
                pasta = Path(tmp) / "ao-vivo"
                pasta.mkdir()
                (pasta / nome).write_text(texto, encoding="utf-8")
                r = subprocess.run(["checkov", "-d", tmp, "--framework", "dockerfile", "secrets", "-o", "json", "--compact"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
                try:
                    achados += normalizar.checkov(json.loads(r.stdout), mapa, textos, str(Path(tmp).resolve()))
                except json.JSONDecodeError:
                    avisos.append("Checkov não devolveu resultado.")
    saida = [{k: f[k] for k in ("line", "category", "rule_id", "tool", "message")} for f in achados if f["category"] != FORA]
    saida.sort(key=lambda f: (f["line"], f["category"], f["tool"]))
    return {"achados": saida, "avisos": avisos, "fora_de_escopo": sum(f["category"] == FORA for f in achados)}


def exemplos():
    ex = {}
    for versao in ("vulneravel", "corrigido"):
        for nome in ("Dockerfile", "docker-compose.yml"):
            p = RAIZ / "demo" / versao / nome
            if p.exists():
                ex[f"{versao}/{nome}"] = ler_texto(p)
    return ex


class App(BaseHTTPRequestHandler):
    mapa = []

    def log_message(self, fmt, *args):
        pass

    def _enviar(self, codigo, corpo, tipo="text/html; charset=utf-8"):
        dados = corpo.encode("utf-8") if isinstance(corpo, str) else corpo
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _arquivo(self, caminho):
        caminho = caminho.resolve()
        if RAIZ not in caminho.parents or not caminho.is_file():
            return self._enviar(404, INICIO.replace("__CORPO__", "<p>Não encontrado. Rode antes os scripts 07 e 09.</p>"))
        self._enviar(200, caminho.read_bytes(), mimetypes.guess_type(str(caminho))[0] or "application/octet-stream")

    def do_GET(self):
        rota = self.path.split("?", 1)[0]
        if rota == "/":
            self._enviar(200, INICIO.replace("__CORPO__", LINKS))
        elif rota == "/analisar":
            pagina = ANALISAR.replace("__EXEMPLOS__", json.dumps(exemplos(), ensure_ascii=False).replace("</", "<\\/")) \
                             .replace("__INFO__", json.dumps(CATEGORIAS_INFO, ensure_ascii=False).replace("</", "<\\/"))
            self._enviar(200, pagina)
        elif rota in ("/apresentacao", "/apresentacao/"):
            self._arquivo(RAIZ / "apresentacao" / "index.html")
        elif rota.startswith("/apresentacao/"):
            self._arquivo(RAIZ / "apresentacao" / rota[len("/apresentacao/"):])
        elif rota == "/painel.html":
            self._arquivo(RAIZ / "painel.html")
        else:
            self._enviar(404, INICIO.replace("__CORPO__", "<p>Página não encontrada.</p>" + LINKS))

    def do_POST(self):
        if self.path != "/api/analisar":
            return self._enviar(404, "{}", "application/json")
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > LIMITE:
            return self._enviar(413, json.dumps({"erro": "arquivo grande demais"}), "application/json")
        try:
            pedido = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            resultado = analisar(str(pedido.get("nome", "Dockerfile")), str(pedido.get("texto", "")),
                                 set(pedido.get("ferramentas", ["regras"])), self.mapa)
            self._enviar(200, json.dumps(resultado, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as ex:  # noqa: BLE001 — devolve o erro para a página em vez de derrubar o app
            self._enviar(500, json.dumps({"erro": str(ex)}), "application/json; charset=utf-8")


ESTILO = """<style>body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:#fcfcfb;color:#1b1b1a}
header{padding:16px 28px;border-bottom:1px solid #e4e3df;display:flex;gap:22px;align-items:baseline}header b{font-size:18px}
header a{color:#2a78d6;text-decoration:none}main{padding:22px 28px;max-width:1300px}
.links{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.links a{display:block;border:1px solid #e4e3df;border-radius:12px;padding:20px;
background:#fff;color:inherit;text-decoration:none}.links a:hover{border-color:#2a78d6}.links h2{margin:0 0 6px;font-size:19px;color:#2a78d6}.links p{margin:0;color:#52514e}
</style>"""
NAV = '<header><b>SIN 451 · App de apresentação</b><a href="/">Início</a><a href="/apresentacao/">Slides</a><a href="/painel.html">Painel</a><a href="/analisar">Análise ao vivo</a></header>'
INICIO = f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>SIN 451 — App</title>{ESTILO}</head><body>{NAV}<main>__CORPO__</main></body></html>'
LINKS = """<h1 style="font:600 30px Georgia,serif">Configuração insegura em contêineres: clássico × IA</h1><div class="links">
<a href="/apresentacao/"><h2>Slides</h2><p>A apresentação, com os resultados do projeto. Teclas → ← e F para tela cheia.</p></a>
<a href="/painel.html"><h2>Painel de resultados</h2><p>Métricas, gráficos e o visualizador arquivo por arquivo.</p></a>
<a href="/analisar"><h2>Análise ao vivo</h2><p>Cole ou edite um Dockerfile e veja os achados, o impacto e a mitigação.</p></a></div>"""

ANALISAR = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Análise ao vivo</title>{ESTILO}<style>
.grade{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}textarea{{width:100%;height:430px;font:13px/1.5 Consolas,"DejaVu Sans Mono",monospace;
border:1px solid #d6d5cf;border-radius:8px;padding:10px;box-sizing:border-box;tab-size:2}}.barra{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 10px}}
button{{font:inherit;padding:6px 12px;border-radius:7px;border:1px solid #d6d5cf;background:#fff;cursor:pointer}}button.prim{{background:#2a78d6;color:#fff;border-color:#2a78d6}}
label{{font-size:14px;color:#52514e}}select{{font:inherit;padding:5px}}.res{{border:1px solid #e4e3df;border-radius:10px;background:#fff;padding:14px;min-height:430px}}
.cod{{font:12.5px/1.6 Consolas,"DejaVu Sans Mono",monospace;margin-bottom:14px}}.l{{display:flex;padding:0 6px}}.l.m{{background:#fff4ec}}.n{{color:#9a988f;width:30px;text-align:right;margin-right:10px;flex:none}}
.c{{white-space:pre-wrap;word-break:break-all;flex:1}}.b{{display:inline-block;font:600 10.5px system-ui;padding:1px 6px;border-radius:9px;margin-left:5px;background:#fde4dc;color:#a33a12}}
.cat{{border-left:4px solid #eb6834;padding:4px 12px;margin:12px 0}}.cat h3{{margin:2px 0 4px;font-size:16px}}.cat ul{{margin:4px 0;padding-left:20px;font-size:14px}}
.ok{{border-left:4px solid #0d8a5a;padding:8px 12px;background:#effaf4}}.av{{color:#8a6100;font-size:13px}}small{{color:#52514e}}</style></head><body>{NAV}<main>
<div class="barra"><b>Exemplos:</b><span id="ex"></span></div>
<div class="grade"><div><div class="barra"><label>Tipo <select id="nome"><option>Dockerfile</option><option>docker-compose.yml</option></select></label>
<label><input type="checkbox" value="regras" checked> regras próprias</label><label><input type="checkbox" value="hadolint"> Hadolint</label>
<label><input type="checkbox" value="checkov"> Checkov <small>(lento)</small></label><button class="prim" id="ir">Analisar</button></div>
<textarea id="txt" spellcheck="false"></textarea></div><div class="res" id="res"><small>Escolha um exemplo ou cole um arquivo e clique em Analisar.</small></div></div>
</main><script>const EX=__EXEMPLOS__,INFO=__INFO__;const txt=document.getElementById('txt'),nome=document.getElementById('nome'),res=document.getElementById('res');
Object.keys(EX).forEach(k=>{{const b=document.createElement('button');b.textContent=k.replace('vulneravel','vulnerável');b.onclick=()=>{{txt.value=EX[k];
nome.value=k.endsWith('.yml')?'docker-compose.yml':'Dockerfile';analisar()}};document.getElementById('ex').append(b,' ')}});
function esc(s){{return String(s).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}
function mask(s){{return s.replace(/((?:pass|pwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|credential)[\\w-]*\\s*[=:]\\s*["']?)([^\\s"'$][^\\s"']*)/ig,'$1****')}}
async function analisar(){{const f=[...document.querySelectorAll('input[type=checkbox]:checked')].map(c=>c.value);res.innerHTML='<small>Analisando...</small>';
const r=await fetch('/api/analisar',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{nome:nome.value,texto:txt.value,ferramentas:f}})}});
const d=await r.json();if(d.erro){{res.innerHTML='<p class="av">Erro: '+esc(d.erro)+'</p>';return}}
const por={{}};d.achados.forEach(a=>(por[a.line]=por[a.line]||[]).push(a));
let h='<div class="cod">'+txt.value.split('\\n').map((l,i)=>{{const m=por[i+1]||[];return `<div class="l${{m.length?' m':''}}"><span class="n">${{i+1}}</span><span class="c">${{esc(mask(l))}}${{
m.map(a=>`<span class="b" title="${{esc(a.message)}}">${{esc(INFO[a.category].nome)}} · ${{esc(a.tool)}}</span>`).join('')}}</span></div>`}}).join('')+'</div>';
const cats=[...new Set(d.achados.map(a=>a.category))];
if(!cats.length)h+='<div class="ok"><b>Nenhuma das 3 falhas encontrada.</b></div>';
cats.forEach(c=>{{const i=INFO[c],n=d.achados.filter(a=>a.category===c).length;h+=`<div class="cat"><h3>${{esc(i.nome)}} — ${{n}} achado(s)</h3><b>Impacto</b><ul>${{
i.impacto.map(x=>'<li>'+esc(x)+'</li>').join('')}}</ul><b>Como corrigir</b><ul>${{i.mitigacao.map(x=>'<li>'+esc(x)+'</li>').join('')}}</ul></div>`}});
d.avisos.forEach(a=>h+='<p class="av">'+esc(a)+'</p>');res.innerHTML=h}}
document.getElementById('ir').onclick=analisar;const k0=Object.keys(EX)[0];if(k0){{txt.value=EX[k0]}}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8451)
    ap.add_argument("--sem-navegador", action="store_true")
    a = ap.parse_args()
    App.mapa = normalizar.carregar_mapeamento(RAIZ / "mapeamento.csv")
    servidor = ThreadingHTTPServer(("127.0.0.1", a.porta), App)
    url = f"http://127.0.0.1:{a.porta}/"
    print(f"App rodando em {url}  (Ctrl+C para parar)")
    if not a.sem_navegador:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nApp encerrado.")


if __name__ == "__main__":
    main()
