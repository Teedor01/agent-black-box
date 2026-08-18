# Agent Black Box — Infrastructure Setup Plan

---

## 1. CockroachDB Cloud — account + free-tier cluster

1. Sign up at https://cockroachlabs.cloud/signup 
2. Create a **Serverless** cluster on the free tier. Note the region you
   pick... keep it close to whichever AWS region you'll deploy Lambda in
   (matters for latency, not correctness, since MCP calls go over HTTPS
   regardless).
3. From the Cloud Console, create a **SQL user** for the application
   backend (read/write).
4. Download the connection string (`postgresql://...`). This goes into AWS
   Secrets Manager in Step 4 below — never into a committed file.

### ccloud CLI (used once, per the architecture doc — provisioning only)

```
:: install (see https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started for current install command)
ccloud auth login
ccloud cluster list
```

Use this to confirm the cluster is up and to script cluster details if you
want them in a setup script later — it is not part of the running system,
so don't over-invest here.

---

## 2. Apply the schema

From `cmd.exe`, using the CockroachDB SQL client (`cockroach sql` binary,
or any `psql`-compatible client since CockroachDB speaks the Postgres wire
protocol):

```
cockroach sql --url "<your-connection-string>" --file src\db\schema.sql
```

Verify:

```
cockroach sql --url "<your-connection-string>" --execute "SHOW TABLES;"
```

You should see all six tables: `sources`, `episodes`, `episode_sources`,
`claims`, `lessons`, `contradictions`.

**Do this before picking the embedding dimension casually.** `claims.embedding`
and `lessons.embedding` are declared `VECTOR(1024)` in `schema.sql` — confirm
that number matches the actual Bedrock embedding model you select in Step 3
before applying the schema. Changing it after rows exist means a migration.

---

## 3. Amazon Bedrock — model access

1. In the AWS Console, go to **Bedrock → Model access** in region
   **us-east-1** and request access to:
   - An embeddings model (e.g. Titan Text Embeddings V2 — confirm current
     output dimensions, configurable to 256/512/1024; match this to the
     schema's `VECTOR(1024)` or change the schema to match).
   - **Claude Sonnet 5** for planning / claim extraction / lesson
     generation. 
2. Access approval can take a few minutes to a few hours on some accounts
3. Note the exact embedding model ID (e.g. `amazon.titan-embed-text-v2:0`)
   — you'll need it verbatim in Lambda environment variables once agent
   code starts 

---

## 4. AWS Secrets Manager — credentials

Store, as separate secrets:

- CockroachDB connection string (app backend, read/write role from Step 1.3)
- CockroachDB MCP bearer token (read-only, from Step 5 below)


---

## 5. CockroachDB Managed MCP Server 

| | OAuth | API key (service account) |
|---|---|---|
| Used for | Your own Claude Code / Cursor, dev-time | The Lambda's runtime credential |
| How it authenticates | Interactive browser login | A static bearer token |
| Works from Lambda? | **No** — needs a browser | **Yes** |

### 5a. Dev-time (your own Claude Code) — OAuth

This is what the Cloud Console's **Integrations → Claude Code** page
walks you through (the `claude mcp add cockroachdb-cloud ... --transport
http` command). Optionally add `--header "mcp-cluster-id: <your-cluster-id>"`
to scope it to just this cluster (find the ID in the cluster's Overview
page URL) rather than every cluster in your org. Run `claude /mcp` after
adding it and authorize through the browser flow. This connection is for
you to poke at the schema interactively — it is **not** what the Lambda
uses.

### 5b. Runtime (the Lambda's credential) — Service Account + API key

1. In the Cloud Console: **Access** (or **Organization → Service
   Accounts**) → create a new service account.
2. Assign it the **Cluster Operator** role (or Cluster Admin, if
   Operator isn't sufficient — Operator is the narrower of the two and
   should cover the read tools this project uses) scoped to this cluster.
3. Generate an API key for the service account. **Copy the secret key
   now** — it's typically shown once.
4. This API key is the value that goes in `COCKROACHDB_MCP_BEARER_TOKEN`
   (used as `Authorization: Bearer <key>`), stored in Secrets Manager
   (Step 4), never in this doc or in chat.
5. Optionally add the same `mcp-cluster-id` scoping as above so this
   credential can only ever touch this one cluster.



### 5c. Verify before trusting either connection

```
python scripts\verify_mcp_connection.py
```

This now prints every tool's full `inputSchema`, which is what settles
the one remaining unconfirmed detail: `src/mcp/client.py` assumes the
`select_query` tool's argument key is `"sql"` — check the printed schema
and fix `execute_sql()` in that file if it's actually called something
else (`"query"`, `"statement"`, etc.).

---

## 6. AWS Lambda — execution role 


1. Create an IAM role for the future Lambda function with:
   - `bedrock:InvokeModel` scoped to the specific model IDs from Step 3
     (not `bedrock:*`)
   - `secretsmanager:GetSecretValue` scoped to the two secrets from Step 4
   - Standard Lambda execution permissions (CloudWatch Logs write)
---
