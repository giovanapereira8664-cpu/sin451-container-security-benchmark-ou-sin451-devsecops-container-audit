"""Dias 4–5 — Método IA com modelos da NVIDIA (3 níveis).

Antes: crie o arquivo .env com a linha  NVIDIA_API_KEY=nvapi-...   (nunca envie esse arquivo ao Git)

    python 04_ia.py teste                        # "hello world": confirma que a chave funciona
    python 04_ia.py modelos                      # lista os modelos disponíveis na sua conta
    python 04_ia.py prompt corpus/dvwa/Dockerfile   # mostra o prompt exato (para o relatório)
    python 04_ia.py rodar --nivel pequeno --limite 3   # teste curto
    python 04_ia.py rodar --nivel pequeno           # corpus inteiro
    python 04_ia.py rodar                           # os 3 níveis do modelos.json
Saída:
    results/normalized/IA-<nivel>.jsonl,  results/ia_log_<nivel>.csv,  cache/ (respostas salvas)
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451 import ia  # noqa: E402
from sin451.comum import ler_manifesto, ler_texto, ordenar, salvar_csv, salvar_jsonl  # noqa: E402


def carregar_modelos(caminho):
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {k: v for k, v in dados.items() if not k.startswith("_")}


def rodar(a):
    modelos = carregar_modelos(a.modelos)
    niveis = [a.nivel] if a.nivel else list(modelos)
    cliente = ia.Cliente(ia.chave_api(), a.cache, intervalo=60 / a.rpm)
    manifesto = ler_manifesto(a.corpus)
    if a.conjunto != "todos":
        manifesto = [m for m in manifesto if m["conjunto"] == a.conjunto]
    if a.limite:
        manifesto = manifesto[: a.limite]
    for nivel in niveis:
        modelo = modelos[nivel]
        metodo = f"IA-{nivel}"
        print(f"\n== {metodo}: {modelo} ({len(manifesto)} arquivos)")
        todos, log = [], []
        for i, m in enumerate(manifesto, 1):
            texto = ler_texto(Path(a.corpus) / m["file"])
            reg = {"file": m["file"], "status": "", "origem": "", "segundos": "", "tokens_entrada": "",
                   "tokens_saida": "", "achados": 0, "descartados": 0, "erro": ""}
            try:
                resposta, info = cliente.conversar(modelo, ia.montar_mensagens(m["file"], texto))
                reg.update({k: info.get(k, "") for k in ("origem", "segundos", "tokens_entrada", "tokens_saida")})
                achados, desc = ia.converter(resposta, m["file"], len(texto.splitlines()), modelo, metodo)
                todos += achados
                reg.update(status="ok", achados=len(achados), descartados=desc)
            except ValueError as e:
                reg.update(status="erro_json", erro=str(e))
            except RuntimeError as e:
                reg.update(status="erro_api", erro=str(e)[:200])
                if "HTTP 401" in str(e) or "HTTP 403" in str(e) or "HTTP 404" in str(e):
                    print(f"  {m['file']}: {e}")
                    raise SystemExit("A API recusou o pedido (chave ou modelo). Veja a seção de problemas do guia.")
            log.append(reg)
            print(f"  [{i}/{len(manifesto)}] {m['file']}: {reg['status']} ({reg['origem']}) {reg['achados']} achado(s)")
        sufixo = "_parcial" if a.limite else ("" if a.conjunto == "todos" else f"_{a.conjunto}")
        salvar_jsonl(Path(a.saida) / "normalized" / f"{metodo}{sufixo}.jsonl", ordenar(todos))
        salvar_csv(Path(a.saida) / f"ia_log_{nivel}{sufixo}.csv", log, list(log[0]) if log else ["file"])
        erros = sum(r["status"] != "ok" for r in log)
        print(f"  total: {len(todos)} achados, {erros} arquivo(s) com erro")
        if sufixo == "_parcial":
            print("  (execução parcial: o arquivo leva _parcial no nome e não entra na avaliação)")
        elif sufixo:
            print(f"  (só o conjunto {a.conjunto}: avalie com  python 05_avaliar.py --conjunto {a.conjunto})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="acao", required=True)
    sub.add_parser("teste")
    sub.add_parser("modelos")
    p = sub.add_parser("prompt")
    p.add_argument("arquivo")
    r = sub.add_parser("rodar")
    r.add_argument("--nivel")
    r.add_argument("--limite", type=int, default=0)
    r.add_argument("--conjunto", default="todos", choices=["todos", "dev", "teste"])
    r.add_argument("--rpm", type=float, default=30, help="requisições por minuto (limite gratuito ~40)")
    for x in (ap, r):
        x.add_argument("--corpus", default="corpus")
        x.add_argument("--saida", default="results")
        x.add_argument("--cache", default="cache")
        x.add_argument("--modelos", default="modelos.json")
    a = ap.parse_args()

    if a.acao == "teste":
        modelo = next(iter(carregar_modelos(a.modelos).values()))
        t = time.time()
        import tempfile
        texto, info = ia.Cliente(ia.chave_api(), tempfile.mkdtemp()).conversar(  # sem cache: testa a API de verdade
            modelo, [{"role": "user", "content": 'Responda apenas com o JSON {"ok": true}'}])
        print(f"Modelo {modelo} respondeu em {time.time() - t:.1f}s: {texto.strip()[:200]}")
    elif a.acao == "modelos":
        for m in ia.listar_modelos(ia.chave_api()):
            print(m)
    elif a.acao == "prompt":
        caminho = Path(a.arquivo)
        rel = caminho.relative_to(a.corpus).as_posix() if caminho.is_relative_to(a.corpus) else caminho.name
        for msg in ia.montar_mensagens(rel, ler_texto(caminho)):
            print(f"--- {msg['role']} ---\n{msg['content']}\n")
    else:
        rodar(a)


if __name__ == "__main__":
    main()
