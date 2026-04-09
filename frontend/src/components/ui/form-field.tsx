import * as React from "react"

import { cn } from "@/lib/utils"
import { Label } from "@/components/ui/label"

type FormFieldProps = {
  label?: string
  error?: string
  helperText?: string
  // Props typed with id so cloneElement can forward ids; index signature covers aria-* attrs.
  children: React.ReactElement<{ id?: string; [key: string]: unknown }>
  className?: string
}

function FormField({ label, error, helperText, children, className }: FormFieldProps) {
  const id = React.useId()
  const errorId = error ? `${id}-error` : undefined
  const helperId = helperText ? `${id}-helper` : undefined
  const describedBy = [errorId, helperId].filter(Boolean).join(" ") || undefined

  const child = React.cloneElement(children, {
    id: children.props.id ?? id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
  })

  return (
    <div data-slot="form-field" className={cn("grid gap-2", className)}>
      {label ? <Label htmlFor={children.props.id ?? id}>{label}</Label> : null}
      {child}
      {error ? (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {helperText && !error ? (
        <p id={helperId} className="text-sm text-muted-foreground">
          {helperText}
        </p>
      ) : null}
    </div>
  )
}

export { FormField, type FormFieldProps }
