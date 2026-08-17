import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceBadge } from "./SourceBadge";

describe("SourceBadge", () => {
  it("opens external provenance safely", () => {
    render(
      <SourceBadge
        source={{
          source_id: "fifa",
          name: "FIFA",
          url: "https://inside.fifa.com/",
          consulted_at: "2026-08-17",
          quality: "A",
          official: true,
          status: "enabled"
        }}
      />
    );
    const link = screen.getByRole("link", { name: /A · FIFA/ });
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
