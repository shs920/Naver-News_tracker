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
- STALE_MINUTES: optional, default 15
*/

function minutesSince(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  return Math.floor((Date.now() - new Date(value).getTime()) / 60000);
}

async function readLatestRuns(env) {
  const url = new URL(`${env.SUPABASE_URL}/rest/v1/crawler_runs`);
  url.searchParams.set("select", "mode,status,started_at,finished_at");
  url.searchParams.set("status", "eq.success");
  url.searchParams.set("order", "started_at.desc");
  url.searchParams.set("limit", "30");

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

async function dispatchWorkflow(env) {
  const owner = env.GITHUB_OWNER || "shs920";
  const repo = env.GITHUB_REPO || "Naver-News_tracker";
  const workflow = env.GITHUB_WORKFLOW || "crawl.yml";
  const ref = env.GITHUB_REF || "main";

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "naver-news-tracker-watchdog",
      },
      body: JSON.stringify({ ref }),
    },
  );

  if (!response.ok) {
    throw new Error(`GitHub dispatch status ${response.status}: ${await response.text()}`);
  }
}

async function checkAndDispatch(env) {
  const staleMinutes = Number(env.STALE_MINUTES || 15);
  const rows = await readLatestRuns(env);
  const latest = {
    discover: rows.find(row => row.mode === "discover"),
    recheck: rows.find(row => row.mode === "recheck"),
  };

  const discoverAge = minutesSince(latest.discover?.finished_at || latest.discover?.started_at);
  const recheckAge = minutesSince(latest.recheck?.finished_at || latest.recheck?.started_at);
  const stale = discoverAge > staleMinutes || recheckAge > staleMinutes;

  if (stale) {
    await dispatchWorkflow(env);
  }

  return {
    stale,
    discoverAge,
    recheckAge,
    staleMinutes,
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
