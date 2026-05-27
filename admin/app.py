import json
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
PROXY_DIR = BASE_DIR / "proxy"
AGENTS_DIR = BASE_DIR / "agents"
DB_PATH = PROXY_DIR / "quota.db"


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_quota_data():
    """从代理 SQLite 读取 Agent 用量"""
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT agent_id, total_tokens FROM agent_usage")
    rows = cur.fetchall()
    conn.close()
    return {aid: tokens for aid, tokens in rows}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/users")
def list_users():
    routing = read_json(CONFIG_DIR / "user-routing.json")
    defaults = read_json(CONFIG_DIR / "quota-defaults.json")
    quota_data = get_quota_data()
    users = []
    for open_id, info in routing.items():
        agent_id = info.get("agent_name", open_id)
        tokens = quota_data.get(agent_id, 0)
        limit = info.get("quota", {}).get("monthly_tokens", defaults["monthly_tokens"])
        users.append({
            "open_id": open_id,
            "feishu_name": info.get("feishu_name", ""),
            "agent_name": info.get("agent_name", ""),
            "role": info.get("role", ""),
            "enabled": info.get("enabled", True),
            "monthly_tokens": tokens,
            "monthly_limit": limit,
            "percent": round(tokens / limit * 100, 1) if limit else 0,
            "created_at": info.get("created_at", ""),
        })
    return jsonify({"users": users, "defaults": defaults})


@app.route("/api/users/<open_id>", methods=["POST"])
def update_user(open_id):
    data = request.json
    routing = read_json(CONFIG_DIR / "user-routing.json")
    if open_id not in routing:
        return jsonify({"error": "user not found"}), 404
    if "enabled" in data:
        routing[open_id]["enabled"] = data["enabled"]
    if "role" in data:
        routing[open_id]["role"] = data["role"]
    if "quota" in data:
        if "quota" not in routing[open_id]:
            routing[open_id]["quota"] = {}
        if "monthly_tokens" in data["quota"]:
            routing[open_id]["quota"]["monthly_tokens"] = data["quota"]["monthly_tokens"]
        if "rate_per_minute" in data["quota"]:
            routing[open_id]["quota"]["rate_per_minute"] = data["quota"]["rate_per_minute"]
    write_json(CONFIG_DIR / "user-routing.json", routing)
    return jsonify({"success": True})


@app.route("/api/users/<open_id>", methods=["DELETE"])
def delete_user(open_id):
    routing = read_json(CONFIG_DIR / "user-routing.json")
    if open_id not in routing:
        return jsonify({"error": "user not found"}), 404
    routing.pop(open_id)
    write_json(CONFIG_DIR / "user-routing.json", routing)
    agent_dir = AGENTS_DIR / open_id
    if agent_dir.exists():
        shutil.rmtree(agent_dir)
    return jsonify({"success": True})


@app.route("/api/quota/defaults", methods=["POST"])
def update_defaults():
    data = request.json
    path = CONFIG_DIR / "quota-defaults.json"
    current = read_json(path)
    for key in ["monthly_tokens", "rate_per_minute", "daily_warn_tokens"]:
        if key in data:
            current[key] = data[key]
    write_json(path, current)
    return jsonify({"success": True})


@app.route("/api/quota/reset", methods=["POST"])
def reset_quota():
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id")
    month_key = datetime.now().strftime("%Y-%m")
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        if agent_id:
            conn.execute("DELETE FROM agent_usage WHERE agent_id=? AND month=?", (agent_id, month_key))
        else:
            conn.execute("DELETE FROM agent_usage WHERE month=?", (month_key,))
        conn.commit()
        conn.close()
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
