# CityPark Agent — LangGraph Architecture

The diagram below is auto-generated from the live graph definition.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	input_guardrail(input_guardrail)
	intent_detection(intent_detection)
	rag(rag)
	reservation(reservation)
	admin_agent(admin_agent)
	output_guardrail(output_guardrail)
	__end__([<p>__end__</p>]):::last
	__start__ --> input_guardrail;
	admin_agent --> output_guardrail;
	input_guardrail -. &nbsp;pass&nbsp; .-> intent_detection;
	input_guardrail -. &nbsp;blocked&nbsp; .-> output_guardrail;
	intent_detection -. &nbsp;info_query&nbsp; .-> rag;
	intent_detection -.-> reservation;
	rag --> output_guardrail;
	reservation -. &nbsp;admin&nbsp; .-> admin_agent;
	reservation -. &nbsp;output&nbsp; .-> output_guardrail;
	output_guardrail --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc

```

## Node descriptions

| Node | Role |
|------|------|
| `input_guardrail` | Presidio PII/injection filter — blocks harmful input before it reaches the LLM |
| `intent_detection` | GPT-4o classifies message as `info_query`, `reservation`, or `unknown` |
| `rag` | ChromaDB retrieval + live DB context → GPT-4o generates parking info answer |
| `reservation` | Stateful 7-step data collection (name → confirm) using LangGraph checkpointing |
| `admin_agent` | ReAct agent saves to SQLite, emails admin, then `interrupt()` suspends graph |
| `output_guardrail` | Presidio anonymiser scrubs PII from the final response |
