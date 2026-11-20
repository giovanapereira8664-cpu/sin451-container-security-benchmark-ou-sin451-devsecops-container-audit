"""Dias 1–2 — Gabarito (as falhas reais, anotadas por você).

Passo 1:  python 02_gabarito.py rascunho
          cria gabarito/rascunho.csv (abre no Excel) com as linhas candidatas de cada arquivo.
          Preencha as colunas e_falha (S ou N) e category. Acrescente linhas que faltarem.
Passo 2:  python 02_gabarito.py converter
          valida o CSV e gera gabarito/gabarito.jsonl (o arquivo usado na avaliação).

Passo 19: python 02_gabarito.py reanotar   (sorteia 6 arquivos -> gabarito/reanotacao.csv, em branco)
          python 02_gabarito.py comparar   (compara a reanotação com o gabarito e mostra a concordância)

Atenção: anote ANTES de olhar a saída das ferramentas e da IA (senão o gabarito fica enviesado).
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451.comum import CATEGORIAS, ler_csv, ler_jsonl, ler_manifesto, ler_texto, mascarar, salvar_csv, salvar_jsonl  # noqa: E402
from sin451.regras_proprias import instrucoes  # noqa: E402

CAMPOS = ["file", "line", "conteudo", "e_falha", "category", "note"]
PALAVRAS = re.compile(r"(?i)(image:|user:|privileged|environment|pass|secret|token|key|credential|=)")


def candidatas_dockerfile(texto):
    """Rede larga: toda instrução FROM, COPY --from, USER, ENV, ARG e RUN que instala pacote."""
    ultimo_from, tem_user = None, False
    for linha, inst, args in instrucoes(texto):
        if inst == "FROM":
            ultimo_from, tem_user = linha, False
        if inst == "USER":
            tem_user = True
        if inst in ("FROM", "USER", "ENV", "ARG") or (inst in ("COPY", "ADD") and "--from" in args) \
                or (inst == "RUN" and re.search(r"\b(install|add)\b", args)):
            yield linha, f"{inst} {args}"
    if ultimo_from and not tem_user:
        yield ultimo_from, "(estágio final sem nenhum USER — roda como root?)"


def candidatas_compose(texto):
    for n, l in enumerate(texto.splitlines(), 1):
        if l.strip() and not l.strip().startswith("#") and PALAVRAS.search(l):
            yield n, l.strip()


def rascunho(a):
    linhas = []
    for m in ler_manifesto(a.corpus):
        texto = ler_texto(Path(a.corpus) / m["file"])
        gerador = candidatas_compose if m["tipo"] == "compose" else candidatas_dockerfile
        for n, conteudo in gerador(texto):
            linhas.append({"file": m["file"], "line": n, "conteudo": mascarar(conteudo)[:150],
                           "e_falha": "", "category": "", "note": ""})
    destino = Path(a.pasta) / "rascunho.csv"
    if destino.exists() and not a.sobrescrever:
        raise SystemExit(f"{destino} já existe (use --sobrescrever para recriar e PERDER as anotações)")
    salvar_csv(destino, linhas, CAMPOS, excel=True)
    print(f"{len(linhas)} linhas candidatas em {destino}. Abra no Excel, preencha e_falha (S/N) e category.")
    print("Categorias:", ", ".join(CATEGORIAS))


def converter(a):
    manifesto = {m["file"]: int(m["linhas"]) for m in ler_manifesto(a.corpus)}
    itens, erros, vistos = [], [], set()
    for n, l in enumerate(ler_csv(Path(a.pasta) / "rascunho.csv"), 2):
        marca = (l.get("e_falha") or "").strip().upper()
        if marca not in ("S", "SIM", "X", "1"):
            continue
        arq, cat = (l.get("file") or "").strip(), (l.get("category") or "").strip().upper()
        try:
            linha = int(float(l.get("line")))
        except (TypeError, ValueError):
            erros.append(f"linha {n} do CSV: 'line' inválida")
            continue
        if arq not in manifesto:
            erros.append(f"linha {n} do CSV: arquivo '{arq}' não está no manifesto")
        elif cat not in CATEGORIAS:
            erros.append(f"linha {n} do CSV: categoria '{cat}' inválida")
        elif not 1 <= linha <= manifesto[arq]:
            erros.append(f"linha {n} do CSV: linha {linha} fora do arquivo")
        elif (arq, linha, cat) in vistos:
            erros.append(f"linha {n} do CSV: repetida")
        else:
            vistos.add((arq, linha, cat))
            itens.append({"file": arq, "line": linha, "category": cat,
                          "evidence": mascarar(l.get("conteudo", ""))[:150], "note": l.get("note", "")})
    if erros:
        print("Corrija no CSV e rode de novo:\n  " + "\n  ".join(erros))
        raise SystemExit(1)
    itens.sort(key=lambda g: (g["file"], g["line"], g["category"]))
    for i, g in enumerate(itens, 1):
        g["id"] = f"G{i:03d}"
    salvar_jsonl(Path(a.pasta) / "gabarito.jsonl", itens)
    print(f"Gabarito: {len(itens)} falhas em {len({g['file'] for g in itens})} arquivos")
    for cat, n in Counter(g["category"] for g in itens).most_common():
        print(f"  {cat:18s} {n}")


def reanotar(a):
    import random
    rasc = ler_csv(Path(a.pasta) / "rascunho.csv")
    arquivos = sorted({l["file"] for l in rasc})
    escolhidos = set(random.Random(a.semente).sample(arquivos, min(6, len(arquivos))))
    linhas = [{**l, "e_falha": "", "category": "", "note": ""} for l in rasc if l["file"] in escolhidos]
    destino = Path(a.pasta) / "reanotacao.csv"
    if destino.exists() and not a.sobrescrever:
        raise SystemExit(f"{destino} já existe (use --sobrescrever para recriar)")
    salvar_csv(destino, linhas, CAMPOS, excel=True)
    print(f"{len(linhas)} linhas de {len(escolhidos)} arquivos em {destino}:")
    for f in sorted(escolhidos):
        print("  ", f)
    print("Anote SEM olhar o rascunho.csv e depois rode: python 02_gabarito.py comparar")


def comparar(a):
    rean = ler_csv(Path(a.pasta) / "reanotacao.csv")
    arquivos = {l["file"] for l in rean}
    marcar = lambda l: (l.get("e_falha") or "").strip().upper() in ("S", "SIM", "X", "1")  # noqa: E731
    novo = {(l["file"], int(float(l["line"])), (l.get("category") or "").strip().upper()) for l in rean if marcar(l)}
    velho = {(g["file"], g["line"], g["category"]) for g in ler_jsonl(Path(a.pasta) / "gabarito.jsonl") if g["file"] in arquivos}
    iguais = novo & velho
    total = len(novo | velho)
    print(f"Concordância: {len(iguais)} de {total} itens iguais ({len(iguais) / total:.0%})" if total else "Nada anotado.")
    for f, l, c in sorted(velho - novo):
        print(f"  só no gabarito:   {f} linha {l} {c}")
    for f, l, c in sorted(novo - velho):
        print(f"  só na reanotação: {f} linha {l} {c}")
    print("Escreva no relatório o número acima e explique cada divergência (e corrija o gabarito se ele estava errado).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["rascunho", "converter", "reanotar", "comparar"])
    ap.add_argument("--semente", type=int, default=451)
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--pasta", default="gabarito")
    ap.add_argument("--sobrescrever", action="store_true")
    a = ap.parse_args()
    {"rascunho": rascunho, "converter": converter, "reanotar": reanotar, "comparar": comparar}[a.acao](a)


if __name__ == "__main__":
    main()
