import json
import sqlite3
import tempfile
from pathlib import Path
from damage_allocation_engine import run

with tempfile.TemporaryDirectory() as directory:
    db_path = Path(directory) / "test.sqlite3"
    rules_path = Path(directory) / "rules.json"
    rules_path.write_text(json.dumps({
        "version": "test",
        "buffs": {"100": {"kind": "damage_percent", "value": 0.10, "targeting": "party"}},
    }), encoding="utf-8")

    db = sqlite3.connect(db_path)
    db.executescript("""
    create table fights(report_hash text,fight_id integer,start real,end real);
    create table events(report_hash text,fight_id integer,seq integer,payload text);
    """)
    db.execute("insert into fights values(?,?,?,?)", ("report", 1, 0, 10000))
    events = [
        {"type": "applybuff", "timestamp": 0, "sourceID": "owner", "targetID": "player", "abilityGameID": 100, "duration": 10000},
        {"type": "damage", "timestamp": 1000, "sourceID": "player", "targetID": "boss", "amount": 1100},
    ]
    for seq, event in enumerate(events):
        db.execute("insert into events values(?,?,?,?)", ("report", 1, seq, json.dumps(event)))
    db.commit()
    db.close()

    result = run(db_path, rules_path)
    assert round(result["allocated_damage"]) == 100
    db = sqlite3.connect(db_path)
    row = db.execute("select raw_damage,external_gain,ndps from dps_metrics where actor_hash='player'").fetchone()
    assert tuple(round(value) for value in row) == (1100, 100, 100)
    db.close()
with tempfile.TemporaryDirectory() as directory:
    db_path = Path(directory) / "technical_finish.sqlite3"
    rules_path = Path(directory) / "technical_finish_rules.json"

    rules_path.write_text(json.dumps({
        "version": "technical-finish-test",
        "buffs": {
            "1822": {
                "kind": "damage_percent",
                "value": 0.01,
                "targeting": "party",
                "action_values": {
                    "33218": 0.05
                },
                "action_match_ms": 5
            }
        },
    }), encoding="utf-8")

    db = sqlite3.connect(db_path)
    db.executescript("""
    create table fights(
        report_hash text,
        fight_id integer,
        start real,
        end real
    );
    create table events(
        report_hash text,
        fight_id integer,
        seq integer,
        payload text
    );
    """)

    db.execute(
        "insert into fights values(?,?,?,?)",
        ("report", 1, 0, 10000)
    )

    events = [
        {
            "type": "damage",
            "timestamp": 0,
            "sourceID": "owner",
            "targetID": "boss",
            "abilityGameID": 33218,
            "amount": 1000
        },
        {
            "type": "applybuff",
            "timestamp": 0,
            "sourceID": "owner",
            "targetID": "player",
            "abilityGameID": 1822,
            "duration": 20000
        },
        {
            "type": "damage",
            "timestamp": 1000,
            "sourceID": "player",
            "targetID": "boss",
            "amount": 1050
        },
    ]

    for seq, event in enumerate(events):
        db.execute(
            "insert into events values(?,?,?,?)",
            ("report", 1, seq, json.dumps(event))
        )

    db.commit()
    db.close()

    result = run(db_path, rules_path)
    assert round(result["allocated_damage"]) == 50
print("PASS")
