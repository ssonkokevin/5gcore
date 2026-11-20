# Location schema (core side)

Ordered, idempotent SQL for the location functions that live in this
repository: the MME LCS function, the E-SMLC and the LMF. The GMLC's own
database lives in its repository and is not created here.

Applied by the `db` container's init directory on first start
(`/docker-entrypoint-initdb.d/`) or manually, in filename order:

```bash
mysql -h <host> -u <user> -p <database> < database/location/001_location_schema.sql
```

Each script records itself in `tbl_lcs_schema_version`. `IF NOT EXISTS` makes a
re-run harmless; it does not migrate an older shape, so a changed table needs a
new numbered script, never an edit to one already applied.

## Rules

- Every table carries `tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1` and starts
  its primary key with it (decision D11).
- No table stores a position without `method`, `uncertainty_m`, `confidence`
  and `age_seconds` (decision D10).
- `tbl_lcs_result` is append-only. Never update or delete a result row; a
  correction is a new result with its own reference.
- No credentials, keys or subscriber secrets in these tables.

## Canonical cell identity

One string form, used as the key in `tbl_lcs_cell` and in every API:

| RAT | Form | Example |
|---|---|---|
| GSM | `mcc-mnc-lac-ci` | `001-01-4660-1234` |
| UMTS | `mcc-mnc-lac-sac` | `001-01-4660-1234` |
| LTE | `mcc-mnc-eci` | `001-01-123456789` |
| NR | `mcc-mnc-nci` | `001-01-1234567890` |

Components are decimal, no zero padding beyond what the operator's own
numbering uses. `mnc` keeps its given width (2 or 3 digits). ECI is 28 bits
(eNB 20, cell 8); NCI is 36 bits. Parsing and formatting are unit-tested and
marked provisional until TS 23.003 is verified (decision D15).

## Data quality score

`data_quality` is 0-100, set at import:

| Score | Meaning |
|---|---|
| 90-100 | Surveyed coordinates and azimuth, verified within 12 months |
| 70-89 | Operator-supplied plan values, verified within 24 months |
| 40-69 | Estimated from site address or a previous cell-ID calibration |
| 1-39 | Placeholder; usable only to say "somewhere in this area" |
| 0 / NULL | Unknown; the cell must not be used for a published result |

The GMLC surfaces this score on every cell-ID answer and refuses to publish a
result from a cell scored below the tenant's minimum.
