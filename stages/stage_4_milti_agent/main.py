"""Stage 4: Multi-Agent System (In-Process).

Multiple specialised agents collaborate on a complex legal question.
This stage runs in one Python process and uses LangGraph Send objects
to dispatch specialist agents in parallel.
"""

import asyncio
import json
import os
import sys
from typing import Annotated, TypedDict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from common.llm import get_llm


@tool
def search_tax_law(query: str) -> str:
    """Search tax law knowledge base for relevant statutes and penalties."""
    knowledge = [
        (
            ["tax", "evasion", "fraud", "irs"],
            "Tax evasion (26 U.S.C. § 7201): felony, up to $250K fine and 5 years prison. "
            "Civil fraud penalty: 75% of underpayment (IRC § 6663). Failure to file: up to "
            "$25K fine and 1 year prison.",
        ),
        (
            ["offshore", "overseas", "foreign", "fbar", "fatca"],
            "FBAR penalties: up to $100K or 50% of account balance per violation. "
            "FATCA non-compliance: 30% withholding on US-source payments. "
            "Willful violations may trigger criminal prosecution.",
        ),
        (
            ["transfer", "pricing", "corporate"],
            "Transfer pricing violations (IRC § 482): IRS can reallocate income between "
            "related entities. Penalties: 20-40% of underpayment for substantial/gross "
            "valuation misstatements.",
        ),
    ]
    query_lower = query.lower()
    results = [text for keywords, text in knowledge if any(kw in query_lower for kw in keywords)]
    return "\n\n".join(results) if results else "No specific tax law matches found."


@tool
def search_compliance_law(query: str) -> str:
    """Search regulatory compliance knowledge base for applicable frameworks."""
    knowledge = [
        (
            ["data", "privacy", "gdpr", "ccpa", "consent", "user"],
            "CCPA: fines up to $7,500 per intentional violation. GDPR: up to 4% of global "
            "revenue or EUR 20M. FTC Act Section 5 for unfair/deceptive practices. "
            "Class action exposure under state privacy laws ($100-$750 per consumer).",
        ),
        (
            ["sox", "sarbanes", "financial", "sec", "reporting"],
            "SOX § 906: false certification - up to $5M fine, 20 years prison. "
            "§ 802: record destruction - up to 20 years. § 1107: whistleblower "
            "retaliation - up to 10 years. SEC officer/director bars.",
        ),
        (
            ["fcpa", "bribery", "corruption", "foreign"],
            "FCPA anti-bribery: up to $250K fine per violation for individuals, "
            "$2M for corporations. Criminal penalties: up to 5 years prison. "
            "Books and records provisions apply to all SEC-reporting companies.",
        ),
    ]
    query_lower = query.lower()
    results = [text for keywords, text in knowledge if any(kw in query_lower for kw in keywords)]
    return "\n\n".join(results) if results else "No specific compliance matches found."


@tool
def search_privacy_law(query: str) -> str:
    """Search privacy and data protection knowledge base."""
    knowledge = [
        (
            ["data", "privacy", "gdpr", "consent", "personal", "breach"],
            "GDPR requires a lawful basis for processing personal data, transparency notices, "
            "data subject rights, processor controls, and breach notification to regulators "
            "within 72 hours where required. Fines can reach EUR 20M or 4% of annual global turnover.",
        ),
        (
            ["ccpa", "cpra", "california", "consumer"],
            "CCPA/CPRA requires notice, opt-out rights for sale/sharing, data access/deletion "
            "rights, and reasonable security. Intentional violations can trigger civil penalties "
            "up to $7,500 per violation.",
        ),
        (
            ["rò rỉ", "dữ liệu", "leak", "incident"],
            "A data breach may require incident response, forensic investigation, regulator "
            "notification, customer notice, remediation, and preservation of evidence.",
        ),
    ]
    query_lower = query.lower()
    results = [text for keywords, text in knowledge if any(kw in query_lower for kw in keywords)]
    return "\n\n".join(results) if results else "No specific privacy law matches found."


def _last_wins(a: str, b: str) -> str:
    """Reducer: keep the most recently written value."""
    return b if b else a


class LegalState(TypedDict):
    question: str
    law_analysis: str
    needs_tax: bool
    needs_compliance: bool
    needs_privacy: bool
    tax_result: Annotated[str, _last_wins]
    compliance_result: Annotated[str, _last_wins]
    privacy_result: Annotated[str, _last_wins]
    final_answer: str


async def analyze_law(state: LegalState) -> dict:
    """Lead attorney analyses the legal aspects of the question."""
    print("\n  [Node: analyze_law] Lead attorney analysing legal aspects...")
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                "You are a senior corporate litigation attorney specialising in contract law, "
                "tort law, and general business law. Analyse the legal aspects of the question "
                "thoroughly. Keep your analysis under 200 words."
            )
        ),
        HumanMessage(content=state["question"]),
    ]
    result = await llm.ainvoke(messages)
    print(f"  [Node: analyze_law] Done ({len(result.content)} chars)")
    return {"law_analysis": result.content}


async def check_routing(state: LegalState) -> dict:
    """Determine which specialist sub-agents are needed."""
    print("\n  [Node: check_routing] Determining which specialists are needed...")
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                "You are a legal routing expert. Reply with ONLY valid JSON:\n"
                '{"needs_tax": <true|false>, "needs_compliance": <true|false>, '
                '"needs_privacy": <true|false>}\n\n'
                "needs_tax means tax law, IRS, tax evasion, penalties.\n"
                "needs_compliance means SEC, SOX, AML, FCPA, or regulatory compliance.\n"
                "needs_privacy means data, privacy, GDPR, CCPA, or personal data."
            )
        ),
        HumanMessage(content=state["question"]),
    ]
    result = await llm.ainvoke(messages)
    raw = result.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"needs_tax": True, "needs_compliance": True, "needs_privacy": False}

    question_lower = state["question"].lower()
    needs_tax = bool(parsed.get("needs_tax", True))
    needs_compliance = bool(parsed.get("needs_compliance", True))
    needs_privacy = bool(parsed.get("needs_privacy", False)) or any(
        kw in question_lower for kw in ["data", "privacy", "gdpr", "ccpa", "dữ liệu"]
    )

    print(
        "  [Node: check_routing] "
        f"needs_tax={needs_tax}, needs_compliance={needs_compliance}, needs_privacy={needs_privacy}"
    )
    return {"needs_tax": needs_tax, "needs_compliance": needs_compliance, "needs_privacy": needs_privacy}


def route_to_specialists(state: LegalState) -> list[Send]:
    """Dispatch parallel Send objects to specialist nodes."""
    sends: list[Send] = []
    if state.get("needs_tax"):
        sends.append(Send("call_tax_specialist", state))
    if state.get("needs_compliance"):
        sends.append(Send("call_compliance_specialist", state))
    if state.get("needs_privacy"):
        sends.append(Send("call_privacy_specialist", state))
    if not sends:
        sends.append(Send("aggregate", state))
    return sends


async def call_tax_specialist(state: LegalState) -> dict:
    """Tax specialist sub-agent."""
    from langgraph.prebuilt import create_react_agent

    print("\n  [Node: call_tax_specialist] Tax specialist agent starting...")
    tax_prompt = (
        "You are a specialist tax attorney and CPA. Use search_tax_law to ground your analysis. "
        "Keep your response under 200 words."
    )
    llm = get_llm()
    agent = create_react_agent(model=llm, tools=[search_tax_law], prompt=tax_prompt)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": state["question"]}]})
    final_msg = result["messages"][-1].content
    print(f"  [Node: call_tax_specialist] Done ({len(final_msg)} chars)")
    return {"tax_result": final_msg}


async def call_compliance_specialist(state: LegalState) -> dict:
    """Compliance specialist sub-agent."""
    from langgraph.prebuilt import create_react_agent

    print("\n  [Node: call_compliance_specialist] Compliance specialist agent starting...")
    compliance_prompt = (
        "You are a senior regulatory compliance officer. Use search_compliance_law to ground "
        "your analysis. Keep your response under 200 words."
    )
    llm = get_llm()
    agent = create_react_agent(model=llm, tools=[search_compliance_law], prompt=compliance_prompt)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": state["question"]}]})
    final_msg = result["messages"][-1].content
    print(f"  [Node: call_compliance_specialist] Done ({len(final_msg)} chars)")
    return {"compliance_result": final_msg}


async def call_privacy_specialist(state: LegalState) -> dict:
    """Privacy specialist sub-agent."""
    from langgraph.prebuilt import create_react_agent

    print("\n  [Node: call_privacy_specialist] Privacy specialist agent starting...")
    privacy_prompt = (
        "You are a privacy counsel specialising in GDPR, CCPA/CPRA, data breach response, "
        "consent, data subject rights, and privacy litigation. Use search_privacy_law to ground "
        "your analysis. Keep your response under 200 words."
    )
    llm = get_llm()
    agent = create_react_agent(model=llm, tools=[search_privacy_law], prompt=privacy_prompt)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": state["question"]}]})
    final_msg = result["messages"][-1].content
    print(f"  [Node: call_privacy_specialist] Done ({len(final_msg)} chars)")
    return {"privacy_result": final_msg}


async def aggregate(state: LegalState) -> dict:
    """Combine all specialist analyses into a final comprehensive answer."""
    print("\n  [Node: aggregate] Combining all specialist analyses...")
    llm = get_llm()

    sections: list[str] = []
    if state.get("law_analysis"):
        sections.append(f"## Legal Analysis\n{state['law_analysis']}")
    if state.get("tax_result"):
        sections.append(f"## Tax Analysis\n{state['tax_result']}")
    if state.get("compliance_result"):
        sections.append(f"## Regulatory Compliance Analysis\n{state['compliance_result']}")
    if state.get("privacy_result"):
        sections.append(f"## Privacy / GDPR Analysis\n{state['privacy_result']}")

    combined = "\n\n---\n\n".join(sections)
    messages = [
        SystemMessage(
            content=(
                "You are a senior legal counsel synthesising specialist analyses into a "
                "comprehensive, well-structured response. Avoid redundancy. Keep under 500 words."
            )
        ),
        HumanMessage(content=combined),
    ]
    result = await llm.ainvoke(messages)
    print(f"  [Node: aggregate] Done ({len(result.content)} chars)")
    return {"final_answer": result.content}


def create_graph():
    """Build and compile the multi-agent StateGraph."""
    graph = StateGraph(LegalState)
    graph.add_node("analyze_law", analyze_law)
    graph.add_node("check_routing", check_routing)
    graph.add_node("call_tax_specialist", call_tax_specialist)
    graph.add_node("call_compliance_specialist", call_compliance_specialist)
    graph.add_node("call_privacy_specialist", call_privacy_specialist)
    graph.add_node("aggregate", aggregate)

    graph.set_entry_point("analyze_law")
    graph.add_edge("analyze_law", "check_routing")
    graph.add_conditional_edges(
        "check_routing",
        route_to_specialists,
        ["call_tax_specialist", "call_compliance_specialist", "call_privacy_specialist", "aggregate"],
    )
    graph.add_edge("call_tax_specialist", "aggregate")
    graph.add_edge("call_compliance_specialist", "aggregate")
    graph.add_edge("call_privacy_specialist", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()


QUESTION = (
    "If a company breaks a contract, avoids taxes, and leaks customer data, "
    "what are the legal, tax, compliance, and privacy consequences?"
)


async def main():
    print("=" * 70)
    print("STAGE 4: Multi-Agent System (In-Process)")
    print("=" * 70)
    print()
    print("[How it works]")
    print("  1. Lead attorney agent analyses the question")
    print("  2. Router decides which specialist agents are needed")
    print("  3. Tax + Compliance + Privacy specialists run in parallel")
    print("  4. Aggregator combines all analyses into a final answer")
    print()
    print("[Graph topology]")
    print("  analyze_law -> check_routing -> [tax + compliance + privacy] -> aggregate -> END")
    print()
    print(f"Question: {QUESTION}")
    print("-" * 70)

    graph = create_graph()
    result = await graph.ainvoke({
        "question": QUESTION,
        "law_analysis": "",
        "needs_tax": False,
        "needs_compliance": False,
        "needs_privacy": False,
        "tax_result": "",
        "compliance_result": "",
        "privacy_result": "",
        "final_answer": "",
    })

    print("\n" + "=" * 70)
    print("FINAL ANSWER")
    print("=" * 70)
    print(result["final_answer"])
    print()
    print("-" * 70)
    print("[Improvements over Stage 3]")
    print("  + Specialisation: each agent has domain-specific expertise")
    print("  + Parallel execution: specialists run concurrently")
    print("  + Explicit routing: privacy agent is called only for data/privacy/GDPR questions")
    print()
    print("Stage 5 deploys the same idea as independent A2A services.")
    print("=" * 70)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
