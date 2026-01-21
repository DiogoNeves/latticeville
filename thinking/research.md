# Research notes (post-baseline experiments)

This document is a scratchpad for **ideas to test after the baseline implementation is working**.

The baseline implementation is described in [Spec](thinking/spec.md), which is in turn explicitly grounded in the paper summarised in [Summary](thinking/paper/summary.md).  

We will not attempt to implement any of the experiments until the main project is working.  
At the end of the project, we may want to turn the most successful experiments into a short **research-style writeup** (motivation, method, evaluation, results, limitations).

## Research areas

### 0) Baseline note (for context)

Baseline uses a single tool-called `act` decision per tick (e.g., `MOVE` / `INTERACT` / `SAY` / `NOOP`),
validated and executed deterministically by the simulator. Natural-language memory entries are generated
from templates based on executed actions/events.

### 1) Constrained object interactions via exposed state-changing functions

#### Idea
Instead of letting the model freely “decide” arbitrary object state changes from natural language actions, each object exposes a small set of **explicit state-changing functions** (an internal API). When an agent approaches an object (or decides to use it), the simulator exposes that object’s callable functions to the model (plus the object’s current state), and the model chooses which function(s) to call.  
The agent can decide which object to interact with and load the functions automatically, within the LLM call, by providing a function to fetch the object interface, from an object identifier (likely the unique path in the world tree).  

Examples (illustrative):
- `Fridge.take(item)`
- `Stove.turn_on()`, `Stove.turn_off()`, `Stove.set_heat(level)`
- `CoffeeMachine.brew(kind)`, `CoffeeMachine.stop()`

The new state is returned as natural language statements, in the format of *observations*.  

These functions can still call LLMs internally if needed (e.g., to decide *which* ingredient is taken, or to narrate a higher-level action), but the canonical state transition occurs through a designed interface.

#### How it differs from baseline
- Baseline `INTERACT(object_id, verb)` uses a small verb set and simulator-owned transition rules.
- This experiment makes object APIs richer and more object-specific (more structure, potentially better validity).

#### Why it might help
- **Constrains interaction space** so interactions can be intentionally designed (less “anything can happen”).
- **Guarantees consistency** through a clear internal state machine per object (fewer contradictory or impossible states).
- **Improves simulation quality** by separating (a) narrative generation from (b) state transitions. If desired, function execution can remain deterministic even when narration uses an LLM.

#### What to test (once baseline exists)
- Whether agents still feel believable while having a narrower action space.
- Whether object state becomes more stable/legible (fewer invalid transitions, fewer hallucinated state changes).
- Whether “reactive behavior” improves because states are reliable (e.g., “fridge is empty” is derived from inventory rules rather than inferred textually).

