import { imageUrl, thumbUrl } from "@/lib/images";
import type { ImageInfo } from "@/lib/types";
import styles from "./Thumbs.module.css";

type ThumbsProps = {
    images: ImageInfo[];
    title: string;                       // the project's, for each image's alt text
    max?: number;                        // shown at most; the rest counted ("+3")
    onRemove?: (id: string) => void;     // a Remove button under each image
    small?: boolean;                     // 40 px, not links: inside a label (the Apply picker), a click ticks it
};

// A project's images as small thumbnails. Each opens the full image in a new tab (unless `small`).
const Thumbs = ({ images, title, max = images.length, onRemove, small = false }: ThumbsProps) => {
    if (images.length === 0) {
        return null;
    }
    const shown = images.slice(0, max);
    return (
        <ul className={`${styles.thumbs} ${small ? styles.small : ""}`} aria-label={`Images of ${title}`}>
            {shown.map((image, n) => {
                // plain <img>: served by our API to its owner only, not through Next's optimiser
                // eslint-disable-next-line @next/next/no-img-element
                const img = <img src={thumbUrl(image.id)} alt={`${title}, image ${n + 1} of ${images.length}`}
                                 width={image.width} height={image.height} loading="lazy" />;
                return (
                <li key={image.id} className={styles.thumb}>
                    {small ? img : (
                        <a href={imageUrl(image.id)} target="_blank" rel="noopener noreferrer">
                            {img}
                        </a>
                    )}
                    {onRemove && (
                        <button type="button" className={styles.remove} onClick={() => onRemove(image.id)}>
                            Remove<span className={styles.visuallyHidden}> image {n + 1}</span>
                        </button>
                    )}
                </li>
                );
            })}
            {images.length > shown.length && (
                <li className={styles.more}>+{images.length - shown.length}</li>
            )}
        </ul>
    );
};

export default Thumbs;
