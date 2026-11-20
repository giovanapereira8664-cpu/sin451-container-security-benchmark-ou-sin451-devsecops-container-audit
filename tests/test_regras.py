from pathlib import Path

from sin451.regras_proprias import analisar, classificar_tag, instrucoes

DADOS = Path(__file__).parent / "dados"


def achados(nome):
    texto = (DADOS / nome).read_text(encoding="utf-8")
    return sorted((f["line"], f["category"]) for f in analisar(nome, texto))


def test_laboratorio_dockerfile():
    assert achados("Dockerfile") == [(2, "UNPINNED_VERSION"), (4, "UNPINNED_VERSION"), (5, "HARDCODED_SECRET"),
                                     (6, "UNPINNED_VERSION"), (7, "ROOT_USER")]


def test_laboratorio_compose():
    assert achados("docker-compose.yml") == [(3, "UNPINNED_VERSION"), (4, "ROOT_USER"), (6, "HARDCODED_SECRET"),
                                             (12, "HARDCODED_SECRET")]


def test_tags():
    assert classificar_tag("nginx:1.27")[0] == "fixa"
    assert classificar_tag("ubuntu:noble")[0] == "fixa"
    assert classificar_tag("python:alpine")[0] == "movel"
    assert classificar_tag("redis")[0] == "sem_tag"
    assert classificar_tag("localhost:5000/app")[0] == "sem_tag"
    assert classificar_tag("img@sha256:abc")[0] == "fixa"
    assert classificar_tag("${IMG:-postgres:latest}")[0] == "movel"
    assert classificar_tag("${IMG}")[0] == "indeterminado"


def test_user_comentado_e_user_final():
    texto = "FROM node:20\n# USER node\nRUN echo oi\n"
    assert [(f["line"], f["rule_id"]) for f in analisar("x/Dockerfile", texto)] == [(1, "RP-NOUSER")]
    texto = "FROM getsentry/sentry:24.1.0\nUSER 0\nRUN echo\nUSER sentry\n"
    assert analisar("x/Dockerfile", texto) == []


def test_multiestagio_e_continuacao():
    texto = "FROM golang:1.22 AS build\nRUN apk add \\\n    git \\\n    make\nFROM build\nUSER app\n"
    assert [(i[0], i[1]) for i in instrucoes(texto)] == [(1, "FROM"), (2, "RUN"), (5, "FROM"), (6, "USER")]
    assert [(f["line"], f["rule_id"]) for f in analisar("x/Dockerfile", texto)] == [(2, "RP-PKG")]


def test_compose_build_nomeia_imagem():
    texto = "services:\n  app:\n    build: .\n    image: meu-app\n  db:\n    image: postgres\n"
    assert [(f["line"], f["category"]) for f in analisar("x/compose.yaml", texto)] == [(6, "UNPINNED_VERSION")]


def test_laboratorio_demo():
    from pathlib import Path as P
    raiz = P(__file__).parent.parent / "demo"
    contar = lambda v: len([f for n in ("Dockerfile", "docker-compose.yml")
                            for f in analisar(n if n != "Dockerfile" else "Dockerfile", (raiz / v / n).read_text())])
    assert contar("vulneravel") == 7 and contar("corrigido") == 0
