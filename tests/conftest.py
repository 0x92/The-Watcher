import sys
from pathlib import Path

# Ensure the root of the repository is on PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[1]))

import types


if "prometheus_client" not in sys.modules:
    class _MetricStub:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def dec(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

    prometheus_stub = types.SimpleNamespace(
        Counter=_MetricStub,
        Histogram=_MetricStub,
        Gauge=_MetricStub,
        generate_latest=lambda: b"",
        CONTENT_TYPE_LATEST="text/plain",
    )
    sys.modules["prometheus_client"] = prometheus_stub

if "feedparser" not in sys.modules:
    def _feed_parse(*_args, **_kwargs):
        return types.SimpleNamespace(entries=[], get=lambda *_a, **_k: None)

    sys.modules["feedparser"] = types.SimpleNamespace(parse=_feed_parse)




if "sentence_transformers" not in sys.modules:
    class _SentenceTransformerStub:
        def __init__(self, *args, **kwargs):
            pass

        def encode(self, texts, normalize_embeddings=True):
            return [[0.0 for _ in range(16)] for _ in texts]

    sys.modules["sentence_transformers"] = types.SimpleNamespace(
        SentenceTransformer=_SentenceTransformerStub
    )

if "sklearn" not in sys.modules:
    sys.modules["sklearn"] = types.SimpleNamespace(
        cluster=types.SimpleNamespace(MiniBatchKMeans=None)
    )
