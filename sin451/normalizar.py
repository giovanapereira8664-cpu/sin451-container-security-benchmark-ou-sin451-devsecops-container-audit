"""Converte a saída bruta do Hadolint e do Checkov para o schema comum."""
import fnmatch
import os

from .comum import FORA, CATEGORIAS, finding, ler_csv


def carregar_mapeamento(caminho):
    """mapeamento.csv: tool,rule_id,category,justificativa (rule_id aceita * no fim)."""
    regras = []
    for l in ler_csv(caminho):
        cat = l["category"].strip()
        if cat not in CATEGORIAS + (FORA,):
            raise SystemExit(f"mapeamento: categoria desconhecida '{cat}' na regra {l['rule_id']}")
        regras.append((l["tool"].strip().lower(), l["rule_id"].strip(), cat))
    return regras


def categoria(mapa, tool, rule_id):
    for t, padrao, cat in mapa:
        if t == tool and fnmatch.fnmatchcase(rule_id, padrao):
            return cat
    return FORA


def ler_linha(textos, arquivo, linha):
    linhas = textos.get(arquivo, "").splitlines()
    return linhas[linha - 1].strip() if 0 < linha <= len(linhas) else ""


def hadolint(bruto, mapa, textos, metodo="A0"):
    """bruto = {arquivo: [ {code, line, message, level}, ... ]}"""
    res = []
    for arquivo, itens in bruto.items():
        for it in itens or []:
            code = it.get("code", "?")
            linha = int(it.get("line") or 1)
            res.append(finding(arquivo, linha, categoria(mapa, "hadolint", code), code, "hadolint", metodo,
                               it.get("message", ""), ler_linha(textos, arquivo, linha)))
    return res


def blocos_checkov(dados):
    """O Checkov devolve um dict (1 framework) ou uma lista (vários)."""
    for bloco in dados if isinstance(dados, list) else [dados]:
        if isinstance(bloco, dict) and "results" in bloco:
            yield bloco


def caminho_checkov(check, corpus_abs):
    abs_ = check.get("file_abs_path")
    if abs_:
        try:
            return os.path.relpath(abs_, corpus_abs).replace("\\", "/")
        except ValueError:
            pass
    return (check.get("repo_file_path") or check.get("file_path") or "").lstrip("/").replace("\\", "/")


def checkov(dados, mapa, textos, corpus_abs, metodo="A0"):
    res = []
    for bloco in blocos_checkov(dados):
        for c in bloco["results"].get("failed_checks", []):
            arquivo = caminho_checkov(c, corpus_abs)
            if arquivo not in textos:          # ex.: manifesto.csv, arquivos fora do corpus
                continue
            faixa = c.get("file_line_range") or [1, 1]
            linha = max(1, int(faixa[0] or 1))
            rid = c.get("check_id", "?")
            res.append(finding(arquivo, linha, categoria(mapa, "checkov", rid), rid, "checkov", metodo,
                               c.get("check_name", ""), ler_linha(textos, arquivo, linha)))
    return res


def cobertura_checkov(dados, corpus_abs):
    """Quais arquivos o Checkov realmente analisou, por tipo de verificação."""
    vistos = {}
    for bloco in blocos_checkov(dados):
        tipo = bloco.get("check_type", "?")
        for chave in ("failed_checks", "passed_checks"):
            for c in bloco["results"].get(chave, []):
                vistos.setdefault(tipo, set()).add(caminho_checkov(c, corpus_abs))
    return vistos
