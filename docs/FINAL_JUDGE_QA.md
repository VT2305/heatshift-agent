# Judge Q&A

**Why AI? Why not just rules?**
Rules determine what is allowed. The optimiser determines feasibility. The agent determines when replanning is needed, coordinates tools, compares valid outcomes, explains trade-offs and manages interaction over changing state.

**Why not let the LLM schedule directly?**
Worker scheduling contains simultaneous hard constraints. OR-Tools is the scheduling authority; the LLM is the orchestration authority.

**Can the model hallucinate a safety threshold?**
It can say something wrong in natural language, but it has no authority to alter the deterministic rules or validator. The operational decision uses tool outputs.

**What if the weather API fails?**
Live, cached and simulated states are explicitly differentiated. The judged demo does not depend on internet availability.

**What if there is no safe schedule?**
HeatShift returns NO_FEASIBLE_PLAN and refuses to relax hard constraints.

**Can it publish changes autonomously?**
No. The model is not given an approve-plan tool. A human supervisor must approve.

**Is the exposure reduction a medical-risk claim?**
No. It is explicitly a non-medical operational exposure proxy used to compare schedules.

**Is this really agentic?**
A changing environment causes the supervisor to perceive state, select/call tools, plan, validate, explain, request an action, and then re-enter the loop after a new event.
