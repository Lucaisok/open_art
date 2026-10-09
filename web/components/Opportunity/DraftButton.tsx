"use client";

import { useState } from "react";
import styles from "./OpportunityView.module.css";

// "Draft an application": a placeholder until the application agent (web app step 6)
const DraftButton = () => {
    const [note, setNote] = useState("");
    return (
        <>
            <button type="button" className={styles.draft} onClick={() => setNote("Drafting comes in the next step.")}>
                <span>Draft an application</span>
                <span aria-hidden="true" className={styles.draftArrow}>
                    →
                </span>
            </button>
            <p aria-live="polite" className={styles.draftNote}>
                {note}
            </p>
        </>
    );
};

export default DraftButton;
