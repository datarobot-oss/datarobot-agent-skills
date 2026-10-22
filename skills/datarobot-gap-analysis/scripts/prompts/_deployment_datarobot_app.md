# Deployment context: DataRobot custom application

This repository deploys as a DataRobot custom application (the Pulumi program
declares `{resource}` in `{file}`). In that runtime every request reaches the
application through DataRobot's application proxy, which has already
authenticated the user. The proxy strips these headers from the inbound request
and sets them itself before forwarding:

- `x-user-id`, `x-user-email` and the other `x-user-*` identity headers
- `x-datarobot-api-key`: a per-user API token scoped to that user
- `x-datarobot-identity-token`, `x-datarobot-entity-id` and other
  `x-datarobot-*` headers

Treat values read from these headers as trusted, platform-supplied identity, not
as client input. Do not report reading them as missing authentication, missing
input validation, an injection source, or authenticating as a human or shared
account: a per-user scoped token from the proxy is the intended identity model
for this deployment. A local-development fallback (for example a `DEV_USER_ID`
environment variable used when the header is absent) is not a finding either.
Still report identity handling that bypasses the proxy on purpose, such as a
route that accepts a user id from the request body or query string.
