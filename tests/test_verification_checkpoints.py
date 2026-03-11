"""Unit tests for verification_checkpoints module.

Tests cover all 7 verification functions plus the VerificationResult class.
Run with: pytest tests/test_verification_checkpoints.py -v
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime
import time
import sys
import os

# Add scripts/utils to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts', 'utils'))

from verification_checkpoints import (
    VerificationError,
    VerificationResult,
    verify_file_created,
    verify_json_file,
    verify_api_response,
    verify_trello_card_created,
    verify_github_commit,
    create_verification_report
)


class TestVerificationResult:
    """Test VerificationResult class."""

    def test_verification_result_creation(self):
        result = VerificationResult(
            passed=True,
            check_type="test_check",
            details="Test details",
            metadata={"key": "value"}
        )
        assert result.passed is True
        assert result.check_type == "test_check"
        assert result.details == "Test details"
        assert result.metadata == {"key": "value"}
        assert result.timestamp is not None

    def test_verification_result_bool(self):
        passed_result = VerificationResult(True, "test", "passed")
        failed_result = VerificationResult(False, "test", "failed")
        assert bool(passed_result) is True
        assert bool(failed_result) is False

    def test_verification_result_str(self):
        result = VerificationResult(True, "file_check", "File exists")
        assert "PASS" in str(result)
        assert "file_check" in str(result)

        failed = VerificationResult(False, "file_check", "File missing")
        assert "FAIL" in str(failed)

    def test_verification_result_to_dict(self):
        result = VerificationResult(
            passed=True,
            check_type="test",
            details="test",
            metadata={"foo": "bar"}
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert d["check_type"] == "test"
        assert d["details"] == "test"
        assert d["metadata"] == {"foo": "bar"}
        assert "timestamp" in d


class TestVerifyFileCreated:
    """Test verify_file_created function."""

    def test_file_exists_success(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            result = verify_file_created(temp_path)
            assert result.passed is True
            assert result.check_type == "file_verification"
            assert "size_bytes" in result.metadata
        finally:
            os.unlink(temp_path)

    def test_file_not_exists_raises(self):
        with pytest.raises(VerificationError) as exc_info:
            verify_file_created("/nonexistent/file.txt", raise_on_fail=True)
        assert "does not exist" in str(exc_info.value)

    def test_file_not_exists_no_raise(self):
        result = verify_file_created("/nonexistent/file.txt", raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "file_exists"

    def test_directory_not_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_file_created(tmpdir, raise_on_fail=False)
            assert result.passed is False
            assert result.check_type == "file_type"

    def test_min_size_check(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("small")
            temp_path = f.name

        try:
            # Should fail - file too small
            result = verify_file_created(temp_path, min_size=1000, raise_on_fail=False)
            assert result.passed is False
            assert result.check_type == "file_size"

            # Should pass - file meets min size
            result = verify_file_created(temp_path, min_size=3, raise_on_fail=False)
            assert result.passed is True
        finally:
            os.unlink(temp_path)

    def test_required_content_check(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Hello World")
            temp_path = f.name

        try:
            # Should pass - content found
            result = verify_file_created(temp_path, required_content="Hello", raise_on_fail=False)
            assert result.passed is True

            # Should fail - content not found
            result = verify_file_created(temp_path, required_content="Missing", raise_on_fail=False)
            assert result.passed is False
            assert result.check_type == "file_content"
        finally:
            os.unlink(temp_path)

    def test_max_age_check(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test")
            temp_path = f.name

        try:
            # Should pass - file is very recent
            result = verify_file_created(temp_path, max_age_seconds=60, raise_on_fail=False)
            assert result.passed is True

            # Should fail - file age exceeds limit (set to 0 seconds)
            time.sleep(0.1)
            result = verify_file_created(temp_path, max_age_seconds=0, raise_on_fail=False)
            assert result.passed is False
            assert result.check_type == "file_age"
        finally:
            os.unlink(temp_path)


class TestVerifyJsonFile:
    """Test verify_json_file function."""

    def test_valid_json_dict(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump({"key": "value", "number": 42}, f)
            temp_path = f.name

        try:
            result = verify_json_file(temp_path)
            assert result.passed is True
            assert result.check_type == "json_verification"
        finally:
            os.unlink(temp_path)

    def test_required_keys(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump({"id": 123, "name": "test", "status": "active"}, f)
            temp_path = f.name

        try:
            # Should pass - all keys present
            result = verify_json_file(temp_path, required_keys=["id", "name"])
            assert result.passed is True
            assert "found_keys" in result.metadata

            # Should fail - missing key
            result = verify_json_file(temp_path, required_keys=["id", "missing_key"], raise_on_fail=False)
            assert result.passed is False
            assert result.check_type == "json_keys"
        finally:
            os.unlink(temp_path)

    def test_json_array_min_items(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump([1, 2, 3, 4, 5], f)
            temp_path = f.name

        try:
            # Should pass - enough items
            result = verify_json_file(temp_path, min_items=3)
            assert result.passed is True
            assert result.metadata["item_count"] == 5

            # Should fail - not enough items
            result = verify_json_file(temp_path, min_items=10, raise_on_fail=False)
            assert result.passed is False
            assert result.check_type == "json_items"
        finally:
            os.unlink(temp_path)

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            f.write("not valid json {{{")
            temp_path = f.name

        try:
            result = verify_json_file(temp_path, raise_on_fail=False)
            assert result.passed is False
            assert result.check_type == "json_parse"
        finally:
            os.unlink(temp_path)

    def test_file_not_exists(self):
        result = verify_json_file("/nonexistent.json", raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "file_exists"


class TestVerifyApiResponse:
    """Test verify_api_response function."""

    def test_valid_response(self):
        response = {"status": 200, "data": "test"}
        result = verify_api_response(response)
        assert result.passed is True
        assert result.check_type == "api_verification"

    def test_not_dict_fails(self):
        result = verify_api_response("not a dict", raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "response_type"

    def test_required_fields(self):
        response = {"id": 123, "name": "test", "status": "active"}

        # Should pass - all fields present
        result = verify_api_response(response, required_fields=["id", "name"])
        assert result.passed is True

        # Should fail - missing field
        result = verify_api_response(response, required_fields=["id", "missing"], raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "api_fields"

    def test_success_field_present_and_true(self):
        response = {"success": True, "data": "test"}
        result = verify_api_response(response, success_field="success")
        assert result.passed is True

    def test_success_field_missing(self):
        response = {"data": "test"}
        result = verify_api_response(response, success_field="success", raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "api_success_field"

    def test_success_field_false(self):
        response = {"success": False, "error": "Something failed"}
        result = verify_api_response(response, success_field="success", raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "api_success_value"


class TestVerifyTrelloCardCreated:
    """Test verify_trello_card_created function."""

    def test_valid_trello_response(self):
        response = {
            "success": True,
            "return_value": {
                "id": "card123",
                "name": "Test Card",
                "idList": "list456"
            }
        }
        result = verify_trello_card_created(response)
        assert result.passed is True
        assert result.metadata["card_id"] == "card123"
        assert result.metadata["card_name"] == "Test Card"

    def test_success_false(self):
        response = {"success": False}
        result = verify_trello_card_created(response, raise_on_fail=False)
        assert result.passed is False

    def test_missing_card_id(self):
        response = {
            "success": True,
            "return_value": {"name": "Card without ID"}
        }
        result = verify_trello_card_created(response, raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "trello_card_id"

    def test_expected_list_id_match(self):
        response = {
            "success": True,
            "return_value": {
                "id": "card123",
                "idList": "list456"
            }
        }
        result = verify_trello_card_created(response, expected_list_id="list456")
        assert result.passed is True

    def test_expected_list_id_mismatch(self):
        response = {
            "success": True,
            "return_value": {
                "id": "card123",
                "idList": "list456"
            }
        }
        result = verify_trello_card_created(response, expected_list_id="list999", raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "trello_list_id"


class TestVerifyGithubCommit:
    """Test verify_github_commit function."""

    def test_valid_commit_response(self):
        response = {
            "success": True,
            "return_value": {
                "commit": {
                    "sha": "abc123def456",
                    "message": "Add new feature"
                },
                "content": {
                    "path": "src/file.py"
                }
            }
        }
        result = verify_github_commit(response)
        assert result.passed is True
        assert result.metadata["commit_sha"] == "abc123def456"
        assert result.metadata["commit_message"] == "Add new feature"

    def test_success_false(self):
        response = {"success": False}
        result = verify_github_commit(response, raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "github_success"

    def test_missing_commit_sha(self):
        response = {
            "success": True,
            "return_value": {
                "commit": {"message": "No SHA"}
            }
        }
        result = verify_github_commit(response, raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "github_commit_sha"

    def test_missing_commit_object(self):
        response = {
            "success": True,
            "return_value": {}
        }
        result = verify_github_commit(response, raise_on_fail=False)
        assert result.passed is False
        assert result.check_type == "github_commit_sha"


class TestCreateVerificationReport:
    """Test create_verification_report function."""

    def test_report_creation(self):
        results = [
            VerificationResult(True, "check1", "Passed"),
            VerificationResult(True, "check2", "Passed"),
            VerificationResult(False, "check3", "Failed")
        ]

        report = create_verification_report(results, "Test Task")

        assert report["task_name"] == "Test Task"
        assert report["total_checks"] == 3
        assert report["passed"] == 2
        assert report["failed"] == 1
        assert report["success_rate"] == 2/3
        assert len(report["checks"]) == 3
        assert "timestamp" in report

    def test_report_all_passed(self):
        results = [
            VerificationResult(True, "check1", "Passed"),
            VerificationResult(True, "check2", "Passed")
        ]

        report = create_verification_report(results, "Success Task")
        assert report["success_rate"] == 1.0
        assert report["failed"] == 0

    def test_report_empty_results(self):
        report = create_verification_report([], "Empty Task")
        assert report["total_checks"] == 0
        assert report["success_rate"] == 0

    def test_report_save_to_file(self):
        results = [VerificationResult(True, "test", "details")]

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name

        try:
            report = create_verification_report(results, "Save Test", save_to=temp_path)

            # Verify file was created
            assert os.path.exists(temp_path)

            # Verify content
            with open(temp_path, 'r') as f:
                saved_report = json.load(f)
            assert saved_report["task_name"] == "Save Test"
            assert saved_report["total_checks"] == 1
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
