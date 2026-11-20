from sin451 import normalizar
from sin451.avaliador import casar, metricas
from sin451.ia import converter, extrair_json

MAPA = [("hadolint", "DL3002", "ROOT_USER"), ("checkov", "CKV_SECRET_*", "HARDCODED_SECRET"),
        ("checkov", "CKV_DOCKER_7", "UNPINNED_VERSION")]
TEXTOS = {"r/Dockerfile": "FROM x:latest\nENV PASSWORD=abc\nUSER root\n"}


def test_hadolint_e_checkov():
    h = normalizar.hadolint({"r/Dockerfile": [{"code": "DL3002", "line": 3, "message": "m"},
                                              {"code": "DL3059", "line": 2, "message": "m"}]}, MAPA, TEXTOS)
    assert [(f["line"], f["category"]) for f in h] == [(3, "ROOT_USER"), (2, "OUT_OF_SCOPE")]
    dados = [{"check_type": "dockerfile", "results": {"failed_checks": [
                {"check_id": "CKV_DOCKER_7", "file_path": "/r/Dockerfile", "file_line_range": [1, 1], "check_name": "n"}]}},
             {"check_type": "secrets", "results": {"failed_checks": [
                {"check_id": "CKV_SECRET_6", "file_abs_path": "/c/r/Dockerfile", "file_line_range": [2, 2]},
                {"check_id": "CKV_SECRET_6", "file_abs_path": "/c/manifesto.csv", "file_line_range": [2, 2]}]}}]
    c = normalizar.checkov(dados, MAPA, TEXTOS, "/c")
    assert [(f["line"], f["category"]) for f in c] == [(1, "UNPINNED_VERSION"), (2, "HARDCODED_SECRET")]
    assert "****" in c[1]["evidence"] and "abc" not in c[1]["evidence"]


def f(line, cat="ROOT_USER", arq="a"):
    return {"file": arq, "line": line, "category": cat, "rule_id": "x"}


def test_casamento():
    gab = [f(10), f(20), f(5, "HARDCODED_SECRET")]
    ach = [f(11), f(12), f(30), f(10), f(5, "OUT_OF_SCOPE")]
    m = metricas(casar(ach, gab, 2))
    assert (m["TP"], m["FP"], m["FN"], m["DUP"]) == (1, 1, 2, 2)
    m0 = metricas(casar(ach, gab, 0))
    assert (m0["TP"], m0["FP"], m0["FN"]) == (1, 3, 2)


def test_parse_llm():
    texto = '<think>hmm</think>Claro!\n```json\n{"findings":[{"line":3,"category":"root_user","evidence":"USER root"},' \
            '{"line":99,"category":"ROOT_USER"},{"line":"2","category":"XYZ"}]}\n```'
    ach, desc = converter(texto, "r/Dockerfile", 3, "m", "IA-pequeno")
    assert [(a["line"], a["category"]) for a in ach] == [(3, "ROOT_USER")] and desc == 2
    assert extrair_json('[{"line": 1, "category": "ROOT_USER"}]')["findings"][0]["line"] == 1
