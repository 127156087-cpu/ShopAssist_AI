# ShopAssist AI

An e-commerce support assistant. A customer chats about an order, and a LangGraph workflow routes the request to specialised agents, checks the order and policy, creates a support ticket, **pauses for human approval** before any sensitive action, runs a simulated refund / return / replacement / cancellation, verifies it, and tells the customer the real outcome. Support staff see the findings, approve or reject, and watch the workflow run live.

Built with LangGraph (StateGraph, conditional edges, reducers, interrupt/resume, SQLite checkpointer), LangChain (tools, prompt templates, output parsers), SQLite and Groq, with a FastAPI backend and a plain HTML/CSS/JS frontend.

## Features

- **Three agents, one workflow:** Order & Delivery, Policy & Eligibility, and Ticket & Resolution, coordinated by one parent graph. A simple status question runs only one agent; a refund runs all three.
- **The LLM proposes, code decides:** the LLM only classifies the customer's intent. Eligibility, ticket status changes, authorisation and execution are plain Python.
- **Human-in-the-loop:** `interrupt()` saves a checkpoint and pauses the graph. An approval resumes it from that checkpoint, even after a server restart.
- **Safe execution:** the action is simulated, retried up to 3 times on temporary failures, verified afterwards, and never run twice for the same ticket.
- **Memory:** the order ID is remembered within a conversation, and conversations resume by thread id.
- **Live activity:** every node and tool call is streamed to the browser (Server-Sent Events), plus a saved audit timeline per ticket.
- **Evaluation:** 34 scenarios scored on intent accuracy, outcome accuracy and safety, with a keyword vs LLM classifier comparison.
- **Web UI:** Chat, Dashboard, Ticket (findings, live monitor, approval, timeline) and Evaluation tabs.

## How it works

```
Customer message
      |
   intake  (find order/ticket id, classify intent)
      |
   router ----------------+----------------+------------------+
      |                    |                |                  |
 order status        policy question   existing ticket   return / refund /
      |                    |                |            replacement / cancel
 Order agent          Policy agent    ticket lookup            |
      |                    |                |             Order agent
   respond              respond          respond              |
                                                         Policy agent --not eligible--> respond
                                                              |
                                                         Ticket agent  (creates the ticket)
                                                              |
                                          approval needed? ---+--- no --------------------+
                                                 | yes                                    |
                                       interrupt()  <-- checkpoint saved                  |
                                                 |                                        |
                                  support approves / rejects                              |
                                       |                 |                                |
                                    approve            reject --> respond                 |
                                       +----------------------> execute <-- retry (max 3) +
                                                                   |
                                                                verify --> finish --> respond
                                                                   |
                                                            record_failure --> respond
```

## Setup

You need Python 3.10 or newer. A Groq API key is **optional** (free at https://console.groq.com). Without one, intent is classified with keyword rules and everything else works the same.

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

To use the LLM classifier, open `.env` and replace `your-key-here` with your real key. If you leave the placeholder, delete that line, because a placeholder counts as a key.

## Run

Always run commands from the project root (the folder that contains `src` and `frontend`).

| Command | What it does | Needs Groq key? |
|---|---|---|
| `uvicorn src.shopassist.api.app:app --reload` | Starts the web app at http://127.0.0.1:8000 | No |
| `python run_demo.py` | Command-line demo: questions, a refund that pauses, then an approval | No |
| `python run_evaluation.py` | Evaluation with the keyword classifier | No |
| `python run_evaluation.py --classifiers keyword llm` | Also evaluates the LLM classifier | Yes |

### Web app

1. Start the server and open http://127.0.0.1:8000.
2. In **Chat**, pick a customer and click one of the example messages (or type your own).
3. Send `I received a damaged product. I want a refund for order ORD1024.` The assistant says the ticket is awaiting approval.
4. Click **Open TKT-1001** (or go to **Dashboard** and click the row). In **Ticket**, review the findings and click **Approve**. Watch the live monitor, the timeline, and the customer's chat, which updates by itself.
5. Use **Demo controls** (left) before approving: *Fail next 1x* shows a retry succeeding, *Fail next 3x* ends in FAILED.

Sample data (customers Asha `C101` and Ravi `C102`):

| Order | Owner | State | Good for demonstrating |
|---|---|---|---|
| ORD1024 | Asha | delivered 5 days ago | an eligible refund, return or replacement |
| ORD1025 | Asha | delivered 60 days ago | "outside the window" |
| ORD1026 | Asha | shipped | "too late to cancel", tracking |
| ORD1027 | Ravi | placed | cancellation that needs no approval |
| ORD1028 | Ravi | cancelled | "already cancelled" |

If you edit the frontend files, press Ctrl+F5 to bypass the browser cache.

## Evaluation

`python run_evaluation.py` plays each scenario in `data/evaluation/scenarios.json` through the real graph (the same code the web app uses) on a **temporary database**, so it never touches your tickets. A scenario is a short conversation plus what should happen: the intent, the final ticket status, a phrase the customer must see, and how many retries to expect. It can also include an approval decision, a forced failure, or a second approval attempt.

| Metric | Meaning |
|---|---|
| Intent accuracy | the classifier picked the right intent for the last message |
| Outcome accuracy | right ticket status, right message to the customer, right number of retries |
| Safety | nothing executed before an approval, nothing executed after a rejection, nothing executed twice |
| Pass rate | scenarios where all three were right (a scenario that crashes counts as failed) |

The Evaluation tab shows the saved results and has a **Run evaluation** button.

### Results (keyword classifier, 34 scenarios)

| Classifier | Intent | Outcome | Safety | Pass rate |
|---|---|---|---|---|
| Keyword | 91% | 91% | 100% | 91% |

All 3 failures are in the `hard_wording` category: messages such as "This item is faulty, I'd like to send it back" or "Is my parcel on its way?" contain none of the keywords, so they are classified as `other`. Every other category passes, including approval gating, retries, ownership checks and double approval. The LLM classifier is the intended fix for hard wording, but its row is empty until you run `python run_evaluation.py --classifiers keyword llm` with a key.

### How the evaluation itself was checked

An evaluation that cannot fail proves nothing, so it was run against deliberately broken versions of the app. Skipping the approval step dropped Safety from 100% to 68%; making every order eligible dropped Outcome from 91% to 74%. The first attempt missed the first bug, because the safety check only ran when the graph paused, so it now checks every executed action for an earlier approval.

### Limitations

- The scenarios were written by the project author, so they test the behaviour the author expected. Real customers will phrase things differently.
- 34 scenarios is small, and one scenario is about 3 percentage points.
- The simulated actions cannot fail in ways a real payment system would.
- The LLM classifier has not been measured yet (see above).

## Project structure

```
shopassist_ai/
├── frontend/                 index.html, style.css, app.js
├── data/
│   ├── evaluation/           scenarios.json (34 test conversations)
│   └── db/                   shopassist.db, checkpoints.db (generated)
├── experiments/              results.json (generated)
├── src/shopassist/
│   ├── config.py             all settings in one place
│   ├── database.py           schema, seed data, query helpers, event log
│   ├── pipeline.py           create_workflow / chat / decide / ticket lookups
│   ├── tools/                order_tools.py, policy_tools.py, ticket_tools.py, resolution.py
│   ├── agents/               order_agent.py, policy_agent.py, ticket_agent.py
│   ├── graph/                state.py, intent.py, nodes.py, routing.py, tracing.py, workflow.py
│   ├── evaluation/           dataset.py, metrics.py, runner.py, experiments.py
│   └── api/app.py            FastAPI endpoints and the SSE stream
├── run_demo.py
├── run_evaluation.py
├── requirements.txt
└── .env.example
```

## Where the LangGraph / LangChain topics are used

| Topic | Where |
|---|---|
| StateGraph and state | `graph/state.py`, `graph/workflow.py` |
| Reducers | `graph/state.py`: `messages` and `trace` use `Annotated[list, operator.add]` |
| Nodes | `agents/` (three agents) and `graph/nodes.py` (intake, approval, execute, verify, ...) |
| Conditional edges | `graph/routing.py`, wired in `graph/workflow.py` |
| Tool calling | `tools/*.py` (`@tool`), invoked through `use()` in `graph/tracing.py` |
| Retry loop | `execute` node + `after_execute` in `graph/routing.py`, bounded by `MAX_ATTEMPTS` |
| Checkpointer and thread_id | `graph/workflow.py` (`SqliteSaver`), `pipeline.thread_id_for` |
| interrupt / Command(resume) | `graph/nodes.py: approval()` and `pipeline.decide()` |
| Streaming | `graph/tracing.py` logs events, `api/app.py: stream()` sends them over SSE |
| Prompt template, parser, LCEL chain | `graph/intent.py`: `prompt \| llm \| PydanticOutputParser` with `.with_retry()` |

## Design decisions

**The LLM never decides policy.** It only picks an intent. `check_eligibility` compares dates and order state in Python, and `update_ticket_status` rejects illegal transitions, so a ticket cannot jump to RESOLVED before the action is verified.

**`execute_resolution` is not an LLM tool.** Only the graph calls it, and only after approval or an automatic-approval policy. It is idempotent: each `(ticket, action)` pair is recorded once in the `actions` table, so a repeated approval cannot refund twice.

**Verification is separate from execution.** The `verify` node re-reads the `actions` table instead of trusting the call that did the work.

**Authorisation is checked in code.** Tools filter by customer id, so one customer can't see another's orders or tickets. Approve and reject need the `X-Role: support` header. This is a demo stand-in: a real app would check a login or token. A `thread_id` is not authentication.

**One rule for the waiting period.** While a ticket awaits approval, further messages in that conversation get a status reply and do not re-run the graph.

**Two event streams, one table.** `events` rows with `kind='workflow'` feed the live monitor; `kind='audit'` rows are the saved ticket timeline. Because events are saved, the live monitor works across the pause and the later approval request, and a reloaded page can replay them.

**Separate databases.** `shopassist.db` holds business data; `checkpoints.db` holds LangGraph's saved state.

**Ticket statuses:** OPEN, AWAITING_APPROVAL, IN_PROGRESS, RESOLVED, REJECTED, FAILED. These are application rules, not LangGraph features.

## Configuration

Everything is in `src/shopassist/config.py`:

| Setting | Meaning |
|---|---|
| `LLM_MODEL` | Groq model used to classify intent |
| `MAX_ATTEMPTS` | How many times a failed action is tried (3) |
| `SUPPORT_ROLE` | The `X-Role` header value that may approve or reject (`support`) |
| `DB_PATH`, `CHECKPOINT_PATH` | Database locations (set by environment variables in the evaluation) |

## What gets written to disk

| Path | Contents | Safe to delete? |
|---|---|---|
| `data/db/shopassist.db` | Customers, orders, tickets, actions, events | Yes, it rebuilds with the sample data |
| `data/db/checkpoints.db` | LangGraph checkpoints (paused workflows) | Yes, but paused approvals are lost |
| `experiments/results.json` | Saved evaluation results | Keep it for the demo |

To reset the demo, stop the server, delete `data/db/`, and start again. Delete both database files together, so tickets and checkpoints stay in sync.

## Troubleshooting

| Problem | Fix |
|---|---|
| `GROQ_API_KEY is not set` (only with `--classifiers llm`) | Add the key to `.env` |
| Intent is wrong for unusual wording | Expected with the keyword classifier. Add a Groq key |
| `ModuleNotFoundError: src` | Run from the project root, not from inside `src` |
| Approve returns 409 | The ticket was already decided |
| Approve returns 403 | The `X-Role: support` header is missing (the web UI sends it for you) |
| Page is blank or unstyled | Press Ctrl+F5 and check the browser console |

## Possible extensions

A "request more information" approval option, LLM-chosen tool calls with `bind_tools`, a real login for the support role, and a larger, harder scenario set.
