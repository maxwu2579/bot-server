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
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhsYnhkbG5wZ2pvY3h3ZGtwZmRoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY4NzUxMjMsImV4cCI6MjA5MjQ1MTEyM30.2l2Kj18wdTKxsSLk6im5Q1FxrE3fopzzBPIB41lvmUU"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_PASSWORD = "13434256266a"
SIGN_SECRET = "2579561724a"

TRIAL_SECONDS = 3600  # 1 小时


def check_signature(data: dict) -> bool:
    sig = data.pop("sig", "")
    expected = hmac.new(
        SIGN_SECRET.encode(), json.dumps(data, sort_keys=True).encode(), hashlib.sha256
    ).hexdigest()
    data["sig"] = sig
    return hmac.compare_digest(sig, expected)


# ============================================================
#  试用接口（新增）
# ============================================================


@app.route("/trial", methods=["POST"])
def trial():
    """
    试用验证：一台设备永久只能试用1次
    返回剩余秒数，客户端根据这个时间运行
    """
    data = request.json or {}
    if not check_signature(dict(data)):
        return jsonify({"valid": False, "reason": "签名错误"}), 403

    machine_id = data.get("machine_id", "")
    if not machine_id:
        return jsonify({"valid": False, "reason": "缺少设备码"})

    # 查是否已经试用过
    result = supabase.table("trials").select("*").eq("machine_id", machine_id).execute()

    if result.data:
        # 已试用过，查剩余时间
        trial_record = result.data[0]
        first_used = datetime.fromisoformat(trial_record["first_used"])
        elapsed = (datetime.utcnow() - first_used).total_seconds()
        remaining = TRIAL_SECONDS - int(elapsed)

        if remaining <= 0:
            return jsonify({"valid": False, "reason": "试用已用完，请购买授权码"})
        return jsonify(
            {
                "valid": True,
                "remaining": remaining,
                "message": f"试用剩余 {remaining//60} 分钟",
            }
        )
    else:
        # 第一次试用，记录时间
        supabase.table("trials").insert(
            {
                "machine_id": machine_id,
                "first_used": datetime.utcnow().isoformat(),
            }
        ).execute()
        return jsonify(
            {"valid": True, "remaining": TRIAL_SECONDS, "message": "开始试用 1 小时"}
        )


# ============================================================
#  验证接口
# ============================================================


@app.route("/verify", methods=["POST"])
def verify():
    data = request.json or {}
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

    expire_at = lic.get("expire_at", "")
    if expire_at and datetime.utcnow().isoformat() > expire_at:
        return jsonify({"valid": False, "reason": "授权码已过期"})

    if lic.get("plan") != plan:
        return jsonify({"valid": False, "reason": "套餐类型不匹配"})

    saved_mid = lic.get("machine_id")
    if not saved_mid:
        supabase.table("licenses").update({"machine_id": machine_id}).eq(
            "key", key
        ).execute()
    elif saved_mid != machine_id:
        return jsonify({"valid": False, "reason": "授权码已在其他设备使用"})

    return jsonify({"valid": True, "expire_at": expire_at, "plan": plan})


# ============================================================
#  生成授权码
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
#  撤销授权码
# ============================================================


@app.route("/admin/revoke", methods=["POST"])
def revoke_key():
    data = request.json or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "无权限"}), 403

    key = data.get("key", "")
    if not key:
        return jsonify({"error": "缺少key"}), 400

    supabase.table("licenses").update({"expire_at": "2000-01-01T00:00:00"}).eq(
        "key", key
    ).execute()

    return jsonify({"ok": True, "revoked": key})


# ============================================================
#  重置试用（仅管理员用，测试时方便）
# ============================================================


@app.route("/admin/reset_trial", methods=["POST"])
def reset_trial():
    data = request.json or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "无权限"}), 403

    machine_id = data.get("machine_id", "")
    if not machine_id:
        return jsonify({"error": "缺少 machine_id"}), 400

    supabase.table("trials").delete().eq("machine_id", machine_id).execute()
    return jsonify({"ok": True, "reset": machine_id})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
