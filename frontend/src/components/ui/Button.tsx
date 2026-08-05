import type { ButtonHTMLAttributes, ReactNode } from "react";


interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "text" | "danger";
  icon?: ReactNode;
}

export function Button({
  variant = "secondary",
  icon,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button className={`button button--${variant} ${className}`.trim()} {...props}>
      {icon}
      {children}
    </button>
  );
}
