# Nebula Agents - Atomic File Operations

Utility modules for the Nebula agent system providing robust file operations with integrity verification.

## Overview

This repository contains atomic file operation utilities designed to prevent data corruption and partial writes across all Nebula agent file operations.

## Features

### Atomic File Operations (`scripts/utils/atomic_file_ops.py`)

Core module providing:

- **atomic_write()** - Write-to-temp + atomic rename pattern
- **atomic_update()** - Update with automatic backup creation
- **safe_read()** - Read with optional SHA-256 checksum verification
- **create_backup()** - Timestamped backup creation with retention management
- **verify_integrity()** - SHA-256 checksum validation
- **rollback()** - Restore from backup atomically
- **cleanup_backups()** - Automatic backup retention management

### Key Benefits

- Prevents partial writes and data corruption
- SHA-256 integrity verification for all operations
- Automatic backup management with configurable retention
- Comprehensive error handling with custom exceptions
- Full type hints and documentation

## Installation

```bash
git clone https://github.com/86ethanliu/nebula-agents.git
cd nebula-agents
```

## Usage

### Basic Atomic Write

```python
from scripts.utils.atomic_file_ops import atomic_write

# Write with automatic checksum calculation
success, checksum = atomic_write('config.json', json_content)
if success:
    print(f"File written with checksum: {checksum}")
```

### Safe Read with Verification

```python
from scripts.utils.atomic_file_ops import safe_read

# Read and verify integrity
content, verified = safe_read('config.json', expected_checksum)
if verified:
    config = json.loads(content)
```

### Update with Automatic Backup

```python
from scripts.utils.atomic_file_ops import atomic_update, rollback

# Update with automatic backup
success, checksum, backup_path = atomic_update('data.json', new_content)

# Rollback if needed
if not success:
    rollback(backup_path, 'data.json')
```

### Manual Backup Management

```python
from scripts.utils.atomic_file_ops import create_backup, cleanup_backups

# Create timestamped backup
backup_path = create_backup('important.json', max_backups=5)

# Clean up old backups (keeps 3 most recent)
deleted = cleanup_backups('important.json', max_backups=3)
```

## Architecture

### Atomic Write Pattern

1. Write content to temporary file in same directory
2. Flush and fsync to ensure data is on disk
3. Calculate SHA-256 checksum for verification
4. Atomically rename temp file to target (OS-level atomic operation)
5. Return success status and checksum

### Error Handling

Custom exceptions for different failure modes:
- `AtomicFileError` - Base exception for atomic operations
- `IntegrityError` - Checksum verification failures
- `BackupError` - Backup operation failures

## Testing

The module includes 20 comprehensive tests covering:
- Basic atomic write operations
- Checksum verification
- Backup creation and rollback
- Error handling and edge cases
- Concurrent access scenarios

Test suite SHA: `91495aa1`

## Related Components

- `file_integrity_checker.py` (SHA: `bffb59f3`) - Integrity monitoring
- Integration with Nebula agent file operations

## Implementation Status

**Commit:** `a1b2097dca947f30d5ac1e9adca7c9387d46daea`  
**Module SHA:** `359d702d0253a19800b5053605698007d8060611`  
**Date:** 2026-03-10  
**Status:** Complete - Ready for integration

## Contributing

This is a utility module for the Nebula agent system. For issues or improvements, please contact the Nebula development team.

## License

Internal utility module for Nebula agent system.
