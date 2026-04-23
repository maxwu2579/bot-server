# server.py
# 部署到 Railway / Render / VPS 都可以
# pip install flask supabase

from flask import Flask, request, jsonify
from datetime import datetime
import secrets

app = Flask(__name__)

# ── Supabase 配置 ──
# 1. 去 https://supabase.com 注册免费账号
# 2. 新建项目，在 Table Editor 建 licenses 表：
#    - key (text, primary key)
#    - plan (text)  → "week" / "month"
#    - machine_id (text, nullable)
#    - expire_at (text)  → ISO 格式时间字符串
#    - created_at (text)
from supabase import create_client

SUPABASE_URL = "https://hlbxdlnpgjocxwdkpfdh.supabase.co/rest/v1/"  # ← 换成你的
SUPABASE_KEY = "sb_publishable_5VEg7XyCNQPqfADbbp3tHw_KMbnJDhx"  # ← 换成你的

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
#  验证接口
# ============================================================


@app.route("/verify", methods=["GET"])
def verify():
    key = request.args.get("key", "").strip()
    machine_id = request.args.get("machine_id", "")
    plan = request.args.get("plan", "")

    if not key:
        return jsonify({"valid": False, "reason": "授权码为空"})

    # 查数据库
    result = supabase.table("licenses").select("*").eq("key", key).execute()
    if not result.data:
        return jsonify({"valid": False, "reason": "授权码不存在"})

    lic = result.data[0]

    # 检查过期
    expire_at = lic.get("expire_at", "")
    if expire_at and datetime.utcnow().isoformat() > expire_at:
        return jsonify({"valid": False, "reason": "授权码已过期"})

    # 检查套餐是否匹配
    if lic.get("plan") != plan:
        return jsonify({"valid": False, "reason": "套餐类型不匹配"})

    # 绑定/校验机器码
    saved_mid = lic.get("machine_id")
    if not saved_mid:
        # 第一次激活，绑定机器码
        supabase.table("licenses").update({"machine_id": machine_id}).eq(
            "key", key
        ).execute()
    elif saved_mid != machine_id:
        return jsonify({"valid": False, "reason": "授权码已在其他设备使用"})

    return jsonify({"valid": True, "expire_at": expire_at, "plan": plan})


# ============================================================
#  生成授权码接口（你自己用，加密码保护）
# ============================================================

ADMIN_PASSWORD = "你的管理密码"  # ← 改掉


@app.route("/admin/gen", methods=["POST"])
def gen_key():
    data = request.json or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "无权限"}), 403

    plan = data.get("plan", "month")  # week / month
    days = {"week": 7, "month": 30}.get(plan, 30)

    from datetime import timedelta

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
