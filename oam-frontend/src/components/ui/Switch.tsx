import { forwardRef } from 'react'
import { clsx } from 'clsx'

export interface SwitchProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, label, id, ...props }, ref) => {
    const switchId = id || label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="flex items-center gap-2">
        <input
          ref={ref}
          type="checkbox"
          id={switchId}
          role="switch"
          className={clsx(
            'h-5 w-5 shrink-0 rounded border-surface-300 text-primary-600 focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:border-surface-600 dark:bg-surface-700',
            className
          )}
          {...props}
        />
        {label && <label htmlFor={switchId} className="text-sm font-medium text-surface-700 dark:text-surface-300 cursor-pointer">{label}</label>}
      </div>
    )
  }
)

Switch.displayName = 'Switch'