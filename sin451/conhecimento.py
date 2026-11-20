"""Impacto e mitigação de cada categoria (usado no relatório, nos slides e no app)."""

CATEGORIAS_INFO = {
    "UNPINNED_VERSION": {
        "nome": "Versão não fixada",
        "pergunta": "A imagem ou o pacote pode mudar sem você saber?",
        "ruim": "FROM python:alpine\nRUN apk add --no-cache curl\nimage: redis:latest",
        "bom": "FROM python:3.12-alpine3.20@sha256:<digest>\nimage: redis:7.4.1-alpine",
        "impacto": [
            "Cada build pode puxar uma imagem diferente: o que foi testado não é o que vai para produção.",
            "Uma versão nova pode trazer vulnerabilidade conhecida (CVE) ou quebrar a aplicação sem aviso.",
            "Se a imagem publicada for adulterada (ataque à cadeia de suprimentos), ela entra sem nenhuma barreira.",
        ],
        "mitigacao": [
            "Usar tag com número de versão e, de preferência, o digest @sha256 da imagem.",
            "Fixar a versão dos pacotes do sistema (apt-get install pacote=versão) ou instalar só o necessário.",
            "Atualizar de forma controlada, com Dependabot ou Renovate abrindo pedidos de mudança revisados.",
            "Varrer as imagens com um scanner de CVE (por exemplo, Trivy) antes de publicar.",
        ],
        "referencia": "CIS Docker Benchmark 4.x; Hadolint DL3006/DL3007/DL3008; Checkov CKV_DOCKER_7",
    },
    "ROOT_USER": {
        "nome": "Contêiner como root",
        "pergunta": "Se a aplicação for invadida, o atacante já é administrador?",
        "ruim": "USER root          # ou nenhum USER\nprivileged: true",
        "bom": "RUN adduser -D -u 10001 app\nUSER app\ncap_drop: [ALL]\nsecurity_opt: [\"no-new-privileges:true\"]",
        "impacto": [
            "Uma falha na aplicação vira controle total do contêiner: instalar ferramentas, ler e alterar qualquer arquivo.",
            "Root no contêiner é o mesmo usuário 0 do servidor: uma falha do kernel ou do Docker facilita escapar para o host.",
            "Com privileged: true, o contêiner recebe todas as capacidades do Linux e acesso aos dispositivos do host.",
        ],
        "mitigacao": [
            "Criar um usuário sem privilégios e terminar o Dockerfile com USER app.",
            "No compose, usar user: e remover privileged: true.",
            "Retirar capacidades (cap_drop: [ALL]) e ativar no-new-privileges; usar read_only quando possível.",
            "Considerar Docker rootless ou user namespaces no servidor.",
        ],
        "referencia": "CIS Docker Benchmark 4.1 e 5.4; Hadolint DL3002; Checkov CKV_DOCKER_3/CKV_DOCKER_8",
    },
    "HARDCODED_SECRET": {
        "nome": "Segredo escrito no arquivo",
        "pergunta": "Quem tem o repositório ou a imagem consegue ler a senha?",
        "ruim": "ENV DB_PASSWORD=abc123\nMYSQL_ROOT_PASSWORD: senha123",
        "bom": "environment:\n  DB_PASSWORD: ${DB_PASSWORD:?defina}\n# ou secrets: do compose / BuildKit --secret",
        "impacto": [
            "A senha fica no histórico do Git para sempre, mesmo que o arquivo seja corrigido depois.",
            "Fica gravada nas camadas da imagem: qualquer um com a imagem lê com docker history ou docker inspect.",
            "Com a senha, um atacante acessa o banco ou o serviço direto, sem precisar de outra falha.",
        ],
        "mitigacao": [
            "Passar segredos só na hora de rodar (variável de ambiente externa, arquivo .env fora do Git).",
            "Usar secrets do Docker/compose ou de um cofre (Vault, gerenciador da nuvem); no build, BuildKit --secret.",
            "Ativar detecção de segredos no repositório (Checkov secrets, gitleaks) antes do commit.",
            "Se vazou: trocar a senha imediatamente; apagar do arquivo não basta.",
        ],
        "referencia": "OWASP Secrets Management Cheat Sheet; CWE-798; Checkov CKV_SECRET_*",
    },
}
