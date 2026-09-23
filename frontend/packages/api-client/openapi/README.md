# OpenAPI schemas

Put one schema per service here as `<service>.json` (for example `auth.json`, `catalog.json`),
exported from the service's OpenAPI endpoint. Then run from `frontend/`:

```
pnpm gen-api
```

Types are written to `src/generated/<service>.ts`. Point the aliases in `src/types.ts` at the
generated schemas so the rest of the app keeps importing the same names.
