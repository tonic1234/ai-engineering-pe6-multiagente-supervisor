"""test_supervisor.py — el cerebro del sistema.

Lo que se prueba:
- la decisión del supervisor es ESTRUCTURADA (un objeto con `next` limitado a los
  nombres reales de los nodos): es lo que después se mapea en las aristas condicionales;
- el CORTE DURO: si ya se pasó de MAX_PASOS decide FINISH sin consultar al LLM. Es la
  defensa contra el "Supervisor Infinito" que nombra el enunciado.
"""

from __future__ import annotations

import pytest

from supervisor import MAX_PASOS, DecisionSupervisor, Supervisor


class LLMEstructuradoFalso:
    """Doble del LLM con salida estructurada: devuelve lo que le pidamos."""

    def __init__(self, decision):
        self.decision = decision
        self.prompts = []

    def invoke(self, mensajes):
        self.prompts.append(mensajes)
        return self.decision


class LLMEstructuradoExplosivo:
    """Si lo llaman cuando no corresponde, el test explota con un mensaje claro."""

    def invoke(self, mensajes):  # pragma: no cover - solo se usa para fallar
        raise AssertionError("El supervisor consultó al LLM cuando debía cortar por MAX_PASOS")


class LLMFalso:
    """Doble del LLM "pelado": solo sabe devolver el runnable estructurado."""

    def __init__(self, decision):
        self.estructurado = LLMEstructuradoFalso(decision)

    def with_structured_output(self, esquema):
        assert esquema is DecisionSupervisor
        return self.estructurado


def estado(pasos=0, contribuciones=None):
    return {
        "messages": [],
        "next_agent": None,
        "contribuciones": contribuciones or [],
        "pasos": pasos,
        "task_completed": False,
        "validacion": None,
    }


def test_decision_estructurada_mapea_a_nodos_reales():
    decision = DecisionSupervisor(next="analista", razon="ya tengo el dato, falta el cálculo")
    supervisor = Supervisor(llm=LLMFalso(decision))

    resultado = supervisor.decidir(estado())

    assert resultado.next == "analista"
    assert resultado.razon


def test_literal_solo_acepta_nombres_del_grafo():
    with pytest.raises(Exception):
        DecisionSupervisor(next="agente_que_no_existe", razon="...")


def test_el_prompt_lleva_las_contribuciones():
    """Anti "pérdida de contexto": el supervisor ve quién aportó qué."""

    decision = DecisionSupervisor(next="FINISH", razon="listo")
    llm = LLMFalso(decision)
    supervisor = Supervisor(llm=llm)
    contribuciones = [
        {"agente": "investigador", "aporte": "14 días con menos de 5 años"},
        {"agente": "analista", "aporte": "Resultado: 287"},
    ]

    supervisor.decidir(estado(pasos=2, contribuciones=contribuciones))

    prompts = str(llm.estructurado.prompts)
    assert "investigador" in prompts
    assert "287" in prompts


def test_corte_duro_por_max_pasos_sin_consultar_al_llm():
    supervisor = Supervisor(llm=LLMEstructuradoExplosivo())
    resultado = supervisor.decidir(estado(pasos=MAX_PASOS))
    assert resultado.next == "FINISH"


def test_nodo_supervisor_devuelve_la_actualizacion_del_estado():
    from supervisor import nodo_supervisor

    decision = DecisionSupervisor(
        next="investigador",
        instruccion="Buscá los tramos de vacaciones por antigüedad",
        razon="falta el dato de la empresa",
    )
    supervisor = Supervisor(llm=LLMFalso(decision))

    actualizacion = nodo_supervisor(estado(), supervisor=supervisor)

    assert actualizacion["next_agent"] == "investigador"
    assert actualizacion["instruccion"] == "Buscá los tramos de vacaciones por antigüedad"
    assert actualizacion["task_completed"] is False


# ---------------------------------------------------------------------------
# La red determinista contra la delegación repetida (bug de la primera corrida real:
# el modelo insistía con el investigador y el analista nunca corría).
# ---------------------------------------------------------------------------
def test_si_ya_aporto_el_investigador_lo_redirige_al_analista():
    from supervisor import nodo_supervisor

    decision = DecisionSupervisor(next="investigador", instruccion="buscá otra vez", razon="insiste")
    supervisor = Supervisor(llm=LLMFalso(decision))
    estado_repetido = estado(
        pasos=1,
        contribuciones=[
            {"agente": "investigador", "aporte": "[Fuente: politica_vacaciones.txt] 15, 20 y 25 días"}
        ],
    )

    actualizacion = nodo_supervisor(estado_repetido, supervisor=supervisor)

    assert actualizacion["next_agent"] == "analista"
    # Y la instrucción se reemplaza por una del oficio correcto (no la de búsqueda).
    assert actualizacion["instruccion"].startswith("Calculá")


def test_no_redirige_si_el_aporte_anterior_fue_un_error():
    from supervisor import nodo_supervisor

    decision = DecisionSupervisor(next="investigador", instruccion="probá de nuevo", razon="falló")
    supervisor = Supervisor(llm=LLMFalso(decision))
    estado_con_error = estado(
        pasos=1,
        contribuciones=[{"agente": "investigador", "aporte": "ERROR: no se encontró el dato"}],
    )

    actualizacion = nodo_supervisor(estado_con_error, supervisor=supervisor)

    assert actualizacion["next_agent"] == "investigador"


def test_si_quiere_cerrar_con_un_dominio_sin_cubrir_lo_manda_al_que_falta():
    """El validador manda: no se cierra la respuesta con media tarea hecha."""

    from supervisor import nodo_supervisor

    decision = DecisionSupervisor(next="FINISH", razon="me parece que ya está")
    supervisor = Supervisor(llm=LLMFalso(decision))
    estado_a_medias = estado(
        pasos=1,
        contribuciones=[
            {"agente": "investigador", "aporte": "[Fuente: politica_vacaciones.txt] 15, 20 y 25 días"}
        ],
    )

    actualizacion = nodo_supervisor(estado_a_medias, supervisor=supervisor)

    assert actualizacion["next_agent"] == "analista"
    assert actualizacion["instruccion"].startswith("Calculá")


def test_si_quiere_cerrar_sin_ningun_aporte_lo_deja_cerrar():
    """Una pregunta que no necesita al equipo se cierra igual (sin dar vueltas)."""

    from supervisor import nodo_supervisor

    decision = DecisionSupervisor(next="FINISH", razon="no hace falta delegar")
    supervisor = Supervisor(llm=LLMFalso(decision))

    actualizacion = nodo_supervisor(estado(), supervisor=supervisor)

    assert actualizacion["next_agent"] == "FINISH"
    assert actualizacion["task_completed"] is True


def test_con_los_dos_dominios_cubiertos_deja_la_decision_como_esta():
    from supervisor import nodo_supervisor

    decision = DecisionSupervisor(next="analista", instruccion="revisá la cuenta", razon="refinar")
    supervisor = Supervisor(llm=LLMFalso(decision))
    estado_completo = estado(
        pasos=2,
        contribuciones=[
            {"agente": "investigador", "aporte": "[Fuente: politica_vacaciones.txt] 15, 20 y 25 días"},
            {"agente": "analista", "aporte": "Resultado: 250. Cuenta: 2*15 + 6*20 + 4*25."},
        ],
    )

    actualizacion = nodo_supervisor(estado_completo, supervisor=supervisor)

    assert actualizacion["next_agent"] == "analista"
