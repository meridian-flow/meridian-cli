import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header bar */}
      <header className="border-b border-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm tracking-tight text-accent-text font-semibold">
            meridian
          </span>
          <Badge variant="secondary" className="text-xs font-mono">
            app
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs font-mono">
            no spawns
          </Badge>
        </div>
      </header>

      {/* Main content area */}
      <main className="flex items-center justify-center px-6 py-24">
        <Card className="w-full max-w-lg">
          <CardHeader>
            <CardTitle className="font-mono text-lg">Spawn Workspace</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground leading-relaxed">
              No active spawns. Create one via the API or connect to an existing spawn
              to see streaming AG-UI events here.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled>
                Connect to Spawn
              </Button>
              <Button size="sm" disabled>
                New Spawn
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}

export default App
