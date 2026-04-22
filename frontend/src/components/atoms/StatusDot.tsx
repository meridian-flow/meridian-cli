import { cn } from "@/lib/utils"

export type SpawnStatus = 
  | "running" 
  | "queued" 
  | "succeeded" 
  | "failed" 
  | "cancelled" 
  | "finalizing"

interface StatusDotProps {
  status: SpawnStatus
  size?: "sm" | "md" | "lg"
  className?: string
}

const sizeMap = {
  sm: 8,
  md: 10,
  lg: 12,
} as const

export function StatusDot({ status, size = "md", className }: StatusDotProps) {
  const s = sizeMap[size]
  const strokeWidth = s >= 10 ? 1.5 : 1
  const center = s / 2
  const radius = (s - strokeWidth) / 2

  // Smaller icon dimensions for overlays
  const iconSize = s * 0.5
  const iconStroke = s >= 10 ? 1.5 : 1.25

  const baseClasses = cn("inline-block shrink-0", className)

  // Running: filled circle with pulse animation
  if (status === "running") {
    return (
      <svg
        width={s}
        height={s}
        viewBox={`0 0 ${s} ${s}`}
        className={baseClasses}
        style={{ animation: "pulse 1s ease-in-out infinite" }}
      >
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="var(--status-running)"
        />
      </svg>
    )
  }

  // Queued: half-filled circle (bottom half)
  if (status === "queued") {
    return (
      <svg
        width={s}
        height={s}
        viewBox={`0 0 ${s} ${s}`}
        className={baseClasses}
      >
        <defs>
          <clipPath id={`half-clip-${s}`}>
            <rect x={0} y={center} width={s} height={center} />
          </clipPath>
        </defs>
        <circle
          cx={center}
          cy={center}
          r={radius - strokeWidth / 2}
          fill="none"
          stroke="var(--status-queued)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={center}
          cy={center}
          r={radius - strokeWidth / 2}
          fill="var(--status-queued)"
          clipPath={`url(#half-clip-${s})`}
        />
      </svg>
    )
  }

  // Succeeded: filled circle with tiny check overlay
  if (status === "succeeded") {
    const checkPath = `M${center - iconSize / 3} ${center} L${center - iconSize / 8} ${center + iconSize / 4} L${center + iconSize / 3} ${center - iconSize / 4}`
    return (
      <svg
        width={s}
        height={s}
        viewBox={`0 0 ${s} ${s}`}
        className={baseClasses}
      >
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="var(--status-succeeded)"
        />
        <path
          d={checkPath}
          fill="none"
          stroke="white"
          strokeWidth={iconStroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }

  // Failed: filled circle with tiny x overlay
  if (status === "failed") {
    const offset = iconSize / 3
    return (
      <svg
        width={s}
        height={s}
        viewBox={`0 0 ${s} ${s}`}
        className={baseClasses}
      >
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="var(--status-failed)"
        />
        <line
          x1={center - offset}
          y1={center - offset}
          x2={center + offset}
          y2={center + offset}
          stroke="white"
          strokeWidth={iconStroke}
          strokeLinecap="round"
        />
        <line
          x1={center + offset}
          y1={center - offset}
          x2={center - offset}
          y2={center + offset}
          stroke="white"
          strokeWidth={iconStroke}
          strokeLinecap="round"
        />
      </svg>
    )
  }

  // Cancelled: ring only (no fill)
  if (status === "cancelled") {
    return (
      <svg
        width={s}
        height={s}
        viewBox={`0 0 ${s} ${s}`}
        className={baseClasses}
      >
        <circle
          cx={center}
          cy={center}
          r={radius - strokeWidth / 2}
          fill="none"
          stroke="var(--status-cancelled)"
          strokeWidth={strokeWidth}
        />
      </svg>
    )
  }

  // Finalizing: filled circle with slower pulse (2s)
  if (status === "finalizing") {
    return (
      <svg
        width={s}
        height={s}
        viewBox={`0 0 ${s} ${s}`}
        className={baseClasses}
        style={{ animation: "pulse 2s ease-in-out infinite" }}
      >
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="var(--status-finalizing)"
        />
      </svg>
    )
  }

  // Fallback
  return null
}
