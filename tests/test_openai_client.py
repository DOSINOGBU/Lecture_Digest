import unittest

from lecturedigest.errors import OpenAIClientError
from lecturedigest.openai_client import (
    OpenAIClient,
    OpenAIRequest,
    OpenAITransportResponse,
    error_code_for_status,
    format_dry_run_result,
    is_retryable_status,
    json_body,
    load_openai_api_key,
    redact_sensitive,
)
from support import FakeTransport, TimeoutTransport, openai_env


class OpenAIClientTest(unittest.TestCase):
    def test_loads_api_key_from_environment_mapping(self):
        self.assertEqual(
            load_openai_api_key({"OPENAI_API_KEY": " test-openai-key "}),
            "test-openai-key",
        )

    def test_rejects_missing_api_key(self):
        with self.assertRaises(OpenAIClientError) as context:
            load_openai_api_key({})

        self.assertEqual(
            context.exception.detail.code,
            "openai_api_key_missing",
        )
        self.assertFalse(context.exception.detail.retryable)

    def test_rejects_empty_api_key(self):
        with self.assertRaises(OpenAIClientError) as context:
            load_openai_api_key({"OPENAI_API_KEY": "  "})

        self.assertEqual(
            context.exception.detail.code,
            "openai_api_key_missing",
        )

    def test_fake_success_response_records_standard_metadata(self):
        transport = FakeTransport(
            OpenAITransportResponse(
                status_code=200,
                body=b'{"ok": true}',
            )
        )
        client = OpenAIClient(transport=transport, env=openai_env())

        result = client.send(_request())

        self.assertTrue(result.succeeded)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.body, b'{"ok": true}')
        self.assertEqual(result.metadata.provider, "openai")
        self.assertEqual(result.metadata.endpoint, "/v1/responses")
        self.assertEqual(result.metadata.use_case, "unit_test")
        self.assertEqual(result.metadata.model, "gpt-4o")
        self.assertEqual(result.metadata.prompt_version, "prompt-v1")
        self.assertEqual(result.metadata.input_size_bytes, 15)
        self.assertEqual(result.metadata.status, "succeeded")
        self.assertFalse(result.metadata.retryable)
        self.assertEqual(result.metadata.estimated_cost, "unknown")
        self.assertIsNone(result.to_processing_issue())
        self.assertEqual(
            transport.calls[0]["headers"]["Authorization"],
            "Bearer test-openai-key",
        )

    def test_fake_429_response_becomes_retryable_issue(self):
        client = OpenAIClient(
            transport=FakeTransport(
                OpenAITransportResponse(
                    status_code=429,
                    body=b'{"error": "rate limited"}',
                )
            ),
            env=openai_env(),
        )

        result = client.send(_request())
        issue = result.to_processing_issue(stage="transcription")

        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "openai_rate_limited")
        self.assertTrue(result.metadata.retryable)
        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "openai_rate_limited")
        self.assertEqual(issue.stage, "transcription")
        self.assertTrue(issue.retryable)

    def test_fake_500_response_becomes_retryable_issue(self):
        client = OpenAIClient(
            transport=FakeTransport(OpenAITransportResponse(status_code=500)),
            env=openai_env(),
        )

        result = client.send(_request())

        self.assertEqual(result.error_code, "openai_server_error")
        self.assertTrue(result.metadata.retryable)

    def test_timeout_becomes_retryable_failure_without_raising(self):
        client = OpenAIClient(
            transport=TimeoutTransport(),
            env=openai_env(),
        )

        result = client.send(_request())

        self.assertEqual(result.error_code, "openai_request_timeout")
        self.assertTrue(result.metadata.retryable)
        self.assertIsNotNone(result.to_processing_issue())

    def test_dry_run_skips_api_key_and_transport(self):
        transport = FakeTransport(OpenAITransportResponse(status_code=200))
        client = OpenAIClient(transport=transport, env={})

        result = client.send(_request(), dry_run=True)

        self.assertEqual(result.metadata.status, "dry_run")
        self.assertFalse(result.metadata.retryable)
        self.assertEqual(transport.calls, [])
        output = format_dry_run_result(result)
        self.assertIn("endpoint=/v1/responses", output)
        self.assertIn("model=gpt-4o", output)
        self.assertIn("inputSizeBytes=15", output)
        self.assertIn("externalDataBoundary=text-only", output)

    def test_redacts_api_key_authorization_and_local_paths(self):
        payload = {
            "Authorization": "Bearer test-openai-key",
            "message": (
                "failed for test-openai-key at "
                "C:\\Users\\name\\lecture.mp4 and /home/name/file.txt"
            ),
            "nested": [{"api_key": "test-openai-key"}],
        }

        redacted = redact_sensitive(payload, env=openai_env())

        self.assertEqual(redacted["Authorization"], "[REDACTED]")
        self.assertNotIn("test-openai-key", str(redacted))
        self.assertNotIn("C:\\Users", str(redacted))
        self.assertNotIn("/home/name", str(redacted))
        self.assertIn("[LOCAL_PATH]", str(redacted))

    def test_retryable_status_classification(self):
        self.assertTrue(is_retryable_status(429))
        self.assertTrue(is_retryable_status(500))
        self.assertTrue(is_retryable_status(503))
        self.assertFalse(is_retryable_status(400))
        self.assertFalse(is_retryable_status(401))
        self.assertEqual(error_code_for_status(401), "openai_auth_failed")
        self.assertEqual(error_code_for_status(400), "openai_client_error")


def _request() -> OpenAIRequest:
    return OpenAIRequest(
        endpoint="/v1/responses",
        use_case="unit_test",
        model="gpt-4o",
        prompt_version="prompt-v1",
        body=json_body({"input": "hello"}),
        input_size_bytes=15,
        external_data_boundary="text-only",
    )

if __name__ == "__main__":
    unittest.main()
