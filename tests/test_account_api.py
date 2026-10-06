"""
Testes dos endpoints de conta: perfil, troca de senha, exportação de
dados e exclusão da conta (routes/chats_api.py).

A exportação e a exclusão são os mecanismos concretos por trás dos
direitos prometidos na Política de Privacidade do projeto, então valem
teste de comportamento, não só de status HTTP.
"""

from backend import db
from conftest import SENHA_PADRAO, cadastrar, logar


# --------------------------------------------------------------------------
# Perfil
# --------------------------------------------------------------------------


def test_atualizar_perfil_salva_todos_os_campos(cliente, usuario_logado):
    resposta = cliente.post(
        "/api/account",
        json={
            "name": "Igor",
            "image": "avatar_robot",
            "displayName": "Ig",
            "pronoun": "ele/dele",
            "interests": ["música", "programação"],
        },
    )
    assert resposta.status_code == 200

    linha = db.query_one("SELECT * FROM users WHERE id = %s", (usuario_logado["id"],))
    assert linha["name"] == "Igor"
    assert linha["display_name"] == "Ig"
    assert linha["pronoun"] == "ele/dele"
    assert linha["interests"] == ["música", "programação"]


def test_nome_muito_curto_e_recusado(cliente, usuario_logado):
    resposta = cliente.post("/api/account", json={"name": "A"})
    assert resposta.status_code == 400
    assert db.query_one("SELECT name FROM users")["name"] == "Pessoa"


def test_foto_grande_demais_ou_que_nao_e_imagem_e_recusada(cliente, usuario_logado):
    grande = "data:image/jpeg;base64," + "A" * 400_000
    assert cliente.post("/api/account", json={"name": "Igor", "image": grande}).status_code == 400
    nao_imagem = "data:text/html;base64,PHNjcmlwdD4="
    assert cliente.post("/api/account", json={"name": "Igor", "image": nao_imagem}).status_code == 400
    assert db.query_one("SELECT image FROM users")["image"] is None

    # A foto reduzida pelo navegador (poucos KB) continua aceita.
    pequena = "data:image/jpeg;base64," + "A" * 20_000
    assert cliente.post("/api/account", json={"name": "Igor", "image": pequena}).status_code == 200


def test_interesses_duplicados_sao_removidos_mantendo_a_ordem(cliente, usuario_logado):
    cliente.post(
        "/api/account",
        json={"name": "Igor", "interests": ["rock", "  rock  ", "jazz", "rock"]},
    )
    assert db.query_one("SELECT interests FROM users")["interests"] == ["rock", "jazz"]


def test_interesses_vazios_sao_descartados(cliente, usuario_logado):
    cliente.post("/api/account", json={"name": "Igor", "interests": ["", "   ", "rock"]})
    assert db.query_one("SELECT interests FROM users")["interests"] == ["rock"]


def test_quantidade_de_interesses_e_limitada(cliente, usuario_logado):
    """O limite existe porque essa lista é reenviada à IA a cada mensagem."""
    cliente.post(
        "/api/account",
        json={"name": "Igor", "interests": [f"interesse-{i}" for i in range(100)]},
    )
    assert len(db.query_one("SELECT interests FROM users")["interests"]) == 25


def test_interesse_muito_longo_e_truncado(cliente, usuario_logado):
    cliente.post("/api/account", json={"name": "Igor", "interests": ["a" * 500]})
    assert len(db.query_one("SELECT interests FROM users")["interests"][0]) == 60


def test_interesses_em_formato_invalido_viram_lista_vazia(cliente, usuario_logado):
    cliente.post("/api/account", json={"name": "Igor", "interests": "não é uma lista"})
    assert db.query_one("SELECT interests FROM users")["interests"] == []


# --------------------------------------------------------------------------
# Troca de senha estando logado
# --------------------------------------------------------------------------


def test_trocar_senha_com_senha_atual_correta(cliente, usuario_logado):
    resposta = cliente.post(
        "/api/account/password",
        json={"currentPassword": SENHA_PADRAO, "newPassword": "Outra-Senha-456"},
    )
    assert resposta.status_code == 200

    cliente.post("/api/logout")
    assert logar(cliente, senha=SENHA_PADRAO).status_code == 401
    assert logar(cliente, senha="Outra-Senha-456").status_code == 200


def test_trocar_senha_com_senha_atual_errada_devolve_401(cliente, usuario_logado):
    resposta = cliente.post(
        "/api/account/password",
        json={"currentPassword": "senha-que-nao-e-a-atual", "newPassword": "Outra-Senha-456"},
    )
    assert resposta.status_code == 401


def test_trocar_para_senha_curta_e_recusado(cliente, usuario_logado):
    resposta = cliente.post(
        "/api/account/password",
        json={"currentPassword": SENHA_PADRAO, "newPassword": "123"},
    )
    assert resposta.status_code == 400


def test_trocar_senha_derruba_outros_dispositivos_mas_mantem_o_atual(
    cliente, aplicacao, usuario_logado
):
    """
    Regressão da correção de segurança: sessões abertas em outro lugar
    precisam cair, mas quem trocou a senha não deve ser deslogado da
    própria tela.
    """
    outro_dispositivo = aplicacao.test_client()
    assert logar(outro_dispositivo).status_code == 200

    cliente.post(
        "/api/account/password",
        json={"currentPassword": SENHA_PADRAO, "newPassword": "Outra-Senha-456"},
    )

    assert outro_dispositivo.get("/api/me").status_code == 401
    assert cliente.get("/api/me").status_code == 200


# --------------------------------------------------------------------------
# Exportação de dados
# --------------------------------------------------------------------------


def test_exportacao_inclui_perfil_conversas_e_mensagens(cliente, conversa, ia_falsa):
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "oi"})

    corpo = cliente.get("/api/account/export").get_json()

    assert corpo["profile"]["email"] == "pessoa@exemplo.com"
    assert len(corpo["chats"]) == 1
    assert [m["content"] for m in corpo["chats"][0]["messages"]] == [
        "oi",
        "Resposta simulada do TrashTalker.",
    ]


def test_exportacao_inclui_o_aceite_dos_termos(cliente, usuario_logado):
    from backend.auth import CONSENT_VERSION

    consent = cliente.get("/api/account/export").get_json()["consent"]
    assert consent["version"] == CONSENT_VERSION
    assert consent["acceptedAt"]


def test_exportacao_nao_vaza_hash_de_senha(cliente, usuario_logado):
    corpo = cliente.get("/api/account/export").get_json()
    assert "password_hash" not in corpo["profile"]
    assert "passwordHash" not in corpo["profile"]


def test_exportacao_funciona_com_conta_sem_conversa(cliente, usuario_logado):
    """
    Caso de borda real: `= ANY(%s)` com lista vazia faz o Postgres
    reclamar ("cannot determine type of empty array"), então o código
    precisa evitar a query nesse cenário.
    """
    resposta = cliente.get("/api/account/export")
    assert resposta.status_code == 200
    assert resposta.get_json()["chats"] == []


def test_exportacao_nao_inclui_dados_de_outro_usuario(cliente, aplicacao, usuario_logado):
    outro = aplicacao.test_client()
    cadastrar(outro, email="outro@exemplo.com", nome="Outro")
    logar(outro, email="outro@exemplo.com")
    outro.post("/api/chats")

    assert cliente.get("/api/account/export").get_json()["chats"] == []


# --------------------------------------------------------------------------
# Exclusão da conta
# --------------------------------------------------------------------------


def test_excluir_conta_com_senha_errada_devolve_401(cliente, usuario_logado):
    resposta = cliente.post("/api/account/delete", json={"password": "senha-errada-aqui", "confirmation": "eu quero excluir essa conta"})
    assert resposta.status_code == 401
    assert db.query_one("SELECT id FROM users") is not None


def test_excluir_conta_remove_tudo_em_cascata(cliente, conversa, ia_falsa):
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "oi"})

    resposta = cliente.post("/api/account/delete", json={"password": SENHA_PADRAO, "confirmation": "eu quero excluir essa conta"})
    assert resposta.status_code == 200

    assert db.query("SELECT * FROM users") == []
    assert db.query("SELECT * FROM chats") == []
    assert db.query("SELECT * FROM messages") == []
    assert db.query("SELECT * FROM sessions") == []


def test_apos_excluir_conta_a_sessao_deixa_de_valer(cliente, usuario_logado):
    cliente.post("/api/account/delete", json={"password": SENHA_PADRAO, "confirmation": "eu quero excluir essa conta"})
    assert cliente.get("/api/me").status_code == 401


def test_excluir_conta_exige_frase_exata(cliente, usuario_logado):
    for confirmation in (None, "", "excluir", "Eu quero excluir essa conta"):
        resposta = cliente.post("/api/account/delete", json={"password": SENHA_PADRAO, "confirmation": confirmation})
        assert resposta.status_code == 400
        assert db.query_one("SELECT id FROM users") is not None
        assert cliente.get("/api/me").status_code == 200
