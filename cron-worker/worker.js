/**
 * Reliable external trigger for the venue-monitor GitHub Actions workflows.
 *
 * Why this exists: GitHub's own `schedule:` trigger is documented as
 * best-effort and gets delayed or dropped under load -- not suitable for
 * "within minutes" freshness. This Worker calls GitHub's REST API to fire
 * `workflow_dispatch` instead, which goes through GitHub's normal event
 * queue rather than the deprioritized schedule queue.
 *
 * Two Cron Triggers (configured in wrangler.toml) hit this same Worker;
 * event.cron tells us which one fired so we know which GitHub workflow
 * to dispatch:
 *   "* * * * *"     (every minute)   -> dune_check.yml
 *   "*5 * * * *"   (every 5 min)    -> check.yml (venue listings)
 *
 * Requires one secret: GITHUB_TOKEN, a fine-grained GitHub Personal Access
 * Token scoped ONLY to this repo, with "Actions: Read and write" permission
 * and nothing else. Set it with:
 *   wrangler secret put GITHUB_TOKEN
**/

const OWNER = "kxtof";
const REPO = "forum-karlin-tracking";
const REF = "main";

const CRON_TO_WORKFLOW = {
  "1 * * * *": "dune_check.yml",
  "0 * * * *": "check.yml",
};

async function dispatchWorkflow(workflowFile, token) {
  const url = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${workflowFile}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": "venue-monitor-cron-worker",
    },
    body: JSON.stringify({ ref: REF }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Dispatch of ${workflowFile} failed: ${res.status} ${body}`);
  }
}

export default {
  async scheduled(event, env, ctx) {
    const workflowFile = CRON_TO_WORKFLOW[event.cron];
    if (!workflowFile) {
      console.error(`Unrecognized cron pattern: ${event.cron}`);
      return;
    }
    try {
      await dispatchWorkflow(workflowFile, env.GITHUB_TOKEN);
      console.log(`Dispatched ${workflowFile}`);
    } catch (err) {
      // No automatic retries on Cron Triggers -- but since this fires every
      // minute (or every 5), a single missed tick is caught by the next one
      // seconds/minutes later, which is exactly the property we wanted.
      console.error(err.message);
    }
  },

  // Optional: lets you trigger a dispatch manually by visiting the Worker's
  // URL with ?workflow=dune_check.yml, handy for testing without waiting
  // for the next cron tick.
  async fetch(request, env) {
    const url = new URL(request.url);
    const workflowFile = url.searchParams.get("workflow");
    if (!workflowFile) {
      return new Response("Pass ?workflow=dune_check.yml or ?workflow=check.yml to test manually.", { status: 400 });
    }
    try {
      await dispatchWorkflow(workflowFile, env.GITHUB_TOKEN);
      return new Response(`Dispatched ${workflowFile}`);
    } catch (err) {
      return new Response(err.message, { status: 500 });
    }
  },
};
