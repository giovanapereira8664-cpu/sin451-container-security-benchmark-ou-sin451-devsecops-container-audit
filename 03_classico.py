"""Dia 3 — Método clássico: Hadolint + Checkov (A0) e A0 + regras próprias (A1).

Uso:
    python 03_classico.py                       # roda tudo e normaliza
    python 03_classico.py --somente-normalizar  # reaproveita results/raw (depois de mexer no mapeamento)
Saída:
    results/raw/hadolint.json, results/raw/checkov.json     saídas brutas
    results/normalized/A0.jsonl, A1.jsonl, regras_proprias.jsonl
    results/versoes.txt, results/tempos.json, results/fora_de_escopo.csv
"""
import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451 import normalizar, regras_proprias  # noqa: E402
from sin451.comum import FORA, CATEGORIAS, ler_manifesto, ler_texto, ordenar, salvar_csv, salvar_jsonl  # noqa: E402


def cmd_hadolint():
    if shutil.which("hadolint"):
        return ["hadolint"]
    return ["docker", "run", "--rm", "-i", "hadolint/hadolint", "hadolint"]


def rodar(cmd, entrada=None):
    r = subprocess.run(cmd, input=entrada, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def rodar_hadolint(corpus, manifesto):
    bruto = {}
    for m in manifesto:
        if m["tipo"] != "dockerfile":
            continue
        cod, saida, erro = rodar(cmd_hadolint() + ["-f", "json", "-"], ler_texto(Path(corpus) / m["file"]))
        try:
            bruto[m["file"]] = json.loads(saida or "[]")
        except json.JSONDecodeError:
            print(f"  aviso: Hadolint não leu {m['file']}: {(erro or saida)[:120]}")
            bruto[m["file"]] = []
    return bruto


def rodar_checkov(corpus):
    cmd = ["checkov", "-d", str(corpus), "--framework", "dockerfile", "secrets", "-o", "json", "--compact"]
    cod, saida, erro = rodar(cmd)
    try:
        return json.loads(saida)
    except json.JSONDecodeError:
        raise SystemExit(f"Checkov não devolveu JSON. Comando: {' '.join(cmd)}\n{erro[-800:]}")


def versoes():
    linhas = [f"python {platform.python_version()} ({platform.system()})"]
    for nome, cmd in (("hadolint", cmd_hadolint() + ["--version"]), ("checkov", ["checkov", "--version"])):
        try:
            linhas.append(f"{nome} {rodar(cmd)[1].strip() or '?'}")
        except FileNotFoundError:
            linhas.append(f"{nome} NÃO ENCONTRADO")
    linhas.append("checkov frameworks: dockerfile, secrets")
    return "\n".join(linhas) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--saida", default="results")
    ap.add_argument("--mapeamento", default="mapeamento.csv")
    ap.add_argument("--somente-normalizar", action="store_true")
    a = ap.parse_args()

    corpus, saida = Path(a.corpus), Path(a.saida)
    raw = saida / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifesto = ler_manifesto(corpus)
    textos = {m["file"]: ler_texto(corpus / m["file"]) for m in manifesto}
    tempos = {}

    if not a.somente_normalizar:
        (saida / "versoes.txt").write_text(versoes(), encoding="utf-8")
        print((saida / "versoes.txt").read_text(encoding="utf-8"))
        t = time.time()
        print("Rodando Hadolint...")
        (raw / "hadolint.json").write_text(json.dumps(rodar_hadolint(corpus, manifesto), indent=1, sort_keys=True), encoding="utf-8")
        tempos["hadolint_s"] = round(time.time() - t, 1)
        t = time.time()
        print("Rodando Checkov (demora alguns minutos)...")
        (raw / "checkov.json").write_text(json.dumps(rodar_checkov(corpus), indent=1), encoding="utf-8")
        tempos["checkov_s"] = round(time.time() - t, 1)

    mapa = normalizar.carregar_mapeamento(a.mapeamento)
    h = json.loads((raw / "hadolint.json").read_text(encoding="utf-8"))
    c = json.loads((raw / "checkov.json").read_text(encoding="utf-8"))
    a0 = normalizar.hadolint(h, mapa, textos, "A0") + normalizar.checkov(c, mapa, textos, str(corpus.resolve()), "A0")

    t = time.time()
    rp = []
    for arq, texto in textos.items():
        rp += regras_proprias.analisar(arq, texto, "regras_proprias")
    tempos["regras_proprias_s"] = round(time.time() - t, 2)
    a1 = [dict(f, method="A1") for f in a0] + [dict(f, method="A1") for f in rp]

    norm = saida / "normalized"
    salvar_jsonl(norm / "A0.jsonl", ordenar(a0))
    salvar_jsonl(norm / "A1.jsonl", ordenar(a1))
    salvar_jsonl(norm / "regras_proprias.jsonl", ordenar(rp))
    if tempos:
        (saida / "tempos.json").write_text(json.dumps(tempos, indent=1), encoding="utf-8")

    # Auditoria: regras fora de escopo e cobertura
    fora = Counter((f["tool"], f["rule_id"], f["message"][:80]) for f in a0 if f["category"] == FORA)
    salvar_csv(saida / "fora_de_escopo.csv",
               [{"tool": t, "rule_id": r, "mensagem": m, "qtd": n} for (t, r, m), n in fora.most_common()],
               ["tool", "rule_id", "mensagem", "qtd"], excel=True)
    print("\nAchados brutos por ferramenta e categoria:")
    cont = Counter((f["tool"], f["category"]) for f in a0 + rp)
    for tool in ("hadolint", "checkov", "regras_proprias"):
        print(f"  {tool:16s} " + "  ".join(f"{cat}={cont[(tool, cat)]}" for cat in CATEGORIAS + (FORA,)))
    print(f"  total A0 = {len(a0)} | regras próprias = {len(rp)} | A1 = {len(a1)}")
    cob = normalizar.cobertura_checkov(c, str(corpus.resolve()))
    n_docker = sum(m["tipo"] == "dockerfile" for m in manifesto)
    vistos = {f for f in cob.get("dockerfile", set()) if f in textos}
    print(f"\nCobertura do Checkov (dockerfile): {len(vistos)} de {n_docker} Dockerfiles analisados")
    faltando = sorted(m["file"] for m in manifesto if m["tipo"] == "dockerfile" and m["file"] not in vistos)
    for f in faltando:
        print(f"  não analisado: {f}")
    print(f"\nRegras fora de escopo: {saida / 'fora_de_escopo.csv'} (decida e registre cada uma)")


if __name__ == "__main__":
    main()
