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
# progreso de transformers/HuggingFace, warnings de tqdm y el log HTTP de la librería de
# Google). No se toca nada del contenido de la demo: solo se filtran estas líneas al guardar.
RUIDO = (
    "AFC",
    "Loading weights",
    "TqdmWarning",
    "unauthenticated requests to the HF Hub",
    "IProgress not found",
    "ipywidgets",
    "autonotebook",
    "Kernel is running over TCP",
    "HTTP Request:",
    "All log messages before absl",
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

Este notebook demuestra el **flujo de delegación** de la pre-entrega 6: quién decide, a quién
le pasa la tarea, con qué instrucción y con qué aporte vuelve.

Corre **dos consultas** para mostrar que el equipo se arma según el pedido:

1. Una que necesita **los dos dominios**: el dato (cuántos días de vacaciones por tramo de
   antigüedad) lo tiene el **investigador** en las políticas internas, y la cuenta total la
   hace el **analista** con la calculadora. El analista no puede correr antes que el
   investigador: los números que usa son los que el investigador trajo.
2. Una que se responde con **un solo dominio** (no hay cuenta que hacer): el supervisor
   cierra con el investigador y no llama al analista al pedo.

El orden lo fija el **supervisor**; los especialistas no se conocen entre sí.
"""

MARKDOWN_TOPOLOGIA = """## 1. La topología del grafo

Se arma una sola vez y se inspecciona. Los especialistas siempre vuelven al supervisor (ese
es el ciclo), y el nodo de `validacion` es el que decide si ya se puede cerrar.
"""

MARKDOWN_DATASET = """## 2. El dataset y el recuperador

El investigador no inventa: busca en el mismo dataset de las pre-entregas anteriores
(políticas internas de una empresa ficticia). Los documentos son largos como para partirse en
varios fragmentos y el índice de Pinecone se puebla desde `data/` con `ingest.py`, así que el
índice y los archivos no se separan nunca.

Acá se ve también **en qué modo quedó el recuperador**: híbrido (BM25 + vectorial) si hay
Pinecone, léxico si no. Si falta la clave, se avisa: no se degrada en silencio.
"""

MARKDOWN_CORRIDA = """## 3. La consulta que necesita los dos dominios

`correr()` recorre el grafo y va mostrando cada paso: la decisión del supervisor (con la
instrucción que le deja al especialista), el aporte que devuelve cada agente y el informe del
validador. Al final imprime la respuesta para el usuario.
"""

MARKDOWN_ESTADO = """## 4. El estado compartido: quién aportó qué

Esto es lo que evita la pérdida de contexto. Cada contribución queda registrada con su autor
(el reducer `operator.add` las acumula en vez de pisarlas), y el supervisor decide mirando esa
lista.
"""

MARKDOWN_TRAZA = """## 5. La traza, paso a paso

La misma corrida, leída del `traza_ejecucion.json` que queda en el repo: el orden en que
trabajó cada nodo, con la decisión y la instrucción de cada paso.
"""

MARKDOWN_SIMPLE = """## 6. La consulta que NO necesita cuenta

Esta pregunta se responde con el dato de la política. El punto es ver dos cosas:

- que la **rúbrica se adapta**: el validador exige el dominio del análisis sólo cuando la
  pregunta pide una cuenta (si no, el flujo nunca cerraría);
- que el supervisor **vuelve a delegar** al investigador con otra instrucción cuando falta la
  segunda parte de la pregunta, y recién después cierra. Son iteraciones reales del ciclo, no
  una sola vuelta.
"""

MARKDOWN_CIERRE = """## 7. Qué demuestra esto

- **Topología jerárquica**: un supervisor que rutea y decide el final; dos especialistas con
  herramientas acotadas (búsqueda y cálculo) que no se llaman entre ellos.
- **Estado compartido estructurado**: `contribuciones` con reducer `operator.add`, más
  `next_agent`, `instruccion`, `pasos`, `task_completed` y el informe de `validacion`.
- **Flujo de supervisión con refinamiento**: el supervisor delega, recibe el aporte, decide si
  falta algo y puede volver a delegar con otra instrucción.
- **Corte del "Supervisor Infinito"**: `MAX_PASOS` en el supervisor, el validador determinista
  y `MAX_REINTENTOS` en las aristas.
- **Contexto acotado**: a cada especialista le llega una instrucción puntual, la pregunta
  original y los aportes (no el historial entero).
- **Errores que no rompen el flujo**: si el proveedor rechaza una llamada, el especialista
  devuelve un aporte marcado como `ERROR:` con el motivo, y el equipo decide qué hacer.
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
        nbf.v4.new_markdown_cell(MARKDOWN_DATASET),
        nbf.v4.new_code_cell(
            "import tiktoken\n"
            "from rag import RAGSystem, chunk_documents, load_dataset\n"
            "\n"
            "codificador = tiktoken.get_encoding('cl100k_base')\n"
            "documentos = load_dataset()\n"
            "print('DATASET')\n"
            "print('=' * 70)\n"
            "for documento in documentos:\n"
            "    tokens = len(codificador.encode(documento.page_content))\n"
            "    print(f\"  {documento.metadata['source']:45s} {tokens:5d} tokens\")\n"
            "print(f\"  total: {len(documentos)} documentos, \"\n"
            "      f\"{sum(len(codificador.encode(d.page_content)) for d in documentos)} tokens\")\n"
            "\n"
            "chunks = chunk_documents(documentos)\n"
            "print(f\"\\n  fragmentos (chunks de 600 tokens): {len(chunks)}\")\n"
            "\n"
            "sistema = RAGSystem()\n"
            "print(f\"\\n  recuperador: {sistema.modo}\")"
        ),
        nbf.v4.new_markdown_cell(MARKDOWN_CORRIDA),
        nbf.v4.new_code_cell("from main import correr\n\nresultado, traza = correr()"),
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
        nbf.v4.new_markdown_cell(MARKDOWN_TRAZA),
        nbf.v4.new_code_cell(
            "for i, paso in enumerate(traza['pasos'], 1):\n"
            "    print(f\"{i}. {paso['nodo']:13s} {paso['detalle']}\")"
        ),
        nbf.v4.new_markdown_cell(MARKDOWN_SIMPLE),
        nbf.v4.new_code_cell(
            "from main import PREGUNTA_SIMPLE\n"
            "\n"
            "resultado_simple, traza_simple = correr(PREGUNTA_SIMPLE, archivo_traza='traza_consulta_simple.json')\n"
            "\n"
            "print('\\n' + '=' * 70)\n"
            "print('RÚBRICA DE ESTA CONSULTA')\n"
            "print('=' * 70)\n"
            "informe = traza_simple['validacion']\n"
            "print('dominios exigidos :', informe['dominios_exigidos'])\n"
            "print('dominios que aportaron:', informe['dominios_con_aporte'])\n"
            "print('suficiente:', informe['suficiente'])\n"
            "\n"
            "print('\\nPASOS:')\n"
            "for i, paso in enumerate(traza_simple['pasos'], 1):\n"
            "    print(f\"{i}. {paso['nodo']:13s} {paso['detalle']}\")\n"
            "\n"
            "print('\\nRESPUESTA FINAL:\\n')\n"
            "print(traza_simple['respuesta_final'])"
        ),
        nbf.v4.new_markdown_cell(MARKDOWN_CIERRE),
    ]

    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }

    print("Ejecutando el notebook (llama al modelo real, puede tardar un par de minutos)...")
    cliente = NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": "."}})
    cliente.execute()

    limpiar_salidas(nb)

    nbf.write(nb, str(ARCHIVO))
    print(f"Listo: {ARCHIVO} con las salidas de la corrida.")


if __name__ == "__main__":
    main()
