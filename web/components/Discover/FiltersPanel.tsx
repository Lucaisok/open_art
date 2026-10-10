import type { DiscoverState } from "@/lib/discover";
import type { DiscoverOptions } from "@/lib/types";
import styles from "./FiltersPanel.module.css";

type FiltersPanelProps = {
    state: DiscoverState;
    options: DiscoverOptions;
    onChange: (next: DiscoverState) => void;
    onClear: () => void;
};

type ListKey = "types" | "disciplines";

// The options panel under the search row (design: DISCOVER.md → 3. Options panel), without the
// matching terms (dropped in step 5b). The note on the order sits under the results heading. Native controls
// only: <details> lists of checkboxes, a <select>, and two checkboxes styled as pills.
const FiltersPanel = ({ state, options, onChange, onClear }: FiltersPanelProps) => {
    const toggleIn = (key: ListKey, value: string) =>
        onChange({
            ...state,
            [key]: state[key].includes(value) ? state[key].filter((v) => v !== value) : [...state[key], value],
        });

    const checklist = (key: ListKey, label: string, values: string[]) => (
        <details className={styles.list}>
            <summary className={styles.summary}>
                <span>
                    {label}
                    {state[key].length > 0 && ` · ${state[key].length}`}
                </span>
                <span aria-hidden="true" className={styles.caret}>
                    ▾
                </span>
            </summary>
            <fieldset className={styles.options}>
                <legend className={styles.visuallyHidden}>{label}</legend>
                {values.map((value) => (
                    <label key={value} className={styles.option}>
                        <input
                            type="checkbox"
                            checked={state[key].includes(value)}
                            onChange={() => toggleIn(key, value)}
                        />
                        <span>{value}</span>
                    </label>
                ))}
            </fieldset>
        </details>
    );

    return (
        <div id="search-options" className={styles.panel}>
            <section aria-labelledby="filters-heading" className={styles.filters}>
                <div className={styles.filtersHead}>
                    <h2 id="filters-heading" className={styles.heading}>
                        Filters
                    </h2>
                    <button type="button" className={styles.textButton} onClick={onClear}>
                        Clear all
                    </button>
                </div>

                {checklist("types", "Type", options.types)}
                {checklist("disciplines", "Discipline", options.disciplines)}

                <div className={styles.countryField}>
                    <label htmlFor="country" className={styles.visuallyHidden}>
                        Country
                    </label>
                    <select
                        id="country"
                        className={styles.select}
                        value={state.country}
                        onChange={(event) => onChange({ ...state, country: event.target.value })}
                    >
                        <option value="">Any country</option>
                        {options.countries.map((country) => (
                            <option key={country} value={country}>
                                {country}
                            </option>
                        ))}
                    </select>
                    <span aria-hidden="true" className={styles.selectCaret}>
                        ▾
                    </span>
                </div>

                <div className={styles.pills}>
                    <label className={styles.pill}>
                        <input
                            type="checkbox"
                            className={styles.pillBox}
                            checked={state.fundedOnly}
                            onChange={() => onChange({ ...state, fundedOnly: !state.fundedOnly })}
                        />
                        <span>Is funded</span>
                    </label>
                    <label className={styles.pill}>
                        <input
                            type="checkbox"
                            className={styles.pillBox}
                            checked={state.noFee}
                            onChange={() => onChange({ ...state, noFee: !state.noFee })}
                        />
                        <span>No application fee</span>
                    </label>
                </div>
            </section>
        </div>
    );
};

export default FiltersPanel;
