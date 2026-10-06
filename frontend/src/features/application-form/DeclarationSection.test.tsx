import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiApplication } from "@/test/fixtures";
import { renderInForm } from "@/test/renderForm";
import { DeclarationSection } from "./DeclarationSection";

describe("DeclarationSection (PROMPT.md §9.7)", () => {
  it("prints the declared name as text, because the inline input clips a long name on paper", async () => {
    const long = "عبد العزيز مصطفى إبراهيم عبد الغفار الشناوي";
    await renderInForm(<DeclarationSection />, { app: apiApplication({ declaration_name: long }) });
    const input = screen.getByLabelText("اسم المقر");
    expect(input).toHaveValue(long);
    expect(input).toHaveClass("print:hidden");
    const printed = input.parentElement?.querySelector("[data-print-value]");
    expect(printed).toHaveTextContent(long);
    expect(printed).toHaveClass("hidden", "print:inline");
  });
});
