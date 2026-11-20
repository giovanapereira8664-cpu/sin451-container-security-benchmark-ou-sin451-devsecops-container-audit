"""Regras próprias (método A1): complementam Hadolint e Checkov.

Mesma lógica do classic_extra_demo.py, mas devolvendo findings no schema comum.
- Dockerfile: lido instrução por instrução (junta linhas com barra invertida).
- docker-compose: lido com o parser YAML (guarda a linha de cada valor).
Limitações (vão para o relatório): não executa nada, não conhece o USER padrão
da imagem base, e ${VAR} sem valor padrão é "indeterminado" (não vira achado).
"""
import re

import yaml

from .comum import finding

FERRAMENTA = "regras_proprias"

# Tags que mudam com o tempo (não identificam uma versão).
TAGS_MOVEIS = {
    "latest", "stable", "edge", "lts", "current", "alpine", "slim", "main", "master",
    "nightly", "rolling", "dev", "develop", "mainline", "beta", "rc", "testing", "unstable",
}
CHAVE_SEGREDO = re.compile(r"(?i)(pass(word|wd)?|pwd|secret|token|api[_-]?key|apikey|private[_-]?key|access[_-]?key|credential)")
VAR = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)(?::?-([^}]*))?\}?")
GERENCIADORES = {
    "apt-get": "=", "apt": "=", "apk": "=", "yum": "-", "dnf": "-", "microdnf": "-",
}


# ---------------------------------------------------------------- utilidades
def resolver(valor, args):
    """Troca ${VAR}/$VAR pelo valor do ARG ou pelo padrão ${VAR:-x}. None = indeterminado."""
    indeterminado = False

    def troca(m):
        nonlocal indeterminado
        nome, padrao = m.group(1), m.group(2)
        if nome in args and args[nome] not in (None, ""):
            return args[nome]
        if padrao is not None and padrao != "":
            return padrao
        indeterminado = True
        return ""

    resolvido = VAR.sub(troca, valor)
    return None if indeterminado else resolvido


def classificar_tag(imagem, args=None):
    """Devolve 'fixa', 'movel', 'sem_tag', 'indeterminado' ou 'ignorar' (scratch)."""
    args = args or {}
    imagem = resolver(imagem.strip().strip("'\""), args)
    if imagem is None:
        return "indeterminado", None
    if imagem in ("", "scratch"):
        return "ignorar", imagem
    if "@sha256:" in imagem:
        return "fixa", imagem
    ultimo = imagem.rsplit("/", 1)[-1]          # tira registry/namespace (registry:5000/x)
    if ":" not in ultimo:
        return "sem_tag", imagem
    tag = ultimo.split(":", 1)[1].lower()
    if tag in TAGS_MOVEIS:
        return "movel", imagem
    # "latest-alpine", "stable-slim" etc. continuam móveis
    if not re.search(r"\d", tag) and any(p in TAGS_MOVEIS for p in re.split(r"[-_.]", tag)):
        return "movel", imagem
    return "fixa", imagem


def instrucoes(texto):
    """Gera (linha_inicial, INSTRUCAO, argumentos), juntando linhas com barra invertida."""
    atual, inicio = None, 0
    for n, bruta in enumerate(texto.splitlines(), 1):
        linha = bruta.strip()
        if atual is None:
            if not linha or linha.startswith("#"):
                continue
            atual, inicio = linha, n
        else:  # continuação da instrução anterior (que terminou com \)
            if not linha or linha.startswith("#"):
                continue
            atual = atual[:-1].rstrip() + " " + linha
        if atual.endswith("\\"):
            continue
        partes = atual.split(None, 1)
        yield inicio, partes[0].upper(), (partes[1] if len(partes) > 1 else "")
        atual = None
    if atual:
        partes = atual.rstrip("\\").split(None, 1)
        yield inicio, partes[0].upper(), (partes[1] if len(partes) > 1 else "")


def pares_env(args):
    """ENV A=1 B=2  ou  ENV A 1  ->  [(A,'1'), ...]"""
    if "=" not in args.split(None, 1)[0]:
        partes = args.split(None, 1)
        return [(partes[0], partes[1] if len(partes) > 1 else "")]
    pares = []
    for m in re.finditer(r"([A-Za-z_][\w.-]*)=(\"[^\"]*\"|'[^']*'|\S*)", args):
        pares.append((m.group(1), m.group(2).strip("'\"")))
    return pares


def valor_literal(valor):
    """True se o valor é um segredo escrito no arquivo (não vazio, não vem de variável)."""
    v = (valor or "").strip().strip("'\"")
    return bool(v) and not v.startswith("$") and v.lower() not in ("none", "null", "false", "true")


def pacotes_sem_versao(cmd):
    """Acha 'apt-get install x y' sem versão. Devolve (gerenciador, [pacotes])."""
    achados = []
    for trecho in re.split(r"&&|;|\|\|", cmd):
        tokens = trecho.split()
        for i, t in enumerate(tokens):
            ger = t.rsplit("/", 1)[-1]
            if ger in GERENCIADORES and i + 1 < len(tokens) and tokens[i + 1] in ("install", "add"):
                sep = GERENCIADORES[ger]
                sem = []
                for p in tokens[i + 2:]:
                    if p.startswith("-") or p.startswith("$") or p in ("\\",):
                        continue
                    if p.endswith((".deb", ".rpm", ".apk")) or "/" in p:
                        continue
                    if sep == "=" and "=" not in p:
                        sem.append(p)
                    elif sep == "-" and not re.search(r"-\d", p):
                        sem.append(p)
                if sem:
                    achados.append((ger, sem))
                break
    return achados


# ---------------------------------------------------------------- Dockerfile
def analisar_dockerfile(texto, arquivo, metodo="regras_proprias"):
    res = []
    args_globais, args = {}, {}
    estagios = set()
    ultimo_from, ultimo_user = None, None
    for linha, inst, a in instrucoes(texto):
        if inst == "ARG":
            nome, _, valor = a.partition("=")
            alvo = args if ultimo_from else args_globais
            alvo[nome.strip()] = valor.strip().strip("'\"") or args_globais.get(nome.strip())
        elif inst == "FROM":
            partes = [p for p in a.split() if not p.startswith("--")]
            imagem = partes[0] if partes else ""
            if len(partes) >= 3 and partes[1].upper() == "AS":
                estagios.add(partes[2].lower())
            args = {}
            ultimo_from, ultimo_user = linha, None
            if imagem.lower() in estagios:
                continue
            tipo, resolvida = classificar_tag(imagem, args_globais)
            if tipo in ("movel", "sem_tag"):
                res.append(finding(arquivo, linha, "UNPINNED_VERSION", "RP-TAG", FERRAMENTA, metodo,
                                   f"imagem base sem versão fixa ({resolvida})", f"FROM {imagem}"))
        elif inst in ("COPY", "ADD") and "--from=" in a:
            origem = re.search(r"--from=(\S+)", a).group(1)
            if origem.lower() in estagios or origem.isdigit():
                continue
            tipo, resolvida = classificar_tag(origem, {**args_globais, **args})
            if tipo in ("movel", "sem_tag"):
                res.append(finding(arquivo, linha, "UNPINNED_VERSION", "RP-TAG", FERRAMENTA, metodo,
                                   f"imagem em COPY --from sem versão fixa ({resolvida})", f"{inst} --from={origem}"))
        elif inst == "RUN":
            for ger, sem in pacotes_sem_versao(a):
                res.append(finding(arquivo, linha, "UNPINNED_VERSION", "RP-PKG", FERRAMENTA, metodo,
                                   f"{ger} instala sem versão: {', '.join(sem[:5])}", f"RUN {ger} install ..."))
        elif inst in ("ENV", "ARG") or inst == "LABEL":
            pass
        elif inst == "USER":
            ultimo_user = (linha, a.strip())
        if inst in ("ENV",) or (inst == "ARG" and "=" in a):
            pares = pares_env(a) if inst == "ENV" else [tuple(a.split("=", 1))]
            for chave, valor in pares:
                if CHAVE_SEGREDO.search(chave) and valor_literal(valor):
                    res.append(finding(arquivo, linha, "HARDCODED_SECRET", "RP-SECRET", FERRAMENTA, metodo,
                                       f"segredo escrito no arquivo ({chave})", f"{inst} {chave}={valor}"))
    # Usuário do estágio final
    if ultimo_from is not None:
        if ultimo_user is None:
            res.append(finding(arquivo, ultimo_from, "ROOT_USER", "RP-NOUSER", FERRAMENTA, metodo,
                               "estágio final sem USER: o contêiner roda como root", "FROM (estágio final)"))
        else:
            usuario = ultimo_user[1].split(":")[0].strip().strip("'\"")
            if usuario in ("root", "0"):
                res.append(finding(arquivo, ultimo_user[0], "ROOT_USER", "RP-ROOT", FERRAMENTA, metodo,
                                   "o último USER é root", f"USER {ultimo_user[1]}"))
    return res


# ---------------------------------------------------------------- compose
def _filho(no, chave):
    if isinstance(no, yaml.MappingNode):
        for k, v in no.value:
            if isinstance(k, yaml.ScalarNode) and k.value == chave:
                return k, v
    return None, None


def analisar_compose(texto, arquivo, metodo="regras_proprias"):
    res = []
    try:
        raiz = yaml.compose(texto, Loader=yaml.SafeLoader)
    except yaml.YAMLError as e:
        print(f"  aviso: {arquivo} não é YAML válido ({e.__class__.__name__}); ignorado")
        return res
    _, servicos = _filho(raiz, "services")
    if servicos is None:          # compose versão 1 (serviços na raiz)
        servicos = raiz
    if not isinstance(servicos, yaml.MappingNode):
        return res
    for _, svc in servicos.value:
        if not isinstance(svc, yaml.MappingNode):
            continue
        _, img = _filho(svc, "image")
        _, build = _filho(svc, "build")
        if isinstance(img, yaml.ScalarNode) and build is None:   # com build:, image: só nomeia a imagem local
            tipo, resolvida = classificar_tag(img.value)
            if tipo in ("movel", "sem_tag"):
                res.append(finding(arquivo, img.start_mark.line + 1, "UNPINNED_VERSION", "RP-TAG", FERRAMENTA, metodo,
                                   f"imagem sem versão fixa ({resolvida})", f"image: {img.value}"))
        _, priv = _filho(svc, "privileged")
        if isinstance(priv, yaml.ScalarNode) and priv.value.lower() in ("true", "yes"):
            res.append(finding(arquivo, priv.start_mark.line + 1, "ROOT_USER", "RP-PRIV", FERRAMENTA, metodo,
                               "privileged: true dá poderes de root no host", "privileged: true"))
        _, user = _filho(svc, "user")
        if isinstance(user, yaml.ScalarNode) and user.value.split(":")[0].strip("'\"") in ("root", "0"):
            res.append(finding(arquivo, user.start_mark.line + 1, "ROOT_USER", "RP-ROOT", FERRAMENTA, metodo,
                               "user: root", f"user: {user.value}"))
        _, env = _filho(svc, "environment")
        pares = []
        if isinstance(env, yaml.MappingNode):
            pares = [(k.value, v.value if isinstance(v, yaml.ScalarNode) else "", v.start_mark.line + 1) for k, v in env.value]
        elif isinstance(env, yaml.SequenceNode):
            for item in env.value:
                if isinstance(item, yaml.ScalarNode) and "=" in item.value:
                    k, v = item.value.split("=", 1)
                    pares.append((k, v, item.start_mark.line + 1))
        for chave, valor, linha in pares:
            if CHAVE_SEGREDO.search(chave) and valor_literal(valor):
                res.append(finding(arquivo, linha, "HARDCODED_SECRET", "RP-SECRET", FERRAMENTA, metodo,
                                   f"segredo escrito no arquivo ({chave})", f"{chave}={valor}"))
    return res


def eh_compose(nome):
    return bool(re.match(r"^(docker-)?compose([.\-_][\w.\-]+)?\.ya?ml$", nome.lower()))


def analisar(caminho_relativo, texto, metodo="regras_proprias"):
    nome = caminho_relativo.rsplit("/", 1)[-1]
    if eh_compose(nome):
        return analisar_compose(texto, caminho_relativo, metodo)
    return analisar_dockerfile(texto, caminho_relativo, metodo)


if __name__ == "__main__":
    # python -m sin451.regras_proprias laboratorio/Dockerfile laboratorio/docker-compose.yml
    import sys
    from pathlib import Path
    from .comum import ler_texto
    total = 0
    for caminho in sys.argv[1:]:
        for f in analisar(Path(caminho).as_posix(), ler_texto(caminho)):
            total += 1
            print(f"{f['file']:35s} linha {f['line']:3d}  {f['category']:17s} {f['message']}")
    print(f"\n{total} achado(s)")
