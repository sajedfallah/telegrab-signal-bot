import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  CircleDollarSign,
  Crown,
  Headphones,
  Home,
  Lock,
  Radio,
  RefreshCw,
  Shield,
  Zap,
} from "lucide-react";

type J = Record<string, any>;
type Page = "home" | "signals" | "trade" | "plans" | "support" | "admin";
const tg = window.Telegram?.WebApp;
async function api(path: string, options: RequestInit = {}) {
  const h = new Headers(options.headers);
  h.set("Content-Type", "application/json");
  if (tg?.initData) h.set("X-Telegram-Init-Data", tg.initData);
  const r = await fetch("/api/v1/miniapp" + path, { ...options, headers: h });
  if (!r.ok) {
    let m = "خطا در ارتباط";
    try {
      m = (await r.json()).detail || m;
    } catch {}
    throw new Error(m);
  }
  return r.status === 204 ? null : r.json();
}
const fmt = (v: any) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 }).format(
    Number(v || 0),
  );
const dt = (v: any) =>
  v
    ? new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium" }).format(
        new Date(v),
      )
    : "—";

function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: any;
  className?: string;
}) {
  return (
    <section className={"card " + className}>
      {title && <h3>{title}</h3>}
      {children}
    </section>
  );
}
function Badge({ value }: { value: any }) {
  const s = String(value || "—").toUpperCase();
  return (
    <span
      className={
        "badge " +
        (s.includes("ACTIVE") || s.includes("OPEN") || s.includes("APPROVED")
          ? "ok"
          : s.includes("PENDING")
            ? "wait"
            : s.includes("CLOSE") || s.includes("REJECT") || s.includes("BLOCK")
              ? "bad"
              : "")
      }
    >
      {s}
    </span>
  );
}
function Empty() {
  return <div className="empty">داده‌ای برای نمایش وجود ندارد</div>;
}

export default function App() {
  const [page, setPage] = useState<Page>("home"),
    [session, setSession] = useState<J | null>(null),
    [data, setData] = useState<J | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    tg?.ready();
    tg?.expand();
    loadSession();
  }, []);
  async function loadSession() {
    setBusy(true);
    setError("");
    try {
      setSession(await api("/session"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function go(p: Page) {
    setPage(p);
    setData(null);
    setError("");
    if (p === "home") return loadSession();
    setBusy(true);
    try {
      setData(
        await api(
          p === "signals"
            ? "/signals"
            : p === "trade"
              ? "/autotrade"
              : p === "plans"
                ? "/commerce"
                : p === "support"
                  ? "/support"
                  : "/admin/data",
        ),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function toast(msg: string) {
    tg?.HapticFeedback?.impactOccurred("light");
    setError(msg);
    setTimeout(() => setError(""), 2600);
  }
  if (!session && !busy)
    return (
      <main className="gate">
        <img
          className="gateLogo"
          src="/miniapp/assets/nexus-logo.png"
          alt="NEXUS"
        />
        <h1>NEXUS</h1>
        <p>{error || "این مینی‌اپ را از داخل ربات NEXUS باز کنید."}</p>
        <button onClick={loadSession}>تلاش دوباره</button>
      </main>
    );
  return (
    <div className="app">
      <header>
        <img
          className="headerLogo"
          src="/miniapp/assets/nexus-logo.png"
          alt="NEXUS"
        />
        <div>
          <small>NEXUS AUTO TRADE</small>
          <h1>سلام، {session?.user?.first_name || "کاربر"}</h1>
        </div>
        <button
          className="icon"
          onClick={() => go(page)}
          aria-label="بروزرسانی"
        >
          <RefreshCw size={18} />
        </button>
      </header>
      {error && <div className="toast">{error}</div>}
      {busy && <div className="loading" />}
      <main>
        {page === "home" && session && <HomePage s={session} go={go} />}{" "}
        {page === "signals" && data && <Signals d={data} />}{" "}
        {page === "trade" && data && (
          <Trade d={data} reload={() => go("trade")} toast={toast} />
        )}{" "}
        {page === "plans" && data && <Plans d={data} s={session!} />}{" "}
        {page === "support" && data && (
          <Support d={data} reload={() => go("support")} toast={toast} />
        )}{" "}
        {page === "admin" && data && (
          <Admin d={data} reload={() => go("admin")} toast={toast} />
        )}
      </main>
      <nav>
        {(
          [
            ["home", Home, "خانه"],
            ["signals", BarChart3, "سیگنال"],
            ["trade", Bot, "اتو ترید"],
            ["plans", CircleDollarSign, "اشتراک"],
            ["support", Headphones, "پشتیبانی"],
          ] as any[]
        ).map(([p, I, l]) => (
          <button
            className={page === p ? "active" : ""}
            onClick={() => go(p)}
            key={p}
          >
            <I size={20} />
            <span>{l}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}

function HomePage({ s, go }: { s: J; go: (p: Page) => void }) {
  const active = s.entitlements.vip || s.entitlements.autotrade;
  function open(url: string) {
    if (!url) return;
    tg?.openTelegramLink
      ? tg.openTelegramLink(url)
      : window.open(url, "_blank");
  }
  async function vip() {
    if (!s.entitlements.vip) return go("plans");
    try {
      const x = await api("/vip-channel-link", { method: "POST" });
      open(x.url);
    } catch {
      go("plans");
    }
  }
  return (
    <>
      <Card className="hero">
        <div className="heroTop">
          <div>
            <small>وضعیت حساب</small>
            <h2>{active ? "اشتراک فعال" : "حساب رایگان"}</h2>
          </div>
          <Badge value={active ? "ACTIVE" : "FREE"} />
        </div>
        <div className="metrics">
          <div>
            <b>{fmt(s.referral.points)}</b>
            <span>امتیاز</span>
          </div>
          <div>
            <b>{s.level?.fa || "Bronze"}</b>
            <span>سطح</span>
          </div>
          <div>
            <b>{s.mt5 ? "متصل" : "قطع"}</b>
            <span>MT5</span>
          </div>
        </div>
      </Card>
      <div className="grid2">
        <button className="quick" onClick={() => go("signals")}>
          <Zap />
          <b>سیگنال‌ها</b>
          <span>فرصت‌های فعال</span>
        </button>
        <button className="quick" onClick={() => go("trade")}>
          <Activity />
          <b>معاملات من</b>
          <span>وضعیت زنده</span>
        </button>
      </div>
      <div className="channelGrid">
        <button className="channel public" onClick={() => open(s.links.public)}>
          <img src="/miniapp/assets/nexus-logo.png" />
          <span>
            <b>ورود به NEXUS</b>
            <small>کانال رسمی نکسوس</small>
          </span>
          <Radio />
        </button>
        <button className="channel vip" onClick={vip}>
          <img src="/miniapp/assets/nexus-vip.png" />
          <span>
            <b>کانال سیگنال VIP</b>
            <small>
              {s.entitlements.vip
                ? "ورود به کانال خصوصی"
                : "نیازمند خرید اشتراک"}
            </small>
          </span>
          {s.entitlements.vip ? <Crown /> : <Lock />}
        </button>
      </div>
      <Card title="دسترسی‌ها">
        <div className="rows">
          <div>
            <span>کانال VIP</span>
            <Badge value={s.entitlements.vip ? "ACTIVE" : "LOCKED"} />
          </div>
          <div>
            <span>AutoTrade</span>
            <Badge value={s.entitlements.autotrade ? "ACTIVE" : "LOCKED"} />
          </div>
          <div>
            <span>انقضا</span>
            <b>{dt(s.license?.expires_at)}</b>
          </div>
        </div>
      </Card>
      {s.user.is_admin && (
        <button className="adminEntry" onClick={() => go("admin")}>
          <Shield />
          ورود به مدیریت مینی‌اپ
        </button>
      )}
    </>
  );
}

function Signals({ d }: { d: J }) {
  return (
    <>
      <div className="title">
        <div>
          <h2>سیگنال‌ها و معاملات امروز</h2>
          <small>به وقت تهران</small>
        </div>
        <span>{d.items.length} مورد</span>
      </div>
      {d.items.length ? (
        d.items.map((x: J) =>
          x.locked ? (
            <Card key={x.id} className="signal lockedSignal">
              <div className="signalHead">
                <div>
                  <b>{x.symbol}</b>
                  <small>سیگنال اختصاصی VIP</small>
                </div>
                <Badge value={x.status} />
              </div>
              <div className="lockMessage">
                <img src="/miniapp/assets/nexus-vip.png" />
                <Lock />
                <b>جزئیات این سیگنال قفل است</b>
                <p>
                  برای مشاهده نقطه ورود، حد ضرر و اهداف، اشتراک VIP تهیه کنید.
                </p>
                <button
                  onClick={() =>
                    document
                      .querySelector<HTMLButtonElement>(
                        "nav button:nth-child(4)",
                      )
                      ?.click()
                  }
                >
                  خرید اشتراک VIP
                </button>
              </div>
            </Card>
          ) : (
            <Card key={x.id} className="signal">
              <div className="signalHead">
                <div>
                  <b>{x.symbol}</b>
                  <small>
                    {x.code} · {x.timeframe}
                  </small>
                </div>
                <div>
                  <small className="channelTag">{x.channel}</small>
                  <Badge value={x.status} />
                </div>
              </div>
              <div className="priceGrid">
                <div>
                  <span>جهت</span>
                  <b className={x.direction === "BUY" ? "buy" : "sell"}>
                    {x.direction}
                  </b>
                </div>
                <div>
                  <span>ورود</span>
                  <b>{x.entry_price}</b>
                </div>
                <div>
                  <span>حد ضرر</span>
                  <b>{x.stop_loss}</b>
                </div>
              </div>
              <div className="targets">
                {x.targets.map((t: J) => (
                  <span key={t.target_no}>
                    TP{t.target_no} <b>{t.price}</b>
                  </span>
                ))}
              </div>
              <footer>
                <span>{x.trailing_code || "بدون تریلینگ"}</span>
                <span>{dt(x.created_at)}</span>
              </footer>
            </Card>
          ),
        )
      ) : (
        <Empty />
      )}
    </>
  );
}

function Trade({
  d,
  reload,
  toast,
}: {
  d: J;
  reload: () => void;
  toast: (x: string) => void;
}) {
  const [r, setR] = useState({
    ...d.risk,
    emergency_stop: !!d.risk.emergency_stop,
  });
  async function save() {
    try {
      await api("/risk", { method: "PUT", body: JSON.stringify(r) });
      toast("تنظیمات ذخیره شد");
      reload();
    } catch (e: any) {
      toast(e.message);
    }
  }
  return (
    <>
      <div className="title">
        <h2>AutoTrade</h2>
        <Badge value={d.account ? "CONNECTED" : "OFFLINE"} />
      </div>
      <div className="metrics top">
        <div>
          <b>{fmt(d.today.net_pnl)}$</b>
          <span>سود امروز</span>
        </div>
        <div>
          <b>{fmt(d.open.length)}</b>
          <span>باز</span>
        </div>
        <div>
          <b>{fmt(d.today.closed)}</b>
          <span>بسته</span>
        </div>
      </div>
      <Card title="مدیریت ریسک">
        <label>
          مرجع تنظیمات
          <select
            value={r.management_mode}
            onChange={(e) => setR({ ...r, management_mode: e.target.value })}
          >
            <option value="SELF">تنظیم شخصی</option>
            <option value="ADMIN">اختیار ادمین</option>
          </select>
        </label>
        <div className="form2">
          <label>
            ریسک هر معامله
            <input
              type="number"
              step=".1"
              value={r.risk_percent}
              onChange={(e) => setR({ ...r, risk_percent: +e.target.value })}
            />
          </label>
          <label>
            حد زیان روزانه
            <input
              type="number"
              value={r.max_daily_loss}
              onChange={(e) => setR({ ...r, max_daily_loss: +e.target.value })}
            />
          </label>
          <label>
            حداکثر معاملات باز
            <input
              type="number"
              value={r.max_open_trades}
              onChange={(e) => setR({ ...r, max_open_trades: +e.target.value })}
            />
          </label>
          <label>
            حداکثر معاملات روزانه
            <input
              type="number"
              value={r.max_daily_trades}
              onChange={(e) =>
                setR({ ...r, max_daily_trades: +e.target.value })
              }
            />
          </label>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={r.emergency_stop}
            onChange={(e) => setR({ ...r, emergency_stop: e.target.checked })}
          />
          <span>توقف اضطراری معاملات جدید</span>
        </label>
        <button onClick={save}>ذخیره تنظیمات</button>
      </Card>
      <Card title="معاملات باز">
        {d.open.length ? (
          d.open.map((x: J) => (
            <div className="tradeRow" key={x.ticket}>
              <div>
                <b>{x.symbol}</b>
                <small>#{x.ticket}</small>
              </div>
              <Badge value={x.status} />
            </div>
          ))
        ) : (
          <Empty />
        )}
      </Card>
    </>
  );
}

function Plans({ d, s }: { d: J; s: J }) {
  const [selected, setSelected] = useState("");
  const [category, setCategory] = useState<"vip" | "autotrade" | "bundle">(
    "vip",
  );
  const [method, setMethod] = useState<"CARD" | "USDT">("USDT");
  const [ref, setRef] = useState("");
  const [msg, setMsg] = useState("");
  const plans = d.plans.filter((p: J) => p.category === category);
  async function submit() {
    if (!selected || ref.trim().length < 4)
      return setMsg("پلن و کد پیگیری را وارد کنید");
    try {
      await api("/payments", {
        method: "POST",
        body: JSON.stringify({ plan_code: selected, method, reference: ref }),
      });
      setMsg("پرداخت برای بررسی ادمین ثبت شد");
      setRef("");
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  return (
    <>
      <div className="title">
        <h2>اشتراک‌ها</h2>
        <Badge value={s.license?.status || "FREE"} />
      </div>
      <div className="planTabs">
        <button
          className={category === "vip" ? "active" : ""}
          onClick={() => {
            setCategory("vip");
            setSelected("");
          }}
        >
          VIP
        </button>
        <button
          className={category === "autotrade" ? "active" : ""}
          onClick={() => {
            setCategory("autotrade");
            setSelected("");
          }}
        >
          AutoTrade
        </button>
        <button
          className={category === "bundle" ? "active" : ""}
          onClick={() => {
            setCategory("bundle");
            setSelected("");
          }}
        >
          AutoTrade + VIP
        </button>
      </div>
      {plans.map((p: J) => (
        <Card key={p.code} className="plan">
          <div>
            <small>
              {category === "vip"
                ? "VIP SIGNAL"
                : category === "bundle"
                  ? "AUTO TRADE + VIP"
                  : "AUTO TRADE"}
            </small>
            <h3>{p.fa || p.en || p.code}</h3>
            <p>{p.days} روز دسترسی</p>
          </div>
          <div className="planPrice">
            <b>{p.price_usdt}</b>
            <span>USDT</span>
          </div>
          <button onClick={() => setSelected(p.code)}>انتخاب</button>
        </Card>
      ))}
      <Card title="ثبت پرداخت">
        <label>
          روش پرداخت
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value as any)}
          >
            <option value="USDT">تتر ({d.payment.usdt_network})</option>
            <option value="CARD">کارت بانکی</option>
          </select>
        </label>
        <div className="paymentBox">
          {method === "USDT" ? (
            <>
              <small>آدرس کیف پول</small>
              <b>{d.payment.usdt_wallet || "توسط ادمین تنظیم نشده"}</b>
            </>
          ) : (
            <>
              <small>شماره کارت به نام {d.payment.owner}</small>
              <b>{d.payment.card}</b>
            </>
          )}
        </div>
        <label>
          پلن
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">انتخاب کنید</option>
            {plans.map((p: J) => (
              <option key={p.code} value={p.code}>
                {p.fa || p.code}
              </option>
            ))}
          </select>
        </label>
        <label>
          هش تراکنش / کد پیگیری
          <input
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            placeholder="کد قابل بررسی"
          />
        </label>
        <button className="primary" onClick={submit}>
          ثبت برای تأیید ادمین
        </button>
        {msg && <p>{msg}</p>}
      </Card>
      <Card title="پرداخت‌های من">
        {d.payments.length ? (
          d.payments.map((p: J) => (
            <div className="tradeRow" key={p.id}>
              <div>
                <b>{p.plan_code}</b>
                <small>{dt(p.created_at)}</small>
              </div>
              <Badge value={p.status} />
            </div>
          ))
        ) : (
          <Empty />
        )}
      </Card>
    </>
  );
}

function Support({
  d,
  reload,
  toast,
}: {
  d: J;
  reload: () => void;
  toast: (x: string) => void;
}) {
  const [f, setF] = useState({ subject: "", message: "", priority: "NORMAL" });
  async function send() {
    try {
      await api("/support", { method: "POST", body: JSON.stringify(f) });
      setF({ subject: "", message: "", priority: "NORMAL" });
      toast("درخواست ثبت شد");
      reload();
    } catch (e: any) {
      toast(e.message);
    }
  }
  return (
    <>
      <div className="title">
        <h2>پشتیبانی</h2>
      </div>
      <Card title="درخواست جدید">
        <label>
          موضوع
          <input
            value={f.subject}
            onChange={(e) => setF({ ...f, subject: e.target.value })}
          />
        </label>
        <label>
          پیام
          <textarea
            rows={4}
            value={f.message}
            onChange={(e) => setF({ ...f, message: e.target.value })}
          />
        </label>
        <button onClick={send}>ارسال درخواست</button>
      </Card>
      {d.items.map((x: J) => (
        <Card key={x.id}>
          <div className="signalHead">
            <b>{x.subject}</b>
            <Badge value={x.status} />
          </div>
          <p>{x.message}</p>
          {x.admin_reply && <div className="reply">پاسخ: {x.admin_reply}</div>}
        </Card>
      ))}
    </>
  );
}

function Admin({
  d,
  reload,
  toast,
}: {
  d: J;
  reload: () => void;
  toast: (x: string) => void;
}) {
  type Section = "hub" | "users" | "finance" | "rewards" | "signals" | "marketing" | "reports" | "system";
  const [tab, setTab] = useState<Section>("hub");
  async function act(path: string, body: J = {}, method = "POST") {
    try {
      await api(path, { method, body: JSON.stringify(body) });
      toast("عملیات ثبت شد");
      reload();
    } catch (e: any) {
      toast(e.message);
    }
  }
  const modules: [Section,string,string][] = [
    ["users","👥","کاربران و اشتراک‌ها"],["finance","💳","مالی، پلن و پرداخت"],
    ["rewards","🎁","رفرال و وفاداری"],["signals","📈","مرکز سیگنال"],
    ["marketing","📣","کمپین و پیام‌رسانی"],["reports","📊","گزارش‌ها و آمار"],
    ["system","⚙️","سیستم، CRM و اتوترید"],
  ];
  const setting = (key:string,label:string) => { const value=prompt(label,String(d.settings[key]??"")); if(value!==null) act("/admin/settings",{key,value},"PUT") };
  const newDiscount=()=>{const code=prompt("کد تخفیف");const percent=prompt("درصد تخفیف");if(code&&percent)act("/admin/discounts",{code,percent:+percent,expires_days:30,max_uses:null})};
  const newCampaign=()=>{const title=prompt("عنوان کمپین");const percent=prompt("درصد تخفیف");if(title&&percent)act("/admin/campaigns",{title_fa:title,title_en:"NEXUS Campaign",percent:+percent,days:7,plan_code:null,audience:"all",max_uses:null})};
  const broadcast=()=>{const message=prompt("متن پیام همگانی");if(message)act("/admin/broadcast",{audience:"ALL",message,channels:["TELEGRAM"]})};
  return (
    <>
      <div className="title">
        <div><h2>مرکز مدیریت NEXUS</h2><small>تمام ابزارهای ادمین ربات</small></div>
        <Shield />
      </div>
      {tab!=="hub"&&<button className="adminBack" onClick={()=>setTab("hub")}>→ بازگشت به منوی مدیریت</button>}
      {tab==="hub"&&<><div className="adminMetrics"><div><b>{fmt(d.overview.stats.users)}</b><span>کاربر</span></div><div><b>{fmt(d.overview.stats.pending)}</b><span>پرداخت در انتظار</span></div><div><b>{fmt(d.overview.signal_stats.active)}</b><span>سیگنال فعال</span></div></div><div className="adminModules">{modules.map(([key,icon,label])=><button onClick={()=>setTab(key)} key={key}><i>{icon}</i><b>{label}</b><small>ورود به بخش</small></button>)}</div></>}
      {tab==="users"&&<><Card title="کاربران، اشتراک و تمدید"><div className="sectionTools"><span>کاربران</span><span>اشتراک‌ها</span><span>سطح کاربران</span><span>تمدید و انقضا</span><span>Trial VIP</span></div></Card>{d.users.map((x:J)=><Card key={x.telegram_id}><div className="signalHead"><div><b>{x.first_name||x.username||x.telegram_id}</b><small>{x.telegram_id} · {x.points_balance} امتیاز</small></div><Badge value={x.status}/></div><div className="actions"><button onClick={()=>act(`/admin/users/${x.telegram_id}/action`,{action:"EXTEND",value:30})}>+۳۰ روز</button><button onClick={()=>act(`/admin/users/${x.telegram_id}/action`,{action:"TRIAL",value:3})}>Trial ۳ روزه</button><button onClick={()=>act(`/admin/users/${x.telegram_id}/action`,{action:"ADD_POINTS",value:100})}>+۱۰۰ امتیاز</button><button className="danger" onClick={()=>act(`/admin/users/${x.telegram_id}/action`,{action:x.status==="BLOCKED"?"UNBLOCK":"BLOCK",value:1})}>{x.status==="BLOCKED"?"رفع مسدودی":"مسدود"}</button><button className="danger" onClick={()=>act(`/admin/users/${x.telegram_id}/action`,{action:"CANCEL",value:1})}>لغو VIP</button></div></Card>)}</>}
      {tab==="finance"&&<><Card title="مالی و پرداخت"><div className="sectionTools"><span>پرداخت‌های در انتظار</span><span>پلن‌ها و قیمت‌ها</span><span>تخفیف‌ها</span><span>نرخ تتر/ریال</span></div><button onClick={()=>setting("usdt_irr_rate","نرخ جدید تتر/ریال")}>💱 نرخ فعلی: {d.settings.usdt_irr_rate||"تنظیم نشده"}</button> <button onClick={newDiscount}>+ ساخت تخفیف</button></Card>{d.payments.filter((x:J)=>x.status==="pending").map((x:J)=><Card key={x.id}><b>{x.plan_code} · {x.telegram_id}</b><div className="actions"><button onClick={()=>act(`/admin/payments/${x.id}/review`,{approve:true})}>تأیید</button><button className="danger" onClick={()=>act(`/admin/payments/${x.id}/review`,{approve:false})}>رد</button></div></Card>)}<Card title="مدیریت پلن‌ها">{d.plans.map((p:J)=><div className="tradeRow" key={p.code}><div><b>{p.code}</b><small>{p.price_usdt||p.usdt_price} USDT · {p.days} روز</small></div><div className="actions"><button onClick={()=>{const v=prompt("قیمت USDT",p.price_usdt||p.usdt_price);if(v)act(`/admin/plans/${p.code}`,{price_usdt:v},"PUT")}}>قیمت</button><button onClick={()=>act(`/admin/plans/${p.code}`,{active:!p.active},"PUT")}>{p.active?"غیرفعال":"فعال"}</button></div></div>)}</Card><Card title="کدهای تخفیف">{d.discounts.map((x:J)=><div className="tradeRow" key={x.id}><b>{x.code} · {x.percent}%</b><button onClick={()=>act(`/admin/discounts/${x.id}?active=${!x.active}`,{},"PUT")}>{x.active?"توقف":"فعال"}</button></div>)}</Card></>}
      {tab==="rewards"&&<><Card title="تنظیمات رفرال و امتیاز"><div className="actions"><button onClick={()=>setting("referral_reward_points","پاداش هر دعوت")}>🎁 پاداش دعوت: {d.settings.referral_reward_points}</button><button onClick={()=>setting("points_per_discount_percent","امتیاز لازم برای هر درصد")}>📐 نرخ امتیاز/تخفیف</button><button onClick={()=>setting("points_discount_cap_percent","سقف تخفیف امتیازی")}>🛡 سقف تخفیف</button></div></Card><Card title="🏆 رتبه‌بندی دعوت‌ها">{d.leaderboard.length?d.leaderboard.map((x:J,i:number)=><div className="tradeRow" key={x.telegram_id}><b>{i+1}. {x.first_name||x.username||x.telegram_id}</b><span>{x.referrals} دعوت · {x.points} امتیاز</span></div>):<Empty/>}</Card></>}
      {tab==="signals"&&<><Card title="مرکز سیگنال"><div className="sectionTools"><span>سیگنال فعال</span><span>نتایج بسته‌شده</span><span>همگام‌سازی زنده</span><span>آمار سیگنال</span><span>راهنمای تریلینگ</span></div><div className="actions"><button onClick={()=>{const symbol=prompt("نماد","XAUUSD");if(symbol)act("/admin/signals",{market_type:"GOLD",symbol,direction:"BUY",timeframe:"M5",order_type:"MARKET",entry_price:2400,stop_loss:2390,targets:[2410],risk_percent:1,destination:"BOTH",volume_mode:"RISK",trailing_code:"NEXUS_TRAIL_07"})}}>+ صدور سیگنال</button><button onClick={reload}>🔄 همگام‌سازی</button></div></Card>{d.signals.map((x:J)=><Card key={x.id}><div className="signalHead"><b>{x.code} · {x.symbol} · {x.direction}</b><Badge value={x.status}/></div><div className="actions"><button onClick={()=>act("/admin/trade-command",{signal_id:x.id,command:"MOVE_SL_TO_ENTRY"})}>BE</button><button onClick={()=>act("/admin/trade-command",{signal_id:x.id,command:"ACTIVATE_TRAILING",value:x.trailing_code||"NEXUS_TRAIL_07"})}>Trailing</button><button className="danger" onClick={()=>act("/admin/trade-command",{signal_id:x.id,command:"CLOSE_SIGNAL"})}>بستن</button></div></Card>)}</>}
      {tab==="marketing"&&<><Card title="کمپین و پیام‌رسانی"><div className="sectionTools"><span>کمپین‌ها</span><span>ارسال پیام</span><span>تخفیف مناسبتی</span><span>همه / VIP / رایگان / منقضی / امتیاز بالا</span></div><div className="actions"><button onClick={newCampaign}>+ ساخت کمپین</button><button onClick={broadcast}>📣 ارسال همگانی تلگرام</button></div></Card>{d.campaigns.map((x:J)=><Card key={x.id}><div className="signalHead"><b>{x.title_fa} · {x.percent}%</b><Badge value={x.active?"ACTIVE":"OFF"}/></div><button onClick={()=>act(`/admin/campaigns/${x.id}?active=${!x.active}`,{},"PUT")}>{x.active?"توقف":"فعال‌سازی"}</button></Card>)}<Card title="صف ارسال‌ها">{d.jobs.map((x:J)=><div className="tradeRow" key={x.id}><b>{x.audience} · {x.channels}</b><Badge value={x.status}/></div>)}</Card></>}
      {tab==="reports"&&<><div className="adminMetrics"><div><b>{fmt(d.overview.dashboard.revenue_today_usdt)}$</b><span>درآمد امروز</span></div><div><b>{fmt(d.overview.dashboard.revenue_month_usdt)}$</b><span>درآمد ماه</span></div><div><b>{fmt(d.overview.stats.active)}</b><span>اشتراک فعال</span></div></div><Card title="گزارش‌ها"><div className="sectionTools"><span>گزارش امروز</span><span>گزارش هفتگی</span><span>آمار کلی</span><span>داشبورد CRM</span><span>آمار سیگنال</span><span>Audit Log</span></div></Card><Card title="آخرین رویدادها">{d.audit.map((x:J)=><div className="tradeRow" key={x.id}><div><b>{x.action}</b><small>{dt(x.created_at)}</small></div><span>#{x.target_id||"—"}</span></div>)}</Card></>}
      {tab==="system"&&<><Card title="سیستم، CRM و اتوترید"><div className="sectionTools"><span>بکاپ دیتابیس</span><span>وضعیت کانال‌ها</span><span>مدیریت مشتری و تمدید</span><span>حساب‌های MT5</span><span>لیست انتظار</span><span>ریسک کاربران</span><span>درخواست تغییر حساب</span><span>پشتیبانی</span></div><div className="actions"><button onClick={()=>act("/admin/backup")}>💾 ایجاد بکاپ</button><button onClick={()=>setting("pricing_source","منبع قیمت: manual/api")}>منبع نرخ</button><button onClick={()=>setting("pricing_ttl_minutes","اعتبار نرخ به دقیقه")}>TTL نرخ</button></div></Card><Card title={`🤖 لیست انتظار (${d.waitlist.length})`}>{d.waitlist.map((x:J)=><div className="tradeRow" key={x.telegram_id}><b>{x.first_name||x.username||x.telegram_id}</b><small>{dt(x.created_at)}</small></div>)}</Card><Card title="درخواست تغییر حساب MT5">{d.account_changes.map((x:J)=><div className="tradeRow" key={x.id}><b>{x.old_account_number} ← {x.new_account_number}</b><div className="actions"><button onClick={()=>act(`/admin/account-changes/${x.id}/review`,{approve:true})}>تأیید</button><button className="danger" onClick={()=>act(`/admin/account-changes/${x.id}/review`,{approve:false})}>رد</button></div></div>)}</Card><Card title="تیکت‌های پشتیبانی">{d.tickets.map((x:J)=><div className="tradeRow" key={x.id}><div><b>{x.subject}</b><small>{x.message}</small></div>{x.status!=="CLOSED"&&<button onClick={()=>{const reply=prompt("پاسخ ادمین");if(reply)act(`/admin/support/${x.id}/reply`,{reply,close:true})}}>پاسخ</button>}</div>)}</Card></>}
    </>
  );
}
