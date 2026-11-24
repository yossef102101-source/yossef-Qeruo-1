import asyncio
import json
import os
import secrets
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from bot_engine_playwright import solve_student_task
import database as db

app = FastAPI(title="منصة حل كيريو التلقائي - نظام الصلاحيات المتكامل")

# تهيئة قاعدة البيانات عند بدء التشغيل
db.init_db()

# إعدادات الأدمن من متغيرات البيئة (بدون كشفها في الواجهة)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "yossef102101@gmail.com").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Yossef123098#@").strip()
active_admin_tokens: set = set()

# نماذج البيانات
class AuthRequest(BaseModel):
    full_name: str
    phone: str

class SolveRequest(BaseModel):
    studentCode: str
    password: str
    schoolType: str
    grade: str
    subject: str

class AdminLoginRequest(BaseModel):
    email: str
    password: str

class UserPermissionUpdate(BaseModel):
    phone: str
    can_solve: bool
    max_accounts: int

class SiteSettingsUpdate(BaseModel):
    is_open: bool
    maintenance_message: Optional[str] = None
    default_can_solve: Optional[bool] = None
    default_max_accounts: Optional[int] = None

# الطابور النشط في الذاكرة
queue_tasks: List[dict] = []
tasks_db: Dict[str, dict] = {}  # key: task_id

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_solutions_for(grade: str, subject: str) -> dict:
    filename = "solutions_grade1_js.json"
    if grade == "grade2":
        if subject == "python":
            filename = "solutions_grade2_python.json"
        elif subject == "finance":
            filename = "solutions_grade2_finance.json"
        else:
            filename = "solutions_grade1_js.json"

    filepath = os.path.join(BASE_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"total_levels": 42, "solutions": {}}

# التحقق من هوية المستخدم عبر التوكن
def require_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="يرجى تسجيل الدخول أولاً للمتابعة.")
    token = authorization.replace("Bearer ", "").strip()
    user = db.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="جلسة الدخول غير صالحة أو منتهية، يرجى إعادة الدخول.")
    return user

# التحقق من هوية الأدمن
def require_admin(x_admin_token: Optional[str] = Header(None)):
    if not x_admin_token or x_admin_token not in active_admin_tokens:
        raise HTTPException(status_code=403, detail="غير مصرح لك بالوصول إلى لوحة الإدارة.")
    return True

# العامل في الخلفية (Queue Worker)
async def queue_worker():
    print("[Worker] 🚀 بدء تشغيل عامل الطابور الفعلي (Playwright + Gemini AI)...")
    while True:
        is_open = db.get_setting("is_open", "1") == "1"
        if len(queue_tasks) > 0 and is_open:
            current_task = queue_tasks[0]
            task_id = current_task["task_id"]
            code = current_task["studentCode"]
            password = current_task["password"]
            grade = current_task["grade"]
            subject = current_task["subject"]
            owner_phone = current_task["owner_phone"]

            tasks_db[task_id]["status"] = "solving"
            tasks_db[task_id]["started_at"] = time.strftime("%X")
            tasks_db[task_id]["logs"] = ["وصل دورك! جاري تشغيل المتصفح الخفي والاتصال بالذكاء الاصطناعي..."]

            sol_data = get_solutions_for(grade, subject)

            def on_progress(level: int, total: int, log_msg: str):
                tasks_db[task_id]["current_level"] = level
                tasks_db[task_id]["progress"] = min(100, int((level / max(total, 1)) * 100))
                logs_list = tasks_db[task_id].setdefault("logs", [])
                if not logs_list or logs_list[-1] != log_msg:
                    logs_list.append(log_msg)

            try:
                await solve_student_task(
                    student_code=code,
                    password=password,
                    subject=subject,
                    phone=owner_phone,
                    solutions_bank=sol_data,
                    progress_callback=on_progress
                )
                tasks_db[task_id]["status"] = "completed"
                tasks_db[task_id]["progress"] = 100

            except Exception as e:
                print(f"[Worker Error] خطأ أثناء معالجة الحساب {code}: {e}")
                tasks_db[task_id]["status"] = "failed"
                tasks_db[task_id]["error"] = str(e)
                tasks_db[task_id].setdefault("logs", []).append(f"❌ توقفت العملية: {str(e)}")

            if queue_tasks and queue_tasks[0]["task_id"] == task_id:
                queue_tasks.pop(0)

            for idx, task in enumerate(queue_tasks):
                tid = task["task_id"]
                if tid in tasks_db:
                    tasks_db[tid]["queue_position"] = idx + 1
        else:
            await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(queue_worker())

# ================= 1. نقاط التسجيل والدخول المفتوحة للمستخدمين =================

@app.post("/api/auth/login")
async def user_register_or_login(req: AuthRequest):
    name = req.full_name.strip()
    phone = req.phone.strip()

    if len(name) < 2:
        raise HTTPException(status_code=400, detail="يرجى إدخال الاسم بشكل صحيح.")
    if len(phone) < 9 or not phone.isdigit():
        raise HTTPException(status_code=400, detail="يرجى إدخال رقم هاتف صحيح مكون من أرقام فقط.")

    user = db.register_or_login_user(name, phone)
    return {
        "success": True,
        "token": user["session_token"],
        "user": {
            "full_name": user["full_name"],
            "phone": user["phone"],
            "can_solve": bool(user["can_solve"]),
            "max_accounts": user["max_accounts"],
            "used_accounts": user["used_accounts"],
            "remaining_accounts": max(0, user["max_accounts"] - user["used_accounts"])
        }
    }

@app.get("/api/auth/me")
async def get_current_user_profile(user: dict = Depends(require_user)):
    # جلب أحدث البيانات من قاعدة البيانات للتأكد من تحديث الصلاحيات فوراً
    fresh_user = db.get_user_by_phone(user["phone"])
    return {
        "success": True,
        "user": {
            "full_name": fresh_user["full_name"],
            "phone": fresh_user["phone"],
            "can_solve": bool(fresh_user["can_solve"]),
            "max_accounts": fresh_user["max_accounts"],
            "used_accounts": fresh_user["used_accounts"],
            "remaining_accounts": max(0, fresh_user["max_accounts"] - fresh_user["used_accounts"])
        }
    }

@app.get("/api/site-status")
async def get_site_status():
    return {
        "is_open": db.get_setting("is_open", "1") == "1",
        "maintenance_message": db.get_setting("maintenance_message", "")
    }

# ================= 2. نقطة الحل المحمية بالصلاحيات والحدود من السيرفر =================

@app.post("/api/solve")
async def join_solve_queue(req: SolveRequest, user: dict = Depends(require_user)):
    # 1. التحقق من أن الموقع مفتوح
    if db.get_setting("is_open", "1") != "1":
        raise HTTPException(status_code=403, detail=db.get_setting("maintenance_message", "الموقع مغلق مؤقتاً."))

    # 2. إعادة جلب بيانات المستخدم من القاعدة لمنع أي تلاعب
    fresh_user = db.get_user_by_phone(user["phone"])
    if not fresh_user:
        raise HTTPException(status_code=401, detail="حساب المستخدم غير موجود.")

    # 3. التحقق الصارم من صلاحية الحل (can_solve)
    if not bool(fresh_user["can_solve"]):
        raise HTTPException(
            status_code=403,
            detail="صلاحية الحل غير مفعلة لحسابك حالياً. يمكنك تصفح الأداة، وللحصول على صلاحية الحل يرجى التواصل مع الإدارة."
        )

    # 4. التحقق الصارم من الحد المسموح به لعدد الحسابات (Quota Enforcement)
    max_acc = int(fresh_user["max_accounts"])
    used_acc = int(fresh_user["used_accounts"])
    student_code = req.studentCode.strip()

    if not student_code or not req.password:
        raise HTTPException(status_code=400, detail="يرجى إدخال كود الطالب وكلمة المرور لمنصة كيريو.")

    # منع إرسال نفس كود الطالب مرتين في الطابور حالياً
    for t in tasks_db.values():
        if t["owner_phone"] == fresh_user["phone"] and t["student_code"] == student_code and t["status"] in ["in_queue", "solving"]:
            return {
                "success": True,
                "task_id": t["task_id"],
                "message": "هذا الحساب قيد المعالجة بالفعل.",
                "position": t["queue_position"]
            }

    if used_acc >= max_acc:
        raise HTTPException(
            status_code=403,
            detail=f"لقد استهلكت الحد الأقصى المسموح به لحسابك ({used_acc} من أصل {max_acc} حسابات). اطلب من الإدارة زيادة الحد المسموح."
        )

    # 5. خصم حساب من الرصيد المسموح وإضافة المهمة للطابور
    db.increment_used_accounts(fresh_user["phone"])
    task_id = f"TASK-{int(time.time())}-{secrets.token_hex(3)}"

    task_payload = {
        "task_id": task_id,
        "owner_phone": fresh_user["phone"],
        "owner_name": fresh_user["full_name"],
        "studentCode": student_code,
        "password": req.password,
        "schoolType": req.schoolType,
        "grade": req.grade,
        "subject": req.subject
    }
    queue_tasks.append(task_payload)
    pos = len(queue_tasks)

    tasks_db[task_id] = {
        "task_id": task_id,
        "owner_phone": fresh_user["phone"],
        "owner_name": fresh_user["full_name"],
        "student_code": student_code,
        "subject": req.subject,
        "grade": req.grade,
        "status": "in_queue",
        "queue_position": pos,
        "progress": 0,
        "logs": ["تم التحقق من الصلاحية والرصيد، وانضم الحساب للطابور بنجاح..."],
        "created_at": time.strftime("%X")
    }

    db.log_audit(
        "SOLVE_REQUEST",
        f"بدء حل حساب كيريو ({student_code}) - الاستهلاك ({used_acc + 1}/{max_acc})",
        fresh_user["phone"],
        fresh_user["full_name"]
    )

    return {
        "success": True,
        "task_id": task_id,
        "position": pos,
        "remaining_accounts": max(0, max_acc - (used_acc + 1))
    }

# جلب مهام المستخدم الحالي فقط (منع أي مستخدم من الوصول لبيانات مستخدم آخر)
@app.get("/api/my-tasks")
async def get_my_tasks(user: dict = Depends(require_user)):
    my_list = [t for t in tasks_db.values() if t["owner_phone"] == user["phone"]]
    my_list.reverse()
    return {"success": True, "tasks": my_list}

@app.get("/api/task-status/{task_id}")
async def get_specific_task_status(task_id: str, user: dict = Depends(require_user)):
    task = tasks_db.get(task_id)
    if not task or task["owner_phone"] != user["phone"]:
        raise HTTPException(status_code=404, detail="الطلب غير موجود أو لا تملك صلاحية الوصول إليه.")
    return {"success": True, "task": task}

# ================= 3. لوحة تحكم الإدارة المحمية (Admin Endpoints) =================

@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest):
    if req.email.strip().lower() == ADMIN_EMAIL and req.password.strip() == ADMIN_PASSWORD:
        admin_token = secrets.token_urlsafe(36)
        active_admin_tokens.add(admin_token)
        db.log_audit("ADMIN_LOGIN", "تسجيل دخول ناجح إلى لوحة تحكم الإدارة")
        return {"success": True, "admin_token": admin_token}
    raise HTTPException(status_code=401, detail="البريد الإلكتروني أو كلمة المرور غير صحيحة!")

@app.get("/api/admin/dashboard")
async def get_admin_dashboard(_: bool = Depends(require_admin)):
    users = db.get_all_users()
    authorized_users = [u for u in users if u["can_solve"] == 1]
    unauthorized_users = [u for u in users if u["can_solve"] == 0]

    in_queue_count = len([t for t in tasks_db.values() if t["status"] == "in_queue"])
    solving_count = len([t for t in tasks_db.values() if t["status"] == "solving"])
    completed_count = len([t for t in tasks_db.values() if t["status"] == "completed"])

    return {
        "settings": {
            "is_open": db.get_setting("is_open", "1") == "1",
            "maintenance_message": db.get_setting("maintenance_message", ""),
            "default_can_solve": db.get_setting("default_can_solve", "0") == "1",
            "default_max_accounts": int(db.get_setting("default_max_accounts", "0"))
        },
        "stats": {
            "total_users": len(users),
            "authorized_users": len(authorized_users),
            "unauthorized_users": len(unauthorized_users),
            "in_queue": in_queue_count,
            "solving": solving_count,
            "completed": completed_count
        },
        "users": users,
        "tasks": list(tasks_db.values())[::-1],
        "audit_logs": db.get_audit_logs(100)
    }

@app.post("/api/admin/user-permissions")
async def admin_update_user_permissions(req: UserPermissionUpdate, _: bool = Depends(require_admin)):
    ok = db.update_user_permissions(req.phone.strip(), 1 if req.can_solve else 0, req.max_accounts)
    if not ok:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود.")
    return {"success": True, "message": "تم تحديث صلاحية المستخدم والحد المسموح بنجاح."}

@app.post("/api/admin/settings")
async def admin_update_settings(req: SiteSettingsUpdate, _: bool = Depends(require_admin)):
    db.set_setting("is_open", "1" if req.is_open else "0")
    if req.maintenance_message is not None:
        db.set_setting("maintenance_message", req.maintenance_message)
    if req.default_can_solve is not None:
        db.set_setting("default_can_solve", "1" if req.default_can_solve else "0")
    if req.default_max_accounts is not None:
        db.set_setting("default_max_accounts", str(max(0, req.default_max_accounts)))

    db.log_audit(
        "SETTINGS_UPDATE",
        f"تحديث إعدادات الأداة (الحالة: {'مفتوح' if req.is_open else 'مغلق'} | الحد الافتراضي: {req.default_max_accounts})"
    )
    return {"success": True}

@app.post("/api/admin/clear-queue")
async def clear_admin_queue(_: bool = Depends(require_admin)):
    queue_tasks.clear()
    for t in tasks_db.values():
        if t["status"] == "in_queue":
            t["status"] = "canceled"
    db.log_audit("QUEUE_CLEAR", "تم تفريغ طابور الانتظار بالكامل من قبل الإدارة")
    return {"success": True}

@app.get("/admin")
async def get_admin_page():
    admin_path = os.path.join(BASE_DIR, "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    raise HTTPException(status_code=404, detail="Admin page not found")

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
