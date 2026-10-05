/**
 * Every UI string of the SPA (PROMPT.md §7.1). Components never hard-code text.
 * Enum labels (statuses, kinships, governorates, document types…) are NOT here: they come
 * from GET /api/v1/reference-data/ so the server stays the single source.
 * The shape is language-neutral so an `en.ts` with the same keys can be added later.
 */
export const ar = {
  app: {
    union: "اتحاد نقابات المهن الطبية",
    project: "مشروع علاج الأعضاء وأسرهم",
    formTitle: "استمارة اشتراك بمشروع العلاج",
    formSubtitle: "( أول مرة - إضافة )",
    skipToContent: "تخطَّ إلى المحتوى",
  },
  common: {
    loading: "جارٍ التحميل…",
    retry: "إعادة المحاولة",
    close: "إغلاق",
    cancel: "إلغاء",
    backHome: "العودة إلى الصفحة الرئيسية",
    required: "مطلوب",
    optional: "اختياري",
    pageUnderConstruction: "هذه الصفحة قيد الإنشاء وستتوفر قريباً.",
    notFoundTitle: "الصفحة غير موجودة",
    notFoundBody: "تأكد من الرابط أو عد إلى الصفحة الرئيسية.",
    loadFailed: "تعذّر تحميل البيانات.",
  },
  errors: {
    network: "تعذّر الاتصال بالخادم. تحقق من الاتصال بالإنترنت ثم أعد المحاولة.",
    unexpected: "حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.",
    sessionExpired: "انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.",
    panelTitle: "يرجى تصحيح الأخطاء التالية قبل المتابعة:",
  },
  auth: {
    signIn: "تسجيل الدخول",
    createAccount: "إنشاء حساب",
    signOut: "تسجيل الخروج",
    signingOut: "جارٍ تسجيل الخروج…",
    externalNote:
      "يتم تسجيل الدخول وإنشاء الحساب واستعادة كلمة المرور عبر بوابة الدخول الآمنة للاتحاد.",
    callbackErrors: {
      AUTH_FAILED: "تعذّر تسجيل الدخول. يرجى المحاولة مرة أخرى.",
      MFA_REQUIRED: "حسابات المسؤولين تتطلب التحقق بخطوتين.",
      EMAIL_IN_USE: "البريد الإلكتروني مرتبط بحساب آخر. تواصل مع إدارة المشروع.",
      ACCOUNT_DISABLED: "هذا الحساب موقوف. تواصل مع إدارة المشروع.",
      EMAIL_CLAIM_MISSING: "لم يُرسل البريد الإلكتروني من بوابة الدخول. تواصل مع إدارة المشروع.",
    },
    dev: {
      title: "دخول تجريبي (بيئة التطوير فقط)",
      hint: "اختر مستخدماً تجريبياً. هذا الخيار غير موجود في بيئة الإنتاج.",
      signInAs: "الدخول باسم {name}",
      roles: { DOCTOR: "طبيب", ADMIN: "مسؤول" },
    },
    signedOutTitle: "تم تسجيل الخروج",
    signedOutBody: "تم إنهاء جلستك بأمان. يمكنك إغلاق هذه الصفحة أو تسجيل الدخول مرة أخرى.",
  },
  nav: {
    main: "القائمة الرئيسية",
    dashboard: "طلباتي",
    profile: "الملف الشخصي",
    adminDashboard: "لوحة المتابعة",
    adminApplications: "الطلبات",
    adminDoctors: "الأعضاء",
    adminFeeSchedules: "جداول الرسوم",
  },
  landing: {
    title: "اشترك في مشروع العلاج لك ولأسرتك",
    lead:
      "استمارة الاشتراك الورقية أصبحت إلكترونية: املأ بياناتك وبيانات المستفيدين، وارفع المستندات وإيصال الدفع، ثم قدّم الطلب وتابع حالته من مكانك.",
    stepsTitle: "خطوات الاشتراك",
    steps: [
      { title: "بيانات العضو", body: "بيانات النقابة والرقم القومي والعنوان كما في الاستمارة الورقية." },
      { title: "المستفيدون", body: "الزوج أو الزوجة والأبناء والوالدان، حتى عشرة مستفيدين." },
      { title: "المستندات", body: "صور البطاقة والكارنيه وشهادات الميلاد والزواج حسب درجة القرابة." },
      { title: "الإيصال", body: "تُحسب الرسوم تلقائياً، ثم ترفع صورة إيصال الدفع." },
      { title: "المراجعة والتقديم", body: "تراجع الاستمارة وتقر بصحتها، فتحصل على رقم الطلب." },
    ],
    slipCaption: "نموذج من رأس الاستمارة",
    slipPhoto: "صورة العضو الأصلي",
    slipNid: "الرقم القومي :",
  },
  dashboard: {
    greeting: "مرحباً د. {name}",
    greetingFallback: "مرحباً بك",
    myApplications: "طلباتي",
    newApplication: "تقديم طلب جديد",
    activeExists: "لديك طلب نشط للسنة المالية {year}. يمكنك متابعته من القائمة.",
    empty: "لم تقدم أي طلبات بعد",
    emptyHint: "ابدأ استمارة السنة المالية {year}. تُحفظ بياناتك تلقائياً ويمكنك العودة إليها في أي وقت.",
    draftTitle: "مسودة — السنة المالية {year}",
    lastSaved: "آخر حفظ: {when}",
    submittedOn: "تاريخ التقديم: {date}",
    continue: "متابعة",
    view: "عرض",
    correct: "تصحيح وإعادة التقديم",
    reviewNotes: "ملاحظات المراجعة",
    details: "التفاصيل",
    beneficiariesCount: "عدد المستفيدين: {count}",
    noReviewNotes: "لا توجد ملاحظات من المراجعة.",
    profileIncomplete: "أكمل بياناتك الشخصية لتسريع تعبئة الاستمارة.",
    goToProfile: "استكمال الملف الشخصي",
  },
  admin: {
    welcome: "لوحة متابعة الطلبات",
  },
  pages: {
    profile: "الملف الشخصي",
    newApplication: "طلب جديد",
    creatingApplication: "جارٍ تجهيز استمارة السنة المالية…",
    application: "الطلب",
    form: "استمارة الاشتراك",
    payment: "رفع إيصال الدفع",
    review: "المراجعة والتقديم",
    status: "حالة الطلب",
    print: "طباعة الاستمارة",
    adminApplication: "تفاصيل الطلب",
    adminDoctor: "بيانات العضو",
  },
  emptyIllustration: "رسم لاستمارة فارغة",
  stepper: {
    label: "مراحل الاستمارة",
    steps: ["البيانات", "المستفيدون", "المستندات", "الإيصال", "المراجعة"],
    stepStatus: {
      complete: "مكتملة",
      current: "الخطوة الحالية",
      upcoming: "لم تبدأ",
    },
  },
  autosave: {
    saving: "جارٍ الحفظ…",
    saved: "تم الحفظ",
    error: "تعذّر الحفظ — إعادة المحاولة",
  },
  nid: {
    digit: "الرقم {index} من {total}",
  },
  boxString: {
    character: "الحرف {index} من {total}",
  },
  upload: {
    choose: "اختيار ملف",
    replace: "استبدال",
    remove: "إزالة",
    uploading: "جارٍ الرفع… {percent}٪",
    attached: "✓ تم الإرفاق: {name}",
    failed: "تعذّر رفع الملف. يرجى المحاولة مرة أخرى.",
    tooLarge: "حجم الملف أكبر من الحد المسموح ({max}).",
    unsupportedType: "نوع الملف غير مدعوم. الأنواع المسموح بها: صور JPG أو PNG أو WEBP.",
    ocr: "مسح تلقائي",
    ocrRunning: "جارٍ المسح…",
    ocrSuccess: "✓ تم استخراج البيانات — راجع الحقول أدناه وعدّل إن لزم",
    ocrFailed: "فشل المسح التلقائي. يمكنك إدخال البيانات يدوياً.",
    preview: "معاينة {name}",
    megabytes: "{value} ميجابايت",
  },
  documents: {
    modalTitle: "مستندات المستفيد: {name}",
    unnamedBeneficiary: "مستفيد بدون اسم",
    saveAndClose: "حفظ وإغلاق",
    attached: "مرفق",
    missing: "غير مرفق",
  },
  fees: {
    title: "ملخص الرسوم",
    tier: "الدرجة {tier}",
    total: "الإجمالي",
    item: "البند",
    amount: "المبلغ",
    serverNote: "تُحسب الرسوم على الخادم وفق جدول السنة المالية {year}.",
    unavailable: "تعذّر حساب الرسوم الآن.",
  },
  actions: {
    print: "طباعة",
    continueToReceipt: "متابعة لرفع الإيصال",
  },
} as const;

export type Messages = typeof ar;

/**
 * Fill `{name}` placeholders: t(ar.dashboard.greeting, { name: "أحمد" }).
 * Unknown placeholders are left visible so a missing value is noticed, not hidden.
 */
export function t(template: string, vars: Record<string, string | number> = {}): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in vars ? String(vars[key]) : match,
  );
}
