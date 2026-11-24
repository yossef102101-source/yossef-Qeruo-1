const state = {
    currentStep: 1,
    schoolType: 'general',
    grade: 'grade1',
    subject: 'js',
    studentCode: '',
    password: '',
    userToken: localStorage.getItem('qureo_user_token') || '',
    user: null,
    currentTaskId: null
};

const subjectsMap = {
    general: {
        grade1: [
            { id: 'js', name: 'جافا سكريبت (JS)', icon: 'code', desc: 'الصف الأول الثانوي' }
        ],
        grade2: [
            { id: 'finance', name: 'ثقافة مالية', icon: 'wallet', desc: 'الصف الثاني الثانوي' },
            { id: 'python', name: 'بايثون (Python)', icon: 'terminal', desc: 'الصف الثاني الثانوي' },
            { id: 'js', name: 'جافا سكريبت (JS)', icon: 'code', desc: 'الصف الثاني الثانوي' }
        ]
    },
    languages: {
        grade1: [
            { id: 'js', name: 'JavaScript (Languages)', icon: 'code', desc: 'Grade 10 / 1st Sec' }
        ],
        grade2: [
            { id: 'finance', name: 'Financial Literacy', icon: 'wallet', desc: 'Grade 11 / 2nd Sec' },
            { id: 'python', name: 'Python (Languages)', icon: 'terminal', desc: 'Grade 11 / 2nd Sec' },
            { id: 'js', name: 'JavaScript (Languages)', icon: 'code', desc: 'Grade 11 / 2nd Sec' }
        ]
    }
};

document.addEventListener('DOMContentLoaded', async () => {
    await checkSiteStatus();
    renderSubjects();
    updateProgressBar();
    if (state.userToken) {
        await refreshUserProfile();
    }
});

async function checkSiteStatus() {
    try {
        const res = await fetch('/api/site-status');
        const data = await res.json();
        const mainContainer = document.getElementById('mainAppContainer');
        const overlay = document.getElementById('maintenanceOverlay');
        const noticeText = document.getElementById('maintenanceNoticeText');

        if (!data.is_open) {
            mainContainer.classList.add('hidden');
            overlay.classList.remove('hidden');
            if (noticeText && data.maintenance_message) noticeText.innerText = data.maintenance_message;
        } else {
            mainContainer.classList.remove('hidden');
            overlay.classList.add('hidden');
        }
    } catch (e) {}
}

// ================= User Auth (Open Registration & Login) =================

function openAuthModal() {
    document.getElementById('authModal').classList.remove('hidden');
}

function closeAuthModal() {
    document.getElementById('authModal').classList.add('hidden');
}

async function submitUserAuth() {
    const name = document.getElementById('authNameInput').value.trim();
    const phone = document.getElementById('authPhoneInput').value.trim();
    const errEl = document.getElementById('authErrorMsg');

    errEl.classList.add('hidden');

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ full_name: name, phone: phone })
        });
        const data = await res.json();

        if (!res.ok) {
            errEl.innerText = data.detail || 'حدث خطأ أثناء التسجيل.';
            errEl.classList.remove('hidden');
            return;
        }

        state.userToken = data.token;
        state.user = data.user;
        localStorage.setItem('qureo_user_token', data.token);
        closeAuthModal();
        renderUserBanner();
    } catch (e) {
        errEl.innerText = 'تعذر الاتصال بالسيرفر.';
        errEl.classList.remove('hidden');
    }
}

async function refreshUserProfile() {
    if (!state.userToken) return;
    try {
        const res = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${state.userToken}` }
        });
        if (!res.ok) {
            logoutUser();
            return;
        }
        const data = await res.json();
        state.user = data.user;
        renderUserBanner();
    } catch (e) {}
}

function renderUserBanner() {
    const loginBtn = document.getElementById('navLoginBtn');
    const navActions = document.getElementById('userNavActions');
    const statusCard = document.getElementById('userStatusCard');
    const noPermBanner = document.getElementById('noPermissionBanner');
    const noPermText = document.getElementById('noPermissionText');

    if (!state.user) {
        loginBtn.classList.remove('hidden');
        navActions.classList.add('hidden');
        statusCard.classList.add('hidden');
        noPermBanner.classList.add('hidden');
        return;
    }

    loginBtn.classList.add('hidden');
    navActions.classList.remove('hidden');
    statusCard.classList.remove('hidden');

    document.getElementById('displayUserName').innerText = state.user.full_name;
    document.getElementById('displayUserPhone').innerText = state.user.phone;
    document.getElementById('userAvatarLetter').innerText = state.user.full_name.charAt(0);
    document.getElementById('displayRemaining').innerText = state.user.remaining_accounts;
    document.getElementById('displayMax').innerText = state.user.max_accounts;

    const badge = document.getElementById('permissionBadge');
    if (state.user.can_solve && state.user.remaining_accounts > 0) {
        badge.className = 'text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30';
        badge.innerText = 'صلاحية الحل مفعلة 🟢';
        noPermBanner.classList.add('hidden');
    } else if (!state.user.can_solve) {
        badge.className = 'text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30';
        badge.innerText = 'صلاحية الحل غير مفعلة 🔒';
        noPermText.innerText = 'صلاحية الحل غير مفعلة لحسابك حالياً. يمكنك تصفح الأداة بحرية، ولتفعيل ميزة الحل يرجى التواصل مع الإدارة.';
        noPermBanner.classList.remove('hidden');
    } else {
        badge.className = 'text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30';
        badge.innerText = 'الرصيد مكتمل (0 متاح)';
        noPermText.innerText = `لقد استخدمت جميع الحسابات المسموح بها (${state.user.used_accounts}/${state.user.max_accounts}). اطلب من الإدارة زيادة الحد المسموح.`;
        noPermBanner.classList.remove('hidden');
    }

    if (window.lucide) lucide.createIcons();
}

function logoutUser() {
    localStorage.removeItem('qureo_user_token');
    state.userToken = '';
    state.user = null;
    renderUserBanner();
    resetApp();
}

// ================= Wizard Navigation =================

function setSchoolType(type) {
    state.schoolType = type;
    const btnGeneral = document.getElementById('type-general');
    const btnLanguages = document.getElementById('type-languages');

    if (type === 'general') {
        btnGeneral.className = 'p-4 rounded-2xl border border-blue-500/50 bg-blue-600/15 text-white font-bold flex items-center justify-center gap-2 hover:bg-blue-600/20 transition-all';
        btnLanguages.className = 'p-4 rounded-2xl border border-slate-800 bg-slate-900/60 text-slate-400 font-bold flex items-center justify-center gap-2 hover:bg-slate-800 transition-all';
    } else {
        btnLanguages.className = 'p-4 rounded-2xl border border-blue-500/50 bg-blue-600/15 text-white font-bold flex items-center justify-center gap-2 hover:bg-blue-600/20 transition-all';
        btnGeneral.className = 'p-4 rounded-2xl border border-slate-800 bg-slate-900/60 text-slate-400 font-bold flex items-center justify-center gap-2 hover:bg-slate-800 transition-all';
    }
    renderSubjects();
}

function setGrade(grade) {
    state.grade = grade;
    const btn1 = document.getElementById('grade-1');
    const btn2 = document.getElementById('grade-2');

    if (grade === 'grade1') {
        btn1.className = 'p-4 rounded-2xl border border-blue-500/50 bg-blue-600/15 text-white font-bold flex items-center justify-center gap-2 hover:bg-blue-600/20 transition-all';
        btn2.className = 'p-4 rounded-2xl border border-slate-800 bg-slate-900/60 text-slate-400 font-bold flex items-center justify-center gap-2 hover:bg-slate-800 transition-all';
    } else {
        btn2.className = 'p-4 rounded-2xl border border-blue-500/50 bg-blue-600/15 text-white font-bold flex items-center justify-center gap-2 hover:bg-blue-600/20 transition-all';
        btn1.className = 'p-4 rounded-2xl border border-slate-800 bg-slate-900/60 text-slate-400 font-bold flex items-center justify-center gap-2 hover:bg-slate-800 transition-all';
    }
    renderSubjects();
}

function renderSubjects() {
    const container = document.getElementById('subjectsContainer');
    const subjects = subjectsMap[state.schoolType][state.grade];

    if (!subjects.some(s => s.id === state.subject)) {
        state.subject = subjects[0].id;
    }

    container.innerHTML = subjects.map(s => {
        const isSelected = s.id === state.subject;
        const activeClass = isSelected
            ? 'border-blue-500/70 bg-gradient-to-b from-blue-600/25 to-indigo-600/25 text-white shadow-lg shadow-blue-500/15'
            : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:bg-slate-900';

        return `
            <div onclick="selectSubject('${s.id}')" class="cursor-pointer p-4 rounded-2xl border ${activeClass} transition-all flex flex-col justify-between">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-bold text-sm text-slate-100">${s.name}</span>
                    <i data-lucide="${s.icon}" class="w-4 h-4 ${isSelected ? 'text-blue-400' : 'text-slate-500'}"></i>
                </div>
                <span class="text-xs text-slate-500">${s.desc}</span>
            </div>
        `;
    }).join('');

    if (window.lucide) lucide.createIcons();
}

function selectSubject(subId) {
    state.subject = subId;
    renderSubjects();
}

function proceedFromStep1() {
    // السماح بالتصفح للجميع، وعند البدء بالحل يُطلب الدخول إذا لم يكن مسجلاً
    if (!state.userToken) {
        openAuthModal();
        return;
    }
    goToStep(2);
}

function goToStep(stepNum) {
    document.querySelectorAll('[id^="step-"]').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(`step-${stepNum}`);
    if (target) {
        target.classList.remove('hidden');
        state.currentStep = stepNum;
        updateProgressBar();
    }
    if (stepNum === 3) {
        populateSummary();
    }
    if (window.lucide) lucide.createIcons();
}

function validateAndGoToStep3() {
    const codeInput = document.getElementById('inputStudentCode');
    const codeError = document.getElementById('codeError');
    const val = codeInput.value.trim();

    if (!val || val.length < 3) {
        codeError.classList.remove('hidden');
        codeInput.focus();
        return;
    }
    codeError.classList.add('hidden');
    state.studentCode = val;
    document.getElementById('solveServerError').classList.add('hidden');
    goToStep(3);
}

function populateSummary() {
    const gradeName = state.grade === 'grade1' ? 'أولى بكالوريا (ثانوي)' : 'ثانية بكالوريا (ثانوي)';
    const typeName = state.schoolType === 'general' ? 'عام' : 'لغات';
    const subObj = subjectsMap[state.schoolType][state.grade].find(s => s.id === state.subject);

    document.getElementById('summaryTrack').innerText = `${gradeName} - ${typeName}`;
    document.getElementById('summarySubject').innerText = subObj ? subObj.name : state.subject;
    document.getElementById('summaryCode').innerText = state.studentCode;
}

function updateProgressBar() {
    const stepsBar = document.getElementById('stepsBar');
    if (state.currentStep > 3) {
        stepsBar.classList.add('hidden');
        return;
    } else {
        stepsBar.classList.remove('hidden');
    }

    const percent = ((state.currentStep - 1) / 2) * 100;
    const line = document.getElementById('progressBarLine');
    if (line) line.style.width = `${Math.min(percent, 100)}%`;

    for (let i = 1; i <= 3; i++) {
        const badge = document.getElementById(`badge-step-${i}`);
        if (!badge) continue;

        if (i < state.currentStep) {
            badge.className = 'w-10 h-10 rounded-full bg-emerald-600 text-white font-bold flex items-center justify-center border-4 border-slate-950 transition-all shadow-lg';
            badge.innerHTML = '<i data-lucide="check" class="w-5 h-5"></i>';
        } else if (i === state.currentStep) {
            badge.className = 'w-10 h-10 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center border-4 border-slate-950 transition-all shadow-lg';
            badge.innerText = i;
        } else {
            badge.className = 'w-10 h-10 rounded-full bg-slate-800 text-slate-400 font-bold flex items-center justify-center border-4 border-slate-950 transition-all';
            badge.innerText = i;
        }
    }
    if (window.lucide) lucide.createIcons();
}

// ================= Server-Enforced Solve Execution =================

let pollTimer = null;

async function joinQueueAndStart() {
    if (!state.userToken) {
        openAuthModal();
        return;
    }

    const passInput = document.getElementById('inputPassword');
    const passError = document.getElementById('passwordError');
    const serverErrBox = document.getElementById('solveServerError');
    const serverErrText = document.getElementById('solveServerErrorText');
    const val = passInput.value.trim();

    if (!val) {
        passError.classList.remove('hidden');
        passInput.focus();
        return;
    }
    passError.classList.add('hidden');
    serverErrBox.classList.add('hidden');

    try {
        const res = await fetch('/api/solve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.userToken}`
            },
            body: JSON.stringify({
                studentCode: state.studentCode,
                password: val,
                schoolType: state.schoolType,
                grade: state.grade,
                subject: state.subject
            })
        });

        const data = await res.json();

        if (!res.ok) {
            serverErrText.innerText = data.detail || 'صلاحية الحل غير مفعلة لحسابك.';
            serverErrBox.classList.remove('hidden');
            await refreshUserProfile();
            return;
        }

        state.currentTaskId = data.task_id;
        await refreshUserProfile();

        goToStep(4);
        document.getElementById('queuePosition').innerText = `#${data.position || 1}`;
        document.getElementById('queueTimeEstimated').innerText = `~ ${(data.position || 1) * 3} دقائق`;
        startTaskPolling();
    } catch (e) {
        serverErrText.innerText = 'تعذر الاتصال بالسيرفر، يرجى المحاولة لاحقاً.';
        serverErrBox.classList.remove('hidden');
    }
}

function startTaskPolling() {
    if (pollTimer) clearInterval(pollTimer);

    const checkTask = async () => {
        if (!state.currentTaskId || !state.userToken) return;
        try {
            const res = await fetch(`/api/task-status/${encodeURIComponent(state.currentTaskId)}`, {
                headers: { 'Authorization': `Bearer ${state.userToken}` }
            });
            if (!res.ok) return;
            const result = await res.json();
            const task = result.task;

            if (task.status === 'in_queue') {
                document.getElementById('queuePosition').innerText = `#${task.queue_position}`;
            } else {
                if (state.currentStep !== 5) goToStep(5);
                const bar = document.getElementById('liveProgressBar');
                const percentText = document.getElementById('progressPercentage');
                const statusText = document.getElementById('currentStatusText');
                const logs = document.getElementById('consoleLogs');

                bar.style.width = `${task.progress || 0}%`;
                percentText.innerText = `${task.progress || 0}%`;

                if (task.logs && Array.isArray(task.logs)) {
                    logs.innerHTML = task.logs.map(line =>
                        `<div class="${line.includes('❌') ? 'text-rose-400 font-bold' : (line.includes('✅') ? 'text-emerald-400 font-bold' : 'text-slate-300')}">> ${line}</div>`
                    ).join('');
                    logs.scrollTop = logs.scrollHeight;
                }

                if (task.status === 'completed') {
                    clearInterval(pollTimer);
                    statusText.innerText = 'اكتمل الحل بنجاح 100%! ✅';
                    statusText.className = 'text-emerald-400 font-bold';
                } else if (task.status === 'failed') {
                    clearInterval(pollTimer);
                    statusText.innerText = `توقف الحل: ${task.error || 'حدث خطأ'}`;
                    statusText.className = 'text-rose-400 font-bold';
                }
            }
        } catch (e) {}
    };

    checkTask();
    pollTimer = setInterval(checkTask, 2500);
}

// ================= User Private Task History =================

async function openMyTasksModal() {
    if (!state.userToken) {
        openAuthModal();
        return;
    }
    document.getElementById('myTasksModal').classList.remove('hidden');
    const listEl = document.getElementById('myTasksList');
    listEl.innerHTML = '<div class="text-slate-500 text-center py-6">جاري تحميل حساباتك...</div>';

    try {
        const res = await fetch('/api/my-tasks', {
            headers: { 'Authorization': `Bearer ${state.userToken}` }
        });
        const data = await res.json();
        if (!data.tasks || data.tasks.length === 0) {
            listEl.innerHTML = '<div class="text-slate-500 text-center py-6">لم تقم بإرسال أي حساب للحل بعد.</div>';
            return;
        }

        listEl.innerHTML = data.tasks.map(t => {
            let badge = '<span class="text-amber-400 font-bold">في الطابور</span>';
            if (t.status === 'solving') badge = `<span class="text-blue-400 font-bold">جاري الحل (${t.progress}%)</span>`;
            if (t.status === 'completed') badge = '<span class="text-emerald-400 font-bold">مكتمل 100% ✅</span>';
            if (t.status === 'failed') badge = `<span class="text-rose-400 font-bold">فشل ❌</span>`;

            return `
                <div class="p-3.5 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
                    <div>
                        <div class="font-bold text-white font-mono">${t.student_code}</div>
                        <div class="text-[11px] text-slate-400">${t.subject} | ${t.created_at}</div>
                    </div>
                    <div>${badge}</div>
                </div>
            `;
        }).join('');
    } catch (e) {
        listEl.innerHTML = '<div class="text-rose-400 text-center py-4">تعذر تحميل السجل.</div>';
    }
}

function closeMyTasksModal() {
    document.getElementById('myTasksModal').classList.add('hidden');
}

function resetApp() {
    if (pollTimer) clearInterval(pollTimer);
    state.studentCode = '';
    state.password = '';
    state.currentTaskId = null;
    document.getElementById('inputStudentCode').value = '';
    document.getElementById('inputPassword').value = '';
    document.getElementById('solveServerError').classList.add('hidden');
    goToStep(1);
}
