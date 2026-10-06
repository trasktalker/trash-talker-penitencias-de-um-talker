"""
check_gemini_tier.py
====================
Mostra, com a resposta crua do Google, em qual plano (gratuito ou pago)
está a GEMINI_API_KEY do .env. Rodar de dentro de python-app:

    py tools\\check_gemini_tier.py

A API do Gemini não tem um endpoint que diga o plano da chave. A prova
vem do erro de cota: quando a chave estoura o limite, o Google devolve um
429 com o nome da cota estourada, e no plano gratuito esse nome contém
"FreeTier" / "free_tier". Uma chamada que dá certo, sozinha, não prova
nada - as duas modalidades respondem igual enquanto há cota.
"""

import json
import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors

MODEL = "gemini-3.8-flash"

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
key = os.environ.get("GEMINI_API_KEY")
if not key:
    sys.exit("GEMINI_API_KEY não encontrada no .env")

print("Chave do .env (final):", "..." + key[-4:])
print("Modelo:", MODEL)
print()

client = genai.Client(api_key=key)
for attempt in range(1, 4):
    try:
        response = client.models.generate_content(model=MODEL, contents="responda só: ok")
    except errors.ServerError as e:
        # 503 = Google sobrecarregado. Não diz nada sobre o plano, tenta de novo.
        print(f"Erro {e.code} (Google sobrecarregado), tentando de novo... [{attempt}/3]")
        time.sleep(3)
        continue
    except errors.ClientError as e:
        print(f"Erro {e.code} {e.status}")
        print()
        print("Resposta completa do Google:")
        print(json.dumps(e.details, indent=2, ensure_ascii=False))
        print()
        raw = json.dumps(e.details)
        if "FreeTier" in raw or "free_tier" in raw:
            print(">>> O Google diz que esta chave está no PLANO GRATUITO (FreeTier).")
        break
    else:
        print("A chamada funcionou:", response.text.strip())
        print("Isso só mostra que ainda há cota hoje; não prova se o plano é pago ou gratuito.")
        break
