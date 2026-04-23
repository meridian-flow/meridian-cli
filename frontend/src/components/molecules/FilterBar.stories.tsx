import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"
import { FilterChip, FilterBar, type StatusFilterValue } from "./FilterBar"
import type { SpawnStatus } from "@/types/spawn"

const meta: Meta<typeof FilterBar> = {
  title: "Components/Molecules/FilterBar",
  component: FilterBar,
  parameters: {
    layout: "padded",
  },
}

export default meta
type Story = StoryObj<typeof FilterBar>

// Interactive wrapper for FilterChip
function FilterChipDemo() {
  const [active, setActive] = useState(false)

  return (
    <div className="flex gap-4 items-center">
      <FilterChip
        label="Running"
        isActive={active}
        count={5}
        onClick={() => setActive(!active)}
      />
      <span className="text-sm text-muted-foreground">
        Click to toggle
      </span>
    </div>
  )
}

export const SingleChip: Story = {
  render: () => <FilterChipDemo />,
}

// FilterBar with state
function FilterBarDemo() {
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('all')
  const [workItemFilter, setWorkItemFilter] = useState<string | null>(null)
  const [agentFilter, setAgentFilter] = useState<string | null>(null)

  const workItems = [
    { work_id: 'auth-refactor', name: 'auth-refactor' },
    { work_id: 'api-redesign', name: 'api-redesign' },
    { work_id: 'ui-polish', name: 'ui-polish' },
  ]

  const agents = ['coder', 'reviewer', 'smoke-tester', 'verifier']

  const statusCounts: Partial<Record<SpawnStatus | 'all', number>> = {
    all: 24,
    running: 2,
    queued: 1,
    succeeded: 18,
    failed: 3,
  }

  return (
    <div className="space-y-4">
      <FilterBar
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        statusCounts={statusCounts}
        workItemFilter={workItemFilter}
        onWorkItemFilterChange={setWorkItemFilter}
        availableWorkItems={workItems}
        agentFilter={agentFilter}
        onAgentFilterChange={setAgentFilter}
        availableAgents={agents}
      />
      <div className="text-sm text-muted-foreground">
        Status: {statusFilter} | Work item: {workItemFilter ?? 'all'} | Agent: {agentFilter ?? 'all'}
      </div>
    </div>
  )
}

export const Default: Story = {
  render: () => <FilterBarDemo />,
}

// Status chips only (no popovers)
function StatusOnlyDemo() {
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('all')

  return (
    <FilterBar
      statusFilter={statusFilter}
      onStatusFilterChange={setStatusFilter}
    />
  )
}

export const StatusChipsOnly: Story = {
  render: () => <StatusOnlyDemo />,
}

// With counts
function WithCountsDemo() {
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('running')

  const statusCounts: Partial<Record<SpawnStatus | 'all', number>> = {
    all: 42,
    running: 3,
    queued: 2,
    succeeded: 35,
    failed: 2,
  }

  return (
    <FilterBar
      statusFilter={statusFilter}
      onStatusFilterChange={setStatusFilter}
      statusCounts={statusCounts}
    />
  )
}

export const WithCounts: Story = {
  render: () => <WithCountsDemo />,
}

// All filter chip variants
export const ChipVariants: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        <FilterChip label="Active" isActive={true} onClick={() => {}} />
        <FilterChip label="Inactive" isActive={false} onClick={() => {}} />
      </div>
      <div className="flex gap-2">
        <FilterChip label="With count" isActive={true} count={5} onClick={() => {}} />
        <FilterChip label="With count" isActive={false} count={12} onClick={() => {}} />
      </div>
      <div className="flex gap-2">
        <FilterChip label="Zero count" isActive={false} count={0} onClick={() => {}} />
        <FilterChip label="Large count" isActive={true} count={999} onClick={() => {}} />
      </div>
    </div>
  ),
}

// Active work item filter
function ActiveFiltersDemo() {
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('running')
  const [workItemFilter, setWorkItemFilter] = useState<string | null>('auth-refactor')
  const [agentFilter, setAgentFilter] = useState<string | null>('coder')

  const workItems = [
    { work_id: 'auth-refactor', name: 'auth-refactor' },
    { work_id: 'api-redesign', name: 'api-redesign' },
  ]

  const agents = ['coder', 'reviewer', 'verifier']

  return (
    <FilterBar
      statusFilter={statusFilter}
      onStatusFilterChange={setStatusFilter}
      workItemFilter={workItemFilter}
      onWorkItemFilterChange={setWorkItemFilter}
      availableWorkItems={workItems}
      agentFilter={agentFilter}
      onAgentFilterChange={setAgentFilter}
      availableAgents={agents}
    />
  )
}

export const ActiveFilters: Story = {
  render: () => <ActiveFiltersDemo />,
}
