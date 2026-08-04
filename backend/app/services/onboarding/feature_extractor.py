from pathlib import Path

from structlog import get_logger

logger = get_logger(__name__)


class FeatureExtractor:
    FEATURE_INDICATORS = [
        "README.md",
        "CONTRIBUTING.md",
        "ARCHITECTURE.md",
        "docs/",
        "documentation/",
        "spec/",
        "specs/",
    ]

    def extract(self, clone_path: str) -> list[dict]:
        features: list[dict] = []
        root = Path(clone_path)

        for indicator in self.FEATURE_INDICATORS:
            path = root / indicator
            if path.exists():
                features.append(
                    {
                        "name": indicator.replace("/", "_").replace(".md", ""),
                        "source": str(path.relative_to(root)),
                        "type": "documentation",
                    }
                )

        return features
