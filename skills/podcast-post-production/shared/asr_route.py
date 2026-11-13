"""Plan transcription and record attempts without contacting providers."""
import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .guards import guard_path
from .package_identity import digest

ROUTES = {
    "bailian-cli": ("qwen-audio-3.1-asr-flash-filetrans", "bl speech recognize"),
    "stepfun": ("stepaudio-2.5-asr", "StepFun ASR"),
    "bailian-native": ("qwen-audio-3.1-asr-flash-filetrans", "DashScope native API"),
}
LABEL = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}\Z")


def label(value, name):
    if not isinstance(value, str) or not LABEL.fullmatch(value):
        raise ValueError("Invalid " + name)
    return value


def integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid " + name)
    return value


def ranges(items, frames):
    seen = set()
    output = []
    for item in items:
        key = label(item["id"], "segment ID")
        start = integer(item["start_frame"], "start frame")
        end = integer(item["end_frame"], "end frame")
        if key in seen or not start < end <= frames:
            raise ValueError("Invalid or repeated segment: " + key)
        seen.add(key)
        output.append({"id": key, "start_frame": start, "end_frame": end})
    return output


def plan(spec, directory):
    if spec["purpose"] not in ("primary", "review") or spec["mode"] not in ("solo", "multitrack", "subtitles"):
        raise ValueError("Unknown transcription mode or purpose")
    source = (directory / spec["source"]).resolve(strict=True)
    source_hash = digest(source)
    if source_hash != spec["source_sha256"]:
        raise ValueError("Source hash differs")
    rate = integer(spec["sample_rate"], "sample rate")
    frames = integer(spec["frames"], "frame count")
    if not rate or not frames:
        raise ValueError("Source clock must be positive")
    timeline = label(spec["timebase"], "timebase")
    parameters = spec.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("Parameters must be an object")
    # Parameters form part of the cache identity; omit potentially private contents from reports.
    parameter_hash = hashlib.sha256(json.dumps(parameters, sort_keys=True, separators=(",", ":"),
                                              allow_nan=False).encode()).hexdigest()
    purpose = spec["purpose"]
    route = next((x for x in (spec.get("explicit_route"), spec.get("project_routes", {}).get(purpose),
                             spec.get("host_routes", {}).get(purpose)) if x is not None), None)
    entries = ranges(spec["segments"], frames)
    if not entries:
        raise ValueError("At least one segment is required")
    result = {"status": "SELECT_PROVIDER", "route": None, "segments": entries,
              "source_sha256": source_hash, "sample_rate": rate, "frames": frames, "timebase": timeline,
              "purpose": purpose, "mode": spec["mode"], "model_calls": 0, "uploads": 0}
    if route is None:
        result["choices"] = ["bailian-cli", "stepfun"]
        return result
    provider = route["provider"]
    if provider not in ROUTES:
        raise ValueError("Unknown provider")
    default_model, entrypoint = ROUTES[provider]
    model = label(route.get("model", default_model), "model")
    billing = label(route["billing_route"], "billing route")
    region = label(route.get("region", "UNKNOWN"), "region")
    binding = {"source_sha256": source_hash, "timebase": timeline, "sample_rate": rate, "frames": frames,
               "parameters_sha256": parameter_hash, "provider": provider, "model": model,
               "billing_route": billing, "region": region}
    result["route"] = {**binding, "entrypoint": entrypoint}

    cache = {}
    for item in spec.get("cache", []):
        key = item["id"]
        if key in cache:
            raise ValueError("Repeated cache segment: " + key)
        cache[key] = item
    for item in entries:
        old = cache.get(item["id"], {})
        raw = None
        matched = old.get("binding") == {**binding, **item}
        if old.get("status") == "complete" and matched:
            try:
                raw = (directory / old["response"]).resolve(strict=True)
                if not raw.is_file() or digest(raw) != old["response_sha256"]:
                    raw = None
            except (OSError, KeyError):
                raw = None
        item["action"] = ("reuse" if raw else
                          "pending" if matched and old.get("status") in ("pending", "unknown") else
                          "retry" if matched and old.get("status") == "failed" else "submit")
    if all(item["action"] == "reuse" for item in entries):
        result["status"] = "CACHE_HIT"
        return result
    submit = [item for item in entries if item["action"] in ("submit", "retry")]
    if not submit:
        result["status"] = "BLOCKED"
        result["reason"] = "Reconcile pending provider requests before submitting again"
        return result
    submit_frames = sum(item["end_frame"] - item["start_frame"] for item in submit)
    result["submitted_seconds"] = submit_frames / rate
    result["estimated_cost_cny"] = None
    # A price is optional evidence, never an inferred account entitlement.
    price = spec.get("verified_hourly_price_cny")
    if price is not None:
        try:
            amount = Decimal(str(price))
            if not amount.is_finite() or amount < 0 or not spec.get("price_checked_date"):
                raise ValueError("Invalid verified price")
            result["estimated_cost_cny"] = str(amount * submit_frames / rate / 3600)
        except (InvalidOperation, TypeError):
            raise ValueError("Invalid verified price") from None
    block = None
    previously_submitted = integer(spec.get("prior_review_submitted_frames", 0), "prior review frames")
    if purpose == "review" and (previously_submitted + submit_frames) * 10 > frames and spec.get("expanded_review_authorized") is not True:
        block = "Review exceeds 10% of source; expanded scope must be authorized"
    elif provider.startswith("bailian") and spec.get("cli_capability") != "supported":
        if provider == "bailian-cli":
            block = "Bailian CLI capability is missing or unverified: " + str(spec.get("cli_gap", "check model and required parameters"))
        elif spec.get("cli_capability") != "missing" or not spec.get("cli_gap") or spec.get("native_authorized") is not True:
            block = "Native API requires a documented CLI capability gap and explicit authorization"
    elif provider == "bailian-native":
        block = "Use the CLI when it supports the task"
    if not block and spec.get("upload_authorized") is not True:
        block = "Upload authorization is missing"
    result["status"] = "BLOCKED" if block else "READY_FOR_AUTHORIZED_HOST"
    if block:
        result["reason"] = block
    return result


def optional_number(value, name):
    if value is None:
        return None
    return integer(value, name)


def money(value):
    if value is None:
        return None
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid cost")
    return str(amount)


def ledger_row(planned, attempt):
    if planned["status"] != "READY_FOR_AUTHORIZED_HOST":
        raise ValueError("Only a ready plan may record an attempted submission")
    key = attempt["segment_id"]
    matches = [item for item in planned["segments"] if item["id"] == key and item["action"] in ("submit", "retry")]
    if len(matches) != 1:
        raise ValueError("Attempt is outside the submitted segment plan")
    item = matches[0]
    binding = planned["route"]
    state = attempt["status"]
    if state not in ("complete", "failed", "pending", "unknown"):
        raise ValueError("Invalid attempt status")
    count = integer(attempt["attempt"], "attempt number")
    if count < 1:
        raise ValueError("Attempt numbers start at one")
    if state == "complete" and not attempt.get("request_id"):
        raise ValueError("Completed attempt requires provider request ID")
    for field in ("timestamp", "request_id", "price_checked_date", "quota_verification"):
        if attempt.get(field) is not None:
            label(attempt[field], field)
    return {**{k: v for k, v in binding.items() if k != "entrypoint"}, **item,
            "timestamp": label(attempt["timestamp"], "timestamp"),
            "submitted_seconds": (item["end_frame"] - item["start_frame"]) / binding["sample_rate"],
            "request_id": attempt.get("request_id"), "attempt": count, "status": state,
            "input_tokens": optional_number(attempt.get("input_tokens"), "input tokens"),
            "output_tokens": optional_number(attempt.get("output_tokens"), "output tokens"),
            "quota_verification": attempt.get("quota_verification", "UNKNOWN"),
            "price_checked_date": attempt.get("price_checked_date"),
            "estimated_cost_cny": money(attempt.get("estimated_cost_cny")),
            "actual_cost_cny": money(attempt.get("actual_cost_cny"))}


def append_ledger(directory, row, *inputs):
    path = guard_path(Path(directory) / "asr-cost-ledger.jsonl", *inputs)
    encoded = (json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n").encode()
    # One append operation, including the newline, prevents interleaved JSONL rows.
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if os.fstat(descriptor).st_nlink != 1:
            raise ValueError("Ledger must be an independent file")
        if os.write(descriptor, encoded) != len(encoded):
            raise OSError("Incomplete ledger append")
    finally:
        os.close(descriptor)
    return path
