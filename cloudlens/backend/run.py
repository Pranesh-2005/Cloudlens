"""Local dev launcher. Use this instead of `python -m uvicorn app.main:app` on
Windows — psycopg's async Postgres connection (used by the LangGraph
checkpointer) can't run on Windows' default ProactorEventLoop, and the policy
has to be set before uvicorn creates its event loop, which is too early for
a fix living inside app.main to take effect.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
