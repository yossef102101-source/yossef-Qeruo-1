import os
import json
import time
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import google.generativeai as genai

# إعداد Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SOLUTIONS_FILES = [
    "solutions_grade1_js.json",
    "solutions_grade2_finance.json"
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
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "أنت مساعد ذكي متخصص في حل أسئلة منصة كيريو (QUREO) للبرمجة بلغة JavaScript و HTML و CSS.\n"
            "أعطني الإجابة النهائية المباشرة والدقيقة فقط بدون أي شرح أو مقدمات أو علامات تنسيق Markdown.\n"
            f"السؤال:\n{question_text}\n"
        )
        if code_context:
            prompt += f"\nالكود الحالي في المحرر:\n{code_context}\n"
        if choices:
            prompt += f"\nالاختيارات المتاحة:\n" + "\n".join([f"- {c}" for c in choices]) + "\n"
            prompt += "اختر النص الدقيق للإجابة الصحيحة من الاختيارات السابقة فقط."

        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini error: {e}")
        return ""

async def run_qureo_solver(student_code: str, student_password: str, log_callback, progress_callback):
    """
    تشغيل متصفح Playwright للدخول إلى بوابة كيريو وحل جميع الفصول المتاحة تلقائياً
    """
    await log_callback("جاري تشغيل المتصفح الخفي والاتصال بالذكاء الاصطناعي...")
    await progress_callback(5, "جاري تهيئة المتصفح...")

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
            await log_callback("جاري فتح بوابة كيريو التعليمية...")
            await progress_callback(10, "فتح بوابة كيريو...")
            await page.goto("https://me-portal.qureo.education/", wait_until="networkidle", timeout=60000)
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
                        await log_callback("تم اختيار بوابة تسجيل دخول التعلم...")
                        await btn.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue

            # الخطوة 2: العثور على حقول تسجيل الدخول وإدخال البيانات
            await log_callback(f"تسجيل الدخول بحساب الطالب: {student_code}...")
            await progress_callback(15, "إدخال بيانات الطالب...")

            login_input = page.locator("input[type='text'], input[name*='id'], input[name*='login'], input[name*='user']").first
            pass_input = page.locator("input[type='password']").first

            await login_input.wait_for(state="visible", timeout=20000)
            await login_input.fill(str(student_code).strip())
            await pass_input.fill(str(student_password).strip())

            submit_btn = page.locator("button[type='submit'], button:has-text('تسجيل الدخول'), input[type='submit']").first
            await submit_btn.click()

            await page.wait_for_load_state("networkidle", timeout=45000)
            await asyncio.sleep(3)

            # التحقق من نجاح تسجيل الدخول
            if "portal.qureo.education" in page.url and await page.locator("input[type='password']").is_visible():
                raise Exception("بيانات الدخول غير صحيحة (تأكد من الكود وكلمة المرور).")

            await log_callback("تم تسجيل الدخول بنجاح! جاري الدخول إلى المنهج...")
            await progress_callback(25, "الدخول إلى المنهج...")

            # الخطوة 3: الضغط على زر "ابدأ" (بدء التعلم) إذا ظهر في الصفحة الرئيسية للكورس
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
                        await log_callback("الضغط على زر (ابدأ) لفتح قائمة الفصول...")
                        await s_btn.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                        await asyncio.sleep(3)
                        break
                except Exception:
                    continue

            # الخطوة 4: البحث عن الدروس غير المكتملة وحلها
            solved_count = 0
            max_steps = 120

            for step in range(max_steps):
                current_progress = min(95, 25 + int((step / max_steps) * 70))

                # البحث عن درس متاح (غير مقفل بقفل) أو زر متابعة
                lesson_cards = page.locator("a[href*='lesson'], div[class*='lesson'], li[class*='lesson'], button:has-text('ابدأ'), button:has-text('التالي'), button:has-text('متابعة')")
                count = await lesson_cards.count()

                if count == 0:
                    # محاولة فتح أول فصل غير مكتمل في القائمة الجانبية
                    chapters = page.locator("div[class*='chapter'], li[class*='chapter']")
                    ch_count = await chapters.count()
                    clicked_chapter = False
                    for i in range(ch_count):
                        ch = chapters.nth(i)
                        html = await ch.inner_html()
                        if "lock" not in html.lower() and "قفل" not in html:
                            await ch.click()
                            await asyncio.sleep(2)
                            clicked_chapter = True
                            break
                    if not clicked_chapter:
                        break

                # التفاعل مع شاشات الحوار والشرح (زر التالي / فهمت / حسناً)
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
                # التحقق من وجود سؤال اختيار من متعدد أو حقل كتابة كود
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
                        await log_callback(f"تحليل سؤال اختياري بالذكاء الاصطناعي...")
                        ans = await ask_gemini_for_answer(q_text, choices=choices_texts)
                        for c_i in range(choices_count):
                            try:
                                t = await choices_loc.nth(c_i).inner_text()
                                if ans and (ans in t or t in ans):
                                    await choices_loc.nth(c_i).click()
                                    action_taken = True
                                    solved_count += 1
                                    await progress_callback(current_progress, f"تم حل {solved_count} خطوة...")
                                    break
                            except Exception:
                                pass

                # التحقق من وجود محرر كود (textarea أو monaco / ace editor)
                code_area = page.locator("textarea").first
                if not action_taken and q_text and await code_area.is_visible(timeout=1000):
                    current_code = await code_area.input_value()
                    await log_callback("توليد الكود البرمجي المطلوب بالذكاء الاصطناعي...")
                    ai_code = await ask_gemini_for_answer(q_text, code_context=current_code)
                    if ai_code:
                        await code_area.fill(ai_code)
                        action_taken = True
                        solved_count += 1
                        await progress_callback(current_progress, f"تم كتابة كود الدرس ({solved_count})...")

                # الضغط على زر المتابعة / الإرسال
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
                    # محاولة فتح أول درس متاح في القائمة
                    avail_lessons = page.locator("div[class*='lesson']:not([class*='lock']), a[href*='lesson']")
                    if await avail_lessons.count() > 0:
                        await avail_lessons.first.click()
                        await asyncio.sleep(2)
                    else:
                        break

            await progress_callback(100, f"اكتملت الجلسة! تم إنجاز {solved_count} خطوة بنجاح.")
            await log_callback(f"اكتمل الحل التلقائي بنجاح! إجمالي الخطوات المنجزة: {solved_count}")
            return {"status": "completed", "solved": solved_count}

        except Exception as e:
            err_msg = str(e)
            await log_callback(f"توقفت العملية: {err_msg}")
            raise e
        finally:
            await browser.close()
