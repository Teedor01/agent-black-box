# Day 6 — Lambda Deployment

Assumes Day 1's IAM role and Secrets Manager entries already exist (see
`infra/SETUP.md`). This is deployment only — the handler code itself is
`src/agent/lambda_handler.py`.

## 1. Build the deployment package

```
python scripts\package_lambda.py
```

Produces `build\lambda_deploy.zip`. Re-run this after any code or
dependency change — it's not watched/incremental.

**Why this can't be a plain `pip install`:** you're building on Windows;
Lambda runs Amazon Linux. `psycopg[binary]` and `lxml` (a trafilatura
dependency) ship compiled C extensions, so a normal Windows pip install
grabs Windows binaries that will fail to import on Lambda with a
misleading error. The script forces `--platform manylinux2014_x86_64
--only-binary=:all:` instead — confirmed working without Docker, since
every dependency here already publishes prebuilt Linux wheels.

## 2. Create the function

In the AWS Console (Lambda → Create function → Author from scratch), or
via CLI:

```
aws lambda create-function ^
  --function-name agent-black-box ^
  --runtime python3.12 ^
  --role arn:aws:iam::<account-id>:role/<the-role-from-infra-SETUP.md> ^
  --handler src.agent.lambda_handler.handler ^
  --zip-file fileb://build/lambda_deploy.zip ^
  --timeout 120 ^
  --memory-size 1024 ^
  --region us-east-1
```

**Timeout:** 120s to start. One episode makes several sequential Bedrock
calls (plan, extract per source, contradiction judgment per candidate,
synthesize) plus source fetches — pad generously rather than tune this
tight before you've measured a real run.

**Memory:** 1024MB — `lxml`/`trafilatura` parsing and the dependency
footprint want headroom; Lambda also scales CPU with memory, which helps
here since nothing in this workload is memory-bound, it's mostly waiting
on network/Bedrock.

## 3. Environment variables

Set on the function (Console → Configuration → Environment variables, or
`aws lambda update-function-configuration --environment`):

| Key | Value |
|---|---|
| `AWS_REGION` | `us-east-1` |
| `SECRET_ARN_COCKROACHDB` | ARN of the CockroachDB connection string secret (Day 1) |
| `SECRET_ARN_MCP_TOKEN` | ARN of the MCP bearer token secret (Day 1) |
| `BEDROCK_EMBEDDING_MODEL_ID` | `amazon.titan-embed-text-v2:0` (or whichever you confirmed in Day 1) |
| `BEDROCK_TEXT_MODEL_ID` | `anthropic.claude-sonnet-5` |

Note what's **not** here: no `COCKROACHDB_CONNECTION_STRING` env var, no
raw secret values. The handler fetches both secrets by ARN at cold start
via `secretsmanager:GetSecretValue` — the plaintext credential never sits
in Lambda's environment variable configuration, only in Secrets Manager
and briefly in memory during execution.

## 4. Test invoke

```
aws lambda invoke ^
  --function-name agent-black-box ^
  --cli-binary-format raw-in-base64-out ^
  --payload "{\"project\": \"crynux\", \"query\": \"What is Crynux's current node architecture?\"}" ^
  response.json

type response.json
```

Expect a 200 with `episode_id`, `final_answer`, `claims_count`,
`lessons_count` in the body. A 500 with a clear error message means a
config/permission issue (check the two secret ARNs and the IAM role's
`bedrock:InvokeModel` scope first) — the handler wraps `run_episode()` in
a try/except specifically so failures come back as a readable payload
instead of a bare Lambda stack trace.

## 5. Redeploying after a code change

```
python scripts\package_lambda.py
aws lambda update-function-code --function-name agent-black-box --zip-file fileb://build/lambda_deploy.zip
```

## MCP retrieve-path (closed as of this pass, verify before demo)

`src/agent/memory.py`'s retrieve stage now reads CockroachDB through the
Managed MCP Server's read-only credential (`src/mcp/client.py`), not
psycopg — the app backend's read/write psycopg credential is used only
by `src/db/repository.py`'s writes at persist time. Before relying on
this in the actual demo, run `python scripts\verify_mcp_connection.py`
once with your real bearer token: the exact SQL-tool name and result
shape were built to spec from CockroachDB's documented conventions, not
confirmed against a live call, since this environment has no access to
your endpoint/token.

## Day 7 — Web UI

### Expose the Lambda to the browser: Function URL

Simpler than a full API Gateway setup for this scope — one HTTPS
endpoint, no routing config needed since the frontend dispatches by an
`"action"` field in the request body, not by path.

```
aws lambda create-function-url-config ^
  --function-name agent-black-box ^
  --auth-type NONE ^
  --cors "AllowOrigins=*,AllowMethods=POST,AllowHeaders=Content-Type"
```

`--auth-type NONE` means anyone with the URL can call it — acceptable for
a hackathon demo, not for anything beyond it. If you want a minimal gate
before submission, switch to `AWS_IAM` and have the frontend sign
requests, or put a shared-secret header check inside `lambda_handler.py`
and validate it before dispatching — either is a small addition, not
architecture work.

Get the URL after creation:

```
aws lambda get-function-url-config --function-name agent-black-box
```

### Run the frontend locally (fastest path for the demo video)

```
cd web
npm install
copy .env.local.example .env.local
:: edit .env.local, paste the real Function URL from above
npm run dev
```

Open `http://localhost:3000`. The Ask view calls `run_episode`; the
Memory Trace view calls `memory_trace` — both hit the same Function URL,
same Lambda, same `run_episode()` loop from Days 3-6.

### Deploying the frontend publicly (optional, for a shareable demo link)

Not required for the hackathon's local demo video, but if you want a
public URL to include in the Devpost submission: push `web/` to a repo
Vercel can see, import it there (framework auto-detected as Next.js), and
set `NEXT_PUBLIC_API_URL` in Vercel's project environment variables to
the same Function URL. No AWS-side change needed either way — the
backend doesn't know or care where the frontend is hosted.
