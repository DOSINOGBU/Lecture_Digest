import json
import unittest

from lecturedigest.errors import IndexingError
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_embeddings import (
    build_embedding_request,
    embed_query_with_openai,
    embed_search_index_with_openai,
    format_embedding_dry_run,
    parse_embedding_response,
)
from lecturedigest.openai_types import OpenAITransportResponse
from lecturedigest.rag import build_search_index
from support import (
    FakeTransport,
    chunked_lecture,
    embedding_response,
    openai_client,
)


class OpenAIEmbeddingTest(unittest.TestCase):
    def test_builds_embedding_request_with_boundary_metadata(self):
        request = build_embedding_request(["React DOM"])
        body = json.loads(request.body.decode("utf-8"))

        self.assertEqual(request.endpoint, "/v1/embeddings")
        self.assertEqual(request.use_case, "rag_embedding")
        self.assertEqual(request.model, "text-embedding-3-large")
        self.assertEqual(request.prompt_version, "embedding-v1")
        self.assertEqual(body["input"], ["React DOM"])
        self.assertIn("Embeddings API", request.external_data_boundary)

    def test_parses_embedding_response_in_request_order(self):
        response = embedding_response([[0.1, 0.2], [0.3, 0.4]])

        vectors = parse_embedding_response(response.body, expected_count=2)

        self.assertEqual(vectors, [[0.1, 0.2], [0.3, 0.4]])

    def test_rejects_embedding_response_with_missing_index(self):
        response = OpenAITransportResponse(
            status_code=200,
            body=json.dumps(
                {"data": [{"index": 1, "embedding": [0.1, 0.2]}]}
            ).encode("utf-8"),
        )

        with self.assertRaises(IndexingError) as context:
            parse_embedding_response(response.body, expected_count=1)

        self.assertEqual(
            context.exception.detail.code,
            "embedding_response_count_mismatch",
        )

    def test_fake_embedding_response_is_cached_on_search_entries(self):
        record = build_search_index(chunked_lecture())
        client = openai_client(embedding_response([[0.1, 0.2]]))

        result = embed_search_index_with_openai(record, client=client)

        self.assertTrue(result.client_result.succeeded)
        self.assertEqual(result.record.search_index[0]["embedding_status"], "ready")
        self.assertEqual(result.record.search_index[0]["embedding_vector"], [0.1, 0.2])
        self.assertIn(
            "openai_call",
            result.record.search_index[0]["embedding_metadata"],
        )
        self.assertEqual(result.record.rag_metadata["embedding_status"], "ready")

    def test_dry_run_does_not_mutate_record_or_require_api_key(self):
        record = build_search_index(chunked_lecture())
        client = OpenAIClient(
            transport=FakeTransport(embedding_response([[0.1, 0.2]])),
            env={},
        )

        result = embed_search_index_with_openai(
            record,
            client=client,
            dry_run=True,
        )

        self.assertTrue(result.dry_run)
        self.assertEqual(result.record, record)
        self.assertEqual(result.client_result.metadata.status, "dry_run")
        self.assertEqual(client.transport.calls, [])
        self.assertIn("willUpload=false", format_embedding_dry_run(result))

    def test_api_failure_marks_entries_and_preserves_issue_context(self):
        record = build_search_index(chunked_lecture())
        client = openai_client(
            OpenAITransportResponse(
                status_code=429,
                body=b'{"error": "rate limited"}',
            )
        )

        result = embed_search_index_with_openai(record, client=client)

        self.assertEqual(result.failed_request_count, 1)
        self.assertEqual(result.record.status, "embedding_failed")
        self.assertEqual(
            result.record.search_index[0]["embedding_status"],
            "failed",
        )
        self.assertEqual(result.record.issues[-1].code, "openai_rate_limited")
        self.assertTrue(result.record.issues[-1].retryable)

    def test_query_embedding_uses_same_client_contract(self):
        client = openai_client(embedding_response([[0.9, 0.1]]))

        result = embed_query_with_openai("React DOM", client=client)

        self.assertEqual(result.embedding, [0.9, 0.1])
        self.assertEqual(result.client_result.metadata.use_case, "rag_embedding")


if __name__ == "__main__":
    unittest.main()
