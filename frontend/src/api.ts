/** 后端接口的薄封装。前端只管展示，不做业务判断。 */
export type Item = {
  seq: number;
  university_name: string;
  major_group: string;
  claimed_min_score: number | null;
  claimed_rank: number | null;
  tier: string | null;
};

export type Finding = {
  seq: number;
  kind: string;
  detail: string;
  claimed: unknown;
  actual: unknown;
  evidence: string;
};

export type Report = {
  mode: "live" | "demo";
  reason?: string;
  intent?: string;
  findings: Finding[];
  narrative: string;
  degraded?: Record<string, string> | null;
};

const base = "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await r.json()) as T;
}

export const getExample = () =>
  fetch(`${base}/example`).then((r) => r.json() as Promise<{ items: Item[]; raw_item_count: number; question: string }>);

export const parseScreenshot = async (file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${base}/parse`, { method: "POST", body: fd });
  return (await r.json()) as { items: Item[]; raw_item_count: number; degraded: string | null };
};

export const confirm = (payload: {
  items: Item[];
  question: string;
  category: string;
  year: number;
  candidate_rank: number | null;
  candidate_subjects: string[];
}) => post<Report>("/confirm", payload);
