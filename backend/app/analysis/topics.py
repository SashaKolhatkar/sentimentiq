"""Keyword, phrase, hashtag and topic-cluster analysis."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config
from ..utils import truncate

STOPWORDS = set(
    """a an the and or but if then than so of in on at to for from with by about into over under
    is are was were be been being it its it's this that these those i my me we our you your he she
    they them their there here what when where why how do does did done have has had having not no
    nor can could would should will just very really too also as more most some any all each every
    one two get got go going get im ive dont didnt doesnt isnt wasnt cant cannot lot lots even still
    would could product review reviews item bought buy purchased purchase use used using one star""".split()
)
HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)")


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9']{1,}", text.lower())
    return [w.strip("'") for w in words if w not in STOPWORDS and len(w) > 2]


def _phrases(texts: list[str], n: int, limit: int = 25) -> list[dict[str, Any]]:
    counter: Counter = Counter()
    for text in texts:
        words = _tokens(text)
        for i in range(len(words) - n + 1):
            counter[" ".join(words[i:i + n])] += 1
    return [{"phrase": p, "count": c} for p, c in counter.most_common(limit) if c > 1]


def _clusters(texts: list[str], sentiments: list[str]) -> list[dict[str, Any]]:
    if len(texts) < 6:
        return []
    try:
        vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), min_df=2, max_features=5000, sublinear_tf=True
        )
        matrix = vectorizer.fit_transform(texts)
        if matrix.shape[1] < 3:
            return []
        n_topics = int(min(8, max(2, len(texts) // 8), matrix.shape[1] - 1))
        nmf = NMF(n_components=n_topics, random_state=42, init="nndsvda", max_iter=220)
        weights = nmf.fit_transform(matrix)
        terms = np.array(vectorizer.get_feature_names_out())
        clusters: list[dict[str, Any]] = []
        for topic_idx in range(n_topics):
            top = np.argsort(nmf.components_[topic_idx])[-6:][::-1]
            members = np.where(weights[:, topic_idx] >= np.quantile(weights[:, topic_idx], 0.72))[0]
            if len(members) == 0:
                continue
            neg_share = float(
                np.mean([1.0 if sentiments[m] in {"negative", "mixed"} else 0.0 for m in members])
            )
            clusters.append(
                {
                    "id": f"topic-{topic_idx + 1}",
                    "label": ", ".join(terms[top][:3]),
                    "terms": list(terms[top]),
                    "size": int(len(members)),
                    "share": round(len(members) / len(texts), 3),
                    "negative_share": round(neg_share, 3),
                    "importance": round(len(members) / len(texts) * (0.7 + neg_share), 3),
                }
            )
        return sorted(clusters, key=lambda c: -c["importance"])
    except Exception:
        return []


def analyze_topics(
    texts: list[str],
    sentiments: list[str],
    timestamps: list[str | None] | None = None,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    keyword_counter: Counter = Counter()
    hashtag_counter: Counter = Counter()
    doc_keywords: list[set[str]] = []
    for text in texts:
        tokens = _tokens(text)
        keyword_counter.update(tokens)
        doc_keywords.append(set(tokens))
        hashtag_counter.update(h.lower() for h in HASHTAG_RE.findall(text))

    keywords = [
        {"word": word, "count": count}
        for word, count in keyword_counter.most_common(60)
        if count >= 2
    ]
    max_count = max((k["count"] for k in keywords), default=1)
    word_cloud = [
        {"text": k["word"], "value": k["count"], "weight": round(0.35 + 0.65 * k["count"] / max_count, 3)}
        for k in keywords[:45]
    ]

    bigrams = _phrases(texts, 2, 25)
    trigrams = _phrases(texts, 3, 20)
    clusters = _clusters(texts, sentiments)

    # Emerging terms: present in the later third of dated data but not the first third.
    emerging: list[dict[str, Any]] = []
    if timestamps and sum(1 for t in timestamps if t) >= 6:
        dated = sorted(
            [(t, set(_tokens(text))) for t, text in zip(timestamps, texts) if t],
            key=lambda x: str(x[0]),
        )
        cut = max(1, len(dated) // 3)
        early: Counter = Counter()
        late: Counter = Counter()
        for _, words in dated[:cut]:
            early.update(words)
        for _, words in dated[-cut:]:
            late.update(words)
        emerging = [
            {"word": word, "early": early.get(word, 0), "late": late.get(word, 0),
             "growth": round((late[word] + 1) / (early.get(word, 0) + 1), 2)}
            for word in late
            if late[word] >= 2 and late[word] > early.get(word, 0) and word not in STOPWORDS
        ]
        emerging = sorted(emerging, key=lambda x: -x["growth"])[:10]

    platform_topics: dict[str, Counter] = defaultdict(Counter)
    for platform, words in zip(platforms or ["unknown"] * len(texts), doc_keywords):
        platform_topics[platform or "unknown"].update(words)

    return {
        "keywords": keywords,
        "word_cloud": word_cloud,
        "bigrams": bigrams,
        "trigrams": trigrams,
        "hashtags": [{"tag": tag, "count": count} for tag, count in hashtag_counter.most_common(25)],
        "clusters": clusters,
        "emerging": emerging,
        "platform_topics": {
            p: [{"word": w, "count": c} for w, c in counts.most_common(12)]
            for p, counts in platform_topics.items()
        },
        "unique_terms": len(keyword_counter),
    }


class TopicAggregator:
    """Counts terms over every record; keeps a bounded deterministic sample for NMF."""

    def __init__(self, total_records: int) -> None:
        self.total_records = max(total_records, 1)
        self.keywords: Counter = Counter()
        self.hashtags: Counter = Counter()
        self.bigrams: Counter = Counter()
        self.trigrams: Counter = Counter()
        self.platform_topics: dict[str, Counter] = defaultdict(Counter)
        self.stride = max(1, self.total_records // config.TOPIC_FIT_SAMPLE)
        self.sample_texts: list[str] = []
        self.sample_sentiments: list[str] = []
        self.sample_timestamps: list[str | None] = []
        self.sample_platforms: list[str] = []

    def add(self, idx: int, text: str, sentiment: str, timestamp: str | None, platform: str) -> None:
        tokens = _tokens(text)
        token_set = set(tokens)
        self.keywords.update(tokens)
        self.hashtags.update(h.lower() for h in HASHTAG_RE.findall(text))
        for n, counter in ((2, self.bigrams), (3, self.trigrams)):
            for i in range(len(tokens) - n + 1):
                counter[" ".join(tokens[i:i + n])] += 1
        self.platform_topics[platform or "unknown"].update(token_set)

        if idx % self.stride == 0 and len(self.sample_texts) < config.TOPIC_FIT_SAMPLE:
            self.sample_texts.append(text)
            self.sample_sentiments.append(sentiment)
            self.sample_timestamps.append(timestamp)
            self.sample_platforms.append(platform or "unknown")

    def result(self) -> dict[str, Any]:
        keywords = [
            {"word": word, "count": count}
            for word, count in self.keywords.most_common(60) if count >= 2
        ]
        max_count = max((k["count"] for k in keywords), default=1)
        word_cloud = [
            {"text": k["word"], "value": k["count"], "weight": round(0.35 + 0.65 * k["count"] / max_count, 3)}
            for k in keywords[:45]
        ]
        clusters = _clusters(self.sample_texts, self.sample_sentiments)

        emerging: list[dict[str, Any]] = []
        dated = sorted(
            [(str(t), _tokens(text)) for t, text in zip(self.sample_timestamps, self.sample_texts) if t],
            key=lambda item: item[0],
        )
        if len(dated) >= 6:
            cut = max(1, len(dated) // 3)
            early: Counter = Counter()
            late: Counter = Counter()
            for _, words in dated[:cut]:
                early.update(words)
            for _, words in dated[-cut:]:
                late.update(words)
            emerging = [
                {"word": word, "early": early.get(word, 0), "late": late.get(word, 0),
                 "growth": round((late[word] + 1) / (early.get(word, 0) + 1), 2)}
                for word in late
                if late[word] >= 2 and late[word] > early.get(word, 0) and word not in STOPWORDS
            ]
            emerging = sorted(emerging, key=lambda x: -x["growth"])[:10]

        return {
            "keywords": keywords,
            "word_cloud": word_cloud,
            "bigrams": [{"phrase": p, "count": c} for p, c in self.bigrams.most_common(25) if c > 1],
            "trigrams": [{"phrase": p, "count": c} for p, c in self.trigrams.most_common(20) if c > 1],
            "hashtags": [{"tag": tag, "count": count} for tag, count in self.hashtags.most_common(25)],
            "clusters": clusters,
            "emerging": emerging,
            "platform_topics": {
                p: [{"word": w, "count": c} for w, c in counts.most_common(12)]
                for p, counts in self.platform_topics.items()
            },
            "unique_terms": len(self.keywords),
            "cluster_sample_size": len(self.sample_texts),
        }
