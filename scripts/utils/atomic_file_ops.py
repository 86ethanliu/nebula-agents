#!/usr/bin/env python3
"""
Atomic File Operations Module

Provides atomic write operations with integrity verification, automatic backups,
and rollback capabilities to prevent data corruption and partial writes across
all Nebula agent file operations.

Key Features:
- Atomic writes using temp file + rename pattern
- SHA-256 checksum verification for file integrity
- Automatic backup creation before overwrites
- Rollback support on failures
- Configurable backup retention

Usage:
    from scripts.utils.atomic_file_ops import atomic_write, safe_read
    
    # Write with automatic integrity verification
    success, checksum = atomic_write('data.json', json_content)
    
    # Read with integrity check
    content, verified = safe_read('data.json', expected_checksum)

Author: Nebula Developer Agent
Date: 2026-03-10
"""

import os
import shutil
import hashlib
import tempfile
import json
from pathlib import Path
from typing import Tuple, Optional, List
from datetime import datetime


class AtomicFileError(Exception):
    """Base exception for atomic file operations."""
    pass


class IntegrityError(AtomicFileError):
    """Raised when file integrity verification fails."""
    pass


class BackupError(AtomicFileError):
    """Raised when backup operations fail."""
    pass


def _calculate_checksum(file_path: str) -> str:
    """
    Calculate SHA-256 checksum of a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Hexadecimal checksum string
        
    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def atomic_write(file_path: str, content: str, mode: str = 'w', 
                 verify: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Atomically write content to a file using temp file + rename pattern.
    
    This prevents partial writes and corruption by:
    1. Writing to a temporary file in the same directory
    2. Verifying the write completed successfully
    3. Atomically renaming temp file to target (OS-level atomic operation)
    4. Calculating and returning checksum for verification
    
    Args:
        file_path: Target file path
        content: Content to write (string for text mode, bytes for binary)
        mode: Write mode ('w' for text, 'wb' for binary)
        verify: Whether to calculate checksum for verification
        
    Returns:
        Tuple of (success: bool, checksum: Optional[str])
        
    Raises:
        AtomicFileError: If write operation fails
        
    Example:
        >>> success, checksum = atomic_write('config.json', json.dumps(data))
        >>> if success:
        ...     print(f"File written with checksum: {checksum}")
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory for atomic rename
    fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f'.{file_path.name}.',
        suffix='.tmp'
    )
    
    try:
        # Write to temp file
        with os.fdopen(fd, mode) as temp_file:
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())  # Force write to disk
        
        # Verify temp file was written
        if not os.path.exists(temp_path):
            raise AtomicFileError(f"Temp file {temp_path} not created")
        
        # Calculate checksum before rename
        checksum = _calculate_checksum(temp_path) if verify else None
        
        # Atomic rename (OS-level atomic operation)
        shutil.move(temp_path, str(file_path))
        
        return True, checksum
        
    except Exception as e:
        # Clean up temp file on failure
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise AtomicFileError(f"Atomic write failed for {file_path}: {e}")


def atomic_update(file_path: str, content: str, mode: str = 'w',
                  create_backup: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Atomically update an existing file with automatic backup.
    
    Creates a backup before updating, then performs atomic write.
    If write fails, backup can be used for rollback.
    
    Args:
        file_path: Target file path
        content: New content
        mode: Write mode ('w' for text, 'wb' for binary)
        create_backup: Whether to create backup before update
        
    Returns:
        Tuple of (success: bool, new_checksum: Optional[str], backup_path: Optional[str])
        
    Raises:
        AtomicFileError: If update operation fails
        
    Example:
        >>> success, checksum, backup = atomic_update('data.json', new_data)
        >>> if not success:
        ...     rollback(backup, 'data.json')
    """
    file_path = Path(file_path)
    backup_path = None
    
    try:
        # Create backup if file exists and backup requested
        if file_path.exists() and create_backup:
            backup_path = create_backup(str(file_path))
        
        # Perform atomic write
        success, checksum = atomic_write(str(file_path), content, mode)
        
        return success, checksum, backup_path
        
    except Exception as e:
        # If atomic write failed and we have backup, rollback
        if backup_path and os.path.exists(backup_path):
            rollback(backup_path, str(file_path))
        raise AtomicFileError(f"Atomic update failed for {file_path}: {e}")


def safe_read(file_path: str, expected_checksum: Optional[str] = None,
              mode: str = 'r') -> Tuple[str, bool]:
    """
    Read file with optional integrity verification.
    
    Args:
        file_path: Path to file to read
        expected_checksum: Optional checksum to verify against
        mode: Read mode ('r' for text, 'rb' for binary)
        
    Returns:
        Tuple of (content: str, verified: bool)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        IntegrityError: If checksum verification fails
        
    Example:
        >>> content, verified = safe_read('config.json', stored_checksum)
        >>> if verified:
        ...     config = json.loads(content)
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Read content
    with open(file_path, mode) as f:
        content = f.read()
    
    # Verify checksum if provided
    verified = False
    if expected_checksum:
        actual_checksum = _calculate_checksum(str(file_path))
        if actual_checksum != expected_checksum:
            raise IntegrityError(
                f"Checksum mismatch for {file_path}:\n"
                f"  Expected: {expected_checksum}\n"
                f"  Actual:   {actual_checksum}"
            )
        verified = True
    
    return content, verified


def create_backup(file_path: str, backup_dir: Optional[str] = None,
                  max_backups: int = 5) -> str:
    """
    Create a timestamped backup of a file.
    
    Args:
        file_path: Path to file to backup
        backup_dir: Optional backup directory (defaults to file's directory)
        max_backups: Maximum number of backups to retain
        
    Returns:
        Path to created backup file
        
    Raises:
        FileNotFoundError: If source file doesn't exist
        BackupError: If backup creation fails
        
    Example:
        >>> backup_path = create_backup('important.json')
        >>> print(f"Backup created at: {backup_path}")
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")
    
    # Determine backup directory
    if backup_dir:
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
    else:
        backup_dir = file_path.parent
    
    # Create timestamped backup filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"{file_path.stem}.backup_{timestamp}{file_path.suffix}"
    backup_path = backup_dir / backup_name
    
    try:
        # Copy file to backup location
        shutil.copy2(str(file_path), str(backup_path))
        
        # Clean up old backups
        cleanup_backups(str(file_path), backup_dir=str(backup_dir), 
                       max_backups=max_backups)
        
        return str(backup_path)
        
    except Exception as e:
        raise BackupError(f"Failed to create backup of {file_path}: {e}")


def verify_integrity(file_path: str, expected_checksum: str) -> bool:
    """
    Verify file integrity using checksum comparison.
    
    Args:
        file_path: Path to file to verify
        expected_checksum: Expected SHA-256 checksum
        
    Returns:
        True if checksums match, False otherwise
        
    Example:
        >>> if verify_integrity('data.json', stored_checksum):
        ...     print("File integrity verified")
    """
    try:
        actual_checksum = _calculate_checksum(file_path)
        return actual_checksum == expected_checksum
    except Exception:
        return False


def rollback(backup_path: str, target_path: str) -> bool:
    """
    Rollback a file from backup using atomic operation.
    
    Args:
        backup_path: Path to backup file
        target_path: Target file path to restore to
        
    Returns:
        True if rollback successful, False otherwise
        
    Example:
        >>> if rollback(backup_path, 'config.json'):
        ...     print("File restored from backup")
    """
    try:
        backup_path = Path(backup_path)
        target_path = Path(target_path)
        
        if not backup_path.exists():
            raise BackupError(f"Backup file not found: {backup_path}")
        
        # Use atomic write for rollback
        with open(backup_path, 'r') as f:
            content = f.read()
        
        success, _ = atomic_write(str(target_path), content)
        return success
        
    except Exception as e:
        print(f"Rollback failed: {e}")
        return False


def cleanup_backups(file_path: str, backup_dir: Optional[str] = None,
                   max_backups: int = 5) -> List[str]:
    """
    Clean up old backup files, keeping only the most recent N backups.
    
    Args:
        file_path: Original file path (to identify related backups)
        backup_dir: Directory containing backups (defaults to file's directory)
        max_backups: Maximum number of backups to retain
        
    Returns:
        List of deleted backup file paths
        
    Example:
        >>> deleted = cleanup_backups('data.json', max_backups=3)
        >>> print(f"Deleted {len(deleted)} old backups")
    """
    file_path = Path(file_path)
    backup_dir = Path(backup_dir) if backup_dir else file_path.parent
    
    # Find all backup files for this file
    pattern = f"{file_path.stem}.backup_*{file_path.suffix}"
    backups = sorted(
        backup_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True  # Newest first
    )
    
    # Delete old backups beyond max_backups
    deleted = []
    for backup in backups[max_backups:]:
        try:
            backup.unlink()
            deleted.append(str(backup))
        except Exception as e:
            print(f"Failed to delete backup {backup}: {e}")
    
    return deleted


if __name__ == '__main__':
    # Basic usage examples
    print("Atomic File Operations Module")
    print("==============================\n")
    
    # Example 1: Atomic write
    test_file = '/tmp/test_atomic.txt'
    success, checksum = atomic_write(test_file, "Hello, atomic world!")
    print(f"Write successful: {success}")
    print(f"Checksum: {checksum}\n")
    
    # Example 2: Safe read with verification
    content, verified = safe_read(test_file, checksum)
    print(f"Read content: {content}")
    print(f"Integrity verified: {verified}\n")
    
    # Example 3: Backup and update
    backup = create_backup(test_file)
    print(f"Backup created: {backup}")
    
    success, new_checksum, _ = atomic_update(test_file, "Updated content!")
    print(f"Update successful: {success}")
    print(f"New checksum: {new_checksum}\n")
    
    # Clean up
    os.unlink(test_file)
    if os.path.exists(backup):
        os.unlink(backup)
