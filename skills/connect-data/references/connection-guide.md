# Connection Guide — SQL Dialects & Setup

## CSV Files

**Connection string:** File path to directory containing `.csv` files

**Template:**
```yaml
type: csv
path: data/my_dataset/
delimiter: ","
encoding: utf-8
```

**Notes:**
- Relative paths resolve from the repo root
- All `.csv` files in the directory are loaded as tables
- Table names are derived from filenames (lowercase, underscores)

---

## DuckDB

**Connection string:** Path to `.duckdb` file

**Template:**
```yaml
type: duckdb
path: data/my_dataset.duckdb
```

**SQL Dialect:** DuckDB's SQL is largely compatible with PostgreSQL, with extensions for analytics (PIVOT, window functions, etc.)

**Notes:**
- DuckDB provides in-process SQL execution — very fast for local datasets
- Can read CSV, Parquet, JSON natively
- Supports complex queries and window functions

---

## MotherDuck

**Connection string:** Cloud database via MCP token

**Template:**
```yaml
type: motherduck
database: my_database
schema: my_schema
token_env: MOTHERDUCK_TOKEN
```

**SQL Dialect:** MotherDuck is based on DuckDB, so SQL is the same

**Setup:**
1. Sign up at motherduck.com
2. Get your authentication token
3. Store in environment: `export MOTHERDUCK_TOKEN="your_token"`
4. Verify: `duckdb -c "SELECT 1"`

**Notes:**
- MotherDuck is cloud-hosted DuckDB — fast analytics on cloud data
- Can query external data (S3, GCS, BigQuery, etc.) directly
- Requires stable internet connection

---

## PostgreSQL

**Connection string:** Host, database, user, password

**Template:**
```yaml
type: postgres
host: localhost
port: 5432
database: my_db
schema: public
user: my_user
password_env: PG_PASSWORD
```

**SQL Dialect:** PostgreSQL (ANSI SQL with extensions)

**Setup:**
1. Install PostgreSQL locally or use cloud (RDS, Heroku, etc.)
2. Store password in environment: `export PG_PASSWORD="your_password"`
3. Test: `psql -h localhost -U my_user -d my_db -c "SELECT 1"`

**Notes:**
- PostgreSQL is a mature relational database
- Excellent support for complex queries, CTEs, window functions
- Can handle very large datasets with indexing

---

## Google BigQuery

**Connection string:** Project ID, dataset, credentials file

**Template:**
```yaml
type: bigquery
project_id: my-gcp-project
dataset: my_dataset
credentials_file: ~/.gcp/service-account-key.json
```

**SQL Dialect:** BigQuery SQL (ANSI SQL with analytics extensions)

**Setup:**
1. Create a GCP project and enable BigQuery
2. Create a service account and download JSON key
3. Store key at `~/.gcp/service-account-key.json`
4. Test: `bq query --use_legacy_sql=false "SELECT 1"`

**Notes:**
- BigQuery is Google's data warehouse — handles petabyte-scale data
- Excellent for very large datasets
- Pay per query (not per storage)
- Fast columnar analysis

---

## Snowflake

**Connection string:** Account, warehouse, database, user, password

**Template:**
```yaml
type: snowflake
account: xy12345.us-east-1
warehouse: compute_wh
database: my_db
schema: public
user: my_user
password_env: SNOWFLAKE_PASSWORD
```

**SQL Dialect:** Snowflake SQL (ANSI SQL with extensions)

**Setup:**
1. Create a Snowflake account
2. Create a warehouse and database
3. Create a user and assign role
4. Store password in environment: `export SNOWFLAKE_PASSWORD="your_password"`
5. Test: `snowsql -a xy12345 -u my_user -d my_db -c "SELECT 1"`

**Notes:**
- Snowflake is a cloud data warehouse — scales elastically
- Great for shared analytics (separation of compute and storage)
- Supports semi-structured data (JSON, Parquet)

---

## AWS Athena

**Connection string:** Glue database, S3 staging dir, region, workgroup

**Template:**
```yaml
type: athena
database: my_glue_database
s3_staging_dir: s3://my-bucket/athena-results/
region_name: us-east-1
work_group: primary
auth_type: default
```

**SQL Dialect:** Presto/Trino SQL (Athena v2/v3 engine)

**Setup:**
1. Ensure your Glue catalog database exists with tables
2. Create an S3 bucket/prefix for query staging results
3. Configure authentication:
   - **IAM role/SSO:** No extra config — boto3 picks up credentials automatically
   - **AWS profile:** Set `auth_type: profile` and `profile_name: your-profile`
   - **Access keys:** Set `auth_type: credentials`, `access_key_env: AWS_ACCESS_KEY_ID`, `secret_key_env: AWS_SECRET_ACCESS_KEY`
4. Test: `aws athena start-query-execution --query-string "SELECT 1" --result-configuration OutputLocation=s3://your-bucket/`

**Notes:**
- Athena is serverless — no infrastructure to manage, pay per query
- Column descriptions are pulled automatically from Glue catalog COMMENT metadata
- Athena does not support true TEMP tables — uses CTAS instead
- TABLESAMPLE BERNOULLI is available for sampling

---

## ClickHouse

**Connection string:** Host, port, database, username, password

**Template:**
```yaml
type: clickhouse
host: localhost
port: 8123
database: my_db
username: default
password_env: CLICKHOUSE_PASSWORD
secure: false
```

**SQL Dialect:** ClickHouse SQL (camelCase functions like dateDiff, nullIf, groupArray)

**Setup:**
1. Install ClickHouse locally or use ClickHouse Cloud
2. Store password in environment: `export CLICKHOUSE_PASSWORD="your_password"`
3. Test: `clickhouse-client -h localhost --port 9000 -q "SELECT 1"` (native) or `curl http://localhost:8123/?query=SELECT+1` (HTTP)

**Notes:**
- ClickHouse is a columnar OLAP database — extremely fast for analytical queries
- HTTP interface (port 8123) used by default via clickhouse-connect
- Set `secure: true` for HTTPS connections (ClickHouse Cloud requires this)
- Column descriptions from COMMENT clauses are pulled automatically during profiling
- Uses Memory engine for session-scoped temporary tables

---

## Connection Testing

For each type, use the ConnectionManager helper:

```python
from helpers.connection_manager import ConnectionManager

config = {
    "type": "postgres",
    "host": "localhost",
    "database": "my_db",
    "user": "my_user",
    "password_env": "PG_PASSWORD"
}

cm = ConnectionManager(config)

# Test connection
if cm.test_connection():
    print("✓ Connected!")
    tables = cm.list_tables()
    print(f"Found {len(tables)} tables")
else:
    print("✗ Connection failed")
```

---

## Credential Security

**Best practices:**
1. **Never store passwords in manifest files** — always use environment variables
2. **Use service accounts for cloud services** — not personal credentials
3. **Rotate credentials regularly** — especially for production databases
4. **Use VPN or SSH tunnels for remote databases** — when connecting from outside the network
5. **Restrict database user permissions** — read-only for analysis, never admin

**Environment variable naming convention:**
- `PG_PASSWORD` for PostgreSQL
- `MOTHERDUCK_TOKEN` for MotherDuck
- `BIGQUERY_CREDENTIALS` for BigQuery
- `SNOWFLAKE_PASSWORD` for Snowflake
- `DATABASE_URL` for connection strings (PostgreSQL-style)
