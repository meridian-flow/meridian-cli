import type { Meta, StoryObj } from "@storybook/react-vite"
import {
  BookOpen,
  FileText,
  Folder,
  FolderOpen,
  Globe,
  Search,
  Pencil,
  Terminal,
} from "lucide-react"

import {
  createTreeCollection,
  useTreeViewNodeContext,
  TreeViewRoot,
  TreeViewTree,
  TreeViewNodeProvider,
  TreeViewItem,
  TreeViewItemText,
  TreeViewBranch,
  TreeViewBranchControl,
  TreeViewBranchContent,
  TreeViewBranchIndentGuide,
  TreeViewBranchText,
} from "./tree-view"

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

interface FileNode {
  id: string
  name: string
  children?: FileNode[]
}

const fileTree = createTreeCollection<FileNode>({
  nodeToValue: (node) => node.id,
  nodeToString: (node) => node.name,
  rootNode: {
    id: "ROOT",
    name: "",
    children: [
      {
        id: "src",
        name: "src",
        children: [
          {
            id: "src/components",
            name: "components",
            children: [
              { id: "src/components/button.tsx", name: "button.tsx" },
              { id: "src/components/card.tsx", name: "card.tsx" },
              { id: "src/components/dialog.tsx", name: "dialog.tsx" },
            ],
          },
          {
            id: "src/features",
            name: "features",
            children: [
              { id: "src/features/auth.tsx", name: "auth.tsx" },
              { id: "src/features/editor.tsx", name: "editor.tsx" },
            ],
          },
          { id: "src/app.tsx", name: "app.tsx" },
          { id: "src/index.ts", name: "index.ts" },
        ],
      },
      { id: "package.json", name: "package.json" },
      { id: "tsconfig.json", name: "tsconfig.json" },
      { id: "README.md", name: "README.md" },
    ],
  },
})

// ---------------------------------------------------------------------------
// Recursive node renderer
// ---------------------------------------------------------------------------

function FolderIcon() {
  const nodeState = useTreeViewNodeContext()
  return nodeState.expanded
    ? <FolderOpen className="size-4 text-muted-foreground" />
    : <Folder className="size-4 text-muted-foreground" />
}

function FileTreeNode({ node, indexPath }: { node: FileNode; indexPath: number[] }) {
  return (
    <TreeViewNodeProvider key={node.id} node={node} indexPath={indexPath}>
      {node.children ? (
        <TreeViewBranch>
          <TreeViewBranchControl>
            <FolderIcon />
            <TreeViewBranchText>{node.name}</TreeViewBranchText>
          </TreeViewBranchControl>
          <TreeViewBranchContent>
            <TreeViewBranchIndentGuide />
            {node.children.map((child, i) => (
              <FileTreeNode
                key={child.id}
                node={child}
                indexPath={[...indexPath, i]}
              />
            ))}
          </TreeViewBranchContent>
        </TreeViewBranch>
      ) : (
        <TreeViewItem>
          <TreeViewItemText>
            <FileText className="size-4 text-muted-foreground" />
            {node.name}
          </TreeViewItemText>
        </TreeViewItem>
      )}
    </TreeViewNodeProvider>
  )
}

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

const meta = {
  title: "UI/TreeView",
  tags: ["autodocs"],
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

/** Basic file tree with expand/collapse and indent guide lines. */
export const FileTree: Story = {
  render: () => (
    <div className="max-w-sm">
      <TreeViewRoot
        collection={fileTree}
        defaultExpandedValue={["src", "src/components"]}
      >
        <TreeViewTree>
          {fileTree.rootNode.children?.map((node, index) => (
            <FileTreeNode key={node.id} node={node} indexPath={[index]} />
          ))}
        </TreeViewTree>
      </TreeViewRoot>
    </div>
  ),
}

/** All nodes expanded to show nested indent guides. */
export const FullyExpanded: Story = {
  render: () => (
    <div className="max-w-sm">
      <TreeViewRoot
        collection={fileTree}
        defaultExpandedValue={["src", "src/components", "src/features"]}
      >
        <TreeViewTree>
          {fileTree.rootNode.children?.map((node, index) => (
            <FileTreeNode key={node.id} node={node} indexPath={[index]} />
          ))}
        </TreeViewTree>
      </TreeViewRoot>
    </div>
  ),
}

/** Activity-style tree — flat list with tool icons. */
export const ActivityStyle: Story = {
  render: () => {
    interface ActivityNode {
      id: string
      name: string
      icon?: "read" | "edit" | "search" | "web" | "bash"
      children?: ActivityNode[]
    }

    const iconMap = {
      read: BookOpen,
      edit: Pencil,
      search: Search,
      web: Globe,
      bash: Terminal,
    }

    const activityTree = createTreeCollection<ActivityNode>({
      nodeToValue: (node) => node.id,
      nodeToString: (node) => node.name,
      rootNode: {
        id: "ROOT",
        name: "",
        children: [
          { id: "t1", name: "Read(chapter-19.md)", icon: "read" },
          { id: "t2", name: 'Search("meditation bell")', icon: "search" },
          { id: "t3", name: "Edit(chapter-19.md)", icon: "edit" },
          { id: "t4", name: 'Web("monastery architecture")', icon: "web" },
          { id: "t5", name: "Bash(scripts/analyze.sh)", icon: "bash" },
        ],
      },
    })

    return (
      <div className="max-w-lg">
        <TreeViewRoot collection={activityTree}>
          <TreeViewTree>
            {activityTree.rootNode.children?.map((node, index) => {
              const Icon = node.icon ? iconMap[node.icon] : null
              return (
                <TreeViewNodeProvider key={node.id} node={node} indexPath={[index]}>
                  <TreeViewItem>
                    <TreeViewItemText>
                      {Icon && <Icon className="size-3.5 shrink-0 text-muted-foreground" />}
                      {node.name}
                    </TreeViewItemText>
                  </TreeViewItem>
                </TreeViewNodeProvider>
              )
            })}
          </TreeViewTree>
        </TreeViewRoot>
      </div>
    )
  },
}
