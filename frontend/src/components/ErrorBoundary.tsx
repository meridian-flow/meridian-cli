import { Component, type ErrorInfo, type ReactNode } from "react"

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
  /** When any value in this array changes, the error state resets. */
  resetKeys?: ReadonlyArray<unknown>
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.props.onError?.(error, errorInfo)
  }

  componentDidUpdate(prevProps: Readonly<ErrorBoundaryProps>): void {
    if (!this.state.hasError) return
    const prev = prevProps.resetKeys ?? []
    const curr = this.props.resetKeys ?? []
    if (prev.length !== curr.length || prev.some((k, i) => k !== curr[i])) {
      this.setState({ hasError: false, error: null })
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="flex items-center justify-center p-4 text-sm text-destructive">
          <p>Something went wrong.</p>
        </div>
      )
    }
    return this.props.children
  }
}
