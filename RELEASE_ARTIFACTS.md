# NEXUS Release Artifacts

## Current local checkpoint

```text
File: NEXUS_v0.9.39.1_READABILITY_FINAL.zip
SHA-256: 319d47d138a1ca07fa9c1f83e97c777d237fa7460edec2fea0ec0ff7719004b7
Version: v0.9.39.1
```

The checksum above was verified against the local release package used for the v0.9.39.1 checkpoint.

## Important: this repository is public

The exact local ZIP is **not safe to blindly commit as a public repository blob** without a release-sanitization pass. The current workstation package can contain operator-specific configuration and runtime/generated files (for example local `config.json` values and `uploads/` evidence) that should not automatically become public.

Before publishing a binary ZIP here or as a public GitHub Release asset, create a sanitized distribution package that excludes or redacts:

- `.env` and any secret files.
- Telegram/API tokens.
- Operator-specific channel IDs when they should remain private.
- Production/local SQLite DB, WAL and SHM files.
- Logs, PID and lock files.
- Device fingerprints.
- Personal client data.
- Runtime screenshots/uploads that are not intentionally public.
- Machine-specific paths when they should not ship as defaults.

## Public release package policy

The recommended public artifact name is:

```text
NEXUS_v0.9.39.1_PUBLIC_SOURCE_RELEASE.zip
```

It should be generated only after:

1. Secret scan passes.
2. Runtime/private data is removed.
3. `config.json` is reset to safe defaults or replaced by examples.
4. Tests/validation documents are included.
5. SHA-256 is generated and recorded here.

## Private operator archive

The exact workstation checkpoint may be retained privately as:

```text
NEXUS_v0.9.39.1_READABILITY_FINAL.zip
```

Do not assume that a private operator archive and a safe public release archive are identical products.

## Related documents

- `VERSION.txt`
- `PROJECT_STATUS.md`
- `RELEASE_NOTES_v0.9.39.1.txt`
- `FINAL_VALIDATION_v0.9.39.1.txt`
- `docs/NEXT_VALIDATION_WORKFLOW_FA.md`
