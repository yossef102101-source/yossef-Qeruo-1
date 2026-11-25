import os
import json
import asyncio
import httpx
from playwright.async_api import async_playwright

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

SOLUTIONS_FILES = [
    "solutions_grade1_js.json",
    "solutions_grade2_finance.json",
    "solutions_grade2_python.json"
]

def load_local_solutions():
    db = {}
    for fname in SOLUTIONS_FILES:
        if os.path.exists(fname):
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        db.update(data)
            except Exception as e:
                print(f"Error loading {fname}: {e}")
    return db

LOCAL_SOLUTIONS = load_local_solutions()

async def ask_gemini_for_answer(question_text: str, code_context: str = "", choices: list = None) -> str:
    if not GEMINI_API_KEY:
        return ""
    try:
        prompt = (
            "أنت مساعد ذكي متخصص في حل أسئلة منصة كيريو (QUREO) للبرمجة بلغة JavaScript و HTML و CSS.\n"
            "أعطني الإجابة النهائية المباشرة والدقيقة فقط بدون أي شرح أو مقدمات أو علامات تنسيق Markdown.\n"
            f"السؤال:\n{question_text}\n"
        )
        if code_context:
            prompt += f"\nالكود الحالي في المحرر:\n{code_context}\n"
        if choices:
            prompt += "\nالاختيارات المتاحة:\n" + "\n".join([f"- {c}" for c in choices]) + "\n"
            prompt += "اختر النص الدقيق للإجابة الصحيحة من الاختيارات السابقة فقط."

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip().replace("```javascript", "").replace("```js", "").replace("```", "").strip()
    except Exception as e:
        print(f"Gemini HTTP error: {e}")
    return ""

async def _call_log(cb, msg: str):
    if not cb:
        return
    if asyncio.iscoroutinefunction(cb):
        await cb(msg)
    else:
        cb(msg)

async def _call_progress(cb, current_val: int, total_val: int, log_msg: str):
    if not cb:
        return
    # الترتيب الصحيح لـ server.py: (الخطوة الحالية int، الإجمالي int، رسالة السجل str)
    args = (int(current_val), int(total_val), str(log_msg))
    if asyncio.iscoroutinefunction(cb):
        await cb(*args)
    else:
        cb(*args)

async def solve_student_task(
    student_code: str = "",
    password: str = "",
    student_password: str = "",
    log_callback=None,
    progress_callback=None,
    **kwargs
):
    """
    الدالة الرئيسية التي يستدعيها server.py لتشغيل المتصفح الخفي وحل دروس كيريو تلقائياً
    """
    actual_pass = password or student_password or kwargs.get("pass", "")

    await _call_log(log_callback, "جاري تشغيل المتصفح الخفي والاتصال بالذكاء الاصطناعي...")
    await _call_progress(progress_callback, 5, 100, "جاري تهيئة المتصفح الخفي...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ar-EG",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await _call_progress(progress_callback, 10, 100, "جاري فتح بوابة كيريو التعليمية...")
            await page.goto("[https://me-portal.qureo.education/](https://me-portal.qureo.education/)", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)

            # الخطوة 1: تخطي شاشة اختيار البوابة ("إلى أين ترغب بالذهاب؟")
            portal_btn_selectors = [
                "text=انتقل إلى تسجيل الدخول للتعلم",
                "a:has-text('تسجيل الدخول للتعلم')",
                "button:has-text('تسجيل الدخول للتعلم')",
                "a[href*='login']",
                "text=Learning Login"
            ]
            for sel in portal_btn_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await _call_log(log_callback, "تم اختيار بوابة تسجيل دخول التعلم...")
                        await btn.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue

            # الخطوة 2: العثور على حقول تسجيل الدخول وإدخال البيانات
            await _call_progress(progress_callback, 15, 100, f"تسجيل الدخول بحساب الطالب: {student_code}...")

            login_input = page.locator("input[type='text'], input[name*='id'], input[name*='login'], input[name*='user']").first
            pass_input = page.locator("input[type='password']").first

            await login_input.wait_for(state="visible", timeout=20000)
            await login_input.fill(str(student_code).strip())
            await pass_input.fill(str(actual_pass).strip())

            submit_btn = page.locator("button[type='submit'], button:has-text('تسجيل الدخول'), input[type='submit']").first
            await submit_btn.click()

            await page.wait_for_load_state("networkidle", timeout=45000)
            await asyncio.sleep(3)

            if "portal.qureo.education" in page.url and await page.locator("input[type='password']").is_visible():
                raise Exception("بيانات الدخول غير صحيحة (تأكد من الكود وكلمة المرور).")

            await _call_progress(progress_callback, 25, 100, "تم تسجيل الدخول بنجاح! جاري الدخول إلى المنهج...")

            # الخطوة 3: الضغط على زر "ابدأ" (بدء التعلم) إذا ظهر
            start_selectors = [
                "button:has-text('ابدأ')",
                "a:has-text('ابدأ')",
                "text=بدء التعلم",
                "button:has-text('Start')"
            ]
            for sel in start_selectors:
                try:
                    s_btn = page.locator(sel).first
                    if await s_btn.is_visible(timeout=4000):
                        await _call_log(log_callback, "الضغط على زر (ابدأ) لفتح قائمة الفصول...")
                        await s_btn.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                        await asyncio.sleep(3)
                        break
                except Exception:
                    continue

            # الخطوة 4: حل الدروس المتاحة تلقائياً
            solved_count = 0
            max_steps = 120

            for step in range(max_steps):
                current_progress = min(95, 25 + int((step / max_steps) * 70))

                next_btns = [
                    "button:has-text('التالي')",
                    "button:has-text('فهمت')",
                    "button:has-text('حسناً')",
                    "button:has-text('إرسال')",
                    "button:has-text('تحقق')",
                    "button:has-text('تشغيل')",
                    "button:has-text('Next')",
                    "button:has-text('Submit')"
                ]

                action_taken = False
                choices_loc = page.locator("label[class*='choice'], div[class*='choice'], button[class*='option'], input[type='radio']")
                choices_count = await choices_loc.count()

                question_el = page.locator("div[class*='question'], p[class*='question'], div[class*='mission'], div[class*='instruction']").first
                q_text = ""
                if await question_el.is_visible(timeout=1000):
                    q_text = await question_el.inner_text()

                if choices_count > 0 and q_text:
                    choices_texts = []
                    for c_i in range(choices_count):
                        try:
                            t = await choices_loc.nth(c_i).inner_text()
                            if t.strip():
                                choices_texts.append(t.strip())
                        except Exception:
                            pass

                    if choices_texts:
                        await _call_log(log_callback, "تحليل سؤال اختياري بالذكاء الاصطناعي...")
                        ans = await ask_gemini_for_answer(q_text, choices=choices_texts)
                        for c_i in range(choices_count):
                            try:
                                t = await choices_loc.nth(c_i).inner_text()
                                if ans and (ans in t or t in ans):
                                    await choices_loc.nth(c_i).click()
                                    action_taken = True
                                    solved_count += 1
                                    await _call_progress(progress_callback, current_progress, 100, f"تمت الإجابة على السؤال ({solved_count})")
                                    break
                            except Exception:
                                pass

                code_area = page.locator("textarea").first
                if not action_taken and q_text and await code_area.is_visible(timeout=1000):
                    current_code = await code_area.input_value()
                    await _call_log(log_callback, "توليد الكود البرمجي المطلوب بالذكاء الاصطناعي...")
                    ai_code = await ask_gemini_for_answer(q_text, code_context=current_code)
                    if ai_code:
                        await code_area.fill(ai_code)
                        action_taken = True
                        solved_count += 1
                        await _call_progress(progress_callback, current_progress, 100, f"تمت كتابة الكود بنجاح ({solved_count})")

                for n_sel in next_btns:
                    try:
                        n_btn = page.locator(n_sel).first
                        if await n_btn.is_visible(timeout=800) and await n_btn.is_enabled():
                            await n_btn.click()
                            action_taken = True
                            await asyncio.sleep(1.5)
                            break
                    except Exception:
                        continue

                if not action_taken:
                    avail_lessons = page.locator("div[class*='lesson']:not([class*='lock']), a[href*='lesson']")
                    if await avail_lessons.count() > 0:
                        await avail_lessons.first.click()
                        await asyncio.sleep(2)
                    else:
                        break

            await _call_progress(progress_callback, 100, 100, f"اكتمل الحل التلقائي بنجاح! إجمالي الخطوات المنجزة: {solved_count}")
            return {"status": "completed", "solved": solved_count}

        except Exception as e:
            err_msg = str(e)
            await _call_log(log_callback, f"توقفت العملية: {err_msg}")
            raise e
        finally:
            await browser.close()

run_qureo_solver = solve_student_task
