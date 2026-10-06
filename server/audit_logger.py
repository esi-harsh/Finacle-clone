"""
Tool call logging decorator.
Every tool execution writes an entry to finance.tool_call_log for complete traceability.
"""

import functools
import json
import time
from typing import Any, Callable
from server.db import get_writer_connection


def log_tool_call(tool_name: str) -> Callable:
    """Decorator to log tool invocation, arguments, result summary, and timing."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            session_id = kwargs.get("session_id", "default_session")
            error_code = None
            output_summary = ""
            
            # Prepare serializable input parameters
            input_data = {}
            for k, v in kwargs.items():
                if hasattr(v, "model_dump"):
                    input_data[k] = v.model_dump()
                elif hasattr(v, "isoformat"):
                    input_data[k] = v.isoformat()
                else:
                    input_data[k] = str(v)

            try:
                result = func(*args, **kwargs)
                if isinstance(result, dict):
                    output_summary = json.dumps(result)[:500]
                elif hasattr(result, "model_dump_json"):
                    output_summary = result.model_dump_json()[:500]
                else:
                    output_summary = str(result)[:500]
                return result
            except Exception as ex:
                error_code = getattr(ex, "code", "UNHANDLED_EXCEPTION")
                output_summary = f"Error: {str(ex)[:400]}"
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)
                try:
                    with get_writer_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO finance.tool_call_log 
                                  (session_id, tool, input_json, output_summary, error_code, duration_ms)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    session_id,
                                    tool_name,
                                    json.dumps(input_data),
                                    output_summary,
                                    error_code,
                                    duration_ms,
                                ),
                            )
                            conn.commit()
                except Exception as log_ex:
                    # Logging failure shouldn't mask tool execution result
                    print(f"Warning: Failed to log tool call {tool_name}: {log_ex}")

        return wrapper
    return decorator
