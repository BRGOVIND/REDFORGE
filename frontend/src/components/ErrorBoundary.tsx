import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Global error boundary — one component throwing must never white-screen the
 * app. Renders a calm, actionable fallback (no stack trace shown to the user;
 * the full error is logged to the console for developers) and offers recovery
 * without a full reload where possible.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Developer-facing only. Never surfaced to the user.
    // eslint-disable-next-line no-console
    console.error('RedForge UI error:', error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-base px-6">
          <div className="w-full max-w-md rounded-xl border border-border bg-surface p-8 text-center">
            <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-lg bg-red-soft">
              <AlertTriangle size={22} className="text-fail" />
            </div>
            <h1 className="text-base font-semibold text-content">Something went wrong</h1>
            <p className="mt-2 text-sm text-content-muted">
              A part of the interface failed to render. Your data is safe and running locally.
              You can try again, or reload the app.
            </p>
            <div className="mt-6 flex items-center justify-center gap-2">
              <button
                onClick={this.reset}
                className="h-9 rounded-lg bg-red-600 px-4 text-sm font-medium text-white transition-colors hover:bg-red-500 rf-focus"
              >
                Try again
              </button>
              <button
                onClick={() => window.location.assign('/')}
                className="h-9 rounded-lg border border-border bg-overlay px-4 text-sm text-content transition-colors hover:border-border-strong rf-focus"
              >
                Reload RedForge
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
