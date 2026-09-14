# API-driven Component States

Every visual component must retain four states during backend integration:

- Loading: skeleton/chart placeholder with stable layout dimensions.
- Empty: meaningful no-data message and relevant action.
- Error: human-readable failure with retry/diagnostic path.
- Ready: full approved component with tenant-scoped data.

Charts must not disappear when data is empty or loading; the card/layout remains. Tables must preserve headers and context. Health cards must distinguish Healthy / Warning / Critical / Unknown. No production component may silently fall back to demo fixture values.