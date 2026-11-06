import { Component, type ErrorInfo, type ReactNode } from "react";

/** Keeps a render error in one page from blanking the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  render() {
    return this.state.failed ? (
      <p role="alert">Something went wrong — reload the page</p>
    ) : (
      this.props.children
    );
  }
}
