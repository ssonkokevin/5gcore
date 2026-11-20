import { clsx } from 'clsx'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {}

export const Card = ({ className, children, ...props }: CardProps) => (
  <div className={clsx('card', className)} {...props}>
    {children}
  </div>
)

interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {}

export const CardHeader = ({ className, children, ...props }: CardHeaderProps) => (
  <div className={clsx('px-6 py-4 border-b border-surface-200 dark:border-surface-700', className)} {...props}>
    {children}
  </div>
)

interface CardTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {}

export const CardTitle = ({ className, children, ...props }: CardTitleProps) => (
  <h3 className={clsx('text-lg font-semibold text-surface-900 dark:text-surface-100', className)} {...props}>
    {children}
  </h3>
)

interface CardDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {}

export const CardDescription = ({ className, children, ...props }: CardDescriptionProps) => (
  <p className={clsx('text-sm text-surface-500 dark:text-surface-400 mt-1', className)} {...props}>
    {children}
  </p>
)

interface CardContentProps extends React.HTMLAttributes<HTMLDivElement> {}

export const CardContent = ({ className, children, ...props }: CardContentProps) => (
  <div className={clsx('p-6', className)} {...props}>
    {children}
  </div>
)

interface CardFooterProps extends React.HTMLAttributes<HTMLDivElement> {}

export const CardFooter = ({ className, children, ...props }: CardFooterProps) => (
  <div className={clsx('px-6 py-4 border-t border-surface-200 dark:border-surface-700', className)} {...props}>
    {children}
  </div>
)