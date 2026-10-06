# language: pt
"""Passos da conta: perfil, troca de senha, exportação e exclusão."""

from backend import db
from behave import then, when


def _lista(texto):
    """Converte 'a, b, c' (como escrito no .feature) em ['a', 'b', 'c']."""
    return [parte.strip() for parte in texto.split(",") if parte.strip()]


# --------------------------------------------------------------------------
# Ações
# --------------------------------------------------------------------------


@when('eu atualizo meu perfil com o nome "{nome}" e os interesses "{interesses}"')
def passo_atualizo_perfil(context, nome, interesses):
    context.resposta = context.cliente.post(
        "/api/account", json={"name": nome, "interests": _lista(interesses)}
    )


@when('eu atualizo meu perfil com o nome "{nome}"')
def passo_atualizo_so_o_nome(context, nome):
    # Passo separado em vez de passar interesses="" no .feature: o parser
    # padrão do Behave não casa `{placeholder}` com string vazia, e o
    # cenário fica mais claro assim.
    context.resposta = context.cliente.post("/api/account", json={"name": nome})


@when('eu troco minha senha de "{atual}" para "{nova}"')
def passo_troco_senha(context, atual, nova):
    context.resposta = context.cliente.post(
        "/api/account/password", json={"currentPassword": atual, "newPassword": nova}
    )


@when("eu exporto meus dados")
def passo_exporto(context):
    context.resposta = context.cliente.get("/api/account/export")


@when('eu apago minha conta com a senha "{senha}"')
def passo_apago_conta(context, senha):
    context.resposta = context.cliente.post(
        "/api/account/delete",
        json={"password": senha, "confirmation": "eu quero excluir essa conta"},
    )


# --------------------------------------------------------------------------
# Verificações
# --------------------------------------------------------------------------


@then('meu perfil deve ter o nome "{nome}"')
def passo_verifica_nome(context, nome):
    linha = db.query_one("SELECT name FROM users WHERE id = %s", (context.usuario["id"],))
    assert linha["name"] == nome, f"nome é {linha['name']!r}"


@then('meus interesses devem ser "{interesses}"')
def passo_verifica_interesses(context, interesses):
    linha = db.query_one(
        "SELECT interests FROM users WHERE id = %s", (context.usuario["id"],)
    )
    assert linha["interests"] == _lista(interesses), linha["interests"]


@then("a exportação deve conter {quantidade:d} conversa")
def passo_exportacao_conversas(context, quantidade):
    corpo = context.resposta.get_json()
    assert len(corpo["chats"]) == quantidade, corpo["chats"]


@then("a exportação não deve conter minha senha")
def passo_exportacao_sem_senha(context):
    perfil = context.resposta.get_json()["profile"]
    assert "password_hash" not in perfil
    assert "passwordHash" not in perfil


@then("não deve restar nenhum dado meu no banco")
def passo_sem_dados(context):
    assert db.query("SELECT * FROM users") == []
    assert db.query("SELECT * FROM chats") == []
    assert db.query("SELECT * FROM messages") == []
    assert db.query("SELECT * FROM sessions") == []
