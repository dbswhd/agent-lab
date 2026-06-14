import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_lab.graph import run_topic
from agent_lab.invoke import ensure_ready, model_name, provider
from agent_lab.session import save_session


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="agent-lab",
        description="Run Planner → Critic → Scribe and save plan.md to sessions/",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the 3-node graph on a topic")
    run_p.add_argument("topic", help='e.g. "C4of5 overlay on KR strategy"')
    run_p.add_argument(
        "--sessions-dir",
        type=Path,
        default=None,
        help="Override sessions output directory",
    )

    serve_p = sub.add_parser("serve", help="Run Agent Lab API server")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    serve_p.add_argument(
        "--daemon",
        action="store_true",
        help="Enable mission scheduler background thread (sets AGENT_LAB_MISSION_SCHEDULER=1)",
    )
    serve_p.add_argument(
        "--reload",
        action="store_true",
        help="Uvicorn auto-reload (dev only)",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        topic = args.topic.strip()
        if not topic:
            print("error: topic must not be empty", file=sys.stderr)
            return 1
        try:
            ensure_ready()
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"Running graph on: {topic}")
        print(f"Backend: {provider()} ({model_name()})\n")
        try:
            state = run_topic(topic)
            folder = save_session(state, base=args.sessions_dir)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            err = str(e)
            print(f"error: {e}", file=sys.stderr)
            if "insufficient_quota" in err or "exceeded your current quota" in err:
                print(
                    "\nhint: Platform API quota — ChatGPT Plus ≠ API billing. "
                    "Use AGENT_LAB_PROVIDER=codex (ChatGPT login via `codex login`) "
                    "or AGENT_LAB_PROVIDER=anthropic in .env.",
                    file=sys.stderr,
                )
            return 1

        print(f"Saved session → {folder}")
        print(f"  plan.md       ({(folder / 'plan.md').stat().st_size} bytes)")
        print(f"  transcript.md")
        print(f"  meta.json")
        return 0

    if args.command == "serve":
        if args.daemon:
            os.environ["AGENT_LAB_MISSION_SCHEDULER"] = "1"
        import uvicorn

        uvicorn.run(
            "app.server.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
