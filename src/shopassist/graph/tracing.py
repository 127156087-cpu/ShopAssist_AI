"""Helpers that turn every node and tool call into a live workflow event (this feeds the SSE panel)."""
from langchain_core.runnables import RunnableConfig

from src.shopassist import database


def traced(name: str):
    """Decorator: log when a node starts and finishes, and add it to the trace."""
    def decorator(function):
        def wrapper(state, config: RunnableConfig):
            thread_id = config["configurable"]["thread_id"]
            database.log_event(thread_id, state.get("ticket_id"), name, "started")
            try:
                update = function(state, thread_id)
            except Exception as error:
                database.log_event(thread_id, state.get("ticket_id"), name, "failed", str(error))
                raise
            message = update.pop("event_msg", "")
            database.log_event(thread_id, update.get("ticket_id") or state.get("ticket_id"), name, "completed", message)
            update["trace"] = [name]
            return update
        return wrapper
    return decorator


def use(tool, thread_id: str, /, **arguments):  # positional-only, so tools may have their own 'thread_id' argument
    """Call a LangChain tool and log the call, whether it succeeds or fails."""
    try:
        result = tool.invoke(arguments)
    except Exception as error:
        database.log_event(thread_id, arguments.get("ticket_id"), tool.name, "tool_failed", str(error))
        raise
    database.log_event(thread_id, arguments.get("ticket_id"), tool.name, "tool_ok", str(result)[:140])
    return result
