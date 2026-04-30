import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lecturedigest.errors import CorrectionError
from lecturedigest.ingestion import register_lecture
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_correction import (
    build_correction_request,
    correct_transcript_with_openai,
    parse_correction_response,
)
from lecturedigest.openai_types import OpenAITransportResponse
from support import FakeTransport, json_response, openai_client


class OpenAICorrectionTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_builds_correction_request_with_protected_terms(self):
        record = _lecture_with_subtitle(self.root, "Use React 18 in app.py")

        request = build_correction_request(record, record.segments)
        body = json.loads(request.body.decode("utf-8"))
        contract = json.loads(body["input"][1]["content"][0]["text"])
        segment = contract["segments"][0]

        self.assertEqual(request.endpoint, "/v1/responses")
        self.assertEqual(request.use_case, "transcript_correction")
        self.assertEqual(request.model, "gpt-4o")
        self.assertEqual(request.prompt_version, "transcript-correction-v1")
        self.assertIn("React", segment["protected_terms"])
        self.assertIn("18", segment["protected_terms"])
        self.assertIn("app.py", segment["protected_terms"])
        self.assertIn("transcript segment text", request.external_data_boundary)

    def test_parses_responses_output_text_json(self):
        response = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "corrections": [
                                        {
                                            "segment_id": "seg-000001",
                                            "corrected_text": "hello",
                                            "confidence": 0.96,
                                            "reason": "typo",
                                        }
                                    ]
                                }
                            ),
                        }
                    ]
                }
            ]
        }

        parsed = parse_correction_response(json.dumps(response).encode("utf-8"))

        self.assertEqual(parsed[0]["segment_id"], "seg-000001")
        self.assertEqual(parsed[0]["corrected_text"], "hello")
        self.assertEqual(parsed[0]["confidence"], 0.96)

    def test_rejects_malformed_response(self):
        with self.assertRaises(CorrectionError) as context:
            parse_correction_response(b'{"output": []}')

        self.assertEqual(
            context.exception.detail.code,
            "correction_response_malformed",
        )

    def test_subtitle_and_stt_transcripts_use_same_openai_correction_path(self):
        subtitle_record = _lecture_with_subtitle(self.root, "helo")
        stt_record = replace(subtitle_record, transcript_source="stt")

        subtitle_result = correct_transcript_with_openai(
            subtitle_record,
            client=openai_client(_success_response("hello")),
        )
        stt_result = correct_transcript_with_openai(
            stt_record,
            client=openai_client(_success_response("hello")),
        )

        self.assertEqual(subtitle_result.record.segments[0].text, "hello")
        self.assertEqual(stt_result.record.segments[0].text, "hello")
        self.assertEqual(subtitle_result.record.correction_log[0].source, "subtitle")
        self.assertEqual(stt_result.record.correction_log[0].source, "stt")

    def test_openai_failure_records_failed_corrections(self):
        record = _lecture_with_subtitle(self.root, "helo")
        client = openai_client(
            OpenAITransportResponse(
                status_code=429,
                body=b'{"error": "rate limited"}',
            )
        )

        result = correct_transcript_with_openai(record, client=client)

        self.assertEqual(result.failed_request_count, 1)
        self.assertEqual(result.record.segments[0].text, "helo")
        self.assertEqual(result.record.correction_log[0].status, "failed")
        self.assertTrue(result.record.correction_log[0].retryable)
        self.assertIn(
            "correction_failed",
            [issue.code for issue in result.record.issues],
        )

    def test_dry_run_does_not_mutate_record_or_require_api_key(self):
        record = _lecture_with_subtitle(self.root, "helo")
        client = OpenAIClient(transport=FakeTransport(_success_response("hello")), env={})

        result = correct_transcript_with_openai(record, client=client, dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.record.segments[0].text, "helo")
        self.assertEqual(result.client_results[0].metadata.status, "dry_run")
        self.assertEqual(client.transport.calls, [])


def _success_response(corrected_text: str) -> OpenAITransportResponse:
    return json_response(
        {
            "corrections": [
                {
                    "segment_id": "seg-000001",
                    "corrected_text": corrected_text,
                    "confidence": 0.96,
                    "reason": "typo",
                }
            ]
        }
    )


def _lecture_with_subtitle(root: Path, text: str):
    video = root / "lecture.mp4"
    subtitle = root / "lecture.srt"
    video.write_bytes(b"fake video")
    subtitle.write_text(
        f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n",
        encoding="utf-8",
    )
    return register_lecture(
        video_path=video,
        subtitle_path=subtitle,
        title="Intro",
        instructor="Teacher",
        category="Coding",
    )


if __name__ == "__main__":
    unittest.main()
