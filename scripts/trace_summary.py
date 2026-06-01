import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.trace import find_latest_trace, format_trace_summary, summarize_trace_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a LiteAct Agent JSONL trace")
    parser.add_argument("trace_file", nargs="?", help="Trace JSONL file. Defaults to latest trace.")
    parser.add_argument("--trace-dir", default="sessions/traces", help="Trace directory for latest lookup.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trace_file = Path(args.trace_file) if args.trace_file else find_latest_trace(args.trace_dir)
    if trace_file is None:
        raise SystemExit(f"No trace files found under {args.trace_dir}")

    print(format_trace_summary(summarize_trace_file(trace_file)))


if __name__ == "__main__":
    main()
