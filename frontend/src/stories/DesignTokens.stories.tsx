import type { Meta, StoryObj } from "@storybook/react-vite"
import { useEffect, useState } from "react"

/**
 * Design System Tokens — Visual documentation of all design tokens
 * 
 * This page renders all CSS custom property tokens from the Meridian design system,
 * making them inspectable in both Paper (light) and Espresso (dark) themes.
 */

// ============================================================================
// Token Data
// ============================================================================

const colorTokens = {
  "Background & Foreground": [
    { name: "--background", description: "Page background" },
    { name: "--foreground", description: "Primary text" },
  ],
  "Card & Popover": [
    { name: "--card", description: "Card background" },
    { name: "--card-foreground", description: "Card text" },
    { name: "--popover", description: "Popover background" },
    { name: "--popover-foreground", description: "Popover text" },
  ],
  "Primary & Secondary": [
    { name: "--primary", description: "Primary buttons, links" },
    { name: "--primary-foreground", description: "Text on primary" },
    { name: "--secondary", description: "Secondary elements" },
    { name: "--secondary-foreground", description: "Text on secondary" },
  ],
  "Muted & Accent": [
    { name: "--muted", description: "Muted backgrounds" },
    { name: "--muted-foreground", description: "Muted text" },
    { name: "--accent", description: "Accent backgrounds" },
    { name: "--accent-foreground", description: "Accent text" },
    { name: "--accent-fill", description: "Icons, borders, fills" },
    { name: "--accent-text", description: "Accent text (AA compliant)" },
  ],
  "Semantic States": [
    { name: "--destructive", description: "Error, danger states" },
    { name: "--success", description: "Success states" },
    { name: "--success-foreground", description: "Text on success" },
  ],
  "Border & Input": [
    { name: "--border", description: "Default borders" },
    { name: "--input", description: "Input borders" },
    { name: "--ring", description: "Focus rings" },
  ],
  "Sidebar": [
    { name: "--sidebar", description: "Sidebar background" },
    { name: "--sidebar-foreground", description: "Sidebar text" },
    { name: "--sidebar-primary", description: "Sidebar primary" },
    { name: "--sidebar-accent", description: "Sidebar accent" },
    { name: "--sidebar-border", description: "Sidebar border" },
  ],
  "Status Colors": [
    { name: "--status-running", description: "Running state (pulsing)" },
    { name: "--status-queued", description: "Queued/waiting state" },
    { name: "--status-succeeded", description: "Success/completed" },
    { name: "--status-failed", description: "Failed/error state" },
    { name: "--status-cancelled", description: "Cancelled state" },
    { name: "--status-finalizing", description: "Finalizing state" },
  ],
}

const typographyScale = [
  { class: "text-xs", label: "Extra Small", sample: "The quick brown fox jumps" },
  { class: "text-sm", label: "Small", sample: "The quick brown fox jumps" },
  { class: "text-base", label: "Base", sample: "The quick brown fox jumps" },
  { class: "text-lg", label: "Large", sample: "The quick brown fox jumps" },
  { class: "text-xl", label: "Extra Large", sample: "The quick brown fox" },
  { class: "text-2xl", label: "2XL", sample: "The quick brown fox" },
  { class: "text-3xl", label: "3XL", sample: "Quick brown fox" },
  { class: "text-4xl", label: "4XL", sample: "Brown fox" },
]

const fontFamilies = [
  { 
    class: "font-sans", 
    name: "Geist", 
    usage: "UI text, labels, buttons, navigation",
    sample: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
  },
  { 
    class: "font-mono", 
    name: "Geist Mono", 
    usage: "Identifiers, spawn IDs, code, paths, terminal output",
    sample: "p281 → spawn_id:abc123 | /usr/bin/node --version"
  },
  { 
    class: "font-editor", 
    name: "iA Writer Quattro", 
    usage: "Prose, markdown rendering, long-form content",
    sample: "The design system provides a consistent visual language across the application, ensuring coherent typography and spacing."
  },
]

const spacingScale = [
  { name: "0.5", value: "0.125rem", pixels: "2px" },
  { name: "1", value: "0.25rem", pixels: "4px" },
  { name: "1.5", value: "0.375rem", pixels: "6px" },
  { name: "2", value: "0.5rem", pixels: "8px" },
  { name: "2.5", value: "0.625rem", pixels: "10px" },
  { name: "3", value: "0.75rem", pixels: "12px" },
  { name: "4", value: "1rem", pixels: "16px" },
  { name: "5", value: "1.25rem", pixels: "20px" },
  { name: "6", value: "1.5rem", pixels: "24px" },
  { name: "8", value: "2rem", pixels: "32px" },
  { name: "10", value: "2.5rem", pixels: "40px" },
  { name: "12", value: "3rem", pixels: "48px" },
  { name: "16", value: "4rem", pixels: "64px" },
  { name: "20", value: "5rem", pixels: "80px" },
  { name: "24", value: "6rem", pixels: "96px" },
]

const radiusScale = [
  { name: "sm", multiplier: "0.6", computed: "0.3rem" },
  { name: "md", multiplier: "0.8", computed: "0.4rem" },
  { name: "lg", multiplier: "1.0", computed: "0.5rem" },
  { name: "xl", multiplier: "1.4", computed: "0.7rem" },
  { name: "2xl", multiplier: "1.8", computed: "0.9rem" },
  { name: "3xl", multiplier: "2.2", computed: "1.1rem" },
  { name: "4xl", multiplier: "2.6", computed: "1.3rem" },
]

const animationTokens = {
  durations: [
    { name: "--duration-fast", value: "100ms", description: "Micro-interactions, hovers" },
    { name: "--duration-default", value: "150ms", description: "Standard transitions" },
    { name: "--duration-slow", value: "250ms", description: "Complex animations, modals" },
  ],
  easings: [
    { name: "--ease-default", value: "cubic-bezier(0.2, 0, 0, 1)", description: "Standard easing" },
    { name: "--ease-spring", value: "cubic-bezier(0.34, 1.56, 0.64, 1)", description: "Bouncy, playful" },
  ],
  keyframes: [
    { name: "pulse", description: "Opacity pulse for running states" },
    { name: "fade-in", description: "Fade in from transparent" },
    { name: "spin", description: "360° rotation for loaders" },
  ],
}

// ============================================================================
// Helper Components
// ============================================================================

function ColorSwatch({ name, description }: { name: string; description: string }) {
  const [value, setValue] = useState("")
  
  useEffect(() => {
    const style = getComputedStyle(document.documentElement)
    setValue(style.getPropertyValue(name).trim())
  }, [name])
  
  return (
    <div className="flex items-center gap-3 py-2">
      <div 
        className="w-12 h-12 rounded-md border border-border shadow-sm flex-shrink-0"
        style={{ backgroundColor: `var(${name})` }}
      />
      <div className="min-w-0 flex-1">
        <code className="font-mono text-sm text-foreground">{name}</code>
        <p className="text-xs text-muted-foreground truncate">{description}</p>
        <p className="text-xs text-muted-foreground font-mono opacity-60 truncate">{value}</p>
      </div>
    </div>
  )
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-2xl font-sans font-semibold text-foreground mb-4 pb-2 border-b border-border">
      {children}
    </h2>
  )
}

function SubsectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-lg font-sans font-medium text-foreground mb-3 mt-6">
      {children}
    </h3>
  )
}

// ============================================================================
// Story Wrapper
// ============================================================================

function DesignTokensPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-12 font-sans">
      {/* Header */}
      <header className="text-center py-8 border-b border-border">
        <h1 className="text-4xl font-semibold text-foreground mb-2">
          Meridian Design Tokens
        </h1>
        <p className="text-lg text-muted-foreground">
          Visual documentation of the design system
        </p>
        <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted text-sm">
          <span className="w-3 h-3 rounded-full" style={{ backgroundColor: 'var(--accent-fill)' }} />
          <span>Paper (Light) / Espresso (Dark) themes</span>
        </div>
      </header>

      {/* Colors Section */}
      <section>
        <SectionHeading>🎨 Color Tokens</SectionHeading>
        <p className="text-muted-foreground mb-6">
          All colors use the oklch color space for perceptual uniformity.
          Toggle theme in the toolbar to see both Paper and Espresso palettes.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {Object.entries(colorTokens).map(([group, tokens]) => (
            <div key={group} className="bg-card rounded-lg border border-border p-4">
              <SubsectionHeading>{group}</SubsectionHeading>
              <div className="space-y-1">
                {tokens.map((token) => (
                  <ColorSwatch key={token.name} {...token} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Typography Section */}
      <section>
        <SectionHeading>📝 Typography</SectionHeading>
        
        {/* Font Families */}
        <SubsectionHeading>Font Families</SubsectionHeading>
        <div className="space-y-6 mb-8">
          {fontFamilies.map((font) => (
            <div key={font.class} className="bg-card rounded-lg border border-border p-5">
              <div className="flex items-baseline justify-between mb-2">
                <span className={`text-xl ${font.class}`}>{font.name}</span>
                <code className="text-xs font-mono text-muted-foreground">.{font.class}</code>
              </div>
              <p className="text-sm text-muted-foreground mb-3">{font.usage}</p>
              <p className={`text-base ${font.class} text-foreground leading-relaxed`}>
                {font.sample}
              </p>
            </div>
          ))}
        </div>

        {/* Type Scale */}
        <SubsectionHeading>Type Scale (Fluid)</SubsectionHeading>
        <div className="bg-card rounded-lg border border-border overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left p-3 text-sm font-medium">Class</th>
                <th className="text-left p-3 text-sm font-medium">Sample</th>
              </tr>
            </thead>
            <tbody>
              {typographyScale.map((item) => (
                <tr key={item.class} className="border-b border-border last:border-0">
                  <td className="p-3">
                    <code className="font-mono text-sm text-accent-text">.{item.class}</code>
                    <span className="text-xs text-muted-foreground ml-2">({item.label})</span>
                  </td>
                  <td className="p-3">
                    <span className={item.class}>{item.sample}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Spacing Section */}
      <section>
        <SectionHeading>📏 Spacing Scale (8pt Grid)</SectionHeading>
        <p className="text-muted-foreground mb-6">
          Based on an 8pt grid system. All values are multiples or subdivisions of 8px.
        </p>
        
        <div className="bg-card rounded-lg border border-border p-4 space-y-3">
          {spacingScale.map((item) => (
            <div key={item.name} className="flex items-center gap-4">
              <code className="w-20 font-mono text-sm text-muted-foreground">
                spacing-{item.name}
              </code>
              <div 
                className="h-6 bg-accent-fill rounded"
                style={{ width: item.value }}
              />
              <span className="text-sm text-muted-foreground">
                {item.value} ({item.pixels})
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Radius Section */}
      <section>
        <SectionHeading>🔵 Border Radius</SectionHeading>
        <p className="text-muted-foreground mb-6">
          Based on --radius: 0.5rem (8px). All radius values are computed as multipliers.
        </p>
        
        <div className="flex flex-wrap gap-6">
          {radiusScale.map((item) => (
            <div key={item.name} className="text-center">
              <div 
                className="w-20 h-20 bg-accent-fill mb-2"
                style={{ borderRadius: `var(--radius-${item.name})` }}
              />
              <code className="block font-mono text-sm text-foreground">
                radius-{item.name}
              </code>
              <span className="text-xs text-muted-foreground">
                {item.computed}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Status Colors Section */}
      <section>
        <SectionHeading>🚦 Status Colors</SectionHeading>
        <p className="text-muted-foreground mb-6">
          Semantic status colors for session and spawn states. 
          Each status has a distinct color visible in both themes.
        </p>
        
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {[
            { name: "running", label: "Running", icon: "●", animation: "pulse 2s infinite" },
            { name: "queued", label: "Queued", icon: "◐", animation: "none" },
            { name: "succeeded", label: "Succeeded", icon: "✓", animation: "none" },
            { name: "failed", label: "Failed", icon: "✗", animation: "none" },
            { name: "cancelled", label: "Cancelled", icon: "○", animation: "none" },
            { name: "finalizing", label: "Finalizing", icon: "…", animation: "pulse 1.5s infinite" },
          ].map((status) => (
            <div 
              key={status.name}
              className="flex items-center gap-3 p-4 bg-card rounded-lg border border-border"
            >
              <span 
                className="text-2xl"
                style={{ 
                  color: `var(--status-${status.name})`,
                  animation: status.animation,
                }}
              >
                {status.icon}
              </span>
              <div>
                <span className="font-medium">{status.label}</span>
                <code className="block text-xs font-mono text-muted-foreground">
                  --status-{status.name}
                </code>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Animation Section */}
      <section>
        <SectionHeading>✨ Animation Tokens</SectionHeading>
        
        {/* Durations */}
        <SubsectionHeading>Duration</SubsectionHeading>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {animationTokens.durations.map((item) => (
            <div key={item.name} className="bg-card rounded-lg border border-border p-4">
              <code className="font-mono text-sm text-accent-text">{item.name}</code>
              <p className="text-2xl font-mono mt-2">{item.value}</p>
              <p className="text-sm text-muted-foreground mt-1">{item.description}</p>
              <DurationDemo duration={item.value} />
            </div>
          ))}
        </div>

        {/* Easings */}
        <SubsectionHeading>Easing Curves</SubsectionHeading>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {animationTokens.easings.map((item) => (
            <div key={item.name} className="bg-card rounded-lg border border-border p-4">
              <code className="font-mono text-sm text-accent-text">{item.name}</code>
              <p className="text-xs font-mono text-muted-foreground mt-1">{item.value}</p>
              <p className="text-sm text-muted-foreground mt-2">{item.description}</p>
              <EasingDemo easing={item.value} />
            </div>
          ))}
        </div>

        {/* Keyframes */}
        <SubsectionHeading>Keyframe Animations</SubsectionHeading>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-card rounded-lg border border-border p-4 text-center">
            <div 
              className="w-12 h-12 rounded-full bg-status-running mx-auto mb-3"
              style={{ animation: "pulse 2s ease-in-out infinite" }}
            />
            <code className="font-mono text-sm">pulse</code>
            <p className="text-xs text-muted-foreground mt-1">Opacity 1 → 0.5 → 1</p>
          </div>
          <div className="bg-card rounded-lg border border-border p-4 text-center">
            <FadeInDemo />
            <code className="font-mono text-sm">fade-in</code>
            <p className="text-xs text-muted-foreground mt-1">Opacity 0 → 1</p>
          </div>
          <div className="bg-card rounded-lg border border-border p-4 text-center">
            <div 
              className="w-12 h-12 rounded-md bg-accent-fill mx-auto mb-3"
              style={{ animation: "spin 2s linear infinite" }}
            />
            <code className="font-mono text-sm">spin</code>
            <p className="text-xs text-muted-foreground mt-1">360° rotation</p>
          </div>
        </div>
      </section>

      {/* Font Usage Guide */}
      <section>
        <SectionHeading>📖 Font Usage Guide</SectionHeading>
        
        <div className="bg-card rounded-lg border border-border overflow-hidden">
          <div className="grid grid-cols-1 divide-y divide-border">
            <div className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="w-8 h-8 rounded bg-primary text-primary-foreground flex items-center justify-center font-sans font-bold">
                  Aa
                </span>
                <span className="font-sans text-lg font-medium">Geist</span>
                <code className="text-xs font-mono text-muted-foreground ml-auto">.font-sans</code>
              </div>
              <p className="text-muted-foreground mb-2">
                The primary UI typeface. Use for all interface text.
              </p>
              <ul className="text-sm space-y-1">
                <li>• <span className="font-sans">Buttons, labels, form inputs</span></li>
                <li>• <span className="font-sans">Navigation menus, tabs</span></li>
                <li>• <span className="font-sans">Headings, titles, captions</span></li>
                <li>• <span className="font-sans">Tooltips, notifications</span></li>
              </ul>
            </div>
            
            <div className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="w-8 h-8 rounded bg-muted text-foreground flex items-center justify-center font-mono text-sm">
                  {"</>"}
                </span>
                <span className="font-mono text-lg">Geist Mono</span>
                <code className="text-xs font-mono text-muted-foreground ml-auto">.font-mono</code>
              </div>
              <p className="text-muted-foreground mb-2">
                Monospace for technical content. Use for anything that needs precise alignment.
              </p>
              <ul className="text-sm space-y-1">
                <li>• <span className="font-mono">spawn_id: p281</span> — Identifiers</li>
                <li>• <span className="font-mono">/usr/local/bin/node</span> — File paths</li>
                <li>• <span className="font-mono">const x = 42;</span> — Code snippets</li>
                <li>• <span className="font-mono">2024-04-22T10:30:00Z</span> — Timestamps</li>
              </ul>
            </div>
            
            <div className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="w-8 h-8 rounded bg-secondary text-secondary-foreground flex items-center justify-center font-editor italic">
                  Aa
                </span>
                <span className="font-editor text-lg">iA Writer Quattro</span>
                <code className="text-xs font-mono text-muted-foreground ml-auto">.font-editor</code>
              </div>
              <p className="text-muted-foreground mb-2">
                Editorial typeface for long-form reading. Optimized for prose.
              </p>
              <ul className="text-sm space-y-1">
                <li>• <span className="font-editor">Markdown document rendering</span></li>
                <li>• <span className="font-editor">AI response content</span></li>
                <li>• <span className="font-editor">Documentation, help text</span></li>
                <li>• <span className="font-editor italic">Emphasis with italic variant</span></li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Contrast Verification */}
      <section>
        <SectionHeading>🔍 Contrast Verification</SectionHeading>
        <p className="text-muted-foreground mb-6">
          WCAG AA requires a minimum contrast ratio of 4.5:1 for normal text.
          All color combinations below meet this threshold.
        </p>
        
        <div className="bg-card rounded-lg border border-border overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left p-3 text-sm font-medium">Background</th>
                <th className="text-left p-3 text-sm font-medium">Foreground</th>
                <th className="text-left p-3 text-sm font-medium">Sample</th>
                <th className="text-left p-3 text-sm font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {[
                { bg: "--background", fg: "--foreground" },
                { bg: "--background", fg: "--muted-foreground" },
                { bg: "--background", fg: "--accent-text" },
                { bg: "--card", fg: "--card-foreground" },
                { bg: "--muted", fg: "--foreground" },
                { bg: "--primary", fg: "--primary-foreground" },
                { bg: "--secondary", fg: "--secondary-foreground" },
                { bg: "--sidebar", fg: "--sidebar-foreground" },
              ].map(({ bg, fg }, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <td className="p-3">
                    <code className="font-mono text-xs">{bg}</code>
                  </td>
                  <td className="p-3">
                    <code className="font-mono text-xs">{fg}</code>
                  </td>
                  <td className="p-3">
                    <span 
                      className="px-2 py-1 rounded text-sm"
                      style={{ 
                        backgroundColor: `var(${bg})`, 
                        color: `var(${fg})` 
                      }}
                    >
                      Sample Text
                    </span>
                  </td>
                  <td className="p-3">
                    <span className="inline-flex items-center gap-1.5 text-sm">
                      <span className="w-2 h-2 rounded-full bg-status-succeeded" />
                      <span className="text-muted-foreground">AA Pass</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Footer */}
      <footer className="text-center py-8 border-t border-border text-sm text-muted-foreground">
        <p>Meridian Design System • Paper (Light) + Espresso (Dark) themes</p>
        <p className="mt-1">Built with oklch colors, Geist typography, 8pt grid</p>
      </footer>
    </div>
  )
}

// Animation demo components
function DurationDemo({ duration }: { duration: string }) {
  const [active, setActive] = useState(false)
  
  return (
    <div className="mt-3">
      <button 
        className="w-full h-8 bg-muted rounded relative overflow-hidden"
        onClick={() => setActive(!active)}
        onMouseEnter={() => setActive(true)}
        onMouseLeave={() => setActive(false)}
      >
        <div 
          className="absolute inset-y-0 left-0 bg-accent-fill"
          style={{ 
            width: active ? '100%' : '0%',
            transition: `width ${duration} ease-out`
          }}
        />
        <span className="relative text-xs text-foreground">Hover to demo</span>
      </button>
    </div>
  )
}

function EasingDemo({ easing }: { easing: string }) {
  const [active, setActive] = useState(false)
  
  return (
    <div className="mt-4 h-12 bg-muted rounded relative overflow-hidden">
      <div 
        className="absolute top-2 w-8 h-8 bg-accent-fill rounded-full"
        style={{ 
          left: active ? 'calc(100% - 2.5rem)' : '0.5rem',
          transition: `left 500ms ${easing}`
        }}
        onMouseEnter={() => setActive(true)}
        onMouseLeave={() => setActive(false)}
      />
    </div>
  )
}

function FadeInDemo() {
  const [key, setKey] = useState(0)
  
  return (
    <div 
      key={key}
      className="w-12 h-12 rounded-md bg-accent-fill mx-auto mb-3 cursor-pointer"
      style={{ animation: "fade-in 1s ease-out" }}
      onClick={() => setKey(k => k + 1)}
      title="Click to replay"
    />
  )
}

// ============================================================================
// Story Export
// ============================================================================

const meta: Meta = {
  title: "Design System/Tokens",
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component: "Visual documentation of all Meridian design system tokens. Toggle theme in the toolbar to see both Paper and Espresso palettes.",
      },
    },
  },
}

export default meta
type Story = StoryObj

export const AllTokens: Story = {
  render: () => <DesignTokensPage />,
  parameters: {
    docs: {
      canvas: {
        sourceState: "hidden",
      },
    },
  },
}
