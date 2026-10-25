# HeatShift plain-English supervisor messages

## Heat spike / plan change
**Heat conditions changed.** Roofing now conflicts with the encoded heavy-work recovery requirement. I moved the heavy outdoor work to a lower-disruption slot, inserted the required recovery event, and validated the revised schedule. No hard safety rule was relaxed. **Approve this plan?**

## No change needed
**Current plan remains compliant.** Heat conditions changed, but no active task violates an encoded constraint. I will keep monitoring.

## Missing data
**Live heat data is unavailable.** I will not invent a reading. The dashboard should use the last confirmed value only if it is visibly marked cached; otherwise the supervisor must choose a fallback scenario or wait for the live signal.

## No feasible plan
**I could not find a safe, valid schedule.** I did not relax any hard safety requirement. Supervisor action is required: adjust the deadline, add qualified manpower, change the task scope, or defer the affected work.

## Worker unavailable
**A worker became unavailable.** I checked skill coverage, task dependencies and heat constraints before proposing a reassignment. The plan remains pending until you approve it.
