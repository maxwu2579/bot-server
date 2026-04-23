# server.py
# pip install flask supabase

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import secrets
import hashlib
import hmac
import json

app = Flask(__name__)

from supabase import create_client

SUPABASE_URL = "https://hlbxdlnpgjocxwdkpfdh.supabase.co"
# ⚠️ 换成 Supabase 的 anon key（eyJ 开头那个）
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhsYnhkbG5wZ2pvY3h3ZGtwZmRoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY4NzUxMjMsImV4cCI6MjA5MjQ1MTEyM30.2l2Kj18wdTKxsSLk6im5Q1FxrE3fopzzBPIB41lvmUU"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_PASSWORD = "13434256266a"  # 建议改得更复杂

# ⚠️ 和 bot_main.py 里的 SIGN_SECRET 保持一致
SIGN_SECRET = "2579561724a"


def check_signature(data: dict) -> bool:
    """验证客户端签名，防止伪造请求"""
    sig = data.pop("sig", "")
    expected = hmac.new(
        SIGN_SECRET.encode(), json.dumps(data, sort_keys=True).encode(), hashlib.sha256
    ).hexdigest()
    data["sig"] = sig  # 还原
    return hmac.compare_digest(sig, expected)


# ============================================================
#  验证接口（改为 POST，和客户端一致）
# ============================================================


@app.route("/verify", methods=["POST"])
def verify():
    data = request.json or {}

    # 签名验证
    if not check_signature(dict(data)):
        return jsonify({"valid": False, "reason": "签名错误"}), 403

    key = data.get("key", "").strip()
    machine_id = data.get("machine_id", "")
    plan = data.get("plan", "")

    if not key:
        return jsonify({"valid": False, "reason": "授权码为空"})

    result = supabase.table("licenses").select("*").eq("key", key).execute()
    if not result.data:
        return jsonify({"valid": False, "reason": "授权码不存在"})

    lic = result.data[0]

    # 过期检查
    expire_at = lic.get("expire_at", "")
    if expire_at and datetime.utcnow().isoformat() > expire_at:
        return jsonify({"valid": False, "reason": "授权码已过期"})

    # 套餐匹配
    if lic.get("plan") != plan:
        return jsonify({"valid": False, "reason": "套餐类型不匹配"})

    # 设备绑定
    saved_mid = lic.get("machine_id")
    if not saved_mid:
        supabase.table("licenses").update({"machine_id": machine_id}).eq(
            "key", key
        ).execute()
    elif saved_mid != machine_id:
        return jsonify({"valid": False, "reason": "授权码已在其他设备使用"})

    return jsonify({"valid": True, "expire_at": expire_at, "plan": plan})


# ============================================================
#  生成授权码（仅你自己用）
# ============================================================


@app.route("/admin/gen", methods=["POST"])
def gen_key():
    data = request.json or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "无权限"}), 403

    plan = data.get("plan", "month")
    days = {"week": 7, "month": 30}.get(plan, 30)
    expire_at = (datetime.utcnow() + timedelta(days=days)).isoformat()

    prefix = {"week": "WK", "month": "MO"}.get(plan, "MO")
    key = f"{prefix}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"

    supabase.table("licenses").insert(
        {
            "key": key,
            "plan": plan,
            "machine_id": None,
            "expire_at": expire_at,
            "created_at": datetime.utcnow().isoformat(),
        }
    ).execute()

    return jsonify({"key": key, "plan": plan, "expire_at": expire_at})


# ============================================================
#  撤销授权码（用户退款/违规时使用）
# ============================================================


@app.route("/admin/revoke", methods=["POST"])
def revoke_key():
    data = request.json or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "无权限"}), 403

    key = data.get("key", "")
    if not key:
        return jsonify({"error": "缺少key"}), 400

    # 把过期时间设为过去，立即失效
    supabase.table("licenses").update({"expire_at": "2000-01-01T00:00:00"}).eq(
        "key", key
    ).execute()

    return jsonify({"ok": True, "revoked": key})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
