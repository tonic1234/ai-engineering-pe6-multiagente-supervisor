"""llm_factory.py — el modelo, elegido por variable de entorno.

Misma idea que en las pre-entregas anteriores: el código de negocio no importa SDKs. Acá
se construye el chat model según LLM_PROVIDER (gemini por defecto, que tiene free tier y
es el camino con el que el repo corre sin tarjeta).

Ojo con el import perezoso: construir ChatGoogleGenerativeAI sin clave en el entorno
falla en el __init__. Si eso pasara al importar el módulo, la suite de tests (que corre
sin claves) no podría ni colectar.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

# Los scripts tienen que poder correrse solos: sin esto, `python main.py` no ve el .env.
load_dotenv()


@lru_cache(maxsize=None)
def get_llm(provider: str | None = None):
    """Devuelve el chat model del proveedor pedido (o del que diga el entorno)."""

    proveedor = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()

    if proveedor == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            temperature=0,
        )

    if proveedor == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)

    if proveedor == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"), temperature=0)

    raise ValueError(f"Proveedor no soportado: {proveedor}")


def texto(mensaje) -> str:
    """Normaliza el contenido de un mensaje a texto plano.

    Gemini no siempre devuelve un string: puede venir una LISTA de bloques
    ([{'type': 'text', 'text': '...', 'extras': {...}}]). Sin normalizar, la respuesta se
    imprime como una lista de diccionarios con metadata interna del proveedor.
    """

    contenido = getattr(mensaje, "content", mensaje)
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        partes = []
        for bloque in contenido:
            if isinstance(bloque, dict):
                partes.append(bloque.get("text", ""))
            else:
                partes.append(str(bloque))
        return "".join(partes).strip()
    return str(contenido)
