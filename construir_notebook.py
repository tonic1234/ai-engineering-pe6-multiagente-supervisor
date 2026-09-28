"""construir_notebook.py — genera demo_flujo.ipynb y lo EJECUTA (con salidas reales).

La consigna pide "un video corto o notebook que demuestre el flujo de delegación". Elegí el
notebook: se puede correr de nuevo y deja las salidas a la vista, sin depender de un video.

Este script existe para no escribir el JSON del notebook a mano y, sobre todo, para
ejecutarlo con nbclient: así el archivo que se publica tiene las salidas REALES de la
corrida (no celdas vacías que el corrector tendría que correr).

Uso:  python construir_notebook.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ARCHIVO = Path(__file__).parent / "demo_flujo.ipynb"

# Ruido de librerías que ensucia las salidas del notebook (avisos de Gemini, barras de
# progreso de transformers/HuggingFace, warnings de tqdm). No se toca nada del contenido
# de la demo: solo se filtran estas líneas al guardar.
RUIDO = (
    "AFC",
    "Loading weights",
    "TqdmWarning",
    "unauthenticated requests to the HF Hub",
    "IProgress not found",
    "ipywidgets",
    "autonotebook",
    "Kernel is running over TCP",
)


def limpiar_salidas(nb) -> None:
    """Saca de las salidas solo las líneas de ruido de librería."""

    for celda in nb.cells:
        if celda.cell_type != "code":
            continue
        nuevas = []
        for salida in celda.get("outputs", []):
            if salida.get("output_type") in ("stream", "error") and isinstance(salida.get("text"), str):
                lineas = [ln for ln in salida["text"].splitlines(keepends=True) if not any(r in ln for r in RUIDO)]
                if not any(ln.strip() for ln in lineas):
                    continue  # la salida era solo ruido
                if salida.get("output_type") == "stream":
                    salida["text"] = "".join(lineas)
            nuevas.append(salida)
        celda["outputs"] = nuevas

MARKDOWN_INTRO = """# Demo del orquestador multi-agente

Este notebook demuestra el **flujo de delegación** de la pre-entrega 6: quién decide, a
quién le pasa la tarea, con qué instrucción y con qué aporte vuelve.

La pregunta está armada para que necesite **los dos dominios**: el dato (cuántos días de
vacaciones por tramo de antigüedad) lo tiene el **investigador** en las políticas internas,
y la cuenta total la hace el **analista** con la calculadora.

El orden lo fija el **supervisor**; los especialistas no se conocen entre sí.
"""

MARKDOWN_TOPOLOGIA = """## 1. La topología del grafo

Se arma una sola vez y se inspecciona. Los especialistas siempre vuelven al supervisor (ese
es el ciclo), y el nodo de `validacion` es el que decide si ya se puede cerrar.
"""

MARKDOWN_CORRIDA = """## 2. La corrida completa

`correr()` recorre el grafo y va mostrando cada paso: la decisión del supervisor (con la
instrucción que le deja al especialista), el aporte que devuelve cada agente y el informe
del validador. Al final imprime la respuesta para el usuario.
"""

MARKDOWN_ESTADO = """## 3. El estado compartido: quién aportó qué

Esto es lo que evita la pérdida de contexto. Cada contribución queda registrada con su
autor, y el supervisor decide mirando esa lista.
"""

MARKDOWN_CIERRE = """## 4. Qué demuestra esto

- **Topología jerárquica**: un supervisor que rutea y decide el final; dos especialistas con
  herramientas acotadas (búsqueda y cálculo) que no se llaman entre ellos.
- **Estado compartido estructurado**: `contribuciones` con reducer `operator.add`, más
  `next_agent`, `pasos`, `task_completed` y el informe de `validacion`.
- **Flujo de supervisión**: el supervisor delega, recibe el aporte y decide si falta algo.
- **Corte del "Supervisor Infinito"**: `MAX_PASOS` en el supervisor, el validador
  determinista y `MAX_REINTENTOS` en las aristas.
- **Contexto acotado**: a cada especialista le llega una instrucción puntual, la pregunta
  original y los aportes (no el historial entero).
"""


def main() -> None:
    nb = nbf.v4.new_notebook()

    nb.cells = [
        nbf.v4.new_markdown_cell(MARKDOWN_INTRO),
        nbf.v4.new_markdown_cell(MARKDOWN_TOPOLOGIA),
        nbf.v4.new_code_cell(
            "from graph import build_app, diagrama_mermaid\n"
            "\n"
            "app = build_app()\n"
            "print(diagrama_mermaid(app))"
        ),
        nbf.v4.new_markdown_cell(MARKDOWN_CORRIDA),
        nbf.v4.new_code_cell(
            "from main import correr\n"
            "\n"
            "resultado, traza = correr()"
        ),
        nbf.v4.new_markdown_cell(MARKDOWN_ESTADO),
        nbf.v4.new_code_cell(
            "print('RESPUESTA FINAL:\\n')\n"
            "print(traza['respuesta_final'])\n"
            "\n"
            "print('\\n' + '=' * 70)\n"
            "print('CONTRIBUCIONES (quién aportó qué)')\n"
            "print('=' * 70)\n"
            "for c in traza['contribuciones']:\n"
            "    print(f\"\\n[{c['agente']}]\\n{c['aporte']}\")\n"
            "\n"
            "print('\\n' + '=' * 70)\n"
            "print('INFORME DEL VALIDADOR')\n"
            "print('=' * 70)\n"
            "print(traza['validacion'])\n"
            "print(f\"\\nPasos de especialistas: {traza['pasos_ejecutados']}\")"
        ),
        nbf.v4.new_markdown_cell(MARKDOWN_CIERRE),
    ]

    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }

    print("Ejecutando el notebook (llama al modelo real, puede tardar un minuto)...")
    cliente = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": "."}})
    cliente.execute()

    limpiar_salidas(nb)

    nbf.write(nb, str(ARCHIVO))
    print(f"Listo: {ARCHIVO} con las salidas de la corrida.")


if __name__ == "__main__":
    main()
