"""
Generate the LangGraph architecture diagram for CityPark Parking Assistant.

Outputs a Mermaid diagram to docs/graph_architecture.md — renderable on
GitHub, GitLab, and in any Markdown viewer. Include in the PowerPoint.

Usage:
    python scripts/generate_graph_diagram.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    from src.agents.graph import build_graph

    print("Building graph...")
    graph = build_graph()
    mermaid = graph.get_graph().draw_mermaid()

    docs_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(docs_dir, exist_ok=True)
    out = os.path.join(docs_dir, "graph_architecture.md")

    with open(out, "w", encoding="utf-8") as f:
        f.write("# CityPark Agent — LangGraph Architecture\n\n")
        f.write("The diagram below is auto-generated from the live graph definition.\n\n")
        f.write("```mermaid\n")
        f.write(mermaid)
        f.write("\n```\n\n")
        f.write("## Node descriptions\n\n")
        f.write("| Node | Role |\n")
        f.write("|------|------|\n")
        f.write("| `input_guardrail` | Presidio PII/injection filter — blocks harmful input before it reaches the LLM |\n")
        f.write("| `intent_detection` | GPT-4o classifies message as `info_query`, `reservation`, or `unknown` |\n")
        f.write("| `rag` | ChromaDB retrieval + live DB context → GPT-4o generates parking info answer |\n")
        f.write("| `reservation` | Stateful 7-step data collection (name → confirm) using LangGraph checkpointing |\n")
        f.write("| `admin_agent` | ReAct agent saves to SQLite, emails admin, then `interrupt()` suspends graph |\n")
        f.write("| `output_guardrail` | Presidio anonymiser scrubs PII from the final response |\n")

    print(f"Diagram saved -> {out}")
    print("\nMermaid source:\n")
    print(mermaid)


if __name__ == "__main__":
    main()
