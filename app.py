"""Classroom-only simulated investing: concurrent research, LLM choice, conditional trade."""
import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr
from agents import Agent, Runner, WebSearchTool, function_tool
from pydantic import BaseModel

ROOT = Path(__file__).parent
MEMORY = ROOT / "agents/triage/memory.md"
PORTFOLIO = ROOT / "portfolio.json"


def load_portfolio():
    if PORTFOLIO.exists():
        return json.loads(PORTFOLIO.read_text())
    return {"cash": 10000.0, "shares": {"AAPL": 3, "MSFT": 2, "JNJ": 4}}


def skill(sector):
    return (ROOT / f"agents/{sector}/skill.md").read_text()


class Research(BaseModel):
    sector: str
    action: str  # BUY or PASS
    symbol: str  # blank for PASS
    rationale: str
    source_url: str
    indicative_price: float  # 0 if not verified


ADVISORS = {
    sector: Agent(
        name=f"{sector.title()} advisor",
        instructions=(
            skill(sector)
            + "\nUse web search for recent evidence. Return structured output. "
            + "action must be BUY or PASS. If price cannot be verified, use 0. "
            + "Do not treat old news as current. This is simulated educational research."
        ),
        tools=[WebSearchTool()],
        output_type=Research,
    )
    for sector in ("energy", "technology", "healthcare")
}


def message(text):
    return {"role": "assistant", "content": text}


async def cycle(history):
    history = list(history or [])
    history.append(message("**Starting:** Three sector advisors researching concurrently..."))
    yield history

    async def research(sector, agent):
        result = await Runner.run(agent, "Research one attractive US stock to buy now, or PASS. Use current web evidence.")
        return sector, result.final_output

    tasks = [asyncio.create_task(research(s, a)) for s, a in ADVISORS.items()]
    findings = []
    try:
        for task in asyncio.as_completed(tasks):
            sector, finding = await task
            findings.append(finding)
            history.append(message(f"**{sector.title()} advisor complete:** {finding.action} {finding.symbol or ''} — {finding.rationale}"))
            yield history
    except Exception as exc:
        for task in tasks:
            task.cancel()
        history.append(message(f"Research failed; no trade placed. {type(exc).__name__}: {exc}"))
        yield history
        return

    history.append(message("**Orchestrator active:** Comparing three recommendations; may choose zero or one trade..."))
    yield history

    before = load_portfolio()
    state = {"trade": None}

    @function_tool
    def execute_simulated_trade(symbol: str, indicative_price: float, reason: str) -> str:
        """Ask the trading agent to buy ONE share of a selected stock in the classroom simulation. Use only one of the researched BUY candidates."""
        if state["trade"] is not None:
            return "Trade already executed this cycle; no additional trade allowed."
        eligible = {r.symbol.upper(): r for r in findings if r.action.upper() == "BUY" and r.symbol}
        symbol = symbol.upper().strip()
        if symbol not in eligible:
            return "Rejected: symbol is not an advisor BUY candidate."
        # No invented market quote: use verified indicative price only.
        verified = eligible[symbol].indicative_price
        if verified <= 0:
            return "Rejected: advisor could not verify an indicative price. Choose PASS."
        if abs(indicative_price - verified) > 0.01:
            return "Rejected: price does not match advisor evidence."
        # Random simulated slippage; not a live execution or executable quote.
        execution_price = round(verified * random.uniform(0.995, 1.005), 2)
        current = load_portfolio()
        if current["cash"] < execution_price:
            return "Rejected: insufficient simulated cash."
        current["cash"] = round(current["cash"] - execution_price, 2)
        current["shares"][symbol] = current["shares"].get(symbol, 0) + 1
        PORTFOLIO.write_text(json.dumps(current, indent=2))
        state["trade"] = {"symbol": symbol, "shares": 1, "price": execution_price, "reason": reason}
        return json.dumps({"status": "SIMULATED BUY", **state["trade"]})

    trader = Agent(
        name="Trading agent",
        instructions="Execute at most one simulated BUY by calling execute_simulated_trade. Never claim real execution.",
        tools=[execute_simulated_trade],
    )

    # The orchestrator retains control: trader is a tool, not a handoff.
    orchestrator = Agent(
        name="Triage / orchestrator",
        instructions=(
            "You manage a simulation. Independently evaluate all three sector reports. "
            "You may choose NO TRADE or one BUY candidate only. No user approval is needed for simulation. "
            "If you choose to buy, call trading_agent exactly once with the researched symbol, "
            "the advisor's indicative_price and your rationale. If price is unverified, choose NO TRADE. "
            "Report all sector views, why you chose the winner or no trade, and the trader's actual response. "
            "Never invent a completed trade. Existing memory:\n" + MEMORY.read_text()[-12000:]
        ),
        tools=[trader.as_tool(tool_name="trading_agent", tool_description="Simulate buying one share of an advisor-recommended stock; returns execution or rejection.")],
    )

    report_input = json.dumps({"research": [r.model_dump() for r in findings], "portfolio_before": before})
    try:
        result = await Runner.run(orchestrator, report_input, max_turns=12)
        report = str(result.final_output)
    except Exception as exc:
        report = f"Orchestrator error: {type(exc).__name__}: {exc}"
    after = load_portfolio()
    stamp = datetime.now(timezone.utc).isoformat()
    record = {"time_utc": stamp, "research": [r.model_dump() for r in findings], "trade": state["trade"], "before": before, "after": after}
    with MEMORY.open("a") as f:
        f.write("\n## Cycle " + stamp + "\n```json\n" + json.dumps(record, indent=2) + "\n```\n")
    history.append(message("**Orchestrator report**\n\n" + report + "\n\n**Portfolio before:** `" + json.dumps(before) + "`\n\n**Portfolio after:** `" + json.dumps(after) + "`\n\n**Executed this cycle:** " + (json.dumps(state["trade"]) if state["trade"] else "No simulated trade")))
    yield history


async def ask(question, history):
    history = list(history or [])
    if not question.strip():
        yield history, ""
        return
    history.append({"role": "user", "content": question})
    history.append(message("**Orchestrator:** Reading trade history..."))
    yield history, ""
    agent = Agent(name="History reporter", instructions="Answer only from the supplied simulated trade memory. Say when information is absent.")
    try:
        result = await Runner.run(agent, "Trade memory:\n" + MEMORY.read_text()[-20000:] + "\n\nQuestion: " + question)
        history[-1] = message(str(result.final_output))
    except Exception as exc:
        history[-1] = message(f"Unable to answer: {exc}")
    yield history, ""


with gr.Blocks(title="Multi-Agent Sector Research (Simulation)") as demo:
    gr.Markdown("# Multi-Agent Sector Research — Simulation\nThree advisors research concurrently; the orchestrator may select **zero or one** simulated buy. No real trades.")
    chatbot = gr.Chatbot(height=530)
    run_button = gr.Button("Run analysis and simulated trading", variant="primary")
    with gr.Row():
        question = gr.Textbox(label="Ask about past simulated trades", placeholder="What trades have we made?")
        ask_button = gr.Button("Ask")
    run_button.click(cycle, inputs=[chatbot], outputs=[chatbot], concurrency_limit=1)
    ask_button.click(ask, inputs=[question, chatbot], outputs=[chatbot, question], concurrency_limit=1)
    question.submit(ask, inputs=[question, chatbot], outputs=[chatbot, question], concurrency_limit=1)

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(server_name="0.0.0.0", server_port=7860)
