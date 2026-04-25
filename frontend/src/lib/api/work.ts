/**
 * Work items — list work items with cursor envelope.
 */

import { request } from './client'
import type { CursorEnvelope, WorkProjection } from './types'

export function fetchWorkItems(): Promise<CursorEnvelope<WorkProjection>> {
  return request<CursorEnvelope<WorkProjection>>('/api/work')
}
