// B1-R12: component styles use design tokens only (see src/ui/tokens.css).
const COLOR_PROPS = [
  "color",
  "background",
  "background-color",
  "fill",
  "stroke",
  "outline-color",
  "/^border(-.+)?-color$/",
];
const SPACING_PROPS = ["/^(margin|padding)(-.+)?$/", "gap", "row-gap", "column-gap"];

// calc() is allowed only with var(--…) operands and unitless numbers, e.g. calc(var(--space-1) * 2).
const TOKEN_CALC = String(/^calc\((?:var\(--[\w-]+\)|-?\d*\.?\d+(?![\w%.])|[\s+*/()-])+\)$/);

export default {
  plugins: ["stylelint-declaration-strict-value"],
  rules: {
    "color-no-hex": true,
    "color-named": "never",
    "function-disallowed-list": [
      "rgb",
      "rgba",
      "hsl",
      "hsla",
      "hwb",
      "lab",
      "lch",
      "oklab",
      "oklch",
    ],
    "scale-unlimited/declaration-strict-value": [
      [
        ...COLOR_PROPS,
        "font",
        "font-family",
        "font-size",
        "/^border(-.+)?-radius$/",
        ...SPACING_PROPS,
      ],
      {
        ignoreValues: [
          "transparent",
          "currentColor",
          "inherit",
          "initial",
          "unset",
          "none",
          "auto",
          "0",
          "50%",
          TOKEN_CALC,
        ],
        ignoreFunctions: false,
        message: "Use a design token: var(--…) (B1-R12), not ${value} for ${property}",
      },
    ],
  },
};
