import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };

type State = { error: Error | null };

export class BootstrapErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Agent Lab UI error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="boot-fallback" role="alert">
          <h1>Agent Lab</h1>
          <p>화면을 불러오지 못했습니다.</p>
          <pre>{this.state.error.message}</pre>
          <p className="boot-fallback-hint">
            앱을 종료한 뒤 터미널에서 <code>make tauri-build</code>로 다시
            빌드하거나, 개발 모드는 <code>make tauri-dev</code>를 사용하세요.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
