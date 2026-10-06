# language: pt
"""Passos específicos do fluxo de "esqueci minha senha"."""

from backend import db
from behave import given, then, when
from passos_comuns import logar


@given('que eu pedi a redefinição de senha do e-mail "{email}"')
@when('eu peço a redefinição de senha do e-mail "{email}"')
def passo_pedir_redefinicao(context, email):
    context.resposta = context.cliente.post("/api/forgot-password", json={"email": email})
    linha = db.query_one("SELECT token FROM password_reset_tokens ORDER BY created_at DESC")
    context.token_redefinicao = linha["token"] if linha else None


@when('eu redefino a senha para "{nova_senha}" usando o token recebido')
def passo_redefinir(context, nova_senha):
    context.resposta = context.cliente.post(
        "/api/reset-password",
        json={"token": context.token_redefinicao, "newPassword": nova_senha},
    )


@then("nenhum token de redefinição deve ter sido gerado")
def passo_sem_token(context):
    assert db.query("SELECT * FROM password_reset_tokens") == []


@then('eu devo conseguir entrar com o e-mail "{email}" e a senha "{senha}"')
def passo_consigo_entrar(context, email, senha):
    cliente = context.aplicacao.test_client()
    resposta = logar(cliente, email, senha)
    assert resposta.status_code == 200, resposta.get_json()


@then('eu não devo conseguir entrar com o e-mail "{email}" e a senha "{senha}"')
def passo_nao_consigo_entrar(context, email, senha):
    cliente = context.aplicacao.test_client()
    assert logar(cliente, email, senha).status_code == 401
