import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "storybook-static", "test-results", ".dependency-cruiser.cjs"] },
  js.configs.recommended,
  tseslint.configs.recommendedTypeChecked,
  jsxA11y.flatConfigs.recommended,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  {
    // B4-R04: money is exact. No binary floats on money paths.
    files: [
      "src/money.ts",
      "src/offerApi.ts",
      "src/ui/NumberField/normalize.ts",
      "src/offers/**",
      "src/nominations/**",
    ],
    ignores: ["**/*.test.ts", "**/*.test.tsx", "**/*.stories.tsx", "**/testSupport.ts"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "Number", message: "No floats on money paths" },
        { name: "parseFloat", message: "No floats on money paths" },
        { name: "parseInt", message: "No floats on money paths" },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.object.name='Number']",
          message: "No floats on money paths",
        },
        {
          selector:
            "CallExpression[callee.property.name=/^(toFixed|toPrecision|toLocaleString|round|parseFloat|parseInt)$/]",
          message: "No floats or locale formatting on money paths",
        },
        {
          selector: "NewExpression[callee.object.name='Intl'][callee.property.name='NumberFormat']",
          message: "Use formatUsd/formatDecimal, not Intl.NumberFormat",
        },
        {
          selector: "UnaryExpression[operator='+'][argument.type!='Literal']",
          message: "Unary + converts to a float",
        },
      ],
    },
  },
  { files: ["**/*.js", "**/*.mjs"], ...tseslint.configs.disableTypeChecked },
);
