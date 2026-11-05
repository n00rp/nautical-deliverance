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
      [...COLOR_PROPS, "font-family", "font-size", ...SPACING_PROPS],
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
        ],
        ignoreFunctions: false,
        message: "Use a design token: var(--…) (B1-R12), not ${value} for ${property}",
      },
    ],
  },
};
