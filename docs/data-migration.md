# Taxonomy migration and data handling

The category hierarchy migrations (`080` and `081`) are automated database
population and normalization steps, equivalent to a repeatable seed. They
contain only canonical category labels, visual metadata, and explicit mapping
rules. They do not contain production account numbers, transaction amounts,
payee records, user identities, credentials, database dumps, or exported ERP
rows.

At runtime, migrations operate only on categories and transaction references
already present in the target workspace database. UUIDs, audit records, and
timestamps are generated at runtime. Production backups and environment files
must remain outside version control.
