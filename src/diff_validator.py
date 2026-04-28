"""
Diff validation and chunking logic.

Implements validation for C code diffs and splitting large diffs by function boundaries.
"""

import re
from typing import List, Tuple


def validate_diff(diff_content: str) -> Tuple[bool, str | None]:
    """
    Validate that diff content is a valid C code diff.

    Args:
        diff_content: Raw diff content as string

    Returns:
        Tuple of (is_valid, error_message). Error message is None if valid.
    """
    # Check for empty or whitespace-only diffs
    if not diff_content or not diff_content.strip():
        return False, "Diff is empty or contains only whitespace"

    # Check for unified diff format markers (@@ -)
    if "@@ -" not in diff_content and "@@ +" not in diff_content:
        return False, "Diff does not contain unified diff format markers (@@ - or @@ +)"

    # Extract C code from diff (lines starting with +, excluding diff markers)
    c_code_lines = []
    for line in diff_content.split('\n'):
        line = line.strip()
        # Skip diff markers
        if line.startswith('diff --git') or line.startswith('---') or line.startswith('+++'):
            continue
        # Skip hunk headers
        if line.startswith('@@'):
            continue
        # Skip removals (lines starting with -)
        if line.startswith('-'):
            continue
        # Keep added lines (strip the + prefix)
        if line.startswith('+'):
            c_code_lines.append(line[1:])
        # Keep context lines (lines without +/-)
        elif line and not line.startswith('+') and not line.startswith('-'):
            c_code_lines.append(line)

    c_code = '\n'.join(c_code_lines)

    # Check for C code patterns
    c_patterns = [
        r'\b(int|void|float|double|char|uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t)\s+\w+\s*\(',
        r'#include\s*[<"][^>"]+[>"]',
        r'typedef\s+struct\s+\w+\s*\{',
        r'struct\s+\w+\s*\{'
    ]

    has_c_pattern = any(re.search(pattern, c_code) for pattern in c_patterns)

    if not has_c_pattern:
        return False, "Diff does not contain valid C code patterns (function definitions, includes, structs, or typedefs)"

    return True, None


def split_diff_by_function(diff_content: str) -> List[str]:
    """
    Split large diffs by function boundaries.

    Diffs with more than 300 lines (including diff markers) are split into chunks
    where each chunk contains complete functions (no partial functions).

    Args:
        diff_content: Raw diff content as string

    Returns:
        List of diff chunks. Returns list with original content if < 300 lines.
    """
    lines = diff_content.split('\n')

    # Count total lines
    if len(lines) < 300:
        return [diff_content]

    # Extract diff header and hunk headers
    diff_header = []
    hunk_header = None
    code_lines = []

    for line in lines:
        stripped = line.strip()
        # Capture diff header
        if stripped.startswith('diff --git') or stripped.startswith('---') or stripped.startswith('+++'):
            diff_header.append(line)
            continue
        # Capture hunk header
        if stripped.startswith('@@'):
            hunk_header = line
            continue
        # Skip removals
        if stripped.startswith('-') and not stripped.startswith('--'):
            continue
        # Keep added and context lines
        code_lines.append(line)

    # If no code lines, return original
    if not code_lines:
        return [diff_content]

    # Find function boundaries in code lines
    # Pattern matches: type name(params) { or type* name(params) {
    # Matches even if there's a + prefix
    # Excludes control flow keywords (if, for, while, switch)
    function_pattern = re.compile(
        r'^\s*\+?\s*(?:\w+\s+)*\*?\s*(?!if|for|while|switch)(\w+)\s*\([^)]*\)\s*\{',
        re.MULTILINE
    )

    # Build full code string for regex matching
    full_code = '\n'.join(code_lines)

    # Find function start positions (line indices)
    function_boundaries = []
    for match in function_pattern.finditer(full_code):
        # Find which line this match is on
        match_pos = match.start()
        char_count = 0
        line_idx = 0
        for i, line in enumerate(code_lines):
            char_count += len(line) + 1  # +1 for newline
            if char_count > match_pos:
                line_idx = i
                break
        function_boundaries.append((line_idx, match.group(1)))

    if not function_boundaries:
        # No functions found, return original
        return [diff_content]

    # Split code into chunks based on function boundaries
    # Try to create chunks of ~80-100 lines each, splitting at function boundaries
    chunks = []
    target_chunk_size = 80
    current_start = 0
    last_boundary_index = 0

    for i in range(1, len(function_boundaries)):
        boundary_line, func_name = function_boundaries[i]

        # Calculate distance from current start to this boundary
        if boundary_line - current_start >= target_chunk_size:
            # Split at the previous boundary
            prev_boundary_line, _ = function_boundaries[last_boundary_index]

            chunk_code = code_lines[current_start:boundary_line]
            chunk = '\n'.join(diff_header + [hunk_header, ''] + chunk_code) if hunk_header else '\n'.join(chunk_code)
            chunks.append(chunk)

            current_start = boundary_line
            last_boundary_index = i

    # Add remaining code as final chunk
    if current_start < len(code_lines):
        chunk_code = code_lines[current_start:]
        chunk = '\n'.join(diff_header + [hunk_header, ''] + chunk_code) if hunk_header else '\n'.join(chunk_code)
        chunks.append(chunk)

    # If splitting failed (only 1 chunk), return original
    if len(chunks) <= 1:
        return [diff_content]

    return chunks
