import * as React from "react"
import { TreeView as ArkTreeView } from "@ark-ui/react/tree-view"
import type { TreeNode, TreeViewRootComponentProps } from "@ark-ui/react/tree-view"

import { cn } from "@/lib/utils"

// Re-export collection utilities, hooks, and types
export { createTreeCollection, useTreeViewNodeContext } from "@ark-ui/react/tree-view"
export type { TreeView as TreeViewTypes, TreeCollection, TreeNode } from "@ark-ui/react/tree-view"

/* -------------------------------- Shared -------------------------------- */

/** Interactive row styles shared between leaf items and branch controls. */
const treeRowStyles =
  "flex cursor-pointer items-center gap-1.5 rounded-md py-1 pl-1.5 pr-2 text-sm outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring"

/* --------------------------------- Root --------------------------------- */

// Generic so callers can pass typed collections (TreeCollection<T>) without casting.
function TreeViewRoot<T extends TreeNode = TreeNode>({
  className,
  ...props
}: TreeViewRootComponentProps<T>) {
  return (
    <ArkTreeView.Root
      data-slot="tree-view"
      className={cn("text-sm", className)}
      {...(props as React.ComponentProps<typeof ArkTreeView.Root>)}
    />
  )
}

/* --------------------------------- Tree --------------------------------- */

function TreeViewTree({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.Tree>) {
  return (
    <ArkTreeView.Tree
      data-slot="tree-view-tree"
      className={cn("flex flex-col", className)}
      {...props}
    />
  )
}

/* --------------------------------- Label -------------------------------- */

function TreeViewLabel({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.Label>) {
  return (
    <ArkTreeView.Label
      data-slot="tree-view-label"
      className={cn("mb-1 text-sm font-medium text-foreground", className)}
      {...props}
    />
  )
}

/* --------------------------------- Item --------------------------------- */

function TreeViewItem({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.Item>) {
  return (
    <ArkTreeView.Item
      data-slot="tree-view-item"
      className={cn(treeRowStyles, "text-foreground", className)}
      {...props}
    />
  )
}

/* ------------------------------ Item Text ------------------------------- */

function TreeViewItemText({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.ItemText>) {
  return (
    <ArkTreeView.ItemText
      data-slot="tree-view-item-text"
      className={cn("flex items-center gap-1.5 truncate", className)}
      {...props}
    />
  )
}

/* --------------------------- Item Indicator ----------------------------- */

function TreeViewItemIndicator({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.ItemIndicator>) {
  return (
    <ArkTreeView.ItemIndicator
      data-slot="tree-view-item-indicator"
      className={cn(
        "inline-flex size-4 shrink-0 items-center justify-center text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

/* -------------------------------- Branch -------------------------------- */

function TreeViewBranch({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.Branch>) {
  return (
    <ArkTreeView.Branch
      data-slot="tree-view-branch"
      className={cn("flex flex-col", className)}
      {...props}
    />
  )
}

/* -------------------------- Branch Control ------------------------------ */

function TreeViewBranchControl({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.BranchControl>) {
  return (
    <ArkTreeView.BranchControl
      data-slot="tree-view-branch-control"
      className={cn(treeRowStyles, className)}
      {...props}
    />
  )
}

/* -------------------------- Branch Content ------------------------------ */

function TreeViewBranchContent({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.BranchContent>) {
  return (
    <ArkTreeView.BranchContent
      data-slot="tree-view-branch-content"
      className={cn("relative flex flex-col pl-3", className)}
      {...props}
    />
  )
}

/* ----------------------- Branch Indent Guide ---------------------------- */

function TreeViewBranchIndentGuide({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.BranchIndentGuide>) {
  return (
    <ArkTreeView.BranchIndentGuide
      data-slot="tree-view-branch-indent-guide"
      className={cn(
        "pointer-events-none absolute bottom-0 left-2 top-0 w-px bg-foreground/10",
        className
      )}
      {...props}
    />
  )
}

/* ------------------------- Branch Indicator ----------------------------- */

function TreeViewBranchIndicator({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.BranchIndicator>) {
  return (
    <ArkTreeView.BranchIndicator
      data-slot="tree-view-branch-indicator"
      className={cn(
        "inline-flex size-4 shrink-0 items-center justify-center text-muted-foreground transition-transform duration-200 [&[data-state=open]]:rotate-90",
        className
      )}
      {...props}
    />
  )
}

/* --------------------------- Branch Text -------------------------------- */

function TreeViewBranchText({
  className,
  ...props
}: React.ComponentProps<typeof ArkTreeView.BranchText>) {
  return (
    <ArkTreeView.BranchText
      data-slot="tree-view-branch-text"
      className={cn("flex items-center gap-1.5 truncate text-foreground", className)}
      {...props}
    />
  )
}

/* -------------------------- Node Provider ------------------------------- */

const TreeViewNodeProvider = ArkTreeView.NodeProvider

export {
  TreeViewRoot,
  TreeViewTree,
  TreeViewLabel,
  TreeViewNodeProvider,
  TreeViewItem,
  TreeViewItemText,
  TreeViewItemIndicator,
  TreeViewBranch,
  TreeViewBranchControl,
  TreeViewBranchContent,
  TreeViewBranchIndentGuide,
  TreeViewBranchIndicator,
  TreeViewBranchText,
}
