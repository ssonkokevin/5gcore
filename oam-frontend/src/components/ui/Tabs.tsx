import { createContext, useContext, useState, ReactNode, useEffect } from 'react'
import { clsx } from 'clsx'

interface TabsContextType {
  value: string
  onValueChange: (value: string) => void
}

const TabsContext = createContext<TabsContextType | null>(null)

interface TabsProps {
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  children: ReactNode
  className?: string
}

export function Tabs({ value, defaultValue, onValueChange, children, className }: TabsProps) {
  const isControlled = value !== undefined
  const [uncontrolledValue, setUncontrolledValue] = useState(defaultValue || '')
  const [initialized, setInitialized] = useState(false)

  // Initialize from defaultValue on mount
  useEffect(() => {
    if (!initialized && defaultValue) {
      setUncontrolledValue(defaultValue)
      setInitialized(true)
    }
  }, [defaultValue, initialized])

  const currentValue = isControlled ? value : uncontrolledValue
  const handleValueChange = (newValue: string) => {
    if (!isControlled) {
      setUncontrolledValue(newValue)
    }
    onValueChange?.(newValue)
  }

  return (
    <TabsContext.Provider value={{ value: currentValue, onValueChange: handleValueChange }}>
      <div className={clsx('space-y-4', className)}>{children}</div>
    </TabsContext.Provider>
  )
}

interface TabsListProps {
  children: ReactNode
  className?: string
}

export function TabsList({ children, className }: TabsListProps) {
  return (
    <div
      role="tablist"
      className={clsx(
        'inline-flex h-10 items-center justify-center rounded-lg bg-surface-100 dark:bg-surface-800 p-1 text-sm font-medium',
        className
      )}
    >
      {children}
    </div>
  )
}

interface TabsTriggerProps {
  value: string
  children: ReactNode
  disabled?: boolean
  className?: string
}

export function TabsTrigger({ value, children, disabled, className }: TabsTriggerProps) {
  const context = useContext(TabsContext)
  if (!context) throw new Error('TabsTrigger must be used within Tabs')

  const { value: activeValue, onValueChange } = context
  const isActive = activeValue === value

  return (
    <button
      role="tab"
      aria-selected={isActive}
      aria-controls={`tabs-content-${value}`}
      id={`tabs-trigger-${value}`}
      data-state={isActive ? 'active' : 'inactive'}
      disabled={disabled}
      onClick={() => !disabled && onValueChange(value)}
      className={clsx(
        'relative inline-flex h-8 items-center justify-center px-4 rounded-md text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
        isActive
          ? 'bg-white dark:bg-surface-700 text-surface-900 dark:text-surface-100 shadow-sm'
          : 'text-surface-500 hover:text-surface-900 dark:text-surface-400 dark:hover:text-surface-100',
        className
      )}
    >
      {children}
    </button>
  )
}

interface TabsContentProps {
  value: string
  children: ReactNode
  className?: string
}

export function TabsContent({ value, children, className }: TabsContentProps) {
  const context = useContext(TabsContext)
  if (!context) throw new Error('TabsContent must be used within Tabs')

  const { value: activeValue } = context
  const isActive = activeValue === value

  return (
    <div
      role="tabpanel"
      id={`tabs-content-${value}`}
      aria-labelledby={`tabs-trigger-${value}`}
      hidden={!isActive}
      className={clsx('mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2', className)}
    >
      {isActive && children}
    </div>
  )
}