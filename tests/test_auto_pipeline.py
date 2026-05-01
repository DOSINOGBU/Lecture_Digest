import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lecturedigest.auto_pipeline import (
    AutoPipelineDependencies,
    AutoPipelineOptions,
    planned_auto_pipeline_steps,
    process_lecture_with_auto_ai,
)
from lecturedigest.errors import ValidationError
from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.storage import JsonLectureRepository
from support import lecture_record, segment


class AutoPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Path(self.temp_dir.name) / "lectures.json"
        self.repository = JsonLectureRepository(self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_subtitle_record_skips_stt_and_ocr_by_default(self):
        record = _subtitle_record()
        self.repository.save(record)
        fake = _FakePipelineSteps()

        result = process_lecture_with_auto_ai(
            self.repository,
            lecture_id=record.lecture_id,
            options=AutoPipelineOptions(openai=True),
            dependencies=fake.dependencies(),
        )

        self.assertEqual(result.status, "completed")
        self.assertNotIn("transcribe", fake.calls)
        self.assertNotIn("ocr", fake.calls)
        self.assertEqual(
            fake.calls,
            [
                "finalize_transcript",
                "chunk",
                "index",
                "generate_notes",
                "generate_cards",
                "generate_quizzes",
            ],
        )
        saved = _saved_record(self.repository, record)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.pipeline_metadata["status"], "completed")
        self.assertEqual(
            saved.approved_note["approval_mode"],
            "auto_best_candidate",
        )
        self.assertEqual(len(saved.flashcards), 1)
        self.assertEqual(len(saved.quiz_items), 1)

    def test_stt_pending_record_runs_transcribe_before_processing(self):
        record = _stt_pending_record()
        self.repository.save(record)
        fake = _FakePipelineSteps()

        process_lecture_with_auto_ai(
            self.repository,
            lecture_id=record.lecture_id,
            options=AutoPipelineOptions(openai=True),
            dependencies=fake.dependencies(),
        )

        self.assertEqual(fake.calls[0], "transcribe")
        saved = _saved_record(self.repository, record)
        self.assertEqual(saved.segments[0].text, "Generated transcript")

    def test_include_ocr_adds_ocr_step(self):
        record = _subtitle_record()
        self.repository.save(record)
        fake = _FakePipelineSteps()

        process_lecture_with_auto_ai(
            self.repository,
            lecture_id=record.lecture_id,
            options=AutoPipelineOptions(openai=True, include_ocr=True),
            dependencies=fake.dependencies(),
        )

        self.assertIn("ocr", fake.calls)

    def test_dry_run_reports_plan_without_api_key_or_save(self):
        record = _subtitle_record()
        self.repository.save(record)

        result = process_lecture_with_auto_ai(
            self.repository,
            lecture_id=record.lecture_id,
            options=AutoPipelineOptions(openai=True, dry_run=True, include_ocr=True),
            dependencies=AutoPipelineDependencies(
                require_api_key=lambda: (_ for _ in ()).throw(AssertionError("api"))
            ),
        )

        self.assertEqual(result.status, "dry_run")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.steps[0]["step"], "ocr")
        self.assertEqual(_pipeline_metadata(self.repository, record), {})

    def test_subtitle_unmatched_blocks_auto_pipeline(self):
        record = replace(
            lecture_record([]),
            status="subtitle_unmatched",
            transcript_source="subtitle_unmatched",
        )
        self.repository.save(record)

        with self.assertRaises(ValidationError) as context:
            process_lecture_with_auto_ai(
                self.repository,
                lecture_id=record.lecture_id,
                options=AutoPipelineOptions(openai=True, dry_run=True),
            )

        self.assertEqual(context.exception.detail.code, "subtitle_unmatched_auto_ai_blocked")

    def test_blocked_actual_run_records_preflight_failure(self):
        record = replace(
            lecture_record([]),
            status="subtitle_unmatched",
            transcript_source="subtitle_unmatched",
        )
        self.repository.save(record)

        with self.assertRaises(ValidationError):
            process_lecture_with_auto_ai(
                self.repository,
                lecture_id=record.lecture_id,
                options=AutoPipelineOptions(openai=True),
            )

        blocked = _saved_record(self.repository, record)
        self.assertEqual(blocked.pipeline_metadata["status"], "failed")
        self.assertEqual(blocked.pipeline_metadata["failed_step"], "preflight")
        self.assertEqual(blocked.issues[-1].code, "subtitle_unmatched_auto_ai_blocked")

    def test_openai_flag_is_required(self):
        record = _subtitle_record()
        self.repository.save(record)

        with self.assertRaises(ValidationError) as context:
            process_lecture_with_auto_ai(
                self.repository,
                lecture_id=record.lecture_id,
                options=AutoPipelineOptions(openai=False),
            )

        self.assertEqual(context.exception.detail.code, "openai_required_for_auto_pipeline")

    def test_resume_skips_completed_steps(self):
        record = replace(
            _subtitle_record(),
            pipeline_metadata={"completed_steps": ["finalize_transcript"]},
        )
        self.repository.save(record)
        fake = _FakePipelineSteps()

        result = process_lecture_with_auto_ai(
            self.repository,
            lecture_id=record.lecture_id,
            options=AutoPipelineOptions(openai=True, resume=True),
            dependencies=fake.dependencies(),
        )

        self.assertEqual(result.steps[0], {"step": "finalize_transcript", "status": "skipped"})
        self.assertNotIn("finalize_transcript", fake.calls)

    def test_all_blocked_note_candidates_stop_before_cards_and_quizzes(self):
        record = _subtitle_record()
        self.repository.save(record)
        fake = _FakePipelineSteps(block_all_notes=True)

        with self.assertRaises(ValidationError) as context:
            process_lecture_with_auto_ai(
                self.repository,
                lecture_id=record.lecture_id,
                options=AutoPipelineOptions(openai=True),
                dependencies=fake.dependencies(),
            )

        self.assertEqual(context.exception.detail.code, "auto_note_candidate_blocked")
        self.assertNotIn("generate_cards", fake.calls)
        metadata = _pipeline_metadata(self.repository, record)
        self.assertEqual(metadata["status"], "failed")
        self.assertEqual(metadata["failed_step"], "auto_approve_note")

    def test_time_budget_saves_partial_checkpoint(self):
        record = _subtitle_record()
        self.repository.save(record)
        fake = _FakePipelineSteps()

        result = process_lecture_with_auto_ai(
            self.repository,
            lecture_id=record.lecture_id,
            options=AutoPipelineOptions(openai=True, time_budget_seconds=0),
            dependencies=fake.dependencies(),
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(fake.calls, [])
        metadata = _pipeline_metadata(self.repository, record)
        self.assertTrue(metadata["time_budget_exhausted"])

    def test_planned_steps_include_stt_only_when_needed(self):
        subtitle_record = _subtitle_record()
        stt_record = _stt_pending_record()

        self.assertNotIn(
            "transcribe",
            planned_auto_pipeline_steps(subtitle_record, include_ocr=False),
        )
        self.assertEqual(
            planned_auto_pipeline_steps(stt_record, include_ocr=False)[0],
            "transcribe",
        )


class _FakePipelineSteps:
    def __init__(self, *, block_all_notes: bool = False) -> None:
        self.calls: list[str] = []
        self.block_all_notes = block_all_notes

    def dependencies(self) -> AutoPipelineDependencies:
        return AutoPipelineDependencies(
            require_api_key=lambda: "test-key",
            transcribe=self._record_step("transcribe"),
            ocr=self._record_step("ocr"),
            correct=self._record_step("finalize_transcript"),
            chunk=self._record_step("chunk"),
            index=self._record_step("index"),
            generate_notes=self._notes_step,
            generate_cards=self._cards_step,
            generate_quizzes=self._quizzes_step,
        )

    def _record_step(self, name: str):
        def run(record: LectureRecord, options: AutoPipelineOptions) -> LectureRecord:
            self.calls.append(name)
            if name == "transcribe":
                return replace(
                    record,
                    status="transcript_ready",
                    stage="transcription",
                    transcript_source="stt",
                    segments=[
                        TranscriptSegment(
                            segment_id="seg-1",
                            start_ts="00:00:00.000",
                            end_ts="00:00:05.000",
                            text="Generated transcript",
                        )
                    ],
                )
            return replace(record, status=f"{name}_ready", stage=name)

        return run

    def _notes_step(self, record, options, checkpoint):
        self.calls.append("generate_notes")
        candidates = (
            [_note_candidate("blocked", failed_rules=["source_mapping_required"])]
            if self.block_all_notes
            else [
                _note_candidate("blocked", failed_rules=["visible_source_artifacts"]),
                _note_candidate("ready"),
                _note_candidate("review", warnings=["minor_warning"]),
            ]
        )
        return replace(
            record,
            status="note_candidates_ready",
            stage="note_generation",
            note_candidates=candidates,
        )

    def _cards_step(self, record, options, checkpoint):
        self.calls.append("generate_cards")
        self._require_auto_approved_note(record)
        return replace(
            record,
            status="cards_ready",
            stage="anki_cards",
            flashcards=[
                {
                    "card_id": "card-1",
                    "status": "ready",
                    "source_note_candidate_id": record.approved_note["candidate_id"],
                }
            ],
        )

    def _quizzes_step(self, record, options, checkpoint):
        self.calls.append("generate_quizzes")
        self._require_auto_approved_note(record)
        return replace(
            record,
            status="quizzes_ready",
            stage="quiz_generation",
            quiz_items=[
                {
                    "quiz_id": "quiz-1",
                    "status": "ready",
                    "source_note_candidate_id": record.approved_note["candidate_id"],
                }
            ],
        )

    def _require_auto_approved_note(self, record: LectureRecord) -> None:
        if record.approved_note.get("approval_mode") != "auto_best_candidate":
            raise AssertionError("card/quiz generation requires auto-approved note")


def _note_candidate(
    candidate_id: str,
    *,
    failed_rules: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "status": "review_required" if warnings else "ready",
        "markdown": "# Intro\n\n## HTML\n\nHTML is the document structure.",
        "sections": [
            {
                "section_key": "html",
                "heading": "HTML",
                "segment_ids": ["seg-1"],
                "start_ts": "00:00:00.000",
                "end_ts": "00:00:05.000",
            }
        ],
        "validation": {
            "status": "failed" if failed_rules else "passed",
            "failed_rules": failed_rules or [],
            "warnings": warnings or [],
            "body_depth": {"metrics": {"source_coverage_ratio": 1.0}},
            "difficulty_explanations": {
                "metrics": {
                    "expected_count": 0,
                    "known_acronym_count": 0,
                    "easy_marker_count": 0,
                }
            },
        },
        "generator_notes": {"difficulty_explanations": []},
    }


def _stt_pending_record() -> LectureRecord:
    return replace(
        lecture_record([]),
        subtitle_path=None,
        transcript_source="stt_pending",
        status="stt_required",
        stage="awaiting_stt",
    )


def _subtitle_record() -> LectureRecord:
    return lecture_record(
        [segment("seg-1", "00:00:00.000", "00:00:05.000", "HTML")]
    )


def _saved_record(
    repository: JsonLectureRepository,
    record: LectureRecord,
) -> LectureRecord:
    saved = repository.get_lecture(record.lecture_id)
    if saved is None:
        raise AssertionError(f"Lecture not saved: {record.lecture_id}")
    return saved


def _pipeline_metadata(
    repository: JsonLectureRepository,
    record: LectureRecord,
) -> dict[str, object]:
    return _saved_record(repository, record).pipeline_metadata


if __name__ == "__main__":
    unittest.main()
