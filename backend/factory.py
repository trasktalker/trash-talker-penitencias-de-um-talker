"""
app.py
======
Ponto de entrada da aplicação (equivalente a src/server.ts).

Responsabilidades:
  1. Criar o app Flask.
  2. Ligar o pool de conexões com o Postgres (db.init_pool()).
  3. Registrar as rotas da API (blueprints em routes/).
  4. Servir os arquivos estáticos do frontend (HTML/CSS/JS/imagens) que
     ficam na pasta ../frontend.
  5. Mapear as URLs "bonitas" (/dashboard, /login, etc.) para o arquivo
     HTML correspondente, para que a navegação pareça idêntica à do
     projeto original em Express.

Como rodar: veja o README.md na raiz de python-app/.
"""

import os

from dotenv import load_dotenv
from flask import Flask, redirect, send_from_directory
from flask_cors import CORS

from backend import db
from backend.routes.auth_api import auth_api
from backend.routes.chats_api import chats_api
from backend.routes.two_factor_api import two_factor_api

# Carrega o arquivo .env (equivalente a `import "dotenv/config"` no
# src/server.ts original). Precisa vir antes de qualquer os.environ.get().
load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BACKEND_DIR, "..", "public")


def create_app(database_url=None):
    """
    Cria e configura a aplicação Flask.

    `database_url` é opcional: quando não é passado (uso normal, via
    `python app.py`), o banco continua vindo de DATABASE_URL no .env,
    sem nenhuma mudança de comportamento. Os testes passam a URL do
    banco de teste aqui (ver tests/conftest.py).
    """
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

    # CORS: só é realmente necessário se o frontend for servido de uma
    # origem diferente do backend (por exemplo, um live-server separado
    # em outra porta durante o desenvolvimento). Quando o Flask serve o
    # frontend diretamente (o padrão deste projeto), front e back estão
    # na mesma origem e isso não tem efeito prático - mas deixamos
    # configurado para não travar esse cenário caso você separe os dois
    # no futuro (ex.: publicar o frontend em outro host).
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5000")
    CORS(app, supports_credentials=True, origins=[frontend_origin])

    db.init_pool(database_url)

    app.register_blueprint(auth_api)
    app.register_blueprint(chats_api)
    app.register_blueprint(two_factor_api)

    # --- Rotas "de página": servem o HTML estático correspondente para
    # cada URL antiga do projeto Express, para manter os mesmos links
    # (ex.: /dashboard/account) funcionando sem extensão .html. ---

    page_routes = {
        "/": "index.html",
        "/login": "login.html",
        "/signup": "signup.html",
        "/forgot-password": "forgot-password.html",
        "/reset-password": "reset-password.html",
        "/privacy": "privacy.html",
        "/terms": "terms.html",
        "/cookies": "cookies.html",
        "/dashboard": "dashboard.html",
        "/dashboard/account": "account.html",
        "/dashboard/settings": "settings.html",
    }

    def make_page_view(filename):
        def view():
            return send_from_directory(FRONTEND_DIR, filename)

        return view

    for path, filename in page_routes.items():
        endpoint = "page_" + filename.replace(".html", "").replace("/", "_")
        app.add_url_rule(path, endpoint=endpoint, view_func=make_page_view(filename))

    @app.route("/dashboard/chat/<chat_id>")
    def chat_page(chat_id):
        # O id da conversa vai na própria URL, igual ao original
        # (/dashboard/chat/:chatId). O JS da página (frontend/js/chat.js)
        # lê esse id de novo a partir de window.location.pathname.
        return send_from_directory(FRONTEND_DIR, "chat.html")

    @app.route("/dashboard/information")
    def information_redirect():
        # information.html foi incorporada à landing pública ("/") - ver
        # frontend/index.html. Mantemos esta rota só para não quebrar
        # links/favoritos antigos: redireciona para a nova home.
        return redirect("/", code=302)

    return app


# Nota: não existe mais um `app = create_app()` solto aqui no nível do
# módulo. Enquanto existia, o simples ato de importar este arquivo já
# abria conexão com o Postgres - e importar `app.py` sem banco (para ler
# as rotas, rodar testes ou qualquer análise estática) quebrava na hora.
#
# `create_app` é uma "application factory", padrão que o próprio Flask
# reconhece: `flask --app app routes` acha essa função sozinho. Para um
# servidor WSGI (gunicorn/waitress), aponte para a fábrica:
#     gunicorn "app:create_app()"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    create_app().run(host="0.0.0.0", port=port, debug=debug)
