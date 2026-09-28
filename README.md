# Pre-entrega 6 — Orquestador multi-agente especializado

Un equipo de agentes que resuelve una consulta que necesita **dos dominios distintos** y una
**síntesis final**: un **Supervisor** que decide quién trabaja, un **investigador** que busca
datos en las políticas internas de la empresa y un **analista** que hace las cuentas con una
calculadora segura. Cuando los dos aportaron, un nodo de **validación** cierra el flujo y se
redacta la respuesta.

La consulta de la demo (y su resultado real, corrido contra Gemini + Pinecone):

> Un colaborador cumplió 12 años en la empresa: 2 años con menos de 3 de antigüedad, 6 años
> con entre 3 y 8, y 4 años con más de 8. ¿Cuántos días de vacaciones le correspondieron en
> total a lo largo de esos 12 años?

```
🔹 supervisor    decide -> investigador | instrucción: Buscá en la política interna de vacaciones...
🔹 investigador  [Fuente: politica_vacaciones.txt] Menos de 3 años: 15 días hábiles por año...
🔹 supervisor    decide -> analista | instrucción: Calculá con los números que ya están en el contexto...
🔹 analista      Resultado: 250 — Cuenta realizada: 2 * 15 + 6 * 20 + 4 * 25
🔹 supervisor    decide -> FINISH
🔹 validacion    suficiente=True | Los dos dominios aportaron y ninguno devolvió error
🔹 sintesis      Respuesta final: 250 días hábiles
```

La salida completa (con las contribuciones y el informe del validador) está en
[`traza_ejecucion.json`](traza_ejecucion.json) y en el notebook
[`demo_flujo.ipynb`](demo_flujo.ipynb), que se publica **ya ejecutado** con las salidas de la
corrida real.

## Topología elegida: jerárquica (patrón Supervisor)

```mermaid
graph TD;
	__start__([start]) --> supervisor;
	supervisor -.-> investigador;
	supervisor -.-> analista;
	supervisor -.-> validacion;
	investigador --> supervisor;
	analista --> supervisor;
	validacion -.-> sintesis;
	validacion -.-> supervisor;
	sintesis --> __end__([end]);
```

**Por qué jerárquica y no colaborativa.** En una topología colaborativa los agentes se
hablan entre sí y el orden lo negocian ellos: es más flexible, pero el resultado depende de
que dos modelos se pongan de acuerdo (y cuando los dos creen tener razón, se repiten entre
ellos). Acá el orden lo fija **un solo nodo**: el supervisor es el único que ve las
contribuciones acumuladas y el único que decide si falta algo, quién lo hace y cuándo se
cierra. Los especialistas no se conocen entre sí: no hay arista `investigador → analista`.

**Cómo se manejan los conflictos entre agentes.** Hay tres casos y ninguno se resuelve por
"voluntad" del modelo:

| Caso | Qué pasa | Cómo se resuelve |
|---|---|---|
| El especialista devuelve un error (`ERROR:` / "no encontré") | El aporte no sirve para cerrar | El validador lo cuenta como dominio **sin cubrir** y el supervisor lo vuelve a mandar con otra instrucción |
| El supervisor insiste con un agente que ya aportó | El otro dominio nunca se cubre | `_corregir_decision()` (en `supervisor.py`) redirige al dominio que falta, con una instrucción del oficio correcto |
| El supervisor quiere cerrar antes de tiempo | Saldría una respuesta a medias | El validador determinista manda: no se cierra con un dominio sin cubrir |
| Los dos quieren hablar para siempre | Bucle eterno (el "Supervisor Infinito" del enunciado) | Tres redes: `MAX_PASOS` en el supervisor, `MAX_REINTENTOS` en las aristas y el validador, que es código y no LLM |

## Estructura del repo

```
state.py                 # AgentState: el estado compartido (esquema del grafo)
tools.py                 # las herramientas: búsqueda en las políticas + calculadora SEGURA (ast, no eval)
agents/
  research_agent.py      # especialista en investigación (búsqueda acotada)
  analyst_agent.py       # especialista en análisis/cómputo (calculadora acotada)
supervisor.py            # el router: salida estructurada, la rúbrica y el corte por pasos
validation.py            # el nodo de Validation: ¿ya se puede cerrar?
nodes.py                 # los nodos que envuelven a los especialistas + la síntesis
graph.py                 # el armado del grafo (aristas condicionales, el ciclo y las rutas de corte)
main.py                  # la demo de punta a punta + la traza de la delegación
demo_flujo.ipynb         # el notebook ejecutado que demuestra el flujo
traza_ejecucion.json     # la traza real de la corrida (quién delegó a quién y por qué)
tests/                   # 44 pruebas que corren SIN claves y SIN red
data/                    # dataset de ejemplo (empresa ficticia, ver nota al final)
```

## El estado compartido

`AgentState` hereda de `MessagesState` y agrega:

| Campo | Para qué |
|---|---|
| `next_agent` | A quién decidió llamar el supervisor (`investigador`, `analista` o `FINISH`) |
| `instruccion` | La instrucción puntual que le deja al especialista elegido |
| `contribuciones` | **`Annotated[list, operator.add]`**: cada aporte se SUMA a la lista con su autor. Es lo que evita la pérdida de contexto en la comunicación asíncrona (si no tuviera el reducer, el aporte del último pisaría al anterior) |
| `pasos` | Cuántos especialistas corrieron (contador del corte) |
| `task_completed` | Si el flujo ya cerró |
| `validacion` | El informe del validador: `suficiente`, `faltantes`, `motivo` |
| `reintentos` | Cuántas veces el validador mandó a refinar |

## Contexto acotado (cómo se evita la "contaminación de contexto")

A cada especialista le llega **un solo mensaje** con tres bloques:

```
Pregunta original: <la consulta del usuario>

Instrucción del supervisor: <qué tiene que hacer exactamente>

Contexto disponible (aportes del equipo hasta ahora):
- [investigador] <los números que trajo>
```

No le llega el historial completo, ni las decisiones previas, ni la metadata del sistema. Lo
que sí le llega es la pregunta original: sin eso el analista no sabe cuántos años tiene el
colaborador y contesta que le falta un número (fue un bug real de la primera versión, hay un
test que lo cubre).

## La rúbrica del validador (lo que se exige para cerrar)

| Dominio | Criterio verificable |
|---|---|
| investigador | El aporte trae el dato **con su fuente** (`[Fuente: ...]`) |
| analista | El aporte trae el output de la calculadora (`Resultado: ...`) |

Un aporte con marca de error (`ERROR:`, `Error al calcular`, `No se encontró`) no cubre su
dominio, aunque tenga texto de sobra.

## Cómo correrlo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # y completá las claves (Gemini gratis en aistudio.google.com/apikey)

python main.py            # la demo completa: flujo + respuesta + traza
python main.py --topologia   # imprime el diagrama Mermaid del grafo
python -m pytest -q       # las 44 pruebas (corren sin claves y sin red)
```

Variables de entorno (todas en `.env.example`):

| Variable | Para qué | Obligatoria |
|---|---|---|
| `LLM_PROVIDER` | `gemini` (default), `openai` o `anthropic` | no |
| `GOOGLE_API_KEY` | clave de Gemini (free tier) | sí, para la corrida real |
| `PINECONE_API_KEY` | base vectorial de la pre-entrega anterior | no: sin ella el recuperador corre en modo léxico (BM25) |
| `INDEX_NAME` / `PINECONE_NAMESPACE` | nombre del índice y del namespace | no |
| `GEMINI_MODEL` / `OPENAI_MODEL` / `ANTHROPIC_MODEL` | modelo por proveedor | no |

## Las pruebas (44, sin claves)

Los tests no llaman al modelo ni a Pinecone: inyectan dobles en los tres lugares donde
habría red (supervisor, especialistas y LLM de la síntesis). Corren en un segundo.

| Archivo | Qué cubre |
|---|---|
| `test_state.py` | El reducer de `contribuciones` y los campos extra del estado |
| `test_tools.py` | La calculadora resuelve bien y **no ejecuta código** (los intentos con `__import__`/`open`/`__subclasses__` no crean ningún archivo: el test lo comprueba en disco) |
| `test_supervisor.py` | Salida estructurada, corte por `MAX_PASOS`, corrección de delegación repetida y de cierre prematuro |
| `test_validation.py` | Suficiencia, errores, y los dos casos reales que aparecieron en las corridas (analista sin cálculo, investigador sin fuente) |
| `test_nodes.py` | Contexto acotado (un mensaje, con la pregunta + instrucción + aportes) y la síntesis |
| `test_graph.py` | Los mapeos de las aristas condicionales y las tres rutas de corte |
| `test_integracion.py` | El flujo completo investigador → analista → validación → síntesis, y el corte con un supervisor que se empecina |

## Qué encontraron las corridas reales (y cómo se arregló)

Correr la demo contra el modelo de verdad destapó cuatro cosas que los dobles no muestran.
Quedan acá porque explican decisiones del código y tienen test de regresión:

1. **El especialista recibía su propia respuesta anterior como instrucción** → el
   investigador contestaba "quedame a disposición" y el analista nunca corría. Se arregló
   pasando la **instrucción del supervisor** (campo `instruccion`) en vez del último mensaje.
2. **El supervisor mandaba al analista a buscar** (instrucción de otro oficio) → el analista
   se negaba y ese texto igual cerraba el flujo. Se arregló en dos lados: el prompt del
   supervisor pide instrucciones por oficio, y el validador exige la marca de la calculadora.
3. **El analista no veía la pregunta original** → "falta un número". El contexto acotado
   ahora incluye la pregunta (acotado es "sin el historial", no "sin el pedido").
4. **La demo corría el grafo dos veces** (una para imprimir el flujo, otra para la
   respuesta) y las dos corridas podían no coincidir. Ahora es **una sola corrida**: el flujo
   se lee del stream de `updates` y el estado final del de `values`.

## Notas

- **Dataset de ejemplo:** las políticas internas de `data/` son de una **empresa ficticia**
  y el texto está inventado (el nombre del dominio es el de una agencia real, como contexto
  del ejercicio; los datos no son reales). Es el mismo dataset de las pre-entregas 3 y 4,
  justamente porque el curso pide que cada módulo se apoye en el anterior.
- **Corre gratis:** embeddings locales (`sentence-transformers/all-MiniLM-L6-v2`, 384
  dimensiones, sin API key) + free tier de Gemini. El recuperador es híbrido (BM25 +
  vectorial) y si no hay Pinecone configurado sigue andando en modo léxico.
- **El notebook** se regenera con `python construir_notebook.py` (lo ejecuta y guarda las
  salidas reales).
