# Agentarium SDK

```powershell
pip install -e packages/agentarium-sdk
agentarium validate packages/agentarium-sdk/examples/research-skill/agentarium.json
agentarium test packages/agentarium-sdk/examples/research-skill/agentarium.json
agentarium publish agentarium.json --workspace-id <uuid> --token <agt_token>
```

Create a scoped API token from the workspace token endpoint. Safe declarative packages are reviewed automatically; dangerous tools or bundled code remain pending for manual review.
