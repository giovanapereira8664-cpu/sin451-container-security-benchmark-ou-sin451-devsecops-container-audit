"""Método IA: chamada aos modelos da NVIDIA (API compatível com OpenAI), com cache e retry.

Usa só a biblioteca padrão do Python (urllib), então não precisa instalar nada.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .comum import CATEGORIAS, finding

URL_PADRAO = "https://integrate.api.nvidia.com/v1"
VERSAO_PROMPT = "v1"

SISTEMA = """Você é um analista de segurança que revisa arquivos de infraestrutura (Dockerfile e docker-compose).
Procure SOMENTE estas 3 categorias de falha:

UNPINNED_VERSION: imagem sem versão fixa (sem tag, tag "latest" ou tag móvel como "alpine", "stable", "lts")
  em FROM, COPY --from ou "image:"; ou pacote do sistema instalado sem versão
  (apt-get/apt/apk/yum/dnf install sem "=versão"). Tag com número de versão (ex.: nginx:1.27) ou digest @sha256 NÃO é falha.
  No compose, "image:" em serviço que também tem "build:" só dá nome à imagem construída: NÃO é falha.
ROOT_USER: o contêiner roda como root: último USER do estágio final é root/0; estágio final sem nenhum USER
  (marque a linha do último FROM); ou, no compose, "user: root" ou "privileged: true".
HARDCODED_SECRET: senha, token ou chave escrita com valor literal no arquivo (ENV, ARG, environment do compose).
  Valor vindo de variável (${VAR}) ou vazio NÃO é falha.

Responda APENAS com um JSON neste formato, sem texto antes ou depois:
{"findings": [{"line": <número da linha>, "category": "<UNPINNED_VERSION|ROOT_USER|HARDCODED_SECRET>", "evidence": "<trecho curto da linha>"}]}
Se não houver falhas, responda {"findings": []}. Use os números de linha mostrados à esquerda."""


def montar_mensagens(arquivo, texto):
    numerado = "\n".join(f"{i:4d}| {l}" for i, l in enumerate(texto.splitlines(), 1))
    return [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": f"Arquivo: {arquivo}\n\n{numerado}"},
    ]


def chave_api():
    chave = os.environ.get("NVIDIA_API_KEY")
    if not chave and Path(".env").exists():
        for linha in Path(".env").read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith("NVIDIA_API_KEY="):
                chave = linha.split("=", 1)[1].strip().strip("'\"")
    if not chave:
        raise SystemExit("Defina a chave: crie um arquivo .env com a linha NVIDIA_API_KEY=nvapi-...")
    return chave


def _requisicao(url, chave, corpo=None, timeout=120):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method="POST" if dados else "GET", headers={
        "Authorization": f"Bearer {chave}", "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def listar_modelos(chave, base=None):
    base = base or os.environ.get("NVIDIA_BASE_URL", URL_PADRAO)
    return sorted(m["id"] for m in _requisicao(f"{base}/models", chave).get("data", []))


class Cliente:
    def __init__(self, chave, pasta_cache="cache", intervalo=1.6, tentativas=5, max_tokens=1500, base=None):
        self.chave, self.cache = chave, Path(pasta_cache)
        self.base = base or os.environ.get("NVIDIA_BASE_URL", URL_PADRAO)
        self.intervalo, self.tentativas, self.max_tokens = intervalo, tentativas, max_tokens
        self._ultima = 0.0

    def _arquivo_cache(self, modelo, mensagens):
        h = hashlib.sha256(json.dumps([modelo, VERSAO_PROMPT, mensagens, self.max_tokens],
                                      ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return self.cache / re.sub(r"[^\w.-]", "_", modelo) / f"{h[:32]}.json"

    def conversar(self, modelo, mensagens):
        """Devolve (texto, info). info['origem'] = 'cache' ou 'api'."""
        arq = self._arquivo_cache(modelo, mensagens)
        if arq.exists():
            salvo = json.loads(arq.read_text(encoding="utf-8"))
            return salvo["texto"], {**salvo["info"], "origem": "cache"}
        corpo = {"model": modelo, "messages": mensagens, "temperature": 0, "top_p": 1,
                 "max_tokens": self.max_tokens, "stream": False}
        espera = 4
        for tentativa in range(1, self.tentativas + 1):
            pausa = self.intervalo - (time.time() - self._ultima)   # respeita o limite por minuto
            if pausa > 0:
                time.sleep(pausa)
            self._ultima = time.time()
            inicio = time.time()
            try:
                resp = _requisicao(f"{self.base}/chat/completions", self.chave, corpo)
            except urllib.error.HTTPError as e:
                detalhe = e.read().decode("utf-8", "replace")[:300]
                if e.code in (429, 500, 502, 503, 504) and tentativa < self.tentativas:
                    print(f"    HTTP {e.code}; nova tentativa em {espera}s")
                    time.sleep(espera)
                    espera *= 2
                    continue
                raise RuntimeError(f"HTTP {e.code}: {detalhe}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if tentativa < self.tentativas:
                    print(f"    falha de rede ({e}); nova tentativa em {espera}s")
                    time.sleep(espera)
                    espera *= 2
                    continue
                raise RuntimeError(f"rede: {e}")
            msg = resp["choices"][0]["message"]
            texto = msg.get("content") or ""
            uso = resp.get("usage") or {}
            info = {"segundos": round(time.time() - inicio, 2),
                    "tokens_entrada": uso.get("prompt_tokens"), "tokens_saida": uso.get("completion_tokens")}
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(json.dumps({"modelo": modelo, "texto": texto, "info": info}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            return texto, {**info, "origem": "api"}
        raise RuntimeError("tentativas esgotadas")


def extrair_json(texto):
    """Tira <think>...</think>, cercas ```json e texto em volta; devolve o objeto ou levanta ValueError."""
    t = re.sub(r"(?s)<think>.*?</think>", "", texto or "").strip()
    cerca = re.search(r"(?s)```(?:json)?\s*(.*?)```", t)
    if cerca:
        t = cerca.group(1).strip()
    ordem = sorted((("{", "}"), ("[", "]")), key=lambda p: t.find(p[0]) if t.find(p[0]) != -1 else 10**9)
    for abre, fecha in ordem:   # tenta primeiro o que aparece antes (objeto ou lista)
        i, j = t.find(abre), t.rfind(fecha)
        if i != -1 and j > i:
            try:
                obj = json.loads(t[i:j + 1])
                return {"findings": obj} if isinstance(obj, list) else obj
            except json.JSONDecodeError:
                continue
    raise ValueError("resposta sem JSON válido")


def converter(texto, arquivo, n_linhas, modelo, metodo):
    """Resposta da LLM -> findings no schema comum. Itens inválidos são descartados e contados."""
    obj = extrair_json(texto)
    achados, descartados = [], 0
    for it in obj.get("findings", []) if isinstance(obj, dict) else []:
        try:
            linha = int(str(it.get("line")).strip())
            cat = str(it.get("category", "")).strip().upper()
        except (ValueError, AttributeError):
            descartados += 1
            continue
        if cat not in CATEGORIAS or not 1 <= linha <= max(1, n_linhas):
            descartados += 1
            continue
        achados.append(finding(arquivo, linha, cat, "LLM", modelo, metodo,
                               str(it.get("explanation", ""))[:200], str(it.get("evidence", ""))))
    return achados, descartados
