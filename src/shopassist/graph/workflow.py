"""Builds the parent LangGraph workflow: intake -> router -> three agents -> approval -> execute -> verify."""
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.shopassist import config
from src.shopassist.agents.order_agent import order_agent
from src.shopassist.agents.policy_agent import policy_agent
from src.shopassist.agents.ticket_agent import ticket_agent
from src.shopassist.graph import nodes, routing
from src.shopassist.graph.state import State


def build_workflow(checkpoint_path: str | None = None):
    """Compile the graph with a SQLite checkpointer, so a paused workflow survives a server restart."""
    path = checkpoint_path or config.CHECKPOINT_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    checkpointer = SqliteSaver(sqlite3.connect(path, check_same_thread=False))

    graph = StateGraph(State)
    graph.add_node("intake", nodes.intake)
    graph.add_node("ask_info", nodes.ask_info)
    graph.add_node("order_agent", order_agent)
    graph.add_node("policy_agent", policy_agent)
    graph.add_node("ticket_agent", ticket_agent)
    graph.add_node("approval", nodes.approval)
    graph.add_node("execute", nodes.execute)
    graph.add_node("verify", nodes.verify)
    graph.add_node("finish", nodes.finish)
    graph.add_node("record_failure", nodes.record_failure)
    graph.add_node("ticket_lookup", nodes.ticket_lookup)
    graph.add_node("respond", nodes.respond)

    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", routing.route_intake, ["ask_info", "ticket_lookup", "policy_agent", "order_agent"])
    graph.add_conditional_edges("order_agent", routing.after_order, ["respond", "policy_agent"])
    graph.add_conditional_edges("policy_agent", routing.after_policy, ["respond", "ticket_agent"])
    graph.add_conditional_edges("ticket_agent", routing.after_ticket, ["approval", "execute"])
    graph.add_conditional_edges("approval", routing.after_approval, ["execute", "respond"])
    graph.add_conditional_edges("execute", routing.after_execute, ["verify", "execute", "record_failure"])
    graph.add_conditional_edges("verify", routing.after_verify, ["finish", "record_failure"])
    for name in ("ask_info", "ticket_lookup", "finish", "record_failure"):
        graph.add_edge(name, "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=checkpointer)
