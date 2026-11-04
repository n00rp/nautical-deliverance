import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./reset.css";

// No StrictMode: its double effect would run the one-shot OIDC callback twice.
createRoot(document.getElementById("root") as HTMLElement).render(<App />);
