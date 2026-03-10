"""Workflow Verification Checkpoints

Lightweight verification layer for agent task workflows. Before marking tasks complete,
agents must verify concrete outputs exist and are valid.

Inspired by the principle of rigorous execution - preventing false completion signals
through post-action verification hooks.

Usage:
    from verification_checkpoints import verify_file_created, verify_api_response
    
    # After file operation
    verify_file_created('/path/to/file.json', min_size=100)
    
    # After API call
    verify_api_response(response, expected_status=200, required_fields=['id', 'status'])
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class VerificationError(Exception):
    """Raised when a verification checkpoint fails."""
    pass


class VerificationResult:
    """Result of a verification check."""
    
    def __init__(self, passed: bool, check_type: str, details: str, metadata: Optional[Dict] = None):
        self.passed = passed
        self.check_type = check_type
        self.details = details
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow().isoformat()
    
    def __bool__(self):
        return self.passed
    
    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.check_type}: {self.details}"
    
    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "check_type": self.check_type,
            "details": self.details,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


def verify_file_created(
    file_path: Union[str, Path],
    min_size: Optional[int] = None,
    max_age_seconds: Optional[int] = None,
    required_content: Optional[str] = None,
    raise_on_fail: bool = True
) -> VerificationResult:
    """Verify a file was created and meets specified criteria.
    
    Args:
        file_path: Path to the file to verify
        min_size: Minimum file size in bytes (optional)
        max_age_seconds: Maximum age since creation in seconds (optional)
        required_content: String that must appear in file content (optional)
        raise_on_fail: If True, raise VerificationError on failure
    
    Returns:
        VerificationResult object
    
    Raises:
        VerificationError: If verification fails and raise_on_fail is True
    """
    path = Path(file_path)
    
    # Check existence
    if not path.exists():
        result = VerificationResult(
            passed=False,
            check_type="file_exists",
            details=f"File does not exist: {file_path}"
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    # Check it's a file, not directory
    if not path.is_file():
        result = VerificationResult(
            passed=False,
            check_type="file_type",
            details=f"Path exists but is not a file: {file_path}"
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    # Get file stats
    stats = path.stat()
    metadata = {
        "size_bytes": stats.st_size,
        "created_timestamp": stats.st_ctime,
        "modified_timestamp": stats.st_mtime
    }
    
    # Check minimum size
    if min_size is not None and stats.st_size < min_size:
        result = VerificationResult(
            passed=False,
            check_type="file_size",
            details=f"File size {stats.st_size} bytes is less than minimum {min_size} bytes",
            metadata=metadata
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    # Check age
    if max_age_seconds is not None:
        age_seconds = datetime.now().timestamp() - stats.st_mtime
        if age_seconds > max_age_seconds:
            result = VerificationResult(
                passed=False,
                check_type="file_age",
                details=f"File age {age_seconds:.0f}s exceeds maximum {max_age_seconds}s",
                metadata=metadata
            )
            if raise_on_fail:
                raise VerificationError(str(result))
            return result
    
    # Check required content
    if required_content is not None:
        try:
            content = path.read_text()
            if required_content not in content:
                result = VerificationResult(
                    passed=False,
                    check_type="file_content",
                    details=f"Required content not found in file",
                    metadata=metadata
                )
                if raise_on_fail:
                    raise VerificationError(str(result))
                return result
        except Exception as e:
            result = VerificationResult(
                passed=False,
                check_type="file_read",
                details=f"Failed to read file content: {e}",
                metadata=metadata
            )
            if raise_on_fail:
                raise VerificationError(str(result))
            return result
    
    return VerificationResult(
        passed=True,
        check_type="file_verification",
        details=f"File verified: {file_path}",
        metadata=metadata
    )


def verify_json_file(
    file_path: Union[str, Path],
    required_keys: Optional[List[str]] = None,
    min_items: Optional[int] = None,
    raise_on_fail: bool = True
) -> VerificationResult:
    """Verify a JSON file exists and contains expected structure.
    
    Args:
        file_path: Path to the JSON file
        required_keys: List of keys that must exist in the JSON (for objects)
        min_items: Minimum number of items (for arrays)
        raise_on_fail: If True, raise VerificationError on failure
    
    Returns:
        VerificationResult object
    """
    # First verify file exists
    file_result = verify_file_created(file_path, raise_on_fail=False)
    if not file_result:
        if raise_on_fail:
            raise VerificationError(str(file_result))
        return file_result
    
    # Try to parse JSON
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result = VerificationResult(
            passed=False,
            check_type="json_parse",
            details=f"Invalid JSON in file: {e}"
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    metadata = {"data_type": type(data).__name__}
    
    # Check required keys (for dict)
    if required_keys and isinstance(data, dict):
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            result = VerificationResult(
                passed=False,
                check_type="json_keys",
                details=f"Missing required keys: {missing_keys}",
                metadata=metadata
            )
            if raise_on_fail:
                raise VerificationError(str(result))
            return result
        metadata["found_keys"] = list(data.keys())
    
    # Check minimum items (for list)
    if min_items is not None and isinstance(data, list):
        if len(data) < min_items:
            result = VerificationResult(
                passed=False,
                check_type="json_items",
                details=f"Array has {len(data)} items, minimum required is {min_items}",
                metadata=metadata
            )
            if raise_on_fail:
                raise VerificationError(str(result))
            return result
        metadata["item_count"] = len(data)
    
    return VerificationResult(
        passed=True,
        check_type="json_verification",
        details=f"JSON file verified: {file_path}",
        metadata=metadata
    )


def verify_api_response(
    response: Dict[str, Any],
    expected_status: Optional[int] = None,
    required_fields: Optional[List[str]] = None,
    success_field: Optional[str] = None,
    raise_on_fail: bool = True
) -> VerificationResult:
    """Verify an API response contains expected data.
    
    Args:
        response: API response dictionary
        expected_status: Expected status code (optional)
        required_fields: List of fields that must exist in response (optional)
        success_field: Field that must be True for success (optional)
        raise_on_fail: If True, raise VerificationError on failure
    
    Returns:
        VerificationResult object
    """
    if not isinstance(response, dict):
        result = VerificationResult(
            passed=False,
            check_type="response_type",
            details=f"Response is not a dictionary: {type(response).__name__}"
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    metadata = {"response_keys": list(response.keys())}
    
    # Check required fields
    if required_fields:
        missing_fields = [field for field in required_fields if field not in response]
        if missing_fields:
            result = VerificationResult(
                passed=False,
                check_type="api_fields",
                details=f"Missing required fields: {missing_fields}",
                metadata=metadata
            )
            if raise_on_fail:
                raise VerificationError(str(result))
            return result
    
    # Check success field
    if success_field:
        if success_field not in response:
            result = VerificationResult(
                passed=False,
                check_type="api_success_field",
                details=f"Success field not found in response",
                metadata=metadata
            )
            if raise_on_fail:
                raise VerificationError(str(result))
            return result
        
        if not response[success_field]:
            result = VerificationResult(
                passed=False,
                check_type="api_success_value",
                details=f"Success field is False",
                metadata=metadata
            )
            if raise_on_fail:
                raise VerificationError(str(result))
            return result
    
    return VerificationResult(
        passed=True,
        check_type="api_verification",
        details="API response verified successfully",
        metadata=metadata
    )


def verify_trello_card_created(
    response: Dict[str, Any],
    expected_list_id: Optional[str] = None,
    raise_on_fail: bool = True
) -> VerificationResult:
    """Verify a Trello card was created successfully.
    
    Args:
        response: Trello API response from create-card action
        expected_list_id: Expected list ID the card should be in (optional)
        raise_on_fail: If True, raise VerificationError on failure
    
    Returns:
        VerificationResult object
    """
    basic_check = verify_api_response(
        response,
        required_fields=['success', 'return_value'],
        success_field='success',
        raise_on_fail=False
    )
    
    if not basic_check:
        if raise_on_fail:
            raise VerificationError(str(basic_check))
        return basic_check
    
    return_value = response.get('return_value', {})
    if not isinstance(return_value, dict) or 'id' not in return_value:
        result = VerificationResult(
            passed=False,
            check_type="trello_card_id",
            details="Card ID not found in response"
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    metadata = {
        "card_id": return_value.get('id'),
        "card_name": return_value.get('name'),
        "list_id": return_value.get('idList')
    }
    
    if expected_list_id and return_value.get('idList') != expected_list_id:
        result = VerificationResult(
            passed=False,
            check_type="trello_list_id",
            details=f"Card in wrong list",
            metadata=metadata
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    return VerificationResult(
        passed=True,
        check_type="trello_card_verification",
        details=f"Trello card created successfully",
        metadata=metadata
    )


def verify_github_commit(
    response: Dict[str, Any],
    raise_on_fail: bool = True
) -> VerificationResult:
    """Verify a GitHub commit was created successfully.
    
    Args:
        response: GitHub API response from create/update file action
        raise_on_fail: If True, raise VerificationError on failure
    
    Returns:
        VerificationResult object
    """
    if not response.get('success'):
        result = VerificationResult(
            passed=False,
            check_type="github_success",
            details="GitHub API call returned success=False"
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    return_value = response.get('return_value', {})
    commit = return_value.get('commit', {})
    
    if not commit or 'sha' not in commit:
        result = VerificationResult(
            passed=False,
            check_type="github_commit_sha",
            details="Commit SHA not found in response"
        )
        if raise_on_fail:
            raise VerificationError(str(result))
        return result
    
    metadata = {
        "commit_sha": commit.get('sha'),
        "commit_message": commit.get('message'),
        "file_path": return_value.get('content', {}).get('path')
    }
    
    return VerificationResult(
        passed=True,
        check_type="github_commit_verification",
        details=f"GitHub commit verified: {commit.get('sha')[:8]}",
        metadata=metadata
    )


def create_verification_report(
    results: List[VerificationResult],
    task_name: str,
    save_to: Optional[Union[str, Path]] = None
) -> Dict:
    """Create a verification report from multiple check results.
    
    Args:
        results: List of VerificationResult objects
        task_name: Name of the task being verified
        save_to: Optional path to save report as JSON
    
    Returns:
        Report dictionary
    """
    report = {
        "task_name": task_name,
        "timestamp": datetime.utcnow().isoformat(),
        "total_checks": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "success_rate": sum(1 for r in results if r.passed) / len(results) if results else 0,
        "checks": [r.to_dict() for r in results]
    }
    
    if save_to:
        with open(save_to, 'w') as f:
            json.dump(report, f, indent=2)
    
    return report
