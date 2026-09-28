"""test_validation.py — el nodo de Validation.

La consigna pide "un nodo de Validation o que el Supervisor tenga una rúbrica": acá están
las dos cosas, y la parte automática se prueba sin LLM.

El validador es determinista a propósito: mira las contribuciones y exige que cada aporte
sea VERIFICABLE (el investigador con su fuente, el analista con el resultado de la
calculadora). Así el flujo no depende de la buena voluntad del modelo para cerrar (el
"Supervisor Infinito" del enunciado) ni acepta promesas de trabajo como trabajo hecho.

El caso del aporte del analista "sin cuenta" no es inventado: apareció en la primera
corrida real contra Gemini, cuando se le pidió al analista que buscara y contestó que eso
no era su trabajo — y ese texto igual cerraba el flujo.
"""

from __future__ import annotations

from validation import validar_estado


def contrib(agente, aporte):
    return {"agente": agente, "aporte": aporte}


APORTE_INVESTIGADOR = (
    "[Fuente: politica_vacaciones.txt] Menos de 3 años: 15 días; de 3 a 8 años: 20 días; "
    "más de 8 años: 25 días."
)
APORTE_ANALISTA = "Resultado: 250. Cuenta: 2*15 + 6*20 + 4*25."


def test_sin_contribuciones_no_es_suficiente():
    informe = validar_estado({"contribuciones": [], "pasos": 0})
    assert informe["suficiente"] is False
    assert set(informe["faltantes"]) == {"investigador", "analista"}


def test_solo_investigacion_no_alcanza():
    informe = validar_estado({"contribuciones": [contrib("investigador", APORTE_INVESTIGADOR)], "pasos": 1})
    assert informe["suficiente"] is False
    assert informe["faltantes"] == ["analista"]


def test_con_los_dos_dominios_es_suficiente():
    estado = {
        "contribuciones": [
            contrib("investigador", APORTE_INVESTIGADOR),
            contrib("analista", APORTE_ANALISTA),
        ],
        "pasos": 2,
    }
    informe = validar_estado(estado)
    assert informe["suficiente"] is True
    assert informe["faltantes"] == []
    assert informe["dominios_con_aporte"] == ["investigador", "analista"]


def test_una_contribucion_con_error_no_cuenta_como_suficiente():
    """Si el especialista devolvió un ERROR, el supervisor tiene que mandarlo de nuevo."""

    estado = {
        "contribuciones": [
            contrib("investigador", "[Fuente: politica_vacaciones.txt] ERROR: no se encontró el tramo."),
            contrib("analista", APORTE_ANALISTA),
        ],
        "pasos": 2,
    }
    informe = validar_estado(estado)
    assert informe["suficiente"] is False
    assert "investigador" in informe["faltantes"]


def test_el_aporte_del_analista_sin_cuenta_no_cuenta():
    """El caso real: el analista contestó que buscar no era su trabajo, sin calcular nada."""

    estado = {
        "contribuciones": [
            contrib("investigador", APORTE_INVESTIGADOR),
            contrib(
                "analista",
                "Mi única función es realizar cuentas con la calculadora. No realizo búsquedas "
                "ni transcripciones de políticas.",
            ),
        ],
        "pasos": 2,
    }
    informe = validar_estado(estado)
    assert informe["suficiente"] is False
    assert informe["faltantes"] == ["analista"]


def test_el_aporte_del_investigador_sin_fuente_no_cuenta():
    """Un dato sin cita no es verificable: puede estar inventado."""

    estado = {
        "contribuciones": [
            contrib("investigador", "Creo que son 15, 20 y 25 días según la antigüedad."),
            contrib("analista", APORTE_ANALISTA),
        ],
        "pasos": 2,
    }
    informe = validar_estado(estado)
    assert informe["suficiente"] is False
    assert informe["faltantes"] == ["investigador"]


def test_el_informe_explica_el_porque_y_el_criterio():
    informe = validar_estado({"contribuciones": [], "pasos": 0})
    assert informe["motivo"]
    assert informe["criterios"]["analista"] == "Resultado:"
    assert informe["dominios_con_aporte"] == []


def test_el_nodo_devuelve_el_campo_validacion():
    from validation import nodo_validador

    actualizacion = nodo_validador(
        {
            "contribuciones": [
                contrib("investigador", APORTE_INVESTIGADOR),
                contrib("analista", APORTE_ANALISTA),
            ],
            "pasos": 2,
        }
    )
    assert actualizacion["validacion"]["suficiente"] is True
    assert actualizacion["task_completed"] is True
    assert actualizacion["reintentos"] == 1
