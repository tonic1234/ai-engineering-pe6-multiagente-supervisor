"""validation.py — el nodo de Validation (la parte que decide si ya se puede cerrar).

La consigna pide "un nodo de Validation o que el Supervisor tenga una rúbrica
personalizada". Acá están las dos, y a propósito:

- el SUPERVISOR lleva la rúbrica en el prompt (ver supervisor.py), porque es el que
  conversa con el modelo;
- el VALIDADOR es determinista y vive en código, porque no quiero que el cierre del flujo
  dependa de la buena voluntad del LLM. Si dejara todo en manos del supervisor, el caso
  clásico es el "Supervisor Infinito": el modelo cree que falta algo, delega de nuevo, y
  así hasta que se agota el contexto.

Cómo decide: mira las contribuciones acumuladas y exige, para cada dominio, que el aporte
sea VERIFICABLE, no una promesa:

- investigador: tiene que traer el dato con su fuente (`[Fuente: ...]`);
- analista: tiene que traer el resultado de la calculadora (`Resultado: ...`).

Esto salió de la primera corrida real: el supervisor le mandó al analista una instrucción
de búsqueda ("buscá y transcribí la política"), el analista contestó que eso no era su
trabajo y ese texto —sin ninguna cuenta— igual pasaba como "aporte válido". Con la regla
de arriba, ese caso vuelve al supervisor y el resultado final sale de la herramienta, no
de la imaginación del modelo.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Los dos dominios que exige la consigna. El orden importa para el informe: primero
# investigación (trae los datos) y después análisis (los procesa).
DOMINIOS = ["investigador", "analista"]

# Qué tiene que aparecer en el aporte de cada dominio para considerarlo verificado.
CRITERIOS = {
    "investigador": "[Fuente:",  # el dato tiene que venir con la cita del documento
    "analista": "Resultado:",  # el número tiene que salir de la calculadora
}

# Marcas de que un aporte NO sirve: es un error devuelto por la herramienta.
MARCAS_DE_ERROR = ["ERROR:", "Error al calcular", "No se encontró"]


def _aporte_util(dominio: str, aporte: str) -> bool:
    """Un aporte cuenta si no trae error y cumple el criterio verificable del dominio."""

    texto = (aporte or "").strip()
    if not texto:
        return False
    if any(marca in texto for marca in MARCAS_DE_ERROR):
        return False
    return CRITERIOS[dominio] in texto


def validar_estado(state: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve el informe de suficiencia del trabajo hecho hasta ahora."""

    contribuciones = state.get("contribuciones") or []
    dominios_con_aporte: List[str] = []

    for dominio in DOMINIOS:
        aportes = [c.get("aporte", "") for c in contribuciones if c.get("agente") == dominio]
        if any(_aporte_util(dominio, a) for a in aportes):
            dominios_con_aporte.append(dominio)

    faltantes = [d for d in DOMINIOS if d not in dominios_con_aporte]
    suficiente = not faltantes

    if suficiente:
        motivo = "Los dos dominios aportaron y ninguno devolvió error: se puede sintetizar."
    elif not contribuciones:
        motivo = "Todavía no corrió ningún especialista."
    else:
        pendientes = ", ".join(f"{d} ({CRITERIOS[d]})" for d in faltantes)
        motivo = f"Falta un aporte verificable de: {pendientes}."

    return {
        "suficiente": suficiente,
        "faltantes": faltantes,
        "dominios_con_aporte": dominios_con_aporte,
        "criterios": CRITERIOS,
        "motivo": motivo,
    }


def nodo_validador(state: Dict[str, Any]) -> Dict[str, Any]:
    """Nodo del grafo: escribe el informe en el estado y suma un reintento."""

    informe = validar_estado(state)
    return {
        "validacion": informe,
        "task_completed": informe["suficiente"],
        "reintentos": state.get("reintentos", 0) + 1,
    }
