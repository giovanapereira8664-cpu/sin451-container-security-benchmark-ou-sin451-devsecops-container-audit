"""Dia 1 — Clona repositórios públicos e monta a pasta corpus/ com Dockerfiles e compose.

Uso:
    python 01_coletar.py                      # usa repos.txt, até 6 arquivos por repositório
    python 01_coletar.py --max-por-repo 4
Saída:
    corpus/<repo>/<caminho original>          cópia dos arquivos escolhidos
    corpus/manifesto.csv                      file, repo, url, commit, tipo, linhas, conjunto
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451.comum import conjunto_de, ler_texto, salvar_csv  # noqa: E402
from sin451.regras_proprias import eh_compose  # noqa: E402

IGNORAR = {".git", "node_modules", "vendor", "third_party", ".github", "testdata", "fixtures"}


def eh_dockerfile(nome):
    n = nome.lower()
    return n == "dockerfile" or n.startswith("dockerfile.") or n.endswith(".dockerfile") or n.endswith("-dockerfile")


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def clonar(nome, url, commit, pasta):
    destino = pasta / nome
    if not destino.exists():
        print(f"  clonando {url}")
        git("clone", "--depth", "1", "--quiet", url, str(destino))
        if commit:
            git("fetch", "--depth", "1", "--quiet", "origin", commit, cwd=destino)
            git("checkout", "--quiet", commit, cwd=destino)
    return destino, git("rev-parse", "HEAD", cwd=destino)


def achar(raiz):
    achados = []
    for p in raiz.rglob("*"):
        if any(parte in IGNORAR for parte in p.relative_to(raiz).parts) or not p.is_file():
            continue
        if eh_dockerfile(p.name):
            achados.append((p, "dockerfile"))
        elif eh_compose(p.name):
            achados.append((p, "compose"))
    # mais rasos primeiro (geralmente os arquivos "de verdade" do projeto), depois ordem alfabética
    return sorted(achados, key=lambda x: (len(x[0].relative_to(raiz).parts), str(x[0]).lower()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", default="repos.txt")
    ap.add_argument("--saida", default="corpus")
    ap.add_argument("--clones", default="_clones")
    ap.add_argument("--max-por-repo", type=int, default=6)
    a = ap.parse_args()

    saida, clones = Path(a.saida), Path(a.clones)
    clones.mkdir(exist_ok=True)
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir()
    linhas = []
    for bruta in Path(a.repos).read_text(encoding="utf-8").splitlines():
        bruta = bruta.split("#", 1)[0].strip()
        if not bruta:
            continue
        partes = bruta.split()
        nome, url = partes[0], partes[1]
        commit = partes[2] if len(partes) > 2 else ""
        try:
            raiz, hash_ = clonar(nome, url, commit, clones)
        except RuntimeError as e:
            print(f"  ERRO em {nome}: {e} (pulei)")
            continue
        escolhidos = achar(raiz)[: a.max_por_repo]
        for origem, tipo in escolhidos:
            rel = origem.relative_to(raiz).as_posix()
            arquivo = f"{nome}/{rel}"
            dest = saida / nome / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origem, dest)
            linhas.append({"file": arquivo, "repo": nome, "url": url, "commit": hash_, "tipo": tipo,
                           "linhas": len(ler_texto(dest).splitlines()), "conjunto": conjunto_de(arquivo)})
        print(f"  {nome}: {len(escolhidos)} arquivo(s), commit {hash_[:10]}")
    salvar_csv(saida / "manifesto.csv", linhas, ["file", "repo", "url", "commit", "tipo", "linhas", "conjunto"])
    n_dev = sum(l["conjunto"] == "dev" for l in linhas)
    print(f"\nCorpus: {len(linhas)} arquivos ({sum(l['tipo'] == 'dockerfile' for l in linhas)} Dockerfiles, "
          f"{sum(l['tipo'] == 'compose' for l in linhas)} compose); dev={n_dev}, teste={len(linhas) - n_dev}")
    print(f"Manifesto: {saida / 'manifesto.csv'}")


if __name__ == "__main__":
    main()
