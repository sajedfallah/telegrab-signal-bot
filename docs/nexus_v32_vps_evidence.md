# V3.2 Windows VPS test evidence

Evidence supplied directly by the user in this chat on 2026-10-15. Codex did not
execute these commands on the VPS. The transcript identifies the authorized
C:\NEXUS_AGENT_TEST checkout, but does not include git rev-parse HEAD.

```text
PS C:\NEXUS_AGENT_TEST> git status --short
?? data/
PS C:\NEXUS_AGENT_TEST> git pull --ff-only origin feature/nexus-agent-system-v1
From https://github.com/sajedfallah/telegrab-signal-bot
 * branch            feature/nexus-agent-system-v1 -> FETCH_HEAD
Already up to date.
PS C:\NEXUS_AGENT_TEST> python -m pytest tests/test_agent_setup_tracker_v31.py tests/test_agent_setup_lifecycle_v32.py -q
...... [100%]
6 passed in 2.29s
```

Gate: PASS for the six baseline V3.1/V3.2 assertions in the reported VPS checkout.
This is not evidence that local recovery commit dd3dce9 or subsequent V3.3 work
was transferred or tested there. No V3.3 integration approval follows from this
result. Preserve the untracked data/ directory; do not clean, delete, stash or
overwrite it as part of verification. Include git rev-parse HEAD with the next
VPS test output to establish exact commit provenance.
