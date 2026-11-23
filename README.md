# SIN 451 — Detecção de configuração insegura em Docker: método clássico × IA (NVIDIA)

| Dia | Script | O que faz |
|-----|--------|-----------|
| 1 | `01_coletar.py` | clona os repositórios de `repos.txt` e monta `corpus/` + `manifesto.csv` |
| 1–2 | `02_gabarito.py rascunho` / `converter` | gabarito anotado à mão → `gabarito/gabarito.jsonl` |
| 3 | `03_classico.py` | Hadolint + Checkov (A0) e A0 + regras próprias (A1), no schema comum |
| 4–5 | `04_ia.py` | modelos NVIDIA em 3 níveis, com cache e retry |
| 5 | `05_avaliar.py` | TP, FP, FN, precisão, recall, F1 e IC 95% |
| 6 | `06_graficos.py`, `07_painel.py` | figuras e painel.html |
| 6 | `08_demonstracao.py` | laboratório `demo/` vulnerável × corrigido: ferramentas + execução (root, segredo na imagem, digest) |
| 7 | `09_apresentacao.py` | slides com os seus resultados em `apresentacao/` (site estático; textos em `apresentacao.json`) |
| 7 | `10_app.py` | app local em http://127.0.0.1:8451: slides, painel e análise ao vivo com impacto e mitigação |

Testes: `python -m pytest -q` (10 testes). Regras próprias no laboratório:
`python -m sin451.regras_proprias laboratorio/Dockerfile laboratorio/docker-compose.yml`

Corpus: só análise estática (nada é construído ou executado). A única execução é a do laboratório `demo/`, que é seu. Segredos aparecem mascarados (`****`).
