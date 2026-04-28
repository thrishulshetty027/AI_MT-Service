# Phase 2: LLM Pipeline Infrastructure - Research

**Researched:** 2026-04-28
**Status:** Complete

## Standard Stack

### Core Dependencies (from Phase 1)

```toml
[tool.poetry.dependencies]
python = "^3.10"
pydantic = "^2.0"
tree-sitter = "^0.20"
tree-sitter-c = "^0.20"

[tool.poetry.dev-dependencies]
pytest = "^9.0"
pytest-cov = "^4.0"
```

### New for Phase 2

No new external dependencies. Phase 2 uses:
- **concurrent.futures.ThreadPoolExecutor** (stdlib) — parallel Stage 1 calls
- **dataclasses** (stdlib) — PipelineState
- **json** (stdlib) — JSON parsing for LLM responses
- **logging** (stdlib) — pipeline execution logging

### Rationale

- **ThreadPoolExecutor**: Ideal for I/O-bound parallel LLM calls. Stage 1 calls 1A, 1B, 1C are independent and can run concurrently. Python 3.10+ futures API is mature.
- **dataclasses**: Lightweight state container. No need for Pydantic here — PipelineState is internal bookkeeping, not a validation boundary.
- **No new pip packages**: Phase 2 is orchestration code wrapping existing `glm_client.py`.

## Architecture Patterns

### Pattern 1: Single LLM Call with Retry

**Purpose:** Wrap `glm_client.call_glm_4_7_flash()` with retry logic for empty responses and JSON parse errors.

**Implementation Pattern:**

```python
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def _call_llm_focused(
    system_prompt: str,
    user_prompt: str,
    call_name: str,
    max_retries: int = 2,
    expect_json: bool = False,
) -> str:
    """
    Execute a single focused LLM call with retry logic.
    
    Args:
        system_prompt: System-level instruction for the LLM
        user_prompt: User content (code, context, prior outputs)
        call_name: Human-readable name for logging (e.g., "1A_Code_Analyst")
        max_retries: Maximum retry attempts (default 2)
        expect_json: If True, retry on JSON parse failure with corrective message
    
    Returns:
        LLM response as string (or parsed JSON dict if expect_json=True)
    
    Raises:
        RuntimeError: If all retries exhausted
    """
    from glm_client import call_glm_4_7_flash
    
    combined_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    for attempt in range(max_retries + 1):
        try:
            response = call_glm_4_7_flash(combined_prompt)
            
            # Check for empty response
            if not response or not response.strip():
                logger.warning(f"[{call_name}] Empty response (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    continue
                raise RuntimeError(f"[{call_name}] Empty response after {max_retries + 1} attempts")
            
            # Check for JSON parse if expected
            if expect_json:
                try:
                    parsed = json.loads(response)
                    return parsed  # Return parsed dict
                except json.JSONDecodeError:
                    logger.warning(f"[{call_name}] JSON parse error (attempt {attempt + 1})")
                    if attempt < max_retries:
                        # Retry with corrective message
                        combined_prompt += "\n\nIMPORTANT: Your previous output was not valid JSON. Output ONLY valid JSON."
                        continue
                    raise RuntimeError(f"[{call_name}] JSON parse failed after {max_retries + 1} attempts")
            
            return response
            
        except Exception as e:
            if "opencode" in str(e).lower():
                logger.error(f"[{call_name}] LLM call failed: {e}")
                if attempt < max_retries:
                    continue
                raise
            raise
    
    raise RuntimeError(f"[{call_name}] All retries exhausted")
```

**Key Points:**
- Retry on empty response immediately (no corrective message needed)
- Retry on JSON parse failure with "your output was not valid JSON" message
- `call_name` for logging and debugging
- `expect_json` flag controls whether to attempt JSON parsing
- Max 3 total attempts (1 initial + 2 retries)

### Pattern 2: PipelineState Dataclass

**Purpose:** Store all intermediate outputs from the 13 LLM calls in a single state object.

**Implementation Pattern:**

```python
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class PipelineState:
    """Container for all intermediate outputs from the 13-call LLM pipeline."""
    
    # Input
    diff_text: str = ""
    pr_number: str = ""
    module_name: str = ""
    
    # Context (from Phase 1)
    function_signatures: List[Dict] = field(default_factory=list)
    struct_definitions: Dict[str, Any] = field(default_factory=dict)
    typedef_map: Dict[str, str] = field(default_factory=dict)
    hal_functions: List[str] = field(default_factory=list)
    
    # Stage 1 outputs (parallel)
    code_analysis: str = ""          # Call 1A: function descriptions
    type_map: Dict = field(default_factory=dict)  # Call 1B: type map JSON
    complexity_tiers: Dict = field(default_factory=dict)  # Call 1C: tier classifications
    
    # Stage 2 outputs (sequential)
    scenarios_raw: str = ""          # Call 2A: scenario plan
    scenarios_critique: str = ""     # Call 2B: scenario critique
    scenarios_final: str = ""        # Call 2C: final scenarios
    
    # Stage 3 outputs (sequential)
    values_raw: str = ""             # Call 3A: concrete values
    values_critique: str = ""        # Call 3B: value critique
    values_final: str = ""           # Call 3C: final values
    
    # Stage 4 outputs (sequential)
    stubs_raw: str = ""              # Call 4A: stub config
    stubs_final: str = ""            # Call 4B: final stub config
    
    # Stage 5 outputs (sequential)
    assembled_json: str = ""         # Call 5A: assembled TestCaseFile JSON
    self_review_result: str = ""     # Call 5B: self-review output
    
    # Validation state
    validation_errors: List[str] = field(default_factory=list)
    
    # Metadata
    call_count: int = 0
    retry_count: int = 0
```

**Key Points:**
- All fields have defaults so state can be built incrementally
- `field(default_factory=...)` for mutable types (lists, dicts)
- Validation errors accumulated across stages
- Metadata for debugging (call_count, retry_count)

### Pattern 3: Parallel Stage 1 Execution

**Purpose:** Execute calls 1A, 1B, 1C in parallel since they have no dependencies on each other.

**Implementation Pattern:**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _run_stage_1_parallel(state: PipelineState) -> PipelineState:
    """Run Stage 1 calls (1A, 1B, 1C) in parallel."""
    
    calls = {
        "1A_Code_Analyst": lambda: _call_llm_focused(
            system_prompt=SYSTEM_PROMPT_1A,
            user_prompt=_build_1a_user_prompt(state),
            call_name="1A_Code_Analyst",
            expect_json=False,
        ),
        "1B_Type_Inspector": lambda: _call_llm_focused(
            system_prompt=SYSTEM_PROMPT_1B,
            user_prompt=_build_1b_user_prompt(state),
            call_name="1B_Type_Inspector",
            expect_json=True,
        ),
        "1C_Complexity_Judge": lambda: _call_llm_focused(
            system_prompt=SYSTEM_PROMPT_1C,
            user_prompt=_build_1c_user_prompt(state),
            call_name="1C_Complexity_Judge",
            expect_json=True,
        ),
    }
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fn): name
            for name, fn in calls.items()
        }
        
        results = {}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                state.call_count += 1
            except Exception as e:
                logger.error(f"[{name}] Parallel execution failed: {e}")
                raise RuntimeError(f"Stage 1 call {name} failed: {e}")
    
    # Assign results to state
    state.code_analysis = results.get("1A_Code_Analyst", "")
    state.type_map = results.get("1B_Type_Inspector", {})
    state.complexity_tiers = results.get("1C_Complexity_Judge", {})
    
    return state
```

**Key Points:**
- `ThreadPoolExecutor(max_workers=3)` for 3 parallel calls
- `as_completed()` for processing results as they arrive
- Each call has its own system prompt and user prompt builder
- Failures propagate immediately (don't continue with partial results)
- `max_workers=3` is optimal — one per call, no need for more

### Pattern 4: Stage-Level Validation Hooks

**Purpose:** Run deterministic validators between stages to catch errors early.

**Implementation Pattern:**

```python
def _validate_stage_output(
    state: PipelineState,
    stage: str,
    required_fields: List[str],
) -> List[str]:
    """
    Validate that a stage produced expected output.
    
    Returns list of error messages (empty if valid).
    """
    errors = []
    
    for field_name in required_fields:
        value = getattr(state, field_name, None)
        if value is None or value == "" or value == {} or value == []:
            errors.append(f"Stage {stage}: Missing required output '{field_name}'")
    
    return errors

def _run_stage_with_validation(
    state: PipelineState,
    stage_name: str,
    stage_fn,
    required_fields: List[str],
    validator_fn=None,
) -> PipelineState:
    """
    Execute a pipeline stage with pre/post validation.
    """
    # Pre-validation
    pre_errors = _validate_stage_output(state, stage_name, required_fields)
    if pre_errors:
        state.validation_errors.extend(pre_errors)
        raise RuntimeError(f"Stage {stage_name} pre-validation failed: {pre_errors}")
    
    # Execute stage
    state = stage_fn(state)
    
    # Post-validation (if custom validator provided)
    if validator_fn:
        post_errors = validator_fn(state)
        if post_errors:
            state.validation_errors.extend(post_errors)
            logger.warning(f"Stage {stage_name} post-validation warnings: {post_errors}")
    
    return state
```

**Key Points:**
- Pre-validation checks that inputs exist before running stage
- Post-validation runs deterministic checks on outputs
- Errors accumulated in `state.validation_errors` for reporting
- `validator_fn` is optional — not all stages need custom validation

## Integration with Existing Code

### glm_client.py Interface

```python
# From glm_client.py (DO NOT MODIFY)
def call_glm_4_7_flash(prompt: str) -> str:
    """Uses opencode CLI to call configured model."""
    # Returns raw text response
    # Raises: Exception on failure, subprocess.TimeoutExpired on timeout
```

**Integration contract:**
- Input: single string prompt (system + user combined)
- Output: raw text response (may contain JSON, markdown, or plain text)
- Timeout: 600 seconds (10 minutes)
- Error: raises Exception on failure

**Key constraint:** `call_glm_4_7_flash()` takes a single string, not separate system/user prompts. We concatenate them in `_call_llm_focused()`.

### Phase 1 Dependencies

| Module | What Phase 2 Uses |
|--------|-------------------|
| `schemas.py` | `TestCaseFile`, `TestCase`, `StubConfig`, `FunctionMeta`, `TestType` |
| `context_assembler.py` | `extract_context_from_diff()`, `ContextPackage` |
| `diff_validator.py` | `validate_diff()` |
| `type_resolver.py` | `classify_parameter()`, `CType` (for type map validation) |

## Common Pitfalls

### Pitfall 1: Combining System + User Prompt Incorrectly

**Problem:** `call_glm_4_7_flash()` takes a single string. System and user prompts must be combined clearly.

**Wrong:**
```python
prompt = system_prompt + user_prompt  # Unclear boundary
```

**Right:**
```python
prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
# Or with explicit section markers:
prompt = f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nUSER CONTENT:\n{user_prompt}"
```

### Pitfall 2: ThreadPoolExecutor Not Cleaning Up

**Problem:** Not using context manager for ThreadPoolExecutor.

**Wrong:**
```python
executor = ThreadPoolExecutor(max_workers=3)
# ... if exception happens, executor never shuts down
```

**Right:**
```python
with ThreadPoolExecutor(max_workers=3) as executor:
    # ... guaranteed cleanup
```

### Pitfall 3: Shared Mutable State in Parallel Calls

**Problem:** Modifying `state` from multiple threads simultaneously.

**Wrong:**
```python
# Multiple threads writing to same state object
state.code_analysis = result_a
state.type_map = result_b  # Race condition
```

**Right:**
```python
# Collect results dict first, then assign to state after all futures complete
results = {}
for future in as_completed(futures):
    results[name] = future.result()

# Single-threaded assignment
state.code_analysis = results["1A_Code_Analyst"]
state.type_map = results["1B_Type_Inspector"]
```

### Pitfall 4: JSON Extraction from LLM Response

**Problem:** LLM may wrap JSON in markdown code blocks.

**Wrong:**
```python
parsed = json.loads(response)  # Fails if ```json\n...\n``` wrapper present
```

**Right:**
```python
def _extract_json(response: str) -> dict:
    """Extract JSON from LLM response, handling markdown wrappers."""
    # Try direct parse first
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code block
    import re
    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))
    
    # Try finding first { to last }
    start = response.find('{')
    end = response.rfind('}')
    if start != -1 and end != -1:
        return json.loads(response[start:end+1])
    
    raise json.JSONDecodeError("No JSON found", response, 0)
```

### Pitfall 5: Blocking on Failed Parallel Calls

**Problem:** One slow/failed call blocks all parallel execution.

**Wrong:**
```python
for future in futures:
    result = future.result()  # Blocks until this future completes
```

**Right:**
```python
for future in as_completed(futures):
    try:
        result = future.result(timeout=660)  # Slightly longer than LLM timeout
    except Exception as e:
        # Cancel remaining futures
        for f in futures:
            f.cancel()
        raise
```

## Architectural Responsibility Map

| Component | Owner | Depends On |
|-----------|-------|------------|
| `multi_call_pipeline.py` | Phase 2 | `schemas.py`, `glm_client.py` |
| `_call_llm_focused()` | Phase 2 | `glm_client.py` |
| `PipelineState` | Phase 2 | None (dataclass) |
| `run_multi_call_pipeline()` | Phase 2 | `_call_llm_focused()`, `PipelineState`, concurrent.futures |
| Stage validation hooks | Phase 2 | `PipelineState` |

---

*Research complete: 2026-04-28*
