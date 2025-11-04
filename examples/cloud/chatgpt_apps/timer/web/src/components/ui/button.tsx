import * as React from "react"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline"
  size?: "default" | "sm" | "lg"
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    const baseStyles: React.CSSProperties = {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: '6px',
      fontSize: '14px',
      fontWeight: 500,
      transition: 'all 0.2s',
      cursor: 'pointer',
      border: 'none',
      outline: 'none',
    }

    const sizeStyles: React.CSSProperties = {
      default: {
        padding: '0.5rem 1rem',
        height: '40px',
      },
      sm: {
        padding: '0.375rem 0.75rem',
        height: '36px',
      },
      lg: {
        padding: '0.625rem 1.25rem',
        height: '44px',
      },
    }[size]

    const variantStyles: React.CSSProperties = {
      default: {
        backgroundColor: '#3b82f6',
        color: 'white',
      },
      outline: {
        backgroundColor: 'transparent',
        border: '1px solid #e5e7eb',
        color: '#374151',
      },
    }[variant]

    return (
      <button
        ref={ref}
        className={className}
        style={{
          ...baseStyles,
          ...sizeStyles,
          ...variantStyles,
          ...props.style,
        }}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
