#!/usr/bin/env python3
"""Build and run the mapped Zephyr boards against LabWired.

This is intentionally a local validation tool, not part of the west command
surface. It records one JSON result per board so long runs can be resumed or
inspected without scrolling terminal logs.
"""

from __future__ import annotations

import argparse
import json
import os
import selectors
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import labwired_sim


@dataclass(frozen=True)
class Result:
    board: str
    system: str
    status: str
    detail: str
    elapsed_s: float | None


def expected_hello(board: str) -> str:
    return f"Hello World! {board}"


def classify_run_result(*, board: str, returncode: int, output: str) -> Result:
    expected = expected_hello(board)
    if expected in output:
        return Result(board, "", "run_pass", f"observed UART: {expected}", None)
    tail = short_detail(output)
    suffix = f"\noutput tail:\n{tail}" if tail else "\noutput tail: <empty>"
    if returncode == 124:
        return Result(board, "", "run_fail", f"timeout; missing expected UART: {expected}{suffix}", None)
    return Result(
        board,
        "",
        "run_fail",
        f"exit {returncode}; missing expected UART: {expected}{suffix}",
        None,
    )


def summarize(rows: list[Result]) -> dict[str, int]:
    return dict(sorted(Counter(row.status for row in rows).items()))


def board_slug(board: str) -> str:
    return board.replace("/", "_").replace("@", "_at_")


def short_detail(output: str, limit: int = 900) -> str:
    text = "\n".join(line for line in output.splitlines() if line.strip())
    return text[-limit:] if len(text) > limit else text


def run_build(args: argparse.Namespace, board: str) -> tuple[bool, str, float]:
    build_dir = Path(args.build_root) / board_slug(board)
    cmd = [
        args.west,
        "build",
        "-p",
        "always",
        "-b",
        board,
        args.sample,
        "-d",
        str(build_dir),
    ]
    env = os.environ.copy()
    if args.toolchain_variant:
        env["ZEPHYR_TOOLCHAIN_VARIANT"] = args.toolchain_variant
    if args.gnuarmemb_toolchain_path:
        env["GNUARMEMB_TOOLCHAIN_PATH"] = args.gnuarmemb_toolchain_path
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=args.zephyr_workspace,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.build_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        return False, f"build timeout after {args.build_timeout}s\n{short_detail(output)}", time.monotonic() - started
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        return False, f"build exit {proc.returncode}\n{short_detail(proc.stdout)}", elapsed
    elf = build_dir / "zephyr" / "zephyr.elf"
    if not elf.exists():
        return False, f"build succeeded but ELF missing: {elf}", elapsed
    return True, str(elf), elapsed


def run_labwired(args: argparse.Namespace, board: str, system: Path, elf: Path) -> tuple[int, str, float]:
    cmd = labwired_sim.build_argv(args.labwired_bin, elf, system, args.max_steps)
    started = time.monotonic()
    # The simulator writes the firmware's UART console to stdout and its own
    # tracing logs to stderr. Keep the streams separate so an interleaved INFO
    # line never splits the console string we match on; stderr is kept only for
    # the failure diagnostic tail.
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    assert proc.stdout is not None and proc.stderr is not None
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ, "out")
    sel.register(proc.stderr, selectors.EVENT_READ, "err")
    output: list[str] = []
    errlog: list[str] = []
    expected = expected_hello(board)
    returncode = 124

    def finish(code: int) -> tuple[int, str, float]:
        # UART (stdout) first so classify_run_result matches on the console;
        # a bounded stderr tail follows for fault/diagnostic context.
        combined = "".join(output)
        if errlog:
            combined += "\n--- sim log (stderr) tail ---\n" + "".join(errlog)[-1500:]
        return code, combined, time.monotonic() - started

    try:
        while True:
            if time.monotonic() - started > args.run_timeout:
                proc.terminate()
                break
            open_streams = False
            for key, _ in sel.select(timeout=0.2):
                line = key.fileobj.readline()
                if line == "":
                    sel.unregister(key.fileobj)
                    continue
                open_streams = True
                if key.data == "err":
                    errlog.append(line)
                    continue
                output.append(line)
                if expected in line:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                    return finish(0)
            polled = proc.poll()
            if polled is not None and not open_streams:
                return finish(polled)
    finally:
        sel.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    return finish(returncode)


def validate_one(args: argparse.Namespace, board: str, system_name: str) -> Result:
    started = time.monotonic()
    system = Path(args.systems_dir) / system_name
    if not system.exists():
        return Result(board, system_name, "system_missing", f"manifest missing: {system}", 0.0)

    built, build_detail, _build_elapsed = run_build(args, board)
    if not built:
        return Result(board, system_name, "build_fail", build_detail, time.monotonic() - started)

    returncode, output, _run_elapsed = run_labwired(args, board, system, Path(build_detail))
    result = classify_run_result(board=board, returncode=returncode, output=output)
    return Result(board, system_name, result.status, result.detail, time.monotonic() - started)


def select_boards(mapping: dict[str, str], only: list[str], limit: int | None) -> list[tuple[str, str]]:
    rows = sorted(mapping.items())
    if only:
        wanted = set(only)
        rows = [(board, system) for board, system in rows if board in wanted]
    if limit is not None:
        rows = rows[:limit]
    return rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parent.parent
    parser.add_argument("--board-map", default=str(repo / "boards.map"))
    parser.add_argument("--zephyr-workspace", default="/home/andrii/zephyrproject")
    parser.add_argument("--sample", default="/home/andrii/zephyrproject/zephyr/samples/hello_world")
    parser.add_argument("--west", default="/home/andrii/zephyrproject/.venv/bin/west")
    parser.add_argument("--labwired-bin", default=os.environ.get("LABWIRED_BIN", "labwired"))
    parser.add_argument("--systems-dir", default=os.environ.get("LABWIRED_SYSTEMS_DIR"))
    parser.add_argument("--build-root", default="/tmp/labwired-zephyr-matrix")
    parser.add_argument("--results", default="/tmp/labwired-zephyr-matrix/results.jsonl")
    parser.add_argument("--toolchain-variant", default=os.environ.get("ZEPHYR_TOOLCHAIN_VARIANT"))
    parser.add_argument("--gnuarmemb-toolchain-path", default=os.environ.get("GNUARMEMB_TOOLCHAIN_PATH"))
    parser.add_argument("--max-steps", type=int, default=5_000_000)
    parser.add_argument("--build-timeout", type=float, default=180.0)
    parser.add_argument("--run-timeout", type=float, default=90.0)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only", action="append", default=[])
    return parser.parse_args(argv)


def write_result(out, result: Result) -> None:
    out.write(json.dumps(asdict(result), sort_keys=True) + "\n")
    out.flush()


def print_result(result: Result) -> None:
    elapsed = f"{result.elapsed_s:.1f}s" if result.elapsed_s is not None else "n/a"
    print(f"  {result.board}: {result.status} ({elapsed}) {result.detail.splitlines()[0]}", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.systems_dir:
        print("--systems-dir or LABWIRED_SYSTEMS_DIR is required", file=sys.stderr)
        return 2
    mapping = labwired_sim.load_board_map(args.board_map)
    boards = select_boards(mapping, args.only, args.limit)
    results_path = Path(args.results)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[Result] = []
    with results_path.open("w", encoding="utf-8") as out:
        if args.jobs == 1:
            for index, (board, system) in enumerate(boards, 1):
                print(f"[{index}/{len(boards)}] {board} -> {system}", flush=True)
                result = validate_one(args, board, system)
                rows.append(result)
                write_result(out, result)
                print_result(result)
        else:
            print(f"running {len(boards)} boards with {args.jobs} workers", flush=True)
            with ThreadPoolExecutor(max_workers=args.jobs) as executor:
                futures = {
                    executor.submit(validate_one, args, board, system): (index, board, system)
                    for index, (board, system) in enumerate(boards, 1)
                }
                for future in as_completed(futures):
                    index, board, system = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001 - keep matrix moving.
                        result = Result(board, system, "validator_error", repr(exc), None)
                    rows.append(result)
                    write_result(out, result)
                    print(f"[{index}/{len(boards)}] {board} -> {system}", flush=True)
                    print_result(result)
    print(json.dumps({"total": len(rows), "summary": summarize(rows), "results": str(results_path)}, sort_keys=True))
    return 0 if rows and all(row.status == "run_pass" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
