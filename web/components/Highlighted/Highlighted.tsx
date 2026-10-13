// A text with some of its words marked (<mark>): the words a call and the artist's documents share
// (api/discover.py CardWhyOut / WhyOut). The API sends each word as written in this text, so the
// match is exact; only whole words are marked ("sound", not the "sound" inside "soundscape").
const escape = (word: string) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const Highlighted = ({ text, words }: { text: string; words: string[] }) => {
    if (words.length === 0) {
        return <>{text}</>;
    }
    // \p{L}: any letter, so a word next to an accented letter isn't cut ("café" stays whole)
    const pattern = new RegExp(`(?<!\\p{L})(${words.map(escape).join("|")})(?!\\p{L})`, "gu");
    const parts = text.split(pattern);   // the capture group keeps the matched words: odd indexes
    return (
        <>
            {parts.map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part))}
        </>
    );
};

export default Highlighted;
