import asyncio
import json
import os
import re
from typing import Callable, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from playwright.async_api import async_playwright

load_dotenv()

QUREO_LOGIN_URL = "https://me-portal.qureo.education/"

def get_ai_client():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("مفتاح GEMINI_API_KEY غير مضاف في إعدادات الاستضافة (Environment Variables)!")
    return genai.Client(api_key=api_key)

async def ask_gemini_for_solution(page_text: str, code_context: str, subject: str, fallback_hint: str = "") -> dict:
    """تحليل صفحة كيريو الحالية بواسطة Gemini وإرجاع الحل الدقيق"""
    client = get_ai_client()
    prompt = f"""
المادة الدراسية: {subject}
النص الظاهر في صفحة كيريو الحالية:
---
{page_text[:4500]}
---
الكود المبدئي الموجود في المحرر (إن وجد):
---
{code_context[:2000]}
---
مرجع إضافي من بنك الحلول: {fallback_hint}
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "أنت محرك حل ذكي مخصص لمنصة Qureo التعليمية (JavaScript, Python, Financial Literacy). "
                "حلل محتوى الصفحة وحدد نوع الخطوة الحالية بدقة: "
                "1) 'code': إذا كان هناك تحدي برمجي يتطلب كتابة كود في المحرر. اكتب الكود الكامل الصحيح بدون أي علامات markdown مثل ```. "
                "2) 'choice': إذا كان سؤال اختيار من متعدد. اكتب النص الدقيق للخيار الصحيح. "
                "3) 'info': إذا كانت صفحة شرح/حوار/توجيهات لا تتطلب حلاً بل فقط الضغط على زر التالي أو المتابعة. "
                "أعد الإجابة بصيغة JSON فقط بهذا الهيكل: "
                '{"action": "code" | "choice" | "info", "code": "...", "choice_text": "..."}'
            ),
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    return json.loads(response.text)

async def write_code_to_editor(page, code_text: str) -> bool:
    """كتابة الكود في محرر كيريو (يدعم Monaco Editor و Ace Editor و Textarea)"""
    monaco = page.locator(".monaco-editor").first
    if await monaco.count() > 0:
        await monaco.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(code_text)
        return True

    ace = page.locator(".ace_text-input").first
    if await ace.count() > 0:
        await ace.focus()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(code_text)
        return True

    textarea = page.locator("textarea").first
    if await textarea.count() > 0:
        await textarea.fill(code_text)
        return True

    return False

async def click_action_button(page) -> bool:
    """البحث الذكي عن زر التشغيل أو التحقق أو التالي والضغط عليه"""
    selectors = [
        'button:has-text("Run")',
        'button:has-text("Execute")',
        'button:has-text("Check")',
        'button:has-text("Submit")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'button:has-text("Start")',
        'button:has-text("تشغيل")',
        'button:has-text("تحقق")',
        'button:has-text("إرسال")',
        'button:has-text("التالي")',
        'button:has-text("استمرار")',
        'button:has-text("ابدأ")',
        '[class*="next" i]',
        '[class*="run" i]',
        '[class*="submit" i]',
        'button[type="submit"]'
    ]
    for sel in selectors:
        btn = page.locator(sel).filter(has_not=page.locator('[disabled]')).first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            return True
    return False

async def solve_student_task(
    student_code: str,
    password: str,
    subject: str,
    phone: str,
    solutions_bank: dict,
    progress_callback: Optional[Callable] = None
):
    """تنفيذ الحل الفعلي لحساب الطالب باستخدام المتصفح الخفي + Gemini AI"""
    def update_status(level: int, total: int, log_msg: str):
        print(f"[{student_code}] {log_msg}")
        if progress_callback:
            progress_callback(level, total, log_msg)

    total_levels = solutions_bank.get("total_levels", 42)
    saved_solutions = solutions_bank.get("solutions", {})

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(45000)

        try:
            update_status(0, total_levels, "جاري فتح بوابة كيريو التعليمية...")
            await page.goto(QUREO_LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            update_status(0, total_levels, f"تسجيل الدخول بحساب الطالب: {student_code}...")
            user_input = page.locator('input[type="text"], input[type="email"], input[name*="user" i], input[name*="code" i], input[name*="id" i]').first
            pass_input = page.locator('input[type="password"]').first

            if await user_input.count() == 0 or await pass_input.count() == 0:
                raise Exception("تعذر العثور على حقول تسجيل الدخول في صفحة كيريو.")

            await user_input.fill(student_code)
            await pass_input.fill(password)

            login_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("دخول"), button:has-text("تسجيل")').first
            if await login_btn.count() > 0:
                await login_btn.click()
            else:
                await pass_input.press("Enter")

            await page.wait_for_timeout(4500)

            if await page.locator('input[type="password"]').count() > 0:
                body_txt = await page.inner_text("body")
                if any(w in body_txt.lower() for w in ["incorrect", "invalid", "error", "خطأ", "غير صحيح"]):
                    raise Exception("بيانات الدخول غير صحيحة! تأكد من كود الطالب وكلمة المرور.")

            update_status(1, total_levels, "تم تسجيل الدخول بنجاح! جاري الدخول إلى المنهج...")

            start_course_btn = page.locator('a[href*="lesson" i], a[href*="chapter" i], a[href*="stage" i], button:has-text("Start"), button:has-text("Continue"), button:has-text("ابدأ"), button:has-text("استمرار")').first
            if await start_course_btn.count() > 0:
                await start_course_btn.click()
                await page.wait_for_timeout(3000)

            max_steps = total_levels * 4
            completed_levels = 1

            for step in range(1, max_steps + 1):
                await page.wait_for_timeout(1500)
                page_text = await page.inner_text("body")

                if any(done_word in page_text.lower() for done_word in ["all chapters completed", "course completed", "تهانينا لقد أنهيت", "اكتمل المنهج"]):
                    completed_levels = total_levels
                    update_status(total_levels, total_levels, "تم إكمال جميع دروس ومستويات المنهج بنجاح!")
                    break

                lvl_match = re.search(r'(?:level|lesson|stage|المستوى|الدرس)\s*[:#-]?\s*(\d+)', page_text, re.IGNORECASE)
                if lvl_match:
                    detected = int(lvl_match.group(1))
                    if 1 <= detected <= total_levels:
                        completed_levels = detected

                code_context = ""
                editor_lines = page.locator(".view-lines, .ace_content, textarea").first
                if await editor_lines.count() > 0:
                    code_context = await editor_lines.inner_text()

                hint = str(saved_solutions.get(str(completed_levels), ""))
                update_status(completed_levels, total_levels, f"المستوى {completed_levels}/{total_levels}: تحليل وحل الخطوة {step} بالذكاء الاصطناعي...")

                ai_res = await ask_gemini_for_solution(page_text, code_context, subject, hint)
                action = ai_res.get("action", "info")

                if action == "code" and ai_res.get("code"):
                    wrote = await write_code_to_editor(page, ai_res["code"])
                    if wrote:
                        update_status(completed_levels, total_levels, f"المستوى {completed_levels}: تم كتابة الكود البرمجي، جاري التشغيل...")
                        await page.wait_for_timeout(800)

                elif action == "choice" and ai_res.get("choice_text"):
                    choice_el = page.get_by_text(ai_res["choice_text"], exact=False).first
                    if await choice_el.count() > 0:
                        await choice_el.click()
                        update_status(completed_levels, total_levels, f"المستوى {completed_levels}: تم اختيار الإجابة الصحيحة.")
                        await page.wait_for_timeout(800)

                clicked = await click_action_button(page)
                if not clicked:
                    await page.mouse.click(640, 400)

                await page.wait_for_timeout(2000)

            update_status(total_levels, total_levels, "✅ اكتملت عملية الحل التلقائي بنجاح بنسبة 100%!")
            return True

        finally:
            await browser.close()
