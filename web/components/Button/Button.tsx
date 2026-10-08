import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "danger";
};

const Button = ({ variant = "primary", className, type = "button", ...props }: ButtonProps) => (
    <button
        type={type}
        className={[styles.button, styles[variant], className].filter(Boolean).join(" ")}
        {...props}
    />
);

export default Button;
