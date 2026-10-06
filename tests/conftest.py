"""
tests/conftest.py
=================
Infraestrutura compartilhada dos testes automatizados (pytest).

Decisões tomadas aqui e por quê:

1. **Banco PostgreSQL de teste, não SQLite.**
   O `db.py` usa recursos que só existem no Postgres: placeholders `%s`
   do psycopg2, `TEXT[]` (coluna `users.interests`), `now()`,
   `= ANY(%s)` e `RealDictCursor`. Rodar contra SQLite exigiria
   reescrever a camada de dados só para os testes - o que faria os
   testes validarem um código diferente do que roda em produção. Por
   isso usamos um Postgres de verdade, apontado por `TEST_DATABASE_URL`.

2. **Trava de segurança contra rodar no banco errado.**
   Se `TEST_DATABASE_URL` não estiver definida, a suíte para com uma
   mensagem explicativa em vez de cair no `DATABASE_URL` do `.env`. E se
   as duas apontarem para o mesmo lugar, a suíte também para. Os testes
   truncam tabelas entre casos - apontar isso para o banco real apagaria
   os dados de verdade.

3. **A IA nunca é chamada de verdade.**
   `ai.generate_reply` faz uma chamada de rede paga ao Gemini. Nos testes
   ela é substituída por uma função determinística (fixture `ia_falsa`).
   O que estamos testando é o comportamento da aplicação em volta da IA
   (persistiu a mensagem? gerou título? devolveu 502 quando a IA falha?),
   não a qualidade da resposta do modelo.
"""

import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(APP_DIR, "backend")
sys.path.insert(0, APP_DIR)

from backend import db  # noqa: E402
from backend.factory import create_app  # noqa: E402

SCHEMA_PATH = os.path.join(BACKEND_DIR, "schema.sql")

TABELAS = ["messages", "chats", "password_reset_tokens", "sessions",
           "two_factor_recovery_codes", "two_factor_login_challenges", "user_two_factor", "users"]

SENHA_PADRAO = "Senha-de-Teste-123"


def _url_do_banco_de_teste():
    """Lê TEST_DATABASE_URL e recusa configurações perigosas."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.exit(
            "TEST_DATABASE_URL não definida. Os testes truncam tabelas e "
            "por isso exigem um banco separado. Ver docs/testes.md.",
            returncode=1,
        )
    if url == os.environ.get("DATABASE_URL"):
        pytest.exit(
            "TEST_DATABASE_URL é igual a DATABASE_URL. Recusando rodar: "
            "os testes apagariam os dados do banco de desenvolvimento.",
            returncode=1,
        )
    return url


@pytest.fixture(scope="session")
def url_banco_teste():
    return _url_do_banco_de_teste()


@pytest.fixture(scope="session")
def aplicacao(url_banco_teste):
    """
    Cria a aplicação Flask uma única vez, ligada ao banco de teste, e
    garante que o schema está aplicado.
    """
    app = create_app(database_url=url_banco_teste)
    app.config.update(TESTING=True)

    with open(SCHEMA_PATH, encoding="utf-8") as arquivo:
        db.execute(arquivo.read())

    yield app

    db.close_pool()


@pytest.fixture(autouse=True)
def banco_limpo(aplicacao):
    """
    Zera as tabelas antes de cada teste, para que um teste nunca dependa
    do estado deixado por outro. `autouse=True` aplica isso a todos os
    testes sem precisar declarar a fixture caso a caso.
    """
    db.execute("TRUNCATE " + ", ".join(TABELAS) + " RESTART IDENTITY CASCADE")
    yield


@pytest.fixture
def cliente(aplicacao):
    """Cliente de teste do Flask (não sobe servidor HTTP de verdade)."""
    return aplicacao.test_client()


@pytest.fixture(autouse=True)
def email_simulado(monkeypatch):
    # Testes nunca enviam e-mails usando as credenciais do ambiente local.
    monkeypatch.setattr("backend.routes.auth_api.send_password_reset_email", lambda *_args: None)


@pytest.fixture
def ia_falsa(monkeypatch):
    """
    Substitui a chamada real ao Gemini por uma resposta fixa. Devolve um
    dicionário que o teste pode inspecionar para saber com que histórico
    a IA foi chamada.
    """
    registro = {"chamadas": []}

    def _falsa(history, user, personality=None, effort=None):
        registro["chamadas"].append(
            {
                "history": history,
                "user": user,
                "personality": personality,
                "effort": effort,
            }
        )
        return "Resposta simulada do TrashTalker."

    monkeypatch.setattr("backend.routes.chats_api.generate_reply", _falsa)
    return registro


@pytest.fixture
def ia_quebrada(monkeypatch):
    """Simula uma falha da IA (chave inválida, filtro de segurança, rede)."""

    def _falha(history, user, personality=None, effort=None):
        raise RuntimeError("Falha simulada da IA")

    monkeypatch.setattr("backend.routes.chats_api.generate_reply", _falha)


# --------------------------------------------------------------------------
# Ajudantes de alto nível usados pelos testes
# --------------------------------------------------------------------------


def cadastrar(cliente, email="pessoa@exemplo.com", senha=SENHA_PADRAO, nome="Pessoa", aceites=True):
    corpo = {"email": email, "password": senha, "name": nome}
    if aceites:
        # As duas confirmações obrigatórias do cadastro (18+/termos e IA).
        corpo.update({"acceptTerms": True, "acceptAi": True})
    return cliente.post("/api/signup", json=corpo)


def logar(cliente, email="pessoa@exemplo.com", senha=SENHA_PADRAO):
    return cliente.post("/api/login", json={"email": email, "password": senha})


@pytest.fixture
def usuario_logado(cliente):
    """
    Cria uma conta e deixa o `cliente` autenticado (o cookie de sessão
    fica guardado no próprio test_client). Devolve os dados do usuário.
    """
    cadastrar(cliente)
    resposta = logar(cliente)
    assert resposta.status_code == 200, resposta.get_json()
    return resposta.get_json()["user"]


@pytest.fixture
def conversa(cliente, usuario_logado):
    """Cria uma conversa vazia para o usuário logado e devolve o id."""
    resposta = cliente.post("/api/chats")
    assert resposta.status_code == 201, resposta.get_json()
    return resposta.get_json()["id"]
