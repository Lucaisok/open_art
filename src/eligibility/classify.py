"""
OpenArt — load the RQ1 eligibility classifier and label sentence chunks.

The model is the one exported by notebooks/eligibility_classifier.ipynb:
a Logistic Regression that reads 768-number sentence embeddings. Text goes
through two steps: fastembed turns each chunk into a vector, then the
classifier turns the vector into class probabilities.

    clf = EligibilityClassifier()
    clf.predict(["Applicants must be resident in Scotland."])
    -> [Prediction(label="RESIDENCE", confidence=0.99, probabilities={...})]
"""

import json
import os
from dataclasses import dataclass
from importlib.metadata import version

import joblib
import numpy as np
from fastembed import TextEmbedding

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(REPO_ROOT, "artifacts", "eligibility_classifier.joblib")
META_PATH = os.path.join(REPO_ROOT, "artifacts", "eligibility_classifier.json")

# same persistent cache as the notebook: fastembed's default is the system temp
# dir, which macOS clears, forcing a ~0.2 GB re-download
EMBEDDING_CACHE_DIR = os.path.expanduser("~/.cache/fastembed")

# sentences embedded per batch. fastembed pads every sentence in a batch to
# the longest one, so with its default (256) a single 300-word chunk makes the
# whole batch slow and memory-hungry. Small batches of similar-length
# sentences (see predict) waste almost no work on padding: on the dev laptop
# this cut the full corpus from 40+ minutes to a few. The vectors are exactly
# the same either way, since each sentence is embedded on its own.
EMBEDDING_BATCH_SIZE = 8


@dataclass
class Prediction:
    label: str                       # most likely class, e.g. "AGE"
    confidence: float                # its probability, 0-1
    probabilities: dict[str, float]  # every class -> probability (sums to 1)


class EligibilityClassifier:
    def __init__(self, model_path: str = MODEL_PATH, meta_path: str = META_PATH):
        with open(meta_path) as f:
            self.metadata = json.load(f)
        self._check_versions()

        # joblib files are pickles, which can run code when loaded: only ever
        # load our own artifact, never a file from an untrusted source
        self.model = joblib.load(model_path)
        self.labels = list(self.model.classes_)

        # the classifier is only meaningful on vectors from the SAME embedding
        # model it was trained on, which the metadata records
        self.embedder = TextEmbedding(self.metadata["embedding_model"], cache_dir=EMBEDDING_CACHE_DIR)

    def _check_versions(self) -> None:
        """Refuse to run if the installed libraries differ from the ones the
        model was trained with. A different scikit-learn can unpickle the model
        wrongly; a different fastembed can produce different vectors. Either
        would give wrong predictions without any error, so fail loudly instead."""
        for package, trained_with in self.metadata["versions"].items():
            installed = version(package)
            if installed != trained_with:
                raise RuntimeError(
                    f"{package} {installed} is installed but the eligibility classifier was "
                    f"trained with {trained_with}: re-export the model from "
                    f"notebooks/eligibility_classifier.ipynb, or install {package}=={trained_with}"
                )

    def embed(self, texts: list[str]) -> np.ndarray:
        """Turn texts into the vectors the classifier reads, one row per text.
        Public so evaluation scripts embed exactly the way the product does."""
        # embed shortest to longest so each batch holds similar lengths, then
        # put the vectors back in the caller's order
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        sorted_vectors = list(self.embedder.embed([texts[i] for i in order], batch_size=EMBEDDING_BATCH_SIZE))
        vectors = np.empty((len(texts), len(sorted_vectors[0])), dtype=np.float32)
        for position, i in enumerate(order):
            vectors[i] = sorted_vectors[position]

        if vectors.shape[1] != self.metadata["embedding_dim"]:
            raise RuntimeError(
                f"embeddings have {vectors.shape[1]} dimensions, the classifier expects "
                f"{self.metadata['embedding_dim']}"
            )
        return vectors

    def predict(self, texts: list[str]) -> list[Prediction]:
        """Classify each chunk. Returns one Prediction per text, in order."""
        if not texts:
            return []
        vectors = self.embed(texts)

        predictions = []
        for row in self.model.predict_proba(vectors):
            best = int(row.argmax())
            predictions.append(Prediction(
                label=self.labels[best],
                confidence=float(row[best]),
                probabilities={label: float(p) for label, p in zip(self.labels, row)},
            ))
        return predictions
