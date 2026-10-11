/**
 * Task 8 · 前端组件测试.
 *
 * 三条断言对应面向前端的三条硬要求：
 * ① 面试官**点开就能看到东西**（不用自己填 30 行表）
 * ② 解析结果**先把行数摆出来让人核对**（Review Focus 3 的界面侧）
 * ③ 报告里**每条发现都带证据**（不能只给个结论）
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const EXAMPLE = {
  items: [
    { seq: 1, university_name: "暨南大学", major_group: "201", claimed_min_score: 612, claimed_rank: 18043, tier: "稳" },
    { seq: 2, university_name: "广东工业大学", major_group: "202", claimed_min_score: 570, claimed_rank: 51302, tier: "冲" },
  ],
  raw_item_count: 2,
  question: "这表稳不稳",
};

const REPORT = {
  mode: "live",
  intent: "stability",
  findings: [
    { seq: 2, kind: "tier_inconsistent", detail: "标为「稳」但实际够不着", claimed: "稳", actual: 51302, evidence: "2025 年 广东工业大学 专业组 202 最低位次 51302" },
  ],
  narrative: "第 2 条 有问题。",
  outcomes: ["rank_conversion"],
  degraded: {},
};

function mockFetch() {
  return vi.fn(async (url: string) => {
    if (url.includes("/example")) return json(EXAMPLE);
    if (url.includes("/confirm")) return json(REPORT);
    return json({});
  });
}
const json = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

describe("App", () => {
  let f: ReturnType<typeof mockFetch>;
  beforeEach(() => {
    f = mockFetch();
    vi.stubGlobal("fetch", f);
  });

  it("① 点「载入示例」就能看到一张已经填好的表，不用自己上传", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /载入示例/ }));
    expect(await screen.findByText(/暨南大学/)).toBeInTheDocument();
  });

  it("② 确认页把**读到的行数**摆出来让人核对", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /载入示例/ }));
    expect(await screen.findByText(/读到 2 条/)).toBeInTheDocument();
  });

  it("③ 报告里每条发现都带证据", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /载入示例/ }));
    await userEvent.click(await screen.findByRole("button", { name: /开始审计/ }));
    await waitFor(() => expect(screen.getByText(/够不着/)).toBeInTheDocument());
    expect(screen.getByText(/最低位次 51302/)).toBeInTheDocument();
  });
});
