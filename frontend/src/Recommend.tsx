import { useState } from "react";

type Rec = { university_name: string; major_group: string; tier: string; reason: string };
type Finding = { seq: number; kind: string; detail: string };

/** 推荐面板。**自审结论和推荐一起显示** —— 那是这个功能与审计接成一条链的地方。 */
export default function Recommend() {
  const [recs, setRecs] = useState<Rec[] | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [busy, setBusy] = useState(false);
  const [rank, setRank] = useState(20000);

  async function go() {
    setBusy(true);
    const r = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score: 600, category: "物理类", rank, year: 2025,
                             subjects: ["物理", "化学", "生物"], cities: ["广州"], majors: ["计算机"] }),
    });
    const d = await r.json();
    setRecs(d.recommendations ?? []);
    setFindings(d.findings ?? []);
    setBusy(false);
  }

  return (
    <section className="mt-8 border-t pt-6">
      <h2 className="font-bold">试一下推荐</h2>
      <p className="text-sm text-slate-500">
        它会生成一份方案，**然后用上面的审计器自己审一遍**。
      </p>
      <label className="mt-3 block text-sm">
        你的全省位次：
        <input className="ml-2 w-32 rounded border px-2 py-1" value={rank}
          onChange={(e) => setRank(Number(e.target.value) || 0)} />
        <button className="ml-3 rounded bg-sky-700 px-3 py-1 text-white" onClick={go} disabled={busy}>
          生成推荐
        </button>
      </label>

      {recs && (
        <>
          <h3 className="mt-4 font-medium">推荐 {recs.length} 条</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {recs.map((r) => (
              <li key={`${r.university_name}-${r.major_group}`} className="rounded border p-2">
                <b>{r.university_name}</b> 组{r.major_group} · {r.tier}
                <div className="text-slate-600">{r.reason}</div>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm">
            <b>自审结论：</b>
            {findings.length === 0
              ? "这份方案通过了审计器 —— 0 处问题。"
              : `审计器报出 ${findings.length} 处问题。`}
          </p>
        </>
      )}
    </section>
  );
}
