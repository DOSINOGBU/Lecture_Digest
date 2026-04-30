import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.errors import EnrichmentError
from lecturedigest.frame_extraction import FrameCandidate
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_types import OpenAITransportResponse
from lecturedigest.vision_ocr import (
    build_vision_ocr_request,
    parse_vision_ocr_response,
    run_vision_ocr_on_frames,
)


class VisionOcrTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_builds_responses_payload_with_original_detail(self):
        frame = _frame(self.root)

        request = build_vision_ocr_request(frame)
        body = json.loads(request.body.decode("utf-8"))

        content = body["input"][0]["content"]
        self.assertEqual(request.endpoint, "/v1/responses")
        self.assertEqual(request.use_case, "vision_ocr")
        self.assertEqual(request.model, "gpt-4o")
        self.assertEqual(request.input_size_bytes, 11)
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["detail"], "original")
        self.assertIn("data:image/jpeg;base64,", content[1]["image_url"])
        self.assertNotIn(str(self.root), request.body.decode("utf-8"))

    def test_parses_direct_ocr_json(self):
        parsed = parse_vision_ocr_response(
            b'{"raw_ocr_text": "Raw", "refined_ocr_text": "Refined", '
            b'"confidence": 0.91}'
        )

        self.assertEqual(parsed["raw_ocr_text"], "Raw")
        self.assertEqual(parsed["refined_ocr_text"], "Refined")
        self.assertEqual(parsed["confidence"], 0.91)

    def test_parses_responses_output_text_json(self):
        response = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "raw_ocr_text": "Raw screen",
                                    "refined_ocr_text": "Refined screen",
                                    "confidence": 0.88,
                                }
                            ),
                        }
                    ]
                }
            ]
        }

        parsed = parse_vision_ocr_response(json.dumps(response).encode("utf-8"))

        self.assertEqual(parsed["raw_ocr_text"], "Raw screen")
        self.assertEqual(parsed["refined_ocr_text"], "Refined screen")
        self.assertEqual(parsed["confidence"], 0.88)

    def test_rejects_malformed_response(self):
        with self.assertRaises(EnrichmentError) as context:
            parse_vision_ocr_response(b'{"output": []}')

        self.assertEqual(
            context.exception.detail.code,
            "vision_ocr_response_malformed",
        )

    def test_openai_failure_becomes_failed_ocr_frame(self):
        frame = _frame(self.root)
        client = OpenAIClient(
            transport=FakeTransport(
                OpenAITransportResponse(
                    status_code=429,
                    body=b'{"error": "rate limited"}',
                )
            ),
            env={"OPENAI_API_KEY": "test-key"},
        )

        result = run_vision_ocr_on_frames([frame], client=client)
        payload_frame = result.ocr_payload["frames"][0]

        self.assertEqual(result.succeeded_frames, 0)
        self.assertEqual(payload_frame["status"], "failed")
        metadata = payload_frame["provider_metadata"]
        self.assertEqual(metadata["error_code"], "openai_rate_limited")
        self.assertTrue(metadata["openai_call"]["retryable"])

    def test_successful_run_normalizes_frame_payload(self):
        frame = _frame(self.root)
        client = OpenAIClient(
            transport=FakeTransport(
                OpenAITransportResponse(
                    status_code=200,
                    body=b'{"raw_ocr_text": "Raw", "refined_ocr_text": "Refined"}',
                )
            ),
            env={"OPENAI_API_KEY": "test-key"},
        )

        result = run_vision_ocr_on_frames([frame], client=client)
        payload_frame = result.ocr_payload["frames"][0]

        self.assertEqual(result.succeeded_frames, 1)
        self.assertEqual(payload_frame["raw_ocr_text"], "Raw")
        self.assertEqual(payload_frame["refined_ocr_text"], "Refined")
        self.assertEqual(payload_frame["frame_width"], 1920)
        self.assertEqual(payload_frame["source_frame_ts"], "00:00:01.000")
        self.assertEqual(payload_frame["provider_metadata"]["detail"], "original")


class FakeTransport:
    def __init__(self, response: OpenAITransportResponse) -> None:
        self.response = response
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _frame(root: Path) -> FrameCandidate:
    path = root / "frame-000001.jpg"
    path.write_bytes(b"fake image!")
    return FrameCandidate(
        frame_id="frame-000001",
        source_frame_ts="00:00:01.000",
        frame_path=path,
        frame_width=1920,
        frame_height=1080,
        change_score=1.0,
        extraction_method="interval",
    )


if __name__ == "__main__":
    unittest.main()
