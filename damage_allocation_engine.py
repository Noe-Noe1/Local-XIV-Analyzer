#!/usr/bin/env python3
"""P0-9 damage allocation for Local XIV Analyzer.

Percentage damage buffs are reversed multiplicatively. When multiple percentage
buffs overlap, their gain is divided with an exact Shapley allocation. Crit/DH
rate buffs are stored as explicitly low-confidence expected-value estimates.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

SCHEMA = """
create table if not exists allocation_runs(
 run_id integer primary key autoincrement,
 created_at text default current_timestamp,
 rules_version text, fights integer, events integer,
 allocated_damage real, warnings integer);
create table if not exists damage_allocations(
 run_id integer, report_hash text, fight_id integer, event_seq integer,
 source_actor text, buff_owner text, buff_id text, buff_kind text,
 observed_damage real, base_damage real, allocated_damage real,
 method text, confidence text, evidence_json text);
create table if not exists dps_metrics(
 run_id integer, report_hash text, fight_id integer, actor_hash text,
 duration_ms real, raw_damage real, dps real, external_gain real,
 own_contribution real, single_target_gain real,
 rdps real, ndps real, adps real, cdps real,
 confidence text, warnings text,
 primary key(run_id, report_hash, fight_id, actor_hash));
"""
DEFAULT_RULES = {"version": "p0-9.rules.1", "buffs": {}}


def load_rules(path=None):
    if not path:
        return DEFAULT_RULES
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not data.get("version") or not isinstance(data.get("buffs"), dict):
        raise ValueError("Invalid allocation rules")
    return data


def event_type(event):
    return str(event.get("type", "")).lower()


def timestamp(event):
    return float(event.get("timestamp") or 0)


def actor(event, key):
    return str(event.get(key) or "")


def ability_id(event):
    value = event.get("abilityGameID")
    if value is None and isinstance(event.get("ability"), dict):
        value = event["ability"].get("guid")
    return str(value or "unknown")


def status_windows(events, rules, fight_end):
    opened = {}
    windows = defaultdict(list)
    for seq, event in enumerate(events):
        kind = event_type(event)
        buff_id = ability_id(event)
        target = actor(event, "targetID")
        owner = actor(event, "sourceID")
        time = timestamp(event)
        if buff_id not in rules["buffs"] or not target:
            continue
        key = (target, buff_id, owner)
        if kind in {"applybuff", "applydebuff", "refreshbuff", "refreshdebuff"}:
            if key in opened:
                old_id, old_owner, start, natural_end, old_seq = opened.pop(key)
                windows[target].append((old_id, old_owner, start, min(time, natural_end), old_seq))
            duration = float(event.get("duration") or 0)
            natural_end = min(time + duration, fight_end) if duration else fight_end
            opened[key] = (buff_id, owner, time, natural_end, seq)
        elif kind in {"removebuff", "removedebuff"} and key in opened:
            old_id, old_owner, start, natural_end, old_seq = opened.pop(key)
            windows[target].append((old_id, old_owner, start, min(time, natural_end), old_seq))
    for (target, _, _), item in opened.items():
        windows[target].append(item)
    return windows


def allocate_percentage(observed, active, rules):
    buffs = []
    for buff_id, owner, *_ in active:
        rule = rules["buffs"][buff_id]
        value = float(rule.get("value", 0))
        if rule.get("kind") == "damage_percent" and value > 0:
            buffs.append((buff_id, owner, value, rule))
    if not buffs:
        return observed, []

    base = observed / math.prod(1 + buff[2] for buff in buffs)
    gain = observed - base
    count = len(buffs)
    allocations = []
    for index, (buff_id, owner, value, rule) in enumerate(buffs):
        contribution = 0.0
        others = [i for i in range(count) if i != index]
        for size in range(count):
            for subset in itertools.combinations(others, size):
                before = base * math.prod(1 + buffs[i][2] for i in subset)
                weight = math.factorial(size) * math.factorial(count - size - 1) / math.factorial(count)
                contribution += weight * (before * (1 + value) - before)
        allocations.append([buff_id, owner, contribution, rule, "exact_percentage", "high"])

    allocated = sum(item[2] for item in allocations)
    scale = gain / allocated if allocated else 1.0
    for item in allocations:
        item[2] *= scale
    return base, allocations


def estimate_crit_dh(observed, event, active, rules):
    critical = bool(event.get("critical") or event.get("isCritical") or event.get("hitType") in (2, 4))
    direct = bool(event.get("directHit") or event.get("isDirectHit") or event.get("hitType") in (3, 4))
    result = []
    for buff_id, owner, *_ in active:
        rule = rules["buffs"][buff_id]
        kind = rule.get("kind")
        if kind not in {"crit_rate", "direct_rate"}:
            continue
        if kind == "crit_rate" and not critical:
            continue
        if kind == "direct_rate" and not direct:
            continue
        rate = float(rule.get("value", 0))
        bonus = float(rule.get("bonus_multiplier", 0.4 if kind == "crit_rate" else 0.25))
        estimate = observed * (rate * bonus) / (1 + rate * bonus)
        result.append([buff_id, owner, estimate, rule, "expected_value_estimate", "low"])
    return result


def run(db_path, rules_path=None):
    db = sqlite3.connect(db_path)
    db.executescript(SCHEMA)
    rules = load_rules(rules_path)
    run_id = db.execute(
        "insert into allocation_runs(rules_version,fights,events,allocated_damage,warnings) values(?,0,0,0,0)",
        (rules["version"],),
    ).lastrowid

    fight_count = event_count = warning_count = 0
    allocated_total = 0.0
    fights = db.execute("select report_hash,fight_id,start,end from fights").fetchall()
    for report_hash, fight_id, start, end in fights:
        events = []
        rows = db.execute(
            "select payload from events where report_hash=? and fight_id=? order by seq",
            (report_hash, fight_id),
        )
        for seq, (payload,) in enumerate(rows):
            try:
                event = json.loads(payload)
                event["_seq"] = seq
                events.append(event)
            except Exception:
                continue

        windows = status_windows(events, rules, float(end))
        raw = defaultdict(float)
        gained = defaultdict(float)
        given = defaultdict(float)
        single = defaultdict(float)
        warnings = defaultdict(set)

        for event in events:
            if event_type(event) not in {"damage", "calculateddamage"}:
                continue
            source = actor(event, "sourceID")
            observed = float(event.get("amount") or 0)
            if not source or observed <= 0:
                continue
            event_count += 1
            raw[source] += observed
            time = timestamp(event)
            active = [window for window in windows.get(source, []) if window[2] <= time < window[3]]
            base, allocations = allocate_percentage(observed, active, rules)
            allocations += estimate_crit_dh(observed, event, active, rules)
            if any(item[4] == "expected_value_estimate" for item in allocations):
                warnings[source].add("crit_dh_allocation_estimated")
                warning_count += 1

            for buff_id, owner, amount, rule, method, confidence in allocations:
                if not owner or owner == source:
                    continue
                gained[source] += amount
                given[owner] += amount
                allocated_total += amount
                if rule.get("targeting") == "single":
                    single[source] += amount
                values = (
                    run_id, report_hash, fight_id, event["_seq"], source, owner,
                    buff_id, rule.get("kind"), observed, base, amount, method,
                    confidence, json.dumps({"timestamp": time, "ability": ability_id(event)}, separators=(",", ":")),
                )
                db.execute("insert into damage_allocations values(" + ",".join("?" * len(values)) + ")", values)

        duration = max(float(end) - float(start), 1)
        for participant in set(raw) | set(given):
            dps = raw[participant] * 1000 / duration
            rdps = (raw[participant] - gained[participant] + given[participant]) * 1000 / duration
            ndps = (raw[participant] - gained[participant]) * 1000 / duration
            adps = (raw[participant] - single[participant]) * 1000 / duration
            cdps = (raw[participant] - single[participant] + given[participant]) * 1000 / duration
            values = (
                run_id, report_hash, fight_id, participant, duration, raw[participant], dps,
                gained[participant], given[participant], single[participant], rdps, ndps,
                adps, cdps, "low" if warnings[participant] else "high",
                ",".join(sorted(warnings[participant])),
            )
            db.execute("insert into dps_metrics values(" + ",".join("?" * len(values)) + ")", values)
        fight_count += 1

    db.execute(
        "update allocation_runs set fights=?,events=?,allocated_damage=?,warnings=? where run_id=?",
        (fight_count, event_count, allocated_total, warning_count, run_id),
    )
    db.commit()
    db.close()
    return {
        "run_id": run_id,
        "rules_version": rules["version"],
        "fights": fight_count,
        "damage_events": event_count,
        "allocated_damage": round(allocated_total, 3),
        "warnings": warning_count,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--rules")
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.rules), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
