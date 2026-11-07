#!/usr/bin/env python3
"""A fake probe agent for the tests: one JSON request in, one JSON plan out."""

import argparse
import json
import sys
import time


def plan(task):
    text = task.lower()
    if "bad" in text:
        return None
    if "empty" in text:
        return []
    if "unknown" in text:
        return [
            {"tool": "nope", "arguments": {}},
            {"tool": "echo", "arguments": {"text": "hello"}},
        ]
    if "sequence" in text:
        return [
            {"tool": "fail", "arguments": {}},
            {"tool": "echo", "arguments": {"text": "hello"}},
        ]
    if "fail" in text:
        return [{"tool": "fail", "arguments": {}}]
    if "long" in text:
        return [{"tool": "echo", "arguments": {"text": "x" * 5000}}]
    return [{"tool": "echo", "arguments": {"text": "hello"}}]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--malformed", action="store_true")
    parser.add_argument("--no-calls", action="store_true")
    parser.add_argument("--calls-not-list", action="store_true")
    parser.add_argument("--bad-tool", action="store_true")
    parser.add_argument("--bad-arguments", action="store_true")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--capture")
    args = parser.parse_args(argv)

    sys.stderr.write("fake agent starting\n")
    sys.stderr.flush()
    request = json.load(sys.stdin)
    if args.capture:
        with open(args.capture, "w", encoding="utf-8") as handle:
            json.dump(request, handle, sort_keys=True)
    if args.silent:
        time.sleep(30)
        return 0
    if args.exit_code:
        sys.stderr.write("fake agent failed\n")
        return args.exit_code
    if args.malformed:
        sys.stdout.write("not json " + "x" * 5000 + "\n")
        return 0

    if args.no_calls:
        response = {}
    elif args.calls_not_list:
        response = {"calls": {}}
    elif args.bad_tool:
        response = {"calls": [{"tool": 5, "arguments": {}}]}
    elif args.bad_arguments:
        response = {"calls": [{"tool": "echo", "arguments": []}]}
    else:
        calls = plan(str(request.get("task", "")))
        if calls is None:
            sys.stdout.write("not json " + "x" * 5000 + "\n")
            return 0
        response = {"calls": calls}

    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
