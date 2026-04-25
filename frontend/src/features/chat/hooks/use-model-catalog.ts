/**
 * useModelCatalog — fetch and normalize the model catalog from GET /api/models.
 *
 * Derives a quick-pick list (pinned + aliased models) and groups the full
 * catalog by harness for the model picker's collapsible sections.
 */

import { useCallback, useEffect, useMemo, useState } from "react"

// ---------------------------------------------------------------------------
// Wire types — shape returned by /api/models
// ---------------------------------------------------------------------------

interface WireAlias {
  alias: string
  model_id?: string
}

interface WireModel {
  model_id: string
  harness: string | null
  aliases?: WireAlias[]
  name?: string
  family?: string
  provider?: string
  cost_tier?: string
  pinned?: boolean
  description?: string
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface QuickPickModel {
  displayName: string
  modelId: string
  harness: string
  provider: string | null
  costTier: string | null
  pinned: boolean
}

export interface CatalogModel {
  modelId: string
  harness: string
  displayName: string
  provider: string | null
  costTier: string | null
  aliases: string[]
  pinned: boolean
  description: string | null
}

export interface ModelCatalog {
  quickPick: QuickPickModel[]
  byHarness: Map<string, CatalogModel[]>
  defaultModel: QuickPickModel | null
}

export interface UseModelCatalogReturn {
  catalog: ModelCatalog | null
  isLoading: boolean
  error: string | null
  refresh: () => void
}

// ---------------------------------------------------------------------------
// Derivation
// ---------------------------------------------------------------------------

function deriveQuickPick(models: CatalogModel[]): QuickPickModel[] {
  const seen = new Set<string>()
  const picks: QuickPickModel[] = []

  for (const model of models) {
    if (!model.pinned && model.aliases.length === 0) continue
    if (seen.has(model.modelId)) continue
    seen.add(model.modelId)

    // If the model has aliases, create a pick for each alias
    if (model.aliases.length > 0) {
      for (const alias of model.aliases) {
        picks.push({
          displayName: alias,
          modelId: model.modelId,
          harness: model.harness,
          provider: model.provider,
          costTier: model.costTier,
          pinned: model.pinned,
        })
      }
    } else {
      picks.push({
        displayName: model.displayName,
        modelId: model.modelId,
        harness: model.harness,
        provider: model.provider,
        costTier: model.costTier,
        pinned: model.pinned,
      })
    }
  }

  // Sort: pinned first, then alphabetically by displayName
  picks.sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    return a.displayName.localeCompare(b.displayName)
  })

  return picks
}

function deriveCatalog(wireModels: WireModel[]): ModelCatalog {
  const catalogModels: CatalogModel[] = wireModels
    .filter((w): w is WireModel & { harness: string } => w.harness !== null)
    .map((w) => ({
      modelId: w.model_id,
      harness: w.harness,
      displayName: w.name ?? w.model_id,
      provider: w.provider ?? null,
      costTier: w.cost_tier ?? null,
      aliases: (w.aliases ?? []).map((a) => a.alias),
      pinned: w.pinned ?? false,
      description: w.description ?? null,
    }))

  const quickPick = deriveQuickPick(catalogModels)

  // Group by harness
  const byHarness = new Map<string, CatalogModel[]>()
  for (const model of catalogModels) {
    const group = byHarness.get(model.harness)
    if (group) {
      group.push(model)
    } else {
      byHarness.set(model.harness, [model])
    }
  }

  // Sort within each harness group by displayName
  for (const group of byHarness.values()) {
    group.sort((a, b) => a.displayName.localeCompare(b.displayName))
  }

  const defaultModel = quickPick.find((m) => m.pinned) ?? quickPick[0] ?? null

  return { quickPick, byHarness, defaultModel }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseModelCatalogOptions {
  /** When false the hook skips fetching and returns null catalog. Defaults to true. */
  enabled?: boolean
}

export function useModelCatalog(
  options: UseModelCatalogOptions = {},
): UseModelCatalogReturn {
  const { enabled = true } = options

  const [catalog, setCatalog] = useState<ModelCatalog | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = useCallback(() => {
    setRefreshKey((k) => k + 1)
  }, [])

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)
    setError(null)

    fetch("/api/models")
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`${res.status} ${res.statusText}`)
        }
        return res.json() as Promise<{ models: WireModel[] }>
      })
      .then((data) => {
        if (cancelled) return
        setCatalog(deriveCatalog(data.models))
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (cancelled) return
        setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [refreshKey, enabled])

  return useMemo(
    () => ({ catalog, isLoading, error, refresh }),
    [catalog, isLoading, error, refresh],
  )
}
