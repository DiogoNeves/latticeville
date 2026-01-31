# Prompts from the Generative Agents paper

This document summarizes the core prompt patterns described in the Generative Agents paper
([PDF](https://arxiv.org/pdf/2304.03442)) for later implementation. The goal is to capture
intent, required inputs, and expected outputs. These prompts are quoted or paraphrased
for documentation and will be adapted to Latticeville’s schemas.

## Observation (memory stream entries)

**Purpose:** Record direct perceptions (actions, object states, interactions).

**Inputs:**
- Local observations for the tick (nearby agents, objects, and changes).
- Agent’s identity and location context.

**Output shape:** Natural language memory entries (short declarative statements).

**Notes from paper:** Observations are direct perceptions stored each tick; they include
own actions, other agents’ actions in the same area, object states, and interactions
(paper §4.1 “Memory and Retrieval”).

## Importance scoring

**Purpose:** Rate how significant a memory is on a 1–10 scale at creation time.

**Prompt excerpt:**
```
On the scale of 1 to 10, where 1 is purely mundane (e.g., brushing teeth, making bed)
and 10 is extremely poignant (e.g., a break up, college acceptance), rate the likely
poignancy of the following piece of memory.

Memory: buying groceries at The Willows Market and Pharmacy

Rating: <fill in="">
```

**Inputs:** One memory text.

**Output shape:** Integer 1–10.

**Notes from paper:** The score is generated at creation time and later normalized
for retrieval (paper §4.1).

## Reflection

**Purpose:** Generate higher-level insights from recent memories.

**Step 1 (question generation) prompt excerpt:**
```
Given only the information above, what are 3 most salient high-level questions
we can answer about the subjects in the statements?
```

**Inputs:** Recent memory statements (e.g., ~100 most recent).

**Output shape:** List of 3 questions.

**Step 2 (insights) prompt excerpt:**
```
Statements about Klaus Mueller

1. Klaus Mueller is writing a research paper
2. Klaus Mueller enjoys reading a book on gentrification
3. Klaus Mueller is conversing with Ayesha Khan about exercising [...]

What 5 high-level insights can you infer from the above statements?
(example format: insight (because of 1, 5, 3))
```

**Inputs:** Retrieved relevant statements.

**Output shape:** 3–5 insights with cited memory indices.

**Notes from paper:** Reflections are stored as memory entries and can reference
other reflections; reflections are triggered when importance exceeds a threshold
(paper §4.2).

## Planning (daily plan in broad strokes)

**Purpose:** Generate a 5–8 chunk day plan and decompose it.

**Prompt excerpt (initial plan):**
```
Name: Eddy Lin (age: 19)
Innate traits: friendly, outgoing, hospitable
Eddy Lin is a student at Oak Hill College studying music theory and composition...
On Tuesday February 12, Eddy 1) woke up and completed the morning routine at 7:00 am, […] 6) got ready to sleep around 10 pm.
Today is Wednesday February 13. Here is Eddy’s plan today in broad strokes: 1)
```

**Inputs:** Agent summary description + previous day summary + current date.

**Output shape:** Ordered list of day chunks (5–8 items).

**Notes from paper:** Plans are stored in memory; then recursively decomposed to
hourly and 5–15 minute actions (paper §4.3).

## Reacting (decide whether to react)

**Purpose:** Decide whether to deviate from plan based on new observation.

**Prompt excerpt:**
```
[Agent’s Summary Description]
It is February 13, 2023, 4:56 pm.
John Lin’s status: John is back home early from work.
Observation: John saw Eddy taking a short walk around his workplace.
Summary of relevant context from John’s memory: Eddy Lin is John’s Lin’s son...
Should John react to the observation, and if so, what would be an appropriate reaction?
```

**Inputs:** Agent summary, current time, observation, summarized relevant context.

**Output shape:** React/ignore decision + reaction description.

**Notes from paper:** If reacting, re-plan from that time forward (paper §4.3.1).

## Dialogue

**Purpose:** Generate utterances during agent conversations.

**Prompt excerpt (initiator):**
```
[Agent’s Summary Description]
It is February 13, 2023, 4:56 pm.
John Lin’s status: John is back home early from work.
Observation: John saw Eddy taking a short walk around his workplace.
Summary of relevant context from John’s memory: Eddy Lin is John’s Lin’s son...
John is asking Eddy about his music composition project. What would he say to Eddy?
```

**Prompt excerpt (response):**
```
[Agent’s Summary Description]
It is February 13, 2023, 4:56 pm.
Eddy Lin’s status: Eddy is taking a short walk around his workplace.
Observation: John is initiating a conversation with Eddy.
Summary of relevant context from Eddy’s memory: John Lin is Eddy Lin’s father...
Here is the dialogue history:
John: Hey Eddy, how’s the music composition project for your class coming along?
How would Eddy respond to John?
```

**Inputs:** Agent summary, time, status, observation, relevant memory summary,
and dialogue history.

**Output shape:** Single utterance.

**Notes from paper:** Dialogue continues until one agent ends it (paper §4.3.2).

