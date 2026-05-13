"""Shared modules for the deliberation orchestrator.

This package replaces the prior shell-with-Python-heredoc implementation.
Shell was fragile for a cluster of related reasons (audit items #6-#11, #13, #15):
  - Heredoc interpolation of LLM output is a quoting minefield
  - Multiple scripts re-implemented TOML reading independently (DRY)
  - Shell injection on user-supplied arguments
  - Config knobs were decorative (hardcoded values overrode them)

Modules:
  config       - SSOT reader for harness.toml [deliberation] block
  state        - epoch.json and bid log management
  sketchboard  - section-boundary parsing, block append, additivity check
  postcheck    - WRITE-mode diff validation (file allowlist + position + heading)
  detect       - contested-section heuristic (v0.1 keyword)
"""
