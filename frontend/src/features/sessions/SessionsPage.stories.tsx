import type { Meta, StoryObj } from '@storybook/react-vite'

import { SessionsPage } from './SessionsPage'
import type {
  SpawnProjection,
  SpawnStats,
  WorkProjection,
} from './lib'

/**
 * Stories pin `dataOverride` to bypass the live hooks. The container still
 * mounts the hooks (rules of hooks) but the view reads from the override,
 * so no network access is required for Storybook.
 */

const meta: Meta<typeof SessionsPage> = {
  title: 'Features/Sessions/SessionsPage',
  component: SessionsPage,
  parameters: {
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => (
      <div className="h-[720px] w-full border-t border-border">
        <Story />
      </div>
    ),
  ],
  argTypes: {
    onNavigateToChat: { action: 'navigate' },
  },
}

export default meta
type Story = StoryObj<typeof SessionsPage>

// ---------------------------------------------------------------------------
// Mock factories
// ---------------------------------------------------------------------------

const NOW = Date.parse('2026-04-22T10:30:00Z')

function iso(offsetMs: number): string {
  return new Date(NOW + offsetMs).toISOString()
}

function makeSpawn(overrides: Partial<SpawnProjection> = {}): SpawnProjection {
  return {
    spawn_id: 'p100',
    status: 'running',
    harness: 'claude',
    model: 'opus-4-7',
    agent: 'coder',
    work_id: null,
    desc: 'Placeholder spawn',
    created_at: iso(-5 * 60_000),
    started_at: iso(-5 * 60_000 + 500),
    finished_at: null,
    ...overrides,
  }
}

const WORK_ITEMS: WorkProjection[] = [
  {
    work_id: 'auth-refactor',
    name: 'Auth Refactor',
    status: 'in-progress',
    description: 'Move auth into middleware layer',
    work_dir: '.meridian/work/auth-refactor',
    created_at: iso(-3 * 3600_000),
    last_activity_at: iso(-2 * 60_000),
    spawn_count: 6,
    session_count: 4,
  },
  {
    work_id: 'dashboard-polish',
    name: 'Dashboard Polish',
    status: 'in-progress',
    description: 'Tighten up the metrics dashboard',
    work_dir: '.meridian/work/dashboard-polish',
    created_at: iso(-6 * 3600_000),
    last_activity_at: iso(-12 * 60_000),
    spawn_count: 4,
    session_count: 3,
  },
  {
    work_id: 'windows-smoke',
    name: 'Windows Smoke Tests',
    status: 'planned',
    description: 'Fill platform coverage gap',
    work_dir: '.meridian/work/windows-smoke',
    created_at: iso(-18 * 3600_000),
    last_activity_at: iso(-45 * 60_000),
    spawn_count: 3,
    session_count: 2,
  },
]

const DEFAULT_SPAWNS: SpawnProjection[] = [
  // Auth Refactor — active, mixed
  makeSpawn({
    spawn_id: 'p201',
    status: 'running',
    agent: 'coder',
    model: 'opus-4-7',
    work_id: 'auth-refactor',
    desc: 'Implement auth middleware',
    started_at: iso(-2 * 60_000),
  }),
  makeSpawn({
    spawn_id: 'p202',
    status: 'queued',
    agent: 'reviewer',
    model: 'sonnet-4-6',
    work_id: 'auth-refactor',
    desc: 'Review auth handoff',
    started_at: iso(-90_000),
  }),
  makeSpawn({
    spawn_id: 'p203',
    status: 'succeeded',
    agent: 'planner',
    model: 'sonnet-4-6',
    work_id: 'auth-refactor',
    desc: 'Draft phase plan',
    started_at: iso(-30 * 60_000),
    finished_at: iso(-25 * 60_000),
  }),
  makeSpawn({
    spawn_id: 'p204',
    status: 'failed',
    agent: 'verifier',
    model: 'haiku-4-5',
    work_id: 'auth-refactor',
    desc: 'Run typecheck + tests',
    started_at: iso(-55 * 60_000),
    finished_at: iso(-50 * 60_000),
  }),
  makeSpawn({
    spawn_id: 'p205',
    status: 'finalizing',
    agent: 'coder',
    model: 'opus-4-7',
    work_id: 'auth-refactor',
    desc: 'Apply review fixes',
    started_at: iso(-4 * 60_000),
  }),

  // Dashboard Polish
  makeSpawn({
    spawn_id: 'p301',
    status: 'running',
    agent: 'frontend-coder',
    model: 'opus-4-7',
    work_id: 'dashboard-polish',
    desc: 'Restyle metrics cards',
    started_at: iso(-12 * 60_000),
  }),
  makeSpawn({
    spawn_id: 'p302',
    status: 'succeeded',
    agent: 'frontend-designer',
    model: 'sonnet-4-6',
    work_id: 'dashboard-polish',
    desc: 'Ship spec revisions',
    started_at: iso(-2 * 3600_000),
    finished_at: iso(-90 * 60_000),
  }),
  makeSpawn({
    spawn_id: 'p303',
    status: 'cancelled',
    agent: 'browser-tester',
    model: 'haiku-4-5',
    work_id: 'dashboard-polish',
    desc: 'Smoke test filter bar',
    started_at: iso(-3 * 3600_000),
    finished_at: iso(-2.5 * 3600_000),
  }),
  makeSpawn({
    spawn_id: 'p304',
    status: 'running',
    agent: 'coder',
    model: 'sonnet-4-6',
    work_id: 'dashboard-polish',
    desc: 'Wire live stats hook',
    started_at: iso(-25 * 60_000),
  }),

  // Windows Smoke
  makeSpawn({
    spawn_id: 'p401',
    status: 'queued',
    agent: 'smoke-tester',
    model: 'sonnet-4-6',
    work_id: 'windows-smoke',
    desc: 'Run primary launch smoke on Win11',
    started_at: iso(-10 * 60_000),
  }),
  makeSpawn({
    spawn_id: 'p402',
    status: 'succeeded',
    agent: 'investigator',
    model: 'opus-4-7',
    work_id: 'windows-smoke',
    desc: 'Diagnose PTY capture on Windows',
    started_at: iso(-4 * 3600_000),
    finished_at: iso(-3.5 * 3600_000),
  }),
  makeSpawn({
    spawn_id: 'p403',
    status: 'failed',
    agent: 'verifier',
    model: 'haiku-4-5',
    work_id: 'windows-smoke',
    desc: 'pytest-llm on PowerShell',
    started_at: iso(-6 * 3600_000),
    finished_at: iso(-5.8 * 3600_000),
  }),

  // Ungrouped
  makeSpawn({
    spawn_id: 'p501',
    status: 'running',
    agent: 'explorer',
    model: 'haiku-4-5',
    work_id: null,
    desc: 'Scan repo for orphaned TODOs',
    started_at: iso(-6 * 60_000),
  }),
  makeSpawn({
    spawn_id: 'p502',
    status: 'succeeded',
    agent: 'web-researcher',
    model: 'sonnet-4-6',
    work_id: null,
    desc: 'Survey LLM caching papers',
    started_at: iso(-8 * 3600_000),
    finished_at: iso(-7.5 * 3600_000),
  }),
  makeSpawn({
    spawn_id: 'p503',
    status: 'queued',
    agent: 'tech-writer',
    model: 'sonnet-4-6',
    work_id: null,
    desc: 'Draft release notes',
    started_at: iso(-55 * 60_000),
  }),
]

function computeStats(spawns: SpawnProjection[]): SpawnStats {
  const s: SpawnStats = {
    running: 0,
    queued: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0,
    finalizing: 0,
    total: spawns.length,
  }
  for (const sp of spawns) {
    const k = sp.status as keyof SpawnStats
    if (k !== 'total' && k in s) (s[k] as number) += 1
  }
  return s
}

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

export const Default: Story = {
  args: {
    dataOverride: {
      spawns: DEFAULT_SPAWNS,
      stats: computeStats(DEFAULT_SPAWNS),
      workItems: WORK_ITEMS,
      onAction: (action, spawnId) => {
        // eslint-disable-next-line no-console
        console.log('[story] action', action, spawnId)
      },
    },
  },
}

export const Empty: Story = {
  args: {
    dataOverride: {
      spawns: [],
      stats: computeStats([]),
      workItems: WORK_ITEMS,
    },
  },
}

export const Loading: Story = {
  args: {
    dataOverride: {
      spawns: [],
      stats: null,
      workItems: [],
      isLoading: true,
    },
  },
}

export const ErrorState: Story = {
  name: 'Error',
  args: {
    dataOverride: {
      spawns: [],
      stats: null,
      workItems: [],
      error: 'ECONNREFUSED http://localhost:7707/api/spawns/list',
      onRefetch: () => {
        // eslint-disable-next-line no-console
        console.log('[story] retry')
      },
    },
  },
}

export const AllRunning: Story = {
  args: {
    dataOverride: (() => {
      const spawns = DEFAULT_SPAWNS.map<SpawnProjection>((s, i) => ({
        ...s,
        status: 'running',
        finished_at: null,
        started_at: iso(-(i + 1) * 60_000),
      }))
      return {
        spawns,
        stats: computeStats(spawns),
        workItems: WORK_ITEMS,
      }
    })(),
  },
}

export const SingleWorkItem: Story = {
  args: {
    dataOverride: (() => {
      const spawns = DEFAULT_SPAWNS.filter((s) => s.work_id === 'auth-refactor')
      return {
        spawns,
        stats: computeStats(spawns),
        workItems: WORK_ITEMS.filter((w) => w.work_id === 'auth-refactor'),
      }
    })(),
  },
}

export const NoWorkItems: Story = {
  args: {
    dataOverride: (() => {
      const spawns = DEFAULT_SPAWNS.map<SpawnProjection>((s) => ({
        ...s,
        work_id: null,
      }))
      return {
        spawns,
        stats: computeStats(spawns),
        workItems: [],
      }
    })(),
  },
}
