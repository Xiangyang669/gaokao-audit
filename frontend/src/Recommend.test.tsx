import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Recommend from "./Recommend";

const json = (b: unknown) => ({ ok: true, json: async () => b }) as Response;
const RESULT = {
  mode: "live",
  recommendations: [{ university_name: "暨南大学", major_group: "201", tier: "稳", reason: "位次相近且合他偏好" }],
  findings: [],
};

describe("Recommend", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn(async () => json(RESULT))));

  it("点一下就能拿到推荐", async () => {
    render(<Recommend />);
    await userEvent.click(screen.getByRole("button", { name: /生成推荐/ }));
    expect(await screen.findByText(/暨南大学/)).toBeInTheDocument();
  });

  it("🔴 自审结论和推荐一起显示", async () => {
    render(<Recommend />);
    await userEvent.click(screen.getByRole("button", { name: /生成推荐/ }));
    expect(await screen.findByText(/自审结论/)).toBeInTheDocument();
    expect(screen.getByText(/0 处问题|通过了审计器/)).toBeInTheDocument();
  });
});
