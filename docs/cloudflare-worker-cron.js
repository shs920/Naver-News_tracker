/*
Cloudflare Workers Cron watchdog for GitHub Actions.

Required Worker variables/secrets:
- GITHUB_TOKEN: fine-grained GitHub token with Actions write access to this repo
- GITHUB_OWNER: shs920
- GITHUB_REPO: Naver-News_tracker
- GITHUB_WORKFLOW: crawl.yml
- GITHUB_REF: main
- SUPABASE_URL: https://your-project.supabase.co
- SUPABASE_SERVICE_ROLE_KEY: Supabase service_role key
- STALE_MINUTES: optional, default 7
- RUNNING_GRACE_MINUTES: optional, default 20
- DISPATCH_COOLDOWN_MINUTES: optional, default 5
*/

function minutesSince(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  return Math.floor((Date.now() - new Date(value).getTime()) / 60000);
}

async function readLatestRuns(env) {
  const url = new URL(`${env.SUPABASE_URL}/rest/v1/crawler_runs`);
  url.searchParams.set("select", "mode,status,started_at,finished_at,github_run_id,error_message");
  url.searchParams.set("order", "started_at.desc");
  url.searchParams.set("limit", "80");

  const response = await fetch(url, {
    headers: {
      apikey: env.SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Supabase status ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

function githubHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "naver-news-tracker-watchdog",
  };
}

async function readGithubWorkflowRuns(env) {
  const owner = env.GITHUB_OWNER || "shs920";
  const repo = env.GITHUB_REPO || "Naver-News_tracker";
  const workflow = env.GITHUB_WORKFLOW || "crawl.yml";
  const ref = env.GITHUB_REF || "main";

  const url = new URL(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/runs`,
  );
  url.searchParams.set("branch", ref);
  url.searchParams.set("per_page", "20");

  const response = await fetch(url, { headers: githubHeaders(env) });
  if (!response.ok) {
    throw new Error(`GitHub runs status ${response.status}: ${await response.text()}`);
  }
  const data = await response.json();
  return data.workflow_runs || [];
}

function hasActiveGithubRun(runs, graceMinutes) {
  return runs.some((run) => {
    const status = run.status || "";
    const age = minutesSince(run.created_at);
    return (
      age <= graceMinutes
      && ["queued", "in_progress", "waiting", "requested", "pending"].includes(status)
    );
  });
}

function hasRecentGithubRun(runs, cooldownMinutes) {
  return runs.some((run) => minutesSince(run.created_at) <= cooldownMinutes);
}

async function dispatchWorkflow(env) {
  const owner = env.GITHUB_OWNER || "shs920";
  const repo = env.GITHUB_REPO || "Naver-News_tracker";
  const workflow = env.GITHUB_WORKFLOW || "crawl.yml";
  const ref = env.GITHUB_REF || "main";

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: githubHeaders(env),
      body: JSON.stringify({ ref }),
    },
  );

  if (!response.ok) {
    throw new Error(`GitHub dispatch status ${response.status}: ${await response.text()}`);
  }
}

async function checkAndDispatch(env) {
  const staleMinutes = Number(env.STALE_MINUTES || 7);
  const runningGraceMinutes = Number(env.RUNNING_GRACE_MINUTES || 20);
  const dispatchCooldownMinutes = Number(env.DISPATCH_COOLDOWN_MINUTES || 5);

  const rows = await readLatestRuns(env);
  const githubRuns = await readGithubWorkflowRuns(env);

  const latest = {
    discover: rows.find(row => row.mode === "discover" && row.status === "success"),
    recheck: rows.find(row => row.mode === "recheck" && row.status === "success"),
  };
  const recentRunningCrawler = rows.some(
    row => row.status === "running" && minutesSince(row.started_at) <= runningGraceMinutes,
  );
  const activeGithubRun = hasActiveGithubRun(githubRuns, runningGraceMinutes);
  const recentGithubRun = hasRecentGithubRun(githubRuns, dispatchCooldownMinutes);

  const discoverAge = minutesSince(latest.discover?.finished_at || latest.discover?.started_at);
  const recheckAge = minutesSince(latest.recheck?.finished_at || latest.recheck?.started_at);
  const stale = discoverAge > staleMinutes || recheckAge > staleMinutes;
  const suppressed = activeGithubRun || recentRunningCrawler || recentGithubRun;

  if (stale && !suppressed) {
    await dispatchWorkflow(env);
  }

  return {
    stale,
    dispatched: stale && !suppressed,
    suppressed,
    activeGithubRun,
    recentGithubRun,
    recentRunningCrawler,
    discoverAge,
    recheckAge,
    staleMinutes,
    runningGraceMinutes,
    dispatchCooldownMinutes,
  };
}

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(checkAndDispatch(env));
  },

  async fetch(_request, env) {
    const result = await checkAndDispatch(env);
    return Response.json(result);
  },
};
