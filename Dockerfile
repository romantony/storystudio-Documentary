# docgen: Ubuntu desktop (XFCE over noVNC) + Firefox + Claude Code + the documentary toolkit and API.
# Builds for arm64 (CodeBuild, the c9g instance) and amd64 (local testing). No secrets and no Claude config in the image.
FROM ubuntu:24.04
ARG TARGETARCH
ARG GIT_SHA=dev
# Pinned: an unpinned install pulled 2.1.301 on 2026-10-15, whose postinstall npm skipped (no native binary). Bump deliberately; the smoke test in buildspec.yml gates the push.
ARG CLAUDE_CODE_VERSION=2.1.296
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

# upgrade first: the base image lags behind Ubuntu's security updates
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
      xfce4 xfce4-terminal dbus-x11 tigervnc-standalone-server tigervnc-tools novnc websockify \
      ffmpeg python3 python3-pip python3-pil git curl ca-certificates gnupg supervisor sudo \
      fonts-dejavu-core fonts-noto-color-emoji xdg-utils nano less jq unzip procps \
      libnss3 libdbus-1-3 libatk1.0-0t64 libatk-bridge2.0-0t64 libgbm1 libasound2t64 libxrandr2 libxkbcommon0 \
      libxfixes3 libxcomposite1 libxdamage1 libpango-1.0-0 libcairo2 libcups2t64 \
 && rm -rf /var/lib/apt/lists/*

# Firefox from Mozilla's apt repository (Ubuntu's own package is a snap, which does not run in a container)
RUN install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list \
 && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla \
 && apt-get update && apt-get install -y --no-install-recommends firefox && rm -rf /var/lib/apt/lists/*

# Node 24 and Claude Code
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/* \
 && npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} && npm cache clean --force

# VS Code for maintaining the scripts from the desktop
RUN A=$([ "$TARGETARCH" = "arm64" ] && echo arm64 || echo x64) \
 && curl -fsSL "https://update.code.visualstudio.com/latest/linux-deb-$A/stable" -o /tmp/code.deb \
 && apt-get update && (echo "code code/add-microsoft-repo boolean false" | debconf-set-selections) \
 && apt-get install -y --no-install-recommends /tmp/code.deb && rm -rf /tmp/code.deb /var/lib/apt/lists/*

# --ignore-installed: Debian ships typing_extensions without pip metadata, so pip cannot upgrade it in place
RUN pip3 install --no-cache-dir --break-system-packages --ignore-installed fastapi uvicorn pydantic boto3

# ubuntu:24.04 ships a user with uid 1000; replace it so files on the volumes are owned by docgen
RUN userdel -r ubuntu 2>/dev/null || true; useradd -m -u 1000 -s /bin/bash docgen \
 && mkdir -p /data/runs /data/claude && chown -R docgen:docgen /data

COPY --chown=docgen:docgen docgen/ /app/docgen/
COPY --chown=docgen:docgen api/ /app/api/
COPY --chown=docgen:docgen prompts/ /app/prompts/
COPY --chown=docgen:docgen remotion/ /app/remotion/
COPY deploy/supervisord.conf /etc/docgen/supervisord.conf
COPY deploy/entrypoint.sh /usr/local/bin/docgen-entrypoint
COPY deploy/start-desktop.sh /usr/local/bin/docgen-start-desktop
RUN chmod +x /usr/local/bin/docgen-entrypoint /usr/local/bin/docgen-start-desktop

USER docgen
# Remotion renders the text overlays (docgen overlay). Install its packages and headless browser, and bundle the
# templates now so a render does not have to. The libraries it needs are in the first apt layer.
RUN cd /app/remotion && npm ci --no-audit --no-fund && npx remotion browser ensure \
 && npx remotion bundle src/index.ts --out-dir bundle --log=error && npm cache clean --force
WORKDIR /data/runs
ENV HOME=/home/docgen DISPLAY=:1 BROWSER=firefox PYTHONPATH=/app \
    CLAUDE_CONFIG_DIR=/data/claude DOCGEN_GEOMETRY=1600x900 DOCGEN_RUNS_DIR=/data/runs DOCGEN_APP=/app DOCGEN_IMAGE=docgen:${GIT_SHA}
EXPOSE 6080 8080
ENTRYPOINT ["docgen-entrypoint"]
