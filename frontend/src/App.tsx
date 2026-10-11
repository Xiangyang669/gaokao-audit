import { useState } from "react";
import { confirm, getExample, parseScreenshot, type Finding, type Item, type Report } from "./api";
import Recommend from "./Recommend";

type Step = "idle" | "confirm" | "report";

const EMPTY_QUERY = { category: "物理类", year: 2025, candidate_rank: 20000, candidate_subjects: ["物理", "化学", "生物"] };

export default function App() {
  const [step, setStep] = useState<Step>("idle");
  const [items, setItems] = useState<Item[]>([]);
  const [rawCount, setRawCount] = useState(0);
  const [degraded, setDegraded] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadExample() {
    setBusy(true);
    const ex = await getExample();
    setItems(ex.items);
    setRawCount(ex.raw_item_count);
    setQuestion(ex.question);
    setDegraded(null);
    setStep("confirm");
    setBusy(false);
  }

  async function upload(file: File) {
    setBusy(true);
    const out = await parseScreenshot(file);
    setItems(out.items);
    setRawCount(out.raw_item_count);
    setDegraded(out.degraded);
    setStep("confirm");
    setBusy(false);
  }

  async function runAudit() {
    setBusy(true);
    const out = await confirm({ items, question, ...EMPTY_QUERY });
    setReport(out);
    setStep("report");
    setBusy(false);
  }

  return (
    <main className="mx-auto max-w-4xl p-6 text-slate-800">
      <h1 className="text-2xl font-bold">高考志愿方案审计器</h1>
      <p className="mt-1 text-sm text-slate-500">
        它不回答「你该怎么填」，它回答「你这份表里，哪些条目的依据对不上」。
      </p>

      {step === "idle" && (
        <section className="mt-6 space-y-3">
          <button className="rounded bg-slate-800 px-4 py-2 text-white" onClick={loadExample} disabled={busy}>
            载入示例
          </button>
          <label className="ml-3 cursor-pointer text-sm text-slate-600 underline">
            或上传一张志愿表截图
            <input type="file" accept="image/*" className="hidden"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
        </section>
      )}

      {step === "confirm" && (
        <section className="mt-6">
          <div className="rounded bg-amber-50 p-3 text-sm">
            <b>请先核对</b>：我从这张表读到 {rawCount} 条。行数不对、或某一格读错了，直接在下面改。
            {degraded && <span className="ml-2 text-red-600">（解析降级：{degraded}）</span>}
          </div>

          <label className="mt-4 block text-sm">
            你的问题：
            <input className="ml-2 w-80 rounded border px-2 py-1" value={question}
              onChange={(e) => setQuestion(e.target.value)} />
          </label>

          <table className="mt-4 w-full border-collapse text-sm">
            <thead>
              <tr className="bg-slate-100 text-left">
                <th className="border p-2">#</th><th className="border p-2">院校</th>
                <th className="border p-2">专业组</th><th className="border p-2">最低分</th>
                <th className="border p-2">最低位次</th><th className="border p-2">档位</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={it.seq}>
                  <td className="border p-2">{it.seq}</td>
                  <td className="border p-2">{it.university_name}</td>
                  <td className="border p-2">{it.major_group}</td>
                  {(["claimed_min_score", "claimed_rank", "tier"] as const).map((k) => (
                    <td key={k} className="border p-2">
                      <input className="w-full" value={String(it[k] ?? "")}
                        onChange={(e) => {
                          const v = e.target.value;
                          setItems((prev) => prev.map((p, j) => (j === i ? { ...p, [k]: k === "tier" ? v : v === "" ? null : Number(v) } : p)));
                        }} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <button className="mt-4 rounded bg-emerald-700 px-4 py-2 text-white" onClick={runAudit} disabled={busy}>
            开始审计
          </button>
        </section>
      )}

      {step === "report" && report && (
        <section className="mt-6">
          {report.mode === "demo" && (
            <div className="rounded bg-slate-100 p-3 text-sm">
              今日体验额度已用完（{report.reason}），下面是演示报告。
            </div>
          )}
          {report.narrative && <p className="mt-4 whitespace-pre-wrap">{report.narrative}</p>}
          <h2 className="mt-6 font-bold">发现的问题（{report.findings.length}）</h2>
          <ul className="mt-2 space-y-3">
            {report.findings.map((f: Finding) => (
              <li key={`${f.seq}-${f.kind}`} className="rounded border p-3">
                <div className="font-medium">第 {f.seq} 条 · {f.kind}</div>
                <div className="text-sm">{f.detail}</div>
                <div className="mt-1 text-xs text-slate-500">证据：{f.evidence}</div>
              </li>
            ))}
          </ul>
          <button className="mt-6 text-sm underline" onClick={() => setStep("idle")}>回到开始</button>
          <Recommend />
        </section>
      )}
    </main>
  );
}
