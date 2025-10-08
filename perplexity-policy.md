As a default, the assistant should conduct code fixes by browsing and editing files directly in VS Code. The perplexity_file_editor.py script should only be used as a fallback when direct VS Code editing is unavailable or problematic.

# Perplexity File Editor Policy

Instructions for conducting code fixes using the reusable perplexity_file_editor.py script.

## 1. Allowed Editing Commands and Workflow

### Available Commands
- **read**: Read file contents
- **write**: Write/overwrite entire file
- **insert**: Insert content at specific line
- **replace**: Replace specific line range
- **delete**: Delete specific line range
- **search**: Search for patterns in file

### Workflow Steps
1. Read target file to understand current state
2. Identify exact lines/sections requiring changes
3. Apply appropriate command (insert/replace/delete)
4. Verify changes by reading updated file
5. Run tests to validate functionality
6. Commit changes if all tests pass

### Command Syntax
```
python perplexity_file_editor.py <command>  [options]
```

## 2. Commit and Branch Policy

### Branch Restrictions
- **ONLY** commit to development branch: `work`
- **NEVER** commit to: `main` or other protected branches
- Always verify current branch before committing: `git branch`

### Commit Process
1. Stage changes: `git add <files>`
2. Create descriptive commit message: `git commit -m "fix: [description]"`
3. Verify commit is on correct branch
4. Do NOT push until explicitly instructed

### Commit Message Format
- Use conventional commits: `fix:`, `feat:`, `refactor:`, `test:`, `docs:`
- Be specific about what was changed and why
- Reference issue numbers when applicable

## 3. Test Collection and Validation

### Before Making Changes
1. Identify relevant test files in `/tests` directory
2. Run existing tests to establish baseline: `pytest <test_file>`
3. Document current test status

### After Making Changes
1. Run affected tests: `pytest tests/test_<module>.py`
2. Run full test suite if changes are significant: `pytest`
3. Check test coverage: `pytest --cov=src`
4. Verify no new failures introduced
5. If tests fail, iterate on fixes before committing

### Test Validation Requirements
- All existing tests must pass
- New functionality requires new tests
- Test coverage should not decrease
- Document any skipped tests with justification

## 4. Constraints and Allowed Folders/Files

### Allowed Edit Locations
- `/src/mcp_agent/` - Source code modules
- `/tests/` - Test files
- `/docs/` - Documentation files
- `/examples/` - Example code and scripts
- Root-level config files (when necessary)

### Restricted Locations
- `.github/workflows/` - Workflow files (requires explicit approval)
- `.git/` - Git internals (never modify directly)
- `venv/`, `.venv/`, `__pycache__/` - Generated directories
- Protected branches via direct commits

### File Type Restrictions
- Primarily edit: `.py`, `.md`, `.yaml`, `.yml`, `.json`, `.toml`
- Avoid binary files, compiled code, or system files
- Always create backups before modifying configuration files

### Safety Constraints
- Make incremental changes (one logical change per commit)
- Never delete files without explicit confirmation
- Preserve existing functionality unless explicitly changing it
- Maintain code style and formatting consistency
- Add comments for non-obvious changes

## 5. Error Handling and Recovery

### If Editor Script Fails
1. Read error message carefully
2. Verify file path exists and is accessible
3. Check line numbers are within file bounds
4. Ensure file is not locked or read-only
5. Try alternative command if appropriate

### If Tests Fail After Changes
1. Read test output to identify failure
2. Revert changes if necessary: `git checkout -- <file>`
3. Re-read original file to understand issue
4. Make corrective edits
5. Re-run tests before committing

### If Committed to Wrong Branch
1. Immediately notify user
2. Do NOT push changes
3. Suggest corrective steps:
   - Create new branch from correct base
   - Cherry-pick commits
   - Reset original branch

## 6. Best Practices
- Always read files before editing
- Make small, focused changes
- Test after each logical change
- Write clear commit messages
- Document assumptions and decisions
- Ask for clarification when uncertain
- Verify branch before committing
- Never force-push or alter history