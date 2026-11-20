"""Peças comuns: categorias, schema de finding, leitura/escrita de JSONL e CSV."""
import csv
import hashlib
import io
import json
import re
from pathlib import Path

CATEGORIAS = ("UNPINNED_VERSION", "ROOT_USER", "HARDCODED_SECRET")
FORA = "OUT_OF_SCOPE"

# Schema comum de finding (todas as fontes saem neste formato):
# {"file": "dvwa/Dockerfile",      caminho relativo à pasta corpus, com "/"
#  "line": 7,                       linha (1 = primeira)
#  "category": "ROOT_USER",         uma das CATEGORIAS ou OUT_OF_SCOPE
#  "rule_id": "DL3002",             regra que gerou (ou "LLM")
#  "tool": "hadolint",              hadolint | checkov | regras_proprias | <modelo>
#  "method": "A0",                  A0 | A1 | regras_proprias | IA-pequeno ...
#  "message": "texto curto",
#  "evidence": "USER root"}         trecho da linha (segredos mascarados)
CAMPOS = ("file", "line", "category", "rule_id", "tool", "method", "message", "evidence")


def finding(file, line, category, rule_id, tool, method, message="", evidence=""):
    return {
        "file": str(file).replace("\\", "/"),
        "line": max(1, int(line or 1)),
        "category": category,
        "rule_id": str(rule_id),
        "tool": tool,
        "method": method,
        "message": (message or "").strip()[:300],
        "evidence": mascarar((evidence or "").strip())[:200],
    }


def ordenar(findings):
    return sorted(findings, key=lambda f: (f["file"], f["line"], f["category"], f["rule_id"], f["tool"]))


def salvar_jsonl(caminho, itens):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as fh:
        for item in itens:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def ler_jsonl(caminho):
    itens = []
    with open(caminho, encoding="utf-8") as fh:
        for n, linha in enumerate(fh, 1):
            linha = linha.strip()
            if linha:
                try:
                    itens.append(json.loads(linha))
                except json.JSONDecodeError as e:
                    raise SystemExit(f"{caminho}, linha {n}: JSON inválido ({e})")
    return itens


def ler_texto(caminho):
    dados = Path(caminho).read_bytes()
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(cod)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", errors="replace")


def ler_csv(caminho):
    """Lê CSV salvo pelo Excel em português (; e cp1252) ou pelo Python (, e utf-8)."""
    texto = ler_texto(caminho)
    amostra = texto[:4096]
    delim = ";" if amostra.count(";") > amostra.count(",") else ","
    return list(csv.DictReader(io.StringIO(texto), delimiter=delim))


def salvar_csv(caminho, linhas, campos, excel=False):
    """excel=True grava com ; e BOM, para abrir certo no Excel em português."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig" if excel else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=";" if excel else ",", extrasaction="ignore")
        w.writeheader()
        for l in linhas:
            w.writerow(l)


def ler_manifesto(corpus):
    caminho = Path(corpus) / "manifesto.csv"
    if not caminho.exists():
        raise SystemExit(f"Não achei {caminho}. Rode antes: python 01_coletar.py")
    return ler_csv(caminho)


def conjunto_de(arquivo):
    """Divide o corpus de forma fixa: ~30% 'dev' (pode olhar e ajustar), ~70% 'teste' (só medir)."""
    h = int(hashlib.sha1(arquivo.encode("utf-8")).hexdigest(), 16)
    return "dev" if h % 10 < 3 else "teste"


_SEGREDO_KV = re.compile(r"(?i)((?:pass|pwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|credential)[\w-]*\s*[=:]\s*[\"']?)([^\s\"']+)")


def mascarar(texto):
    """Troca o valor de pares chave=valor sensíveis por ****. Nunca publique credenciais."""
    return _SEGREDO_KV.sub(lambda m: m.group(1) + ("****" if not m.group(2).startswith("$") else m.group(2)), texto)
