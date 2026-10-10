import styles from "./Skeleton.module.css";

type BoneProps = {
    width?: string;      // any CSS length: "60%", "120px"
    height?: string;
    radius?: string;
    className?: string;
};

// One grey placeholder shape, with the sweeping light band. Decoration only: hidden from screen readers.
export const Bone = ({ width = "100%", height = "16px", radius, className }: BoneProps) => (
    <span
        aria-hidden="true"
        className={`${styles.bone} ${className ?? ""}`}
        style={{ width, height, borderRadius: radius }}
    />
);

// A placeholder card, shaped like a Discover result: type pill, title, facts, then the verdict at the bottom
export const CardBone = ({ minHeight = "340px" }: { minHeight?: string }) => (
    <div aria-hidden="true" className={styles.card} style={{ minHeight }}>
        <Bone width="90px" height="22px" radius="999px" />
        <Bone width="85%" height="26px" />
        <Bone width="60%" height="26px" />
        <Bone width="45%" height="14px" />
        <div className={styles.spacer} />
        <Bone width="110px" height="28px" radius="999px" />
        <Bone width="95%" height="12px" />
        <Bone width="70%" height="12px" />
    </div>
);

// What screen readers hear instead of the shapes
export const LoadingLabel = ({ children }: { children: React.ReactNode }) => (
    <p role="status" className={styles.visuallyHidden}>
        {children}
    </p>
);
