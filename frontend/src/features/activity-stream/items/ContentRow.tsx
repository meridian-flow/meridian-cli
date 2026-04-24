import Markdown from "react-markdown"

import type { ContentItem } from "../types"

type ContentRowProps = {
  item: ContentItem
}

export function ContentRow({ item }: ContentRowProps) {
  return (
    <div className="grid grid-cols-[1.375rem_1fr_auto] px-3">
      <div className="col-span-3 py-2 pl-[11px]">
        <div className="text-sm text-foreground [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:text-xs [&_code]:rounded [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-xs [&_p]:leading-relaxed [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4 [&_li]:my-0.5 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold [&_a]:text-primary [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:italic">
          <Markdown>{item.text}</Markdown>
        </div>
      </div>
    </div>
  )
}
