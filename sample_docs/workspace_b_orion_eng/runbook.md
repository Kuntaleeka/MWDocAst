# Orion Engineering Runbook

## Deploys
Deploys happen on Tuesdays and Thursdays after the change review at 11:00.
The deploy freeze starts on 1 December and ends on 5 January.
Rollbacks are done with `orion rollback <release-id>` and must be announced in #orion-deploys.

## Incidents
Page the on-call engineer via the #orion-incidents channel.
SEV1 incidents need a postmortem within 5 business days; SEV2 within 10.
The incident commander for SEV1 is always the on-call engineering manager.

## Access
Production access requires a hardware security key and is reviewed every 90 days.
Break-glass credentials are stored in the vault under `orion/prod/breakglass`.
