# Multi-Agent Sector Research (simulated)

Five OpenAI Agents SDK agents in one Codespace: three concurrent sector advisors, a triage/orchestrator, and a trading agent called conditionally as an agent tool.


## Design

- Three advisors use hosted OpenAI web search **concurrently** and each reads only its own `agents/<sector>/skill.md` at startup.
- The orchestrator reviews all three and **decides** whether to call `trading_agent` as a tool. This is not a predetermined trading workflow.
- The trading agent can buy at most one share per run; a Python tool checks eligibility, cash and one-trade limit. It uses an advisor's indicative price plus randomized simulated slippage. **No brokerage, real orders, or live executable quotes.**
- `agents/triage/memory.md` stores prior cycles; `portfolio.json` is created on the first simulated trade. Both persist within the Codespace workspace. No other agent is given the memory file.
- The app shows advisor completion, orchestrator status and final result. Tool execution is not individually streamed while the orchestrator is running.
- A valid indicative price is required to simulate a buy; otherwise the agent should pass. Prices and research are informational and may be stale or inaccurate.
- If startup fails, inspect `/tmp/sector-agent-demo.log` or run `python app.py` manually.

**Classroom demonstration only. Not financial or tax advice.**
