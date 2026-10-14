import os

from backend.factory import create_app

# A Vercel procura uma variável `app` neste arquivo.
app = create_app()

# Desenvolvimento local: `python app.py`.
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
