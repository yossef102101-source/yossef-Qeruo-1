import os
import json
import asyncio
from urllib.parse import urlparse
import httpx
from playwright.async_api import async_playwright

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PROXY_URL = os.getenv("PROXY_URL", "").strip()

PORTAL_HOME_URL = "https://" + "me-portal.qureo.education/"
COURSE_JS_URL = "https://" + "me-tp.qureo.education/course/javascript_ar"
GEMINI_BASE_URL = "https://" + "generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key="
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

SOLUTIONS_FILES = [
    "solutions_grade1_js.json",
    "solutions_grade2_finance.json",
    "solutions_grade2_python.json"
]

def build_proxy_config(raw_proxy: str):
    """
    يدعم جميع صيغ البروكسي تلقائياً دون أخطاء:
    1) http://user:pass@ip:port
    2) socks5://user:pass@ip:port
    3) ip:port:user:pass
    4) ip:port
    """
    if not raw_proxy:
        return None
    raw = raw_proxy.strip().strip('"').strip("'")
    if not raw or "ip:port" in raw.lower():
        return None

    try:
        scheme = "http"
        rest = raw
        if "://" in raw:
            scheme, rest = raw.split("://", 1)

        # الصيغة القياسية: user:pass@host:port (نستخدم rsplit للتعامل مع @ داخل كلمة المرور)
        if "@" in rest:
            auth_part, host_part = rest.rsplit("@", 1)
            if ":" not in host_part:
                return None
            host, port_str = host_part.rsplit(":", 1)
            port = int(port_str.strip("/"))
            config = {"server": f"{scheme}://{host}:{port}"}
            if ":" in auth_part:
                u, p = auth_part.split(":", 1)
                config["username"] = u
                config["password"] = p
            return config

        # الصيغة الشائعة بدون @: ip:port:user:pass أو ip:port
        parts = rest.strip("/").split(":")
        if len(parts) == 2:
            host, port = parts[0], int(parts[1])
            return {"server": f"{scheme}://{host}:{port}"}
        elif len(parts) >= 4:
            host, port = parts[0], int(parts[1])
            username = parts[2]
            password = ":".join(parts[3:])
            return {
                "server": f"{scheme}://{host}:{port}",
                "username": username,
                "password": password
            }
    except Exception as e:
        print(f"Invalid proxy format ignored: {e}")
    return None

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
    clean_q = question_text.strip()
    for k, v in LOCAL_SOLUTIONS.items():
        if k and (k in clean_q or clean_q in k):
            if isinstance(v, str) and v.strip():
                return v.strip()

    if not GEMINI_API_KEY:
        return ""
    try:
        prompt = (
            "أنت مساعد ذكي متخصص في حل أسئلة منصة كيريو (QUREO) للبرمجة بلغة JavaScript و HTML و CSS و Python.\n"
            "أعطني الإجابة النهائية المباشرة والدقيقة فقط بدون أي شرح أو مقدمات أو علامات تنسيق Markdown.\n"
            f"السؤال:\n{question_text}\n"
        )
        if code_context:
            prompt += f"\nالكود الحالي في المحرر:\n{code_context}\n"
        if choices:
            prompt += "\nالاختيارات المتاحة:\n" + "\n".join([f"- {c}" for c in choices]) + "\n"
            prompt += "اختر النص الدقيق للإجابة الصحيحة من الاختيارات السابقة فقط."

        url = GEMINI_BASE_URL + GEMINI_API_KEY
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip().replace("```javascript", "").replace("```js", "").replace("```python", "").replace("```", "").strip()
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
    actual_pass = password or student_password or kwargs.get("pass", "")
    proxy_settings = build_proxy_config(PROXY_URL)

    if proxy_settings:
        await _call_log(log_callback, f"تم تفعيل الاتصال عبر البروكسي: {proxy_settings['server']}")
    else:
        await _call_log(log_callback, "تنبيه: صيغة PROXY_URL غير صالحة أو فارغة (تأكد من كتابة IP ورقم المنفذ بشكل صحيح)...")

    await _call_progress(progress_callback, 5, 100, "جاري تهيئة المتصفح الخفي...")

    async with async_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1366,768"
            ]
        }
        if proxy_settings:
            launch_kwargs["proxy"] = proxy_settings

        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="ar-EG",
            timezone_id="Africa/Cairo",
            user_agent=DEFAULT_UA,
            ignore_https_errors=True
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        try:
            await _call_progress(progress_callback, 10, 100, "جاري فتح بوابة كيريو عبر البروكسي...")
            await page.goto(PORTAL_HOME_URL, wait_until="networkidle", timeout=60000)

            try:
                await page.wait_for_selector("button, a, input", timeout=20000)
            except Exception:
                await page.goto(COURSE_JS_URL, wait_until="networkidle", timeout=60000)
                await page.wait_for_selector("button, a, input", timeout=20000)

            await asyncio.sleep(2)

            # الخطوة 1: تخطي شاشة اختيار البوابة ("إلى أين ترغب بالذهاب؟") -> الضغط على الزر الثاني
            if await page.locator("input").count() < 2:
                clickables = page.locator("button:visible, a:visible, [role='button']:visible")
                c_count = await clickables.count()
                clicked = False

                for i in range(c_count):
                    try:
                        t = (await clickables.nth(i).inner_text()).strip()
                        if "للتعلم" in t or "التعلم" in t or "Learning" in t:
                            await _call_log(log_callback, "تم الضغط على زر (انتقل إلى تسجيل الدخول للتعلم)...")
                            await clickables.nth(i).click()
                            await page.wait_for_load_state("networkidle", timeout=30000)
                            await asyncio.sleep(2)
                            clicked = True
                            break
                    except Exception:
                        pass

                if not clicked and c_count >= 2:
                    await _call_log(log_callback, "تم الضغط على الزر الثاني في البوابة...")
                    await clickables.nth(1).click()
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    await asyncio.sleep(2)

            # الخطوة 2: تسجيل الدخول بحساب الطالب
            await _call_progress(progress_callback, 15, 100, f"تسجيل الدخول بحساب الطالب: {student_code}...")
            await page.wait_for_selector("input", timeout=25000)
            all_inputs = page.locator("input:visible")

            if await all_inputs.count() < 2:
                raise Exception("فشل تحميل حقول الدخول؛ تأكد من أن البروكسي مصري ويعمل.")

            await all_inputs.nth(0).fill(str(student_code).strip())
            await all_inputs.nth(1).fill(str(actual_pass).strip())

            submit_btn = page.locator("button[type='submit']:visible, button:has-text('تسجيل الدخول'):visible, button:visible").first
            await submit_btn.click()

            await page.wait_for_load_state("networkidle", timeout=45000)
            await asyncio.sleep(4)

            if await page.locator("input[type='password']:visible").count() > 0:
                raise Exception("بيانات الدخول غير صحيحة (تأكد من الكود وكلمة المرور).")

            await _call_progress(progress_callback, 25, 100, "تم تسجيل الدخول بنجاح! جاري الدخول إلى المنهج...")

            # الخطوة 3: الضغط على زر "ابدأ"
            for _ in range(4):
                start_btn = page.locator("button:has-text('ابدأ'), a:has-text('ابدأ'), button:has-text('Start')").first
                if await start_btn.is_visible(timeout=2500):
                    await _call_log(log_callback, "تم الضغط على زر (ابدأ) لفتح قائمة الفصول...")
                    await start_btn.click()
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    await asyncio.sleep(3)
                    break
                await asyncio.sleep(1.5)

            # الخطوة 4: حل الدروس المتاحة تلقائياً
            solved_count = 0
            max_steps = 150

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
