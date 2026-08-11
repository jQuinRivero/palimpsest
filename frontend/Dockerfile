# syntax=docker/dockerfile:1

FROM node:24.18.0-bookworm-slim AS deps
WORKDIR /app

# npm is pinned, not merely inherited. package-lock.json installs cleanly under
# npm 11.6.x but is rejected as out of sync by npm >= 11.8 ("Missing:
# @emnapi/core@ from lock file"), which are optional wasm32-wasi peers that no
# supported platform installs. CI passes today only because actions/setup-node
# happens to supply 11.6.2; the base image ships a newer npm and fails.
# Pinning makes this image match what CI actually validates instead of
# depending on which npm a base image was rebuilt with.
# See frontend/SECURITY-NOTES.md.
RUN npm install -g npm@11.6.2

# npm ci, never npm install: the lockfile is generated on Linux and carries the
# optional packages this build needs. See CONTRIBUTING.md.
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.18.0-bookworm-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# The reading interface calls the API from the browser, not from this
# container, so this is the address a reader's browser must reach. Next inlines
# NEXT_PUBLIC_* at build time, which is why it is a build argument: changing it
# means rebuilding, not restarting.
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24.18.0-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone output ships only the modules actually traced as reachable, so the
# runtime image carries no build toolchain and no dev dependencies.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

USER node
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["node", "server.js"]
