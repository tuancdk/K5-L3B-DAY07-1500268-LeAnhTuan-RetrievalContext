import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluate_retrieval import is_hit, pack_context  # noqa: E402
from src.retrieval import BM25, HybridRRF, tokenize  # noqa: E402


def chunk(i, text, page=1, section="s1"):
    return {"id": f"c{i}", "text": text, "source_id": "doc", "source": "doc.pdf", "page": page,
            "metadata": {"section": section}}


CHUNKS = [chunk(1, "Thời hạn cho vay trung hạn từ 1 năm đến 5 năm."),
          chunk(2, "Lợi thế thương mại được phân bổ trong 10 năm.", page=2, section="s2"),
          chunk(3, "Ngân hàng có 129 chi nhánh và 238 phòng giao dịch.", page=3)]


class FakeDense:
    def __init__(self, order):
        self.order = order

    def search(self, query, *, filters=None, top_k=3):
        return [{**CHUNKS[i], "rank": r, "score": 1.0 / r} for r, i in enumerate(self.order[:top_k], 1)]


class RetrievalTests(unittest.TestCase):
    def test_tokenize_vietnamese_bigrams(self):
        self.assertEqual(tokenize("Chi Nhánh mới", bigrams=True),
                         ["chi", "nhánh", "mới", "chi_nhánh", "nhánh_mới"])

    def test_bm25_ranks_matching_chunk_first_and_filters(self):
        bm25 = BM25(CHUNKS)
        self.assertEqual(bm25.search("lợi thế thương mại phân bổ")[0]["id"], "c2")
        self.assertEqual(bm25.search("lợi thế thương mại", filters={"section": "s1"}), [])
        self.assertEqual(bm25.search("xyz qwe"), [])

    def test_rrf_fuses_ranks(self):
        bm25 = BM25(CHUNKS)
        hybrid = HybridRRF(FakeDense([0, 2, 1]), bm25, k=60, candidates=3)
        out = hybrid.search("lợi thế thương mại phân bổ 10 năm", top_k=3)
        self.assertEqual([c["rank"] for c in out], [1, 2, 3])
        self.assertEqual(len({c["id"] for c in out}), 3)
        top = out[0]
        self.assertAlmostEqual(top["score"], sum(1 / (60 + r) for r in top["source_ranks"].values() if r), places=5)

    def test_hit_is_normalized_and_page_bound(self):
        gold = [{"source_id": "doc", "page": 1, "evidence": "từ 1 NĂM  đến\n5 năm"}]
        self.assertTrue(is_hit(CHUNKS[0], gold))
        self.assertFalse(is_hit({**CHUNKS[0], "page": 2}, gold))

    def test_pack_context_skips_chunks_over_budget(self):
        kept, text = pack_context(CHUNKS, budget=len(CHUNKS[0]["text"]) + 40)
        self.assertEqual([c["id"] for c in kept], ["c1"])
        self.assertIn("trang 1", text)


if __name__ == "__main__":
    unittest.main()
