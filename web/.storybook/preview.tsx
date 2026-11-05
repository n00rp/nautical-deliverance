import type { Decorator, Preview } from "@storybook/react-vite";
import "../src/reset.css";
import "../src/ui/fonts.css";
import "../src/ui/tokens.css";
import "./preview.css";

// "auto" sets no data-theme, so the OS colour scheme decides (Review Focus 1).
const withTheme: Decorator = (Story, context) => {
  const theme = context.globals["theme"] as string;
  if (theme === "light" || theme === "dark") {
    document.documentElement.setAttribute("data-theme", theme);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  return <Story />;
};

const preview: Preview = {
  decorators: [withTheme],
  globalTypes: {
    theme: {
      description: "Colour theme",
      toolbar: { icon: "circlehollow", items: ["auto", "light", "dark"], dynamicTitle: true },
    },
  },
  initialGlobals: { theme: "auto" },
  parameters: { layout: "centered" },
};
export default preview;
