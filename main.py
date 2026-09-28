"""main.py — la demo de punta a punta del orquestador.

Corre una consulta que obliga a usar LOS DOS dominios (un dato de las políticas internas
+ una cuenta) y muestra el flujo de delegación paso a paso: quién decidió qué, a quién le
pasó la tarea y con qué aporte volvió.

Al final guarda la traza completa en `traza_ejecucion.json` (lo mismo que se ve por
pantalla, pero en un archivo que queda en el repo como evidencia de la corrida).

Uso:
    python main.py                # corre la consulta de la demo
    python main.py --topologia    # imprime el diagrama Mermaid del grafo y sale
    python main.py "otra pregunta"
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from graph import build_app, diagrama_mermaid
from llm_factory import texto

PREGUNTA_DEMO = (
    "Un colaborador cumplió 12 años en la empresa: 2 años con menos de 3 de antigüedad, "
    "6 años con entre 3 y 8, y 4 años con más de 8. ¿Cuántos días de vacaciones le "
    "correspondieron en total a lo largo de esos 12 años?"
)

ARCHIVO_TRAZA = "traza_ejecucion.json"


def estado_inicial(pregunta: str) -> dict:
    return {
        "messages": [HumanMessage(content=pregunta)],
        "next_agent": None,
        "instruccion": None,
        "contribuciones": [],
        "pasos": 0,
        "task_completed": False,
        "validacion": None,
        "reintentos": 0,
    }


def _detalle_de_nodo(nodo: str, actualizacion: dict) -> str:
    """Texto corto para imprimir qué hizo cada nodo."""

    if nodo == "supervisor":
        instruccion = (actualizacion.get("instruccion") or "").replace("\n", " ")[:90]
        sufijo = f" | instrucción: {instruccion}" if instruccion else ""
        return f"decide -> {actualizacion.get('next_agent')}{sufijo}"

    if nodo == "validacion":
        informe = actualizacion.get("validacion") or {}
        return f"suficiente={informe.get('suficiente')} | {informe.get('motivo')}"

    mensajes = actualizacion.get("messages")
    if mensajes:
        return f"[{getattr(mensajes[0], 'name', 'sistema')}] {texto(mensajes[0])[:220]}"

    return ""


def correr(pregunta: str = PREGUNTA_DEMO, app=None):
    """Corre el grafo UNA vez y devuelve (estado_final, traza).

    El flujo se lee del stream de `updates` y el estado final del stream de `values`, en la
    MISMA corrida. (La primera versión hacía dos corridas —una para imprimir y otra para la
    respuesta— y el modelo no es determinista al 100%: la traza que mostraba y la respuesta
    que guardaba podían no coincidir. Con una sola corrida, lo que se ve es lo que pasó.)
    """

    app = app or build_app()
    inicial = estado_inicial(pregunta)

    print("=" * 88)
    print("PREGUNTA:", pregunta)
    print("=" * 88)

    traza = {"pregunta": pregunta, "pasos": []}
    resultado = inicial

    print("\nFLUJO DE DELEGACIÓN\n" + "-" * 88)
    for modo, chunk in app.stream(inicial, stream_mode=["updates", "values"]):
        if modo == "values":
            resultado = chunk
            continue

        for nodo, actualizacion in chunk.items():
            if nodo == "__start__":  # ruido del runtime, no es un paso del equipo
                continue
            detalle = _detalle_de_nodo(nodo, actualizacion)
            print(f"🔹 {nodo:<13} {detalle}")
            traza["pasos"].append({"nodo": nodo, "detalle": detalle})

    traza["contribuciones"] = resultado.get("contribuciones", [])
    traza["validacion"] = resultado.get("validacion")
    traza["respuesta_final"] = texto(resultado["messages"][-1])
    traza["pasos_ejecutados"] = resultado.get("pasos", 0)
    traza["modelo"] = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    traza["proveedor"] = os.getenv("LLM_PROVIDER", "gemini")
    traza["ejecutado_en"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print("\n" + "-" * 88)
    print("RESPUESTA FINAL\n")
    print(traza["respuesta_final"])
    print("-" * 88)
    print(
        f"pasos de especialistas: {traza['pasos_ejecutados']} | "
        f"contribuciones: {len(traza['contribuciones'])} | "
        f"rúbrica cumplida: {(traza['validacion'] or {}).get('suficiente')}"
    )

    with open(ARCHIVO_TRAZA, "w", encoding="utf-8") as archivo:
        json.dump(traza, archivo, ensure_ascii=False, indent=2)
    print(f"traza guardada en {ARCHIVO_TRAZA}")

    return resultado, traza


def main() -> None:
    if "--topologia" in sys.argv:
        print(diagrama_mermaid(build_app(solo_topologia=True)))
        return

    argumentos = [a for a in sys.argv[1:] if not a.startswith("-")]
    correr(argumentos[0] if argumentos else PREGUNTA_DEMO)


if __name__ == "__main__":
    main()
