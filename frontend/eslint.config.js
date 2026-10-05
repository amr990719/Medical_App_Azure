import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// Physical Tailwind direction utilities do not flip with dir="rtl" (CLAUDE.md, rtl-ui skill).
// A class token (start of string, after whitespace or after a variant colon) that is physical.
const PHYSICAL_CLASS =
  String.raw`(^|\s|:)(-?(ml|mr|pl|pr|left|right|scroll-ml|scroll-mr|scroll-pl|scroll-pr)-|` +
  String.raw`text-(left|right)(\s|$)|float-(left|right)(\s|$)|rounded-(l|r|tl|tr|bl|br)(-|\s|$)|` +
  String.raw`border-(l|r)(-|\s|$)|space-x-)`;
const physicalMessage =
  "Use logical utilities (ms/me/ps/pe/start/end/text-start/rounded-s/border-s) instead of physical left/right.";

export default tseslint.config(
  { ignores: ["dist", "coverage", "playwright-report", "test-results", "src/api/schema.d.ts"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.strict],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "no-restricted-syntax": [
        "error",
        { selector: `Literal[value=/${PHYSICAL_CLASS}/]`, message: physicalMessage },
        { selector: `TemplateElement[value.raw=/${PHYSICAL_CLASS}/]`, message: physicalMessage },
      ],
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}", "src/test/**"],
    rules: {
      "no-restricted-syntax": "off",
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
    },
  },
);
