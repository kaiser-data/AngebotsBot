"""Taxonomy JSON is the single source of truth for Python + dashboard."""

from scripts.categorize_offers import FEW_SHOT_EXAMPLES, SUBCATEGORIES, TAXONOMY
from scripts.taxonomy import load_taxonomy, taxonomy_buckets, taxonomy_subcategories


def test_taxonomy_loads_ten_buckets():
    assert len(taxonomy_buckets()) == 10
    assert taxonomy_buckets() == TAXONOMY


def test_every_bucket_has_subcategories():
    subs = taxonomy_subcategories()
    assert set(subs) == set(TAXONOMY)
    for bucket, items in subs.items():
        assert items, bucket
        assert items == SUBCATEGORIES[bucket]


def test_few_shots_use_canonical_labels_only():
    for ex in FEW_SHOT_EXAMPLES:
        cat = ex["expected"]["category"]
        sub = ex["expected"]["subcategory"]
        assert cat in TAXONOMY, ex["title"]
        assert sub in SUBCATEGORIES[cat], (ex["title"], cat, sub)


def test_fallback_map_covers_all_buckets():
    data = load_taxonomy()
    assert set(data["fallback_subcategory"]) == set(data["buckets"])
    for bucket, sub in data["fallback_subcategory"].items():
        assert sub in data["subcategories"][bucket]
