import { Link, useParams } from "react-router-dom";
import { useI18n } from "@/lib/i18n";

const DOCS = {
  privacy: {
    en: ["Privacy policy", [
      ["Who we are", "JobPilot is a job-search workspace. We act as the controller of the personal data you give us, under the Saudi Personal Data Protection Law (PDPL) and in line with the GDPR."],
      ["What we collect", "Account details, your CV and its parsed content, job preferences, applications, notes, contacts you add, reminders, and technical logs (IP, device) for security."],
      ["Why we use it", "To provide the service: job matching, AI reviews, CV tailoring, reminders and optional Gmail sending. We rely on your consent and on the contract with you."],
      ["AI processing", "Only the data needed for each task is sent to our AI providers (Anthropic, OpenAI, Google, or NVIDIA if enabled). Data may be processed outside the Kingdom of Saudi Arabia. Providers do not use it to train models."],
      ["Security", "CV files, Gmail access tokens and other secrets are encrypted at rest. Access is logged."],
      ["Your rights", "You can access, correct, export (Settings → Privacy → Export) and permanently delete your data and account at any time, and withdraw any consent."],
      ["Retention", "We keep your data while your account is active. Deleting your account removes your CVs, files, applications and connected-account access."],
      ["Contact", "For privacy requests, contact the JobPilot team from within the app."]]],
    ar: ["سياسة الخصوصية", [
      ["من نحن", "JobPilot مساحة عمل للبحث عن وظيفة. نحن المتحكم في بياناتك الشخصية وفق نظام حماية البيانات الشخصية السعودي وبما يتوافق مع اللائحة الأوروبية GDPR."],
      ["ما نجمعه", "بيانات الحساب، سيرتك الذاتية ومحتواها المحلَّل، تفضيلات البحث، الطلبات، الملاحظات، جهات الاتصال التي تضيفها، التذكيرات، وسجلات تقنية لأغراض الأمان."],
      ["لماذا نستخدمها", "لتقديم الخدمة: مطابقة الوظائف، المراجعة بالذكاء الاصطناعي، تخصيص السيرة، التذكيرات، والإرسال الاختياري عبر Gmail، استنادًا إلى موافقتك والعقد معك."],
      ["المعالجة بالذكاء الاصطناعي", "نرسل لمزوّدي الذكاء الاصطناعي البيانات اللازمة لكل مهمة فقط، وقد تُعالج خارج المملكة. لا يستخدمها المزوّدون لتدريب النماذج."],
      ["الأمان", "ملفات السيرة الذاتية ورموز الوصول إلى Gmail والأسرار الأخرى مشفّرة، والوصول مسجَّل."],
      ["حقوقك", "يمكنك الاطلاع على بياناتك وتصحيحها وتصديرها وحذفها وحذف حسابك نهائيًا في أي وقت، وسحب أي موافقة."],
      ["الاحتفاظ", "نحتفظ ببياناتك ما دام حسابك نشطًا، وحذف الحساب يزيل السير والملفات والطلبات والوصول للحسابات المرتبطة."],
      ["التواصل", "لطلبات الخصوصية تواصل مع فريق JobPilot من داخل التطبيق."]]],
  },
  terms: {
    en: ["Terms of service", [
      ["The service", "JobPilot helps you organise your job search. We do not apply to jobs on your behalf, and nothing is sent without your explicit approval."],
      ["Your content", "You are responsible for the accuracy of your CV. JobPilot's AI only reorders and rephrases your real data; always review tailored CVs before use."],
      ["Job listings", "Jobs come from official APIs, public company career feeds, and content you add yourself. Listings belong to their publishers and link back to the original source."],
      ["Plans & billing", "Paid plans renew monthly and can be cancelled anytime. Hitting a usage limit never deletes your data."],
      ["Acceptable use", "No spam, no misuse of connected email accounts, no attempts to scrape or abuse the platform."],
      ["Liability", "The service is provided as is. AI output can be wrong; you remain responsible for what you submit to employers."]]],
    ar: ["شروط الخدمة", [
      ["الخدمة", "يساعدك JobPilot على تنظيم بحثك عن عمل. لا نقدّم على الوظائف نيابة عنك، ولا يُرسل أي شيء دون موافقتك الصريحة."],
      ["محتواك", "أنت مسؤول عن دقة سيرتك الذاتية. الذكاء الاصطناعي يعيد ترتيب بياناتك الحقيقية وصياغتها فقط؛ راجع السيرة المخصصة دائمًا قبل استخدامها."],
      ["إعلانات الوظائف", "تأتي الوظائف من واجهات برمجية رسمية وصفحات توظيف عامة للشركات ومحتوى تضيفه بنفسك، وتبقى ملكًا لناشريها مع رابط للمصدر."],
      ["الخطط والدفع", "تتجدد الخطط المدفوعة شهريًا ويمكن إلغاؤها في أي وقت، والوصول إلى حد الاستخدام لا يحذف بياناتك."],
      ["الاستخدام المقبول", "يُمنع الإزعاج وإساءة استخدام البريد المرتبط ومحاولات الكشط أو إساءة استخدام المنصة."],
      ["المسؤولية", "تُقدَّم الخدمة كما هي. قد تخطئ مخرجات الذكاء الاصطناعي، وتبقى مسؤولًا عمّا تقدمه لأصحاب العمل."]]],
  },
};

export default function Legal() {
  const { doc } = useParams();
  const { lang, setLang } = useI18n();
  const [title, sections] = (DOCS[doc] || DOCS.privacy)[lang];
  return (
    <div className="mx-auto max-w-3xl px-5 py-12" data-testid={`legal-${doc}`}>
      <div className="flex items-center justify-between"><Link to="/" className="font-heading font-bold">JobPilot</Link>
        <button onClick={() => setLang(lang === "ar" ? "en" : "ar")} className="text-sm text-emerald-800">{lang === "ar" ? "English" : "العربية"}</button></div>
      <h1 className="mt-10 font-heading text-4xl font-bold tracking-tight">{title}</h1>
      <p className="mt-2 font-mono text-xs text-slate-400">v1.0 · 2026-06</p>
      <div className="mt-8 space-y-6">{sections.map(([h, p]) => <section key={h}><h2 className="font-heading text-lg font-semibold">{h}</h2><p className="mt-1 text-slate-600">{p}</p></section>)}</div>
    </div>
  );
}
