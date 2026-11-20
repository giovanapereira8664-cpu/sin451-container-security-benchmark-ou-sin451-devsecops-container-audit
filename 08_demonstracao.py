"""Dia 6 — Demonstração em ambiente controlado: laboratório VULNERÁVEL × CORRIGIDO.

Uso:  python 08_demonstracao.py              (estático + execução com Docker)
      python 08_demonstracao.py --sem-docker (só a parte estática)

Roda SÓ nos arquivos da pasta demo/ (seus, controlados). Nunca nos arquivos do corpus.
1. Estático: regras próprias, Hadolint e Checkov nas duas versões (quantos achados por categoria).
2. Execução: constrói as duas imagens e mostra o impacto de cada falha:
   - ROOT_USER: com que usuário o processo roda e quantas capacidades do Linux ele tem;
   - HARDCODED_SECRET: se a senha pode ser lida da imagem (docker history / docker inspect);
   - UNPINNED_VERSION: para qual digest a tag móvel aponta hoje (amanhã pode ser outro).
Saída: results/evidencias/evidencias.json (usado nos slides) e um .txt por versão (log completo, mascarado).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sin451 import normalizar, regras_proprias  # noqa: E402
from sin451.comum import CATEGORIAS, FORA, ler_texto, mascarar  # noqa: E402

VERSOES = ("vulneravel", "corrigido")
SENHA_RUNTIME = "senha-de-demonstracao-passada-em-tempo-de-execucao"


def rodar(cmd, log, entrada=None, env=None, cwd=None):
    log.append(f"$ {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, input=entrada, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, cwd=cwd, timeout=900)
    except FileNotFoundError:
        log.append("  (comando não encontrado)")
        return None, ""
    except subprocess.TimeoutExpired:
        log.append("  (tempo esgotado)")
        return None, ""
    saida = (r.stdout or "") + (r.stderr or "")
    log.extend("  " + mascarar(l)[:300] for l in saida.strip().splitlines()[-40:])
    return r.returncode, r.stdout or ""


def estatico(pasta, mapa, log):
    cont = {c: 0 for c in CATEGORIAS}
    por_ferramenta = {}
    achados = []
    textos = {f"{pasta.name}/{n}": ler_texto(pasta / n) for n in ("Dockerfile", "docker-compose.yml")}
    for arq, texto in textos.items():
        achados += regras_proprias.analisar(arq, texto)
    hadolint_cmd = ["hadolint"] if shutil.which("hadolint") else ["docker", "run", "--rm", "-i", "hadolint/hadolint", "hadolint"]
    cod, saida = rodar(hadolint_cmd + ["-f", "json", "-"], log, entrada=textos[f"{pasta.name}/Dockerfile"])
    if cod is not None:
        try:
            achados += normalizar.hadolint({f"{pasta.name}/Dockerfile": json.loads(saida or "[]")}, mapa, textos)
        except json.JSONDecodeError:
            log.append("  (Hadolint não devolveu JSON)")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / pasta.name
        shutil.copytree(pasta, dest)
        cod, saida = rodar(["checkov", "-d", tmp, "--framework", "dockerfile", "secrets", "-o", "json", "--compact"], log)
        if cod is not None:
            try:
                achados += normalizar.checkov(json.loads(saida), mapa, textos, str(Path(tmp).resolve()))
            except json.JSONDecodeError:
                log.append("  (Checkov não devolveu JSON)")
    unicos = set()
    for f in achados:
        if f["category"] != FORA:
            por_ferramenta[f["tool"]] = por_ferramenta.get(f["tool"], 0) + 1
            unicos.add((f["file"], f["line"], f["category"]))
    for _, _, cat in unicos:          # mesma falha apontada por 2 ferramentas conta 1 vez
        cont[cat] += 1
    log.append("Achados estáticos: " + ", ".join(f"{k}={v}" for k, v in cont.items()))
    linhas = sorted({(f["file"], f["line"], f["category"], f["tool"]) for f in achados if f["category"] != FORA})
    return {"por_categoria": cont, "por_ferramenta": por_ferramenta,
            "achados": [{"file": a, "line": l, "category": c, "tool": t} for a, l, c, t in linhas]}


def capacidades(texto):
    for l in texto.splitlines():
        if l.startswith("CapEff:"):
            return bin(int(l.split()[1], 16)).count("1")
    return None


def dinamico(pasta, versao, log):
    ev = {}
    env = dict(os.environ, DB_PASSWORD=SENHA_RUNTIME, COMPOSE_PROJECT_NAME=f"sin451{versao}")
    comp = ["docker", "compose", "-f", str(pasta / "docker-compose.yml")]
    cod, _ = rodar(comp + ["build", "app"], log, env=env)
    if cod != 0:
        ev["erro"] = "falha ao construir a imagem (veja o log)"
        return ev
    imagem = f"sin451-lab-{versao}"
    # ROOT_USER: usuário e capacidades do processo, rodando como o compose manda
    cod, saida = rodar(comp + ["run", "--rm", "--no-deps", "app", "sh", "-c", "id; grep CapEff /proc/self/status"], log, env=env)
    if cod == 0:
        ev["usuario"] = saida.strip().splitlines()[0] if saida.strip() else "?"
        ev["root"] = "uid=0(" in saida
        ev["capacidades"] = capacidades(saida)
    # HARDCODED_SECRET: a senha aparece nas camadas ou na configuração da imagem?
    _, hist = rodar(["docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", imagem], log)
    _, insp = rodar(["docker", "image", "inspect", "--format", "{{json .Config.Env}}", imagem], log)
    segredo_linhas = [mascarar(l.strip()) for l in (hist + "\n" + insp).splitlines() if "PASSWORD" in l.upper()]
    ev["segredo_na_imagem"] = any("PASSWORD=" in l.upper() and SENHA_RUNTIME not in l for l in (hist + insp).splitlines())
    ev["segredo_evidencia"] = segredo_linhas[:3]
    # UNPINNED_VERSION: a que digest a imagem base aponta hoje
    base = next((l.split()[1] for l in ler_texto(pasta / "Dockerfile").splitlines() if l.upper().startswith("FROM ")), "")
    _, dig = rodar(["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", base], log)
    ev["imagem_base"] = base
    ev["digest_hoje"] = dig.strip()
    ev["tag_movel"] = regras_proprias.classificar_tag(base)[0] in ("movel", "sem_tag")
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", default="demo")
    ap.add_argument("--saida", default="results/evidencias")
    ap.add_argument("--mapeamento", default="mapeamento.csv")
    ap.add_argument("--sem-docker", action="store_true")
    a = ap.parse_args()
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    mapa = normalizar.carregar_mapeamento(a.mapeamento)
    usar_docker = not a.sem_docker and shutil.which("docker") and \
        subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    if not a.sem_docker and not usar_docker:
        print("Docker não está rodando: faço só a parte estática. Abra o Docker Desktop e rode de novo.")
    resultado = {"data": datetime.now().strftime("%d/%m/%Y %H:%M"), "docker": bool(usar_docker), "versoes": {}}
    for versao in VERSOES:
        pasta = Path(a.demo) / versao
        log = [f"### Laboratório {versao.upper()} — {resultado['data']}"]
        print(f"\n== {versao}")
        r = {"estatico": estatico(pasta, mapa, log)}
        if usar_docker:
            r["execucao"] = dinamico(pasta, versao, log)
        resultado["versoes"][versao] = r
        (saida / f"{versao}.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
        print("  estático:", r["estatico"]["por_categoria"])
        if "execucao" in r:
            e = r["execucao"]
            print(f"  usuário: {e.get('usuario')} | capacidades: {e.get('capacidades')} | "
                  f"senha legível na imagem: {e.get('segredo_na_imagem')} | base: {e.get('imagem_base')} -> {e.get('digest_hoje')}")
    (saida / "evidencias.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nEvidências em {saida}/ (tire também capturas de tela desta saída para o relatório)")


if __name__ == "__main__":
    main()
