# language: pt
"""
Passos compartilhados: cadastro, login, sessão e verificações de status.

Os passos conversam com a aplicação pelo `test_client()` do Flask - ou
seja, pela mesma API HTTP que o JavaScript do frontend usa. Eles não
chamam funções internas para "forçar" um resultado: o único atalho é a
consulta direta ao banco nas verificações, e mesmo essa serve para
conferir o efeito real de uma ação feita pela API.
"""

from backend import db
from behave import given, then, when

SENHA_PADRAO = "Senha-Forte-123"
EMAIL_PADRAO = "pessoa@exemplo.com"


def cadastrar(cliente, email, senha, nome="Pessoa"):
    return cliente.post("/api/signup", json={
        "email": email, "password": senha, "name": nome,
        # As duas confirmações obrigatórias do cadastro (18+/termos e IA).
        "acceptTerms": True, "acceptAi": True,
    })


def logar(cliente, email, senha):
    return cliente.post("/api/login", json={"email": email, "password": senha})


# --------------------------------------------------------------------------
# Contexto inicial
# --------------------------------------------------------------------------


@given('que não existe conta com o e-mail "{email}"')
def passo_conta_inexistente(context, email):
    assert db.query_one("SELECT id FROM users WHERE email = %s", (email,)) is None


@given('que existe uma conta com o e-mail "{email}" e a senha "{senha}"')
def passo_conta_existente(context, email, senha):
    resposta = cadastrar(context.cliente, email, senha)
    assert resposta.status_code == 201, resposta.get_json()
    context.email_atual = email
    context.senha_atual = senha


@given("que eu estou logado")
def passo_estou_logado(context):
    cadastrar(context.cliente, EMAIL_PADRAO, SENHA_PADRAO)
    resposta = logar(context.cliente, EMAIL_PADRAO, SENHA_PADRAO)
    assert resposta.status_code == 200, resposta.get_json()
    context.email_atual = EMAIL_PADRAO
    context.senha_atual = SENHA_PADRAO
    context.usuario = resposta.get_json()["user"]


@given("que essa conta está aberta em outro dispositivo")
@given("que minha conta está aberta em outro dispositivo")
def passo_outro_dispositivo(context):
    context.outro_cliente = context.aplicacao.test_client()
    resposta = logar(context.outro_cliente, context.email_atual, context.senha_atual)
    assert resposta.status_code == 200, resposta.get_json()
    assert context.outro_cliente.get("/api/me").status_code == 200


# --------------------------------------------------------------------------
# Ações
# --------------------------------------------------------------------------


@when('eu me cadastro com o e-mail "{email}" e a senha "{senha}"')
def passo_me_cadastro(context, email, senha):
    context.resposta = cadastrar(context.cliente, email, senha)
    context.email_atual = email


@when('eu entro com o e-mail "{email}" e a senha "{senha}"')
def passo_entro(context, email, senha):
    context.resposta = logar(context.cliente, email, senha)


@when("eu saio da conta")
def passo_saio(context):
    context.resposta = context.cliente.post("/api/logout")


# --------------------------------------------------------------------------
# Verificações
# --------------------------------------------------------------------------


@then("eu devo receber o status {status:d}")
def passo_verifica_status(context, status):
    assert context.resposta is not None, "nenhuma requisição foi feita neste cenário"
    assert context.resposta.status_code == status, (
        f"esperava {status}, recebi {context.resposta.status_code}: "
        f"{context.resposta.get_data(as_text=True)[:300]}"
    )


@then("a conta deve ser criada")
def passo_conta_criada(context):
    assert context.resposta.status_code == 201, context.resposta.get_json()
    assert db.query_one(
        "SELECT id FROM users WHERE email = %s", (context.email_atual,)
    ) is not None


@then('não deve existir conta com o e-mail "{email}"')
def passo_conta_nao_criada(context, email):
    assert db.query_one("SELECT id FROM users WHERE email = %s", (email,)) is None


@then("eu devo estar autenticado")
def passo_autenticado(context):
    assert context.cliente.get("/api/me").status_code == 200


@then("eu devo continuar autenticado")
def passo_continuo_autenticado(context):
    assert context.cliente.get("/api/me").status_code == 200


@then("eu não devo estar autenticado")
@then("eu ainda não devo estar autenticado")
def passo_nao_autenticado(context):
    assert context.cliente.get("/api/me").status_code == 401


@then("eu devo receber um cookie de sessão")
def passo_cookie(context):
    assert "session_token" in context.resposta.headers.get("Set-Cookie", "")


@then("o outro dispositivo não deve mais estar autenticado")
def passo_outro_dispositivo_caiu(context):
    assert context.outro_cliente is not None
    assert context.outro_cliente.get("/api/me").status_code == 401
